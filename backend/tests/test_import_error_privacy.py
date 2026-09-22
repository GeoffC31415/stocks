"""Import errors must not disclose SQL parameters, credentials or paths."""

from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile

from app.routers import imports, orders


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module,handler,service,filename",
    [
        (imports, "create_import", "import_barclays_xls", "test.xls"),
        (imports, "create_hl_import", "import_hl_holdings_csv", "test.csv"),
        (orders, "import_orders", "import_order_history", "test.xls"),
        (orders, "import_hl_orders", "import_hl_orders_csv", "test.csv"),
    ],
)
async def test_import_error_is_private(monkeypatch, module, handler, service, filename):
    sensitive = "SQL parameters: PRIVATE_SENTINEL /private/portfolio.db"
    monkeypatch.setattr(module, service, AsyncMock(side_effect=RuntimeError(sensitive)))
    session = AsyncMock()
    with pytest.raises(HTTPException) as raised:
        await getattr(module, handler)(
            file=UploadFile(filename=filename, file=BytesIO(b"malformed fixture")),
            session=session,
        )
    assert "PRIVATE_SENTINEL" not in str(raised.value.detail)
    assert "/private" not in str(raised.value.detail)
    assert "Import failed" in str(raised.value.detail)
    session.rollback.assert_awaited_once()
