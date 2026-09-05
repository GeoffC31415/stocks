"""Offline contract regressions for the real market-data adapter."""
import io

from app.services.market_data_service import _http_get


def test_http_get_uses_opener_open_interface():
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://example.test/chart"
            assert timeout == 3
            return io.BytesIO(b'{"chart": {}}')

    assert _http_get("https://example.test/chart", timeout=3, opener=Opener()) == b'{"chart": {}}'


async def test_history_without_cache_never_constructs_provider(monkeypatch):
    from app.services import market_data_service as market

    def forbidden():
        raise AssertionError("analytics must not contact a provider")

    monkeypatch.setattr(market, "make_provider", forbidden)
    assert await market.fetch_history(None, "spx.us") == []
