"""Synthetic HTTP responses; no bank requests or credentials."""

import traceback
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from test_export_classifier import _xls

from app.fetchers import barclays
from app.fetchers.base import FetchError
from app.services.export_classifier import ExportKind

ROOT = "https://www.investments.barclays.co.uk/en-gb/SubAccount/test-account"
SUFFIX = "/Portfolio/InvestmentsOverview/GetInvestmentsFile"


def fake_page(data=b"", status=200):
    response = SimpleNamespace(status=status, body=AsyncMock(return_value=data))
    return SimpleNamespace(
        url=ROOT + "/Portfolio", request=SimpleNamespace(get=AsyncMock(return_value=response))
    )


def collection_page():
    holdings = _xls([["Investment", "Identifier", "Quantity Held", "Value"], ["Cash", "", 0, 1]])
    orders = _xls([["Investment", "Date", "Order Status", "Account", "Buy/Sell", "Quantity"]])
    page = fake_page()
    page.request.get.side_effect = [
        SimpleNamespace(status=200, body=AsyncMock(return_value=data))
        for data in (holdings, orders)
    ]
    investments = SimpleNamespace(get_attribute=AsyncMock(return_value=ROOT + SUFFIX))
    history_export = SimpleNamespace(
        get_attribute=AsyncMock(
            side_effect=lambda *a, **k: (
                page.url.removesuffix("/Orders") + "/Orders/History/GetDocumentFile"
            )
        )
    )

    async def open_orders(**kwargs):
        page.url = ROOT + "/Orders"

    orders_link = SimpleNamespace(
        get_attribute=AsyncMock(return_value=ROOT + "/Orders"),
        click=AsyncMock(side_effect=open_orders),
    )
    history_tab = SimpleNamespace(click=AsyncMock())
    links = SimpleNamespace(
        filter=Mock(
            side_effect=lambda *, has_text: (
                investments if has_text == "Download investments" else history_export
            )
        )
    )
    page.locator = Mock(
        side_effect=lambda selector: history_tab if selector == "#history-tab" else links
    )
    page.get_by_role = Mock(
        side_effect=lambda role, *, name, **kw: (
            orders_link if name == "Orders" else SimpleNamespace(count=AsyncMock(return_value=1))
        )
    )
    page.wait_for_load_state = AsyncMock()
    return page, history_tab, (holdings, orders)


@pytest.mark.asyncio
async def test_collect_real_helpers_reject_account_switch_after_history_click():
    page, history_tab, _ = collection_page()

    async def switch_account(**kwargs):
        page.url = ROOT.replace("test-account", "other-account") + "/Orders"

    history_tab.click.side_effect = switch_account
    with pytest.raises(FetchError, match="account"):
        await barclays.collect_exports(page)
    assert page.request.get.await_count == 1


@pytest.mark.asyncio
async def test_collect_pins_account_before_authentication_check_await():
    page, _, _ = collection_page()
    investments = page.locator("a").filter(has_text="Download investments")
    other_root = ROOT.replace("test-account", "other-account")

    async def switch_account():
        page.url = other_root + "/Portfolio"
        investments.get_attribute.return_value = other_root + SUFFIX
        return 1

    logout = SimpleNamespace(count=AsyncMock(side_effect=switch_account))
    original_roles = page.get_by_role.side_effect
    page.get_by_role.side_effect = lambda role, *, name, **kw: (
        original_roles(role, name=name, **kw) if name == "Orders" else logout
    )
    with pytest.raises(FetchError):
        await barclays.collect_exports(page)
    page.request.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_collect_real_helpers_return_validated_pair():
    page, _, expected = collection_page()
    assert await barclays.collect_exports(page) == expected
    assert page.request.get.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("export_index", [0, 1])
@pytest.mark.parametrize("switch_during", ["request", "body"])
async def test_collect_rejects_account_switch_during_export(export_index, switch_during):
    page, _, data = collection_page()
    responses = [SimpleNamespace(status=200, body=AsyncMock(return_value=value)) for value in data]

    def switch_account():
        page.url = page.url.replace("test-account", "other-account")

    async def get_response(*args, **kwargs):
        index = page.request.get.await_count - 1
        if index == export_index and switch_during == "request":
            switch_account()
        return responses[index]

    async def read_body():
        if switch_during == "body":
            switch_account()
        return data[export_index]

    page.request.get.side_effect = get_response
    responses[export_index].body.side_effect = read_body
    with pytest.raises(FetchError, match="account"):
        await barclays.collect_exports(page)
    assert page.request.get.await_count == export_index + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["read_export", "collect_exports"])
@pytest.mark.parametrize("failure_at", ["request", "body"])
async def test_export_boundaries_sanitize_network_failures(boundary, failure_at):
    sentinel = "PRIVATE_SENTINEL https://user:credential@provider.example/export?token=secret"
    page, _, _ = collection_page()
    if failure_at == "request":
        page.request.get.side_effect = TimeoutError(sentinel)
    else:
        page.request.get.side_effect = None
        page.request.get.return_value = SimpleNamespace(
            status=200, body=AsyncMock(side_effect=RuntimeError(sentinel))
        )
    with pytest.raises(FetchError) as error:
        if boundary == "read_export":
            await barclays.read_export(page, ROOT + SUFFIX, SUFFIX, ExportKind.BARCLAYS_HOLDINGS)
        else:
            await barclays.collect_exports(page)
    assert "PRIVATE_SENTINEL" not in str(error.value)
    assert "provider.example" not in "".join(traceback.format_exception(error.value))
    assert error.value.__suppress_context__
    assert error.value.__cause__ is None
    assert page.request.get.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", ["authentication", "locator", "navigation", "history"])
async def test_collect_boundary_sanitizes_browser_failures(failure_at):
    sentinel = "PRIVATE_SENTINEL https://user:credential@provider.example/private"
    page, history, _ = collection_page()
    if failure_at == "authentication":
        page.get_by_role.side_effect = RuntimeError(sentinel)
    elif failure_at == "locator":
        page.locator.side_effect = RuntimeError(sentinel)
    elif failure_at == "navigation":
        page.wait_for_load_state.side_effect = TimeoutError(sentinel)
    else:
        history.click.side_effect = TimeoutError(sentinel)
    with pytest.raises(FetchError) as error:
        await barclays.collect_exports(page)
    assert "PRIVATE_SENTINEL" not in str(error.value)
    assert "provider.example" not in "".join(traceback.format_exception(error.value))
    assert error.value.__suppress_context__
    assert error.value.__cause__ is None


@pytest.mark.asyncio
async def test_collect_requires_authenticated_investment_page(monkeypatch):
    monkeypatch.setattr(barclays, "_is_logged_in", AsyncMock(return_value=False))
    with pytest.raises(FetchError):
        await barclays.collect_exports(fake_page())


@pytest.mark.asyncio
async def test_collect_returns_pair_without_publishing_or_reauth(monkeypatch):
    from unittest.mock import Mock

    locator = SimpleNamespace(
        get_attribute=AsyncMock(return_value=ROOT + "/Orders"), click=AsyncMock()
    )
    locator.filter = Mock(return_value=locator)
    page = fake_page()
    page.locator = Mock(return_value=locator)
    page.get_by_role = Mock(return_value=locator)
    page.wait_for_load_state = AsyncMock()
    monkeypatch.setattr(barclays, "_is_logged_in", AsyncMock(return_value=True))
    read = AsyncMock(side_effect=[b"holdings", b"orders"])
    monkeypatch.setattr(barclays, "read_export", read)
    assert await barclays.collect_exports(page) == (b"holdings", b"orders")
    assert read.await_count == 2


@pytest.mark.asyncio
async def test_reads_only_exact_observed_account_export():
    data = _xls(
        [
            ["Account"],
            [],
            ["Investment", "Identifier", "Quantity Held", "Value"],
            ["Cash", "", 0, 1],
        ]
    )
    page = fake_page(data)
    assert (
        await barclays.read_export(page, ROOT + SUFFIX, SUFFIX, ExportKind.BARCLAYS_HOLDINGS)
        == data
    )
    page.request.get.assert_awaited_once_with(
        ROOT + SUFFIX, max_redirects=0, max_retries=0, timeout=20000
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "href",
    [
        "https://evil.example/file",
        ROOT.replace("https:", "http:") + SUFFIX,
        ROOT.replace("test-account", "other-account") + SUFFIX,
        ROOT + "/Buy",
        ROOT + SUFFIX + "#fragment",
    ],
)
async def test_rejects_foreign_or_non_export_links_without_request(href):
    page = fake_page()
    with pytest.raises(FetchError):
        await barclays.read_export(page, href, SUFFIX, ExportKind.BARCLAYS_HOLDINGS)
    page.request.get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,status",
    [(b"", 200), (b"<html>Log in</html>", 200), (b"redirect", 302), (b"blocked", 403)],
)
async def test_rejects_empty_login_blocked_and_redirect_responses(data, status):
    with pytest.raises(FetchError):
        await barclays.read_export(
            fake_page(data, status), ROOT + SUFFIX, SUFFIX, ExportKind.BARCLAYS_HOLDINGS
        )
