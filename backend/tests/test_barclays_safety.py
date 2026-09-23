"""No real credentials, browser, bank requests or production DB in these tests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.fetchers import barclays
from app.fetchers.base import NeedsAttention


@pytest.mark.asyncio
async def test_uncertain_attempt_is_latched_before_browser_action(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    calls = []

    async def attempt(page):
        assert barclays.block_marker().exists()
        calls.append(page)
        raise TimeoutError("PRIVATE_SENTINEL")

    monkeypatch.setattr(barclays, "_login_once", attempt, raising=False)
    with pytest.raises(NeedsAttention, match="paused") as error:
        await barclays.login(object())
    assert "PRIVATE_SENTINEL" not in str(error.value)
    with pytest.raises(NeedsAttention):
        await barclays.login(object())
    assert len(calls) == 1
    assert barclays.block_marker().stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_cancellation_keeps_latch(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    monkeypatch.setattr(
        barclays, "_login_once", AsyncMock(side_effect=asyncio.CancelledError), raising=False
    )
    with pytest.raises(asyncio.CancelledError):
        await barclays.login(object())
    assert barclays.block_marker().exists()


@pytest.mark.asyncio
async def test_unknown_post_login_state_cannot_count_as_success(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    monkeypatch.setattr(barclays, "_login_once", AsyncMock(), raising=False)
    monkeypatch.setattr(barclays, "_is_logged_in", AsyncMock(return_value=False))
    with pytest.raises(NeedsAttention):
        await barclays.login(object())
    assert barclays.block_marker().exists()


@pytest.mark.asyncio
async def test_verified_login_keeps_latch_until_exports_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    monkeypatch.setattr(barclays, "_login_once", AsyncMock(), raising=False)
    monkeypatch.setattr(barclays, "_is_logged_in", AsyncMock(return_value=True))
    await barclays.login(object())
    assert barclays.block_marker().exists()


@pytest.mark.asyncio
async def test_unverified_automation_is_disabled_even_with_credentials(tmp_path, monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    for field in ("surname", "membership_number", "passcode", "memorable_word"):
        monkeypatch.setattr(settings, f"barclays_{field}", SecretStr("synthetic"))

    def no_browser(*args, **kwargs):
        raise AssertionError("Unverified unattended login must not open a browser")

    monkeypatch.setattr(barclays, "broker_context", no_browser, raising=False)
    result = await barclays.fetch(tmp_path)
    assert result.status == "needs_attention"
    assert "disabled" in result.detail


@pytest.mark.asyncio
async def test_blocked_fetch_requires_operator_review_without_changing_latch(tmp_path, monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    for field in ("surname", "membership_number", "passcode", "memorable_word"):
        monkeypatch.setattr(settings, f"barclays_{field}", SecretStr("synthetic"))
    marker = barclays.block_marker()
    marker.write_text("Existing uncertain attempt; do not retry.\n")
    before = marker.read_bytes()
    attempt = AsyncMock()
    monkeypatch.setattr(barclays, "_login_once", attempt)
    result = await barclays.fetch(tmp_path)
    assert result.status == "needs_attention"
    assert result.detail is not None
    assert "operator review" in result.detail.lower()
    assert "delete" not in result.detail.lower()
    assert "retry" not in result.detail.lower()
    assert marker.read_bytes() == before
    with pytest.raises(NeedsAttention):
        await barclays.login(object())
    attempt.assert_not_awaited()
    assert marker.read_bytes() == before


def test_block_message_requires_operator_review_not_marker_deletion(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    barclays._block("Synthetic rejection")
    text = barclays.block_marker().read_text().lower()
    assert "operator review" in text
    assert "delete" not in text
    assert "re-enable" not in text


@pytest.mark.asyncio
async def test_untrusted_host_is_never_authenticated():
    page = SimpleNamespace(url="https://evil.example/Portfolio")
    assert not await barclays._is_logged_in(page)


def _configure(monkeypatch, tmp_path, *, armed: bool) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    monkeypatch.setattr(settings, "barclays_auto_login", armed)
    for field in ("surname", "membership_number", "passcode", "memorable_word"):
        monkeypatch.setattr(settings, f"barclays_{field}", SecretStr("synthetic"))


class _FakeContext:
    def __init__(self):
        self.pages = [SimpleNamespace(url="about:blank", get_by_role=lambda *a, **k: None)]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _fake_browser(monkeypatch):
    opened = []

    def ctx(*args, **kwargs):
        opened.append(args)
        return _FakeContext()

    import app.fetchers.base as base

    monkeypatch.setattr(base, "broker_context", ctx)
    monkeypatch.setattr(barclays, "_logout", AsyncMock())
    return opened


@pytest.mark.asyncio
async def test_sync_is_off_unless_explicitly_armed(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path, armed=False)
    opened = _fake_browser(monkeypatch)
    result = await barclays.sync(session=None)
    assert result.status in {"needs_attention", "skipped"}
    assert opened == []
    assert not barclays.block_marker().exists()


@pytest.mark.asyncio
async def test_armed_sync_refuses_while_latched(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path, armed=True)
    opened = _fake_browser(monkeypatch)
    barclays.block_marker().write_text("previous attempt\n")
    result = await barclays.sync(session=None)
    assert result.status == "needs_attention" and opened == []


@pytest.mark.asyncio
async def test_only_verified_login_and_import_rearm(tmp_path, monkeypatch):
    import app.services.barclays_pair_import as pair

    _configure(monkeypatch, tmp_path, armed=True)
    monkeypatch.setattr(barclays, "fetch", AsyncMock(return_value=SimpleNamespace(status="ok")))
    _fake_browser(monkeypatch)

    async def fake_login(page):
        barclays.block_marker().write_text("attempt\n")

    monkeypatch.setattr(barclays, "login", fake_login)
    monkeypatch.setattr(barclays, "_open_investment_overview", AsyncMock())
    monkeypatch.setattr(barclays, "collect_exports", AsyncMock(return_value=(b"h", b"o")))

    # Invalid export: latch kept.
    monkeypatch.setattr(
        pair, "import_barclays_pair", AsyncMock(side_effect=pair.BarclaysExportInvalid("bad"))
    )
    result = await barclays.sync(session=object())
    assert result.status == "needs_attention" and barclays.block_marker().exists()

    # Verified success: latch cleared so the next scheduled run may try once.
    barclays.block_marker().unlink()
    ok = SimpleNamespace(holdings="imported", orders="unchanged", new_orders=0)
    monkeypatch.setattr(pair, "import_barclays_pair", AsyncMock(return_value=ok))
    result = await barclays.sync(session=object())
    assert result.status == "ok" and not barclays.block_marker().exists()


@pytest.mark.asyncio
async def test_unmapped_navigation_keeps_latch(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path, armed=True)
    monkeypatch.setattr(barclays, "fetch", AsyncMock(return_value=SimpleNamespace(status="ok")))
    _fake_browser(monkeypatch)

    async def fake_login(page):
        barclays.block_marker().write_text("attempt\n")

    monkeypatch.setattr(barclays, "login", fake_login)
    result = await barclays.sync(session=object())
    assert result.status == "needs_attention" and barclays.block_marker().exists()
