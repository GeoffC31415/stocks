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
        assert barclays.attempt_marker().exists()
        calls.append(page)
        raise TimeoutError("PRIVATE_SENTINEL")

    monkeypatch.setattr(barclays, "_login_once", attempt, raising=False)
    with pytest.raises(NeedsAttention, match="paused") as error:
        await barclays.login(object())
    assert "PRIVATE_SENTINEL" not in str(error.value)
    with pytest.raises(NeedsAttention):
        await barclays.login(object())
    assert len(calls) == 1
    assert barclays.attempt_marker().stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_cancellation_keeps_latch(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    monkeypatch.setattr(
        barclays, "_login_once", AsyncMock(side_effect=asyncio.CancelledError), raising=False
    )
    with pytest.raises(asyncio.CancelledError):
        await barclays.login(object())
    assert barclays.attempt_marker().exists()


@pytest.mark.asyncio
async def test_unknown_post_login_state_cannot_count_as_success(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    monkeypatch.setattr(barclays, "_login_once", AsyncMock(), raising=False)
    monkeypatch.setattr(barclays, "_is_logged_in", AsyncMock(return_value=False))
    with pytest.raises(NeedsAttention):
        await barclays.login(object())
    assert barclays.attempt_marker().exists()


@pytest.mark.asyncio
async def test_verified_login_keeps_latch_until_exports_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    monkeypatch.setattr(barclays, "_login_once", AsyncMock(), raising=False)
    monkeypatch.setattr(barclays, "_is_logged_in", AsyncMock(return_value=True))
    await barclays.login(object())
    assert barclays.attempt_marker().exists()


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
@pytest.mark.parametrize("marker_kind", ["legacy", "attempt"])
async def test_blocked_fetch_requires_operator_review_without_changing_latch(
    tmp_path, monkeypatch, marker_kind
):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    for field in ("surname", "membership_number", "passcode", "memorable_word"):
        monkeypatch.setattr(settings, f"barclays_{field}", SecretStr("synthetic"))
    # Existing legacy files must remain a permanent pause, not be migrated.
    marker = tmp_path / "barclays-login-blocked"
    assert marker == barclays.block_marker() == barclays.operator_pause_marker()
    if marker_kind == "attempt":
        marker = barclays.attempt_marker()
    marker.write_text("Existing uncertain attempt; do not retry.\n")
    before = marker.read_bytes()
    attempt = AsyncMock()
    monkeypatch.setattr(barclays, "_login_once", attempt)

    def no_browser(*args, **kwargs):
        raise AssertionError("Legacy pause must prevent opening a browser")

    monkeypatch.setattr(barclays, "broker_context", no_browser)
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
    if marker_kind == "legacy":
        assert not barclays.attempt_marker().exists()


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


@pytest.mark.parametrize(
    "url",
    [
        "http://www.investments.barclays.co.uk/en-gb/SubAccount/test/Portfolio",
        "https://user@www.investments.barclays.co.uk/en-gb/SubAccount/test/Portfolio",
    ],
)
async def test_authentication_requires_exact_https_origin(url):
    page = SimpleNamespace(
        url=url, get_by_role=lambda *a, **k: SimpleNamespace(count=AsyncMock(return_value=1))
    )
    assert not await barclays._is_logged_in(page)


def test_unattended_configuration_is_opt_in():
    from app.config import Settings

    config = Settings(_env_file=None)
    assert config.barclays_automation_enabled is False
    assert config.barclays_expected_account is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [None, "account", "close", "guard-edit", "guard-replace", "operator-pause"]
)
async def test_verified_fetch_returns_pair_and_retains_latch_until_commit(
    tmp_path, monkeypatch, failure
):
    from contextlib import asynccontextmanager

    from pydantic import SecretStr
    from test_barclays_sync_service import ACCOUNT, pair

    from app.services.barclays_sync_service import FetchedPair

    monkeypatch.setattr(settings, "browser_profile", tmp_path / "profile")
    for field in ("surname", "membership_number", "passcode", "memorable_word"):
        monkeypatch.setattr(settings, f"barclays_{field}", SecretStr("synthetic"))
    monkeypatch.setattr(settings, "barclays_automation_enabled", True)
    monkeypatch.setattr(
        settings,
        "barclays_expected_account",
        SecretStr("other" if failure == "account" else ACCOUNT),
    )
    page = object()

    @asynccontextmanager
    async def context(*args, **kwargs):
        yield SimpleNamespace(new_page=AsyncMock(return_value=page))
        if failure == "close":
            raise RuntimeError("PRIVATE_SENTINEL")

    monkeypatch.setattr(barclays, "broker_context", context, raising=False)

    async def attempt(_page):
        marker = barclays.attempt_marker()
        if failure == "operator-pause":
            barclays._block("Operator pause during login")
        elif failure == "guard-replace":
            replacement = marker.with_suffix(".operator")
            replacement.write_text("Modified attempt state")
            replacement.replace(marker)
        elif failure == "guard-edit":
            import os

            before = marker.stat()
            marker.write_text("Modified attempt state")
            os.utime(marker, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))

    monkeypatch.setattr(barclays, "_login_once", attempt)
    monkeypatch.setattr(barclays, "_is_logged_in", AsyncMock(return_value=True))
    exports = AsyncMock(return_value=pair())
    monkeypatch.setattr(barclays, "collect_exports", exports)
    result = await barclays.fetch(tmp_path / "inbox")
    if failure:
        assert not isinstance(result, FetchedPair)
        assert result.status == "needs_attention"
        assert barclays.attempt_marker().exists()
        assert "PRIVATE_SENTINEL" not in str(result)
        if failure.startswith("guard-"):
            assert barclays.attempt_marker().read_text() == "Modified attempt state"
            exports.assert_not_awaited()
        if failure == "operator-pause":
            assert "Operator pause during login" in barclays.operator_pause_marker().read_text()
            exports.assert_not_awaited()
            with pytest.raises(NeedsAttention):
                await barclays.login(object())
        return
    assert isinstance(result, FetchedPair)
    assert barclays.attempt_marker().exists()
    result.acknowledge()
    assert not barclays.attempt_marker().exists()


@pytest.mark.parametrize("fail_at", [1, 2])
async def test_fsync_failure_prevents_all_bank_interaction(tmp_path, monkeypatch, fail_at):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    calls = []

    def fsync(fd):
        calls.append(fd)
        if len(calls) == fail_at:
            raise OSError("synthetic disk failure")

    monkeypatch.setattr(barclays.os, "fsync", fsync)
    attempt = AsyncMock()
    monkeypatch.setattr(barclays, "_login_once", attempt)
    with pytest.raises(OSError):
        await barclays.login(object())
    attempt.assert_not_awaited()
    assert barclays.attempt_marker().exists()


async def test_concurrent_attempts_allow_only_one_bank_call(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def attempt(page):
        calls.append(page)
        entered.set()
        await release.wait()

    monkeypatch.setattr(barclays, "_login_once", attempt)
    monkeypatch.setattr(barclays, "_is_logged_in", AsyncMock(return_value=True))
    first = asyncio.create_task(barclays.login(object()))
    await entered.wait()
    try:
        with pytest.raises(NeedsAttention):
            await barclays.login(object())
    finally:
        release.set()
        await first
    assert len(calls) == 1
    assert barclays.attempt_marker().exists()


async def test_operator_pause_created_at_ack_unlink_survives_and_blocks_next_attempt(
    tmp_path, monkeypatch
):
    from contextlib import asynccontextmanager
    from pathlib import Path

    from pydantic import SecretStr
    from test_barclays_sync_service import ACCOUNT, pair

    from app.services.barclays_sync_service import FetchedPair

    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    monkeypatch.setattr(settings, "barclays_automation_enabled", True)
    monkeypatch.setattr(settings, "barclays_expected_account", SecretStr(ACCOUNT))
    for field in ("surname", "membership_number", "passcode", "memorable_word"):
        monkeypatch.setattr(settings, f"barclays_{field}", SecretStr("synthetic"))

    @asynccontextmanager
    async def context(*args, **kwargs):
        yield SimpleNamespace(new_page=AsyncMock(return_value=object()))

    attempt = AsyncMock()
    monkeypatch.setattr(barclays, "broker_context", context)
    monkeypatch.setattr(barclays, "_login_once", attempt)
    monkeypatch.setattr(barclays, "_is_logged_in", AsyncMock(return_value=True))
    monkeypatch.setattr(barclays, "collect_exports", AsyncMock(return_value=pair()))
    result = await barclays.fetch(tmp_path / "inbox")
    assert isinstance(result, FetchedPair)
    unlink = Path.unlink
    interrupted = []

    def pause_before_unlink(path, *args, **kwargs):
        # Deterministic interleaving AFTER acknowledgement's identity check.
        barclays._block("Operator pause during acknowledgement")
        interrupted.append(path)
        unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", pause_before_unlink)
    result.acknowledge()
    assert len(interrupted) == 1
    legacy_pause = tmp_path / "barclays-login-blocked"
    assert legacy_pause.exists(), "automatic acknowledgement removed the operator pause"
    assert "Operator pause during acknowledgement" in legacy_pause.read_text()
    attempt.reset_mock()

    def no_browser(*args, **kwargs):
        raise AssertionError("Operator pause must prevent opening a browser")

    monkeypatch.setattr(barclays, "broker_context", no_browser)
    assert (await barclays.fetch(tmp_path / "inbox")).status == "needs_attention"
    with pytest.raises(NeedsAttention):
        await barclays.login(object())
    attempt.assert_not_awaited()
    assert legacy_pause.exists()


@pytest.mark.parametrize("path_kind", ["operator", "legacy", "arbitrary", "traversal"])
def test_acknowledgement_rejects_non_attempt_paths(tmp_path, monkeypatch, path_kind):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    marker = {
        "operator": barclays.operator_pause_marker(),
        "legacy": barclays.block_marker(),
        "arbitrary": tmp_path / "unrelated-file",
        "traversal": tmp_path / "child" / ".." / "barclays-login-blocked",
    }[path_kind]
    (tmp_path / "child").mkdir()
    marker.write_text("Must never be automatically deleted")
    stat = marker.stat()
    identity = (stat.st_dev, stat.st_ino, stat.st_mtime_ns)
    with pytest.raises(NeedsAttention):
        barclays._acknowledge_attempt(marker, identity)
    assert marker.read_text() == "Must never be automatically deleted"


def test_changed_guard_is_never_cleared(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    marker = barclays.attempt_marker()
    marker.write_text("original")
    stat = marker.stat()
    identity = (stat.st_dev, stat.st_ino, stat.st_mtime_ns)
    marker.write_text("changed by operator")
    with pytest.raises(NeedsAttention):
        barclays._acknowledge_attempt(marker, identity)
    assert marker.read_text() == "changed by operator"


def test_operator_pause_is_durable_without_modifying_attempt_state(tmp_path, monkeypatch):
    import stat

    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    marker = barclays.attempt_marker()
    marker.write_text("Existing attempt")
    before = marker.stat()
    fsync = barclays.os.fsync
    synced = []

    def record_fsync(fd):
        synced.append(barclays.os.fstat(fd).st_mode)
        fsync(fd)

    monkeypatch.setattr(barclays.os, "fsync", record_fsync)
    barclays._block("Synthetic rejection")
    assert len(synced) == 2
    assert stat.S_ISREG(synced[0])
    assert stat.S_ISDIR(synced[1])
    assert barclays.operator_pause_marker().stat().st_mode & 0o777 == 0o600
    assert marker.read_text() == "Existing attempt"
    after = marker.stat()
    assert (after.st_dev, after.st_ino, after.st_mtime_ns) == (
        before.st_dev, before.st_ino, before.st_mtime_ns
    )


async def test_pause_during_attempt_directory_fsync_prevents_bank_call(tmp_path, monkeypatch):
    import stat

    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    fsync = barclays.os.fsync
    inserted = False

    def pause_at_directory_fsync(fd):
        nonlocal inserted
        fsync(fd)
        if stat.S_ISDIR(barclays.os.fstat(fd).st_mode) and not inserted:
            inserted = True
            barclays._block("Operator pause before bank call")

    monkeypatch.setattr(barclays.os, "fsync", pause_at_directory_fsync)
    attempt = AsyncMock()
    monkeypatch.setattr(barclays, "_login_once", attempt)
    with pytest.raises(NeedsAttention):
        await barclays.login(object())
    attempt.assert_not_awaited()
    assert inserted
    assert barclays.operator_pause_marker().exists()
    assert barclays.attempt_marker().exists()


async def test_dangling_legacy_pause_also_blocks_login(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    barclays.operator_pause_marker().symlink_to(tmp_path / "missing")
    attempt = AsyncMock()
    monkeypatch.setattr(barclays, "_login_once", attempt)
    with pytest.raises(NeedsAttention):
        await barclays.login(object())
    attempt.assert_not_awaited()
    assert barclays.operator_pause_marker().is_symlink()
    assert not barclays.attempt_marker().exists()
