"""Local-only, read-only synthetic preview; no migrations, broker or auth store.

Requires an existing frontend build. Creates an EXCLUSIVE disposable DB with
explicitly synthetic holdings and zero orders. Never accepts a real database.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


async def create_synthetic_database(path: Path) -> None:
    from app.models import Base, HoldingSnapshot, ImportBatch, Instrument
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    engine = create_async_engine(f'sqlite+aiosqlite:///{path}')
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as session:
            for i, account in enumerate(('Synthetic ISA', 'Synthetic SIPP'), 1):
                session.add(Instrument(id=i, account_name=account, identifier=f'SYNTHETIC-{i}',
                                       security_name=f'Synthetic example fund {i}', is_cash=False,
                                       asset_class='Equity', sector='Synthetic', region='Global'))
            for batch_id, date in enumerate((dt.date(2026, 1, 1), dt.date(2026, 6, 1), dt.date(2026, 9, 29)), 1):
                session.add(ImportBatch(id=batch_id, as_of_date=date,
                                       created_at=dt.datetime.combine(date, dt.time(18), dt.UTC),
                                       file_sha256=f'{batch_id:064x}', filename='SYNTHETIC fixture'))
                for instrument_id in (1, 2):
                    # Two independent observations per account: fund and cash.
                    cash_id = instrument_id + 2
                    if batch_id == 1:
                        session.add(Instrument(id=cash_id, account_name=('Synthetic ISA' if instrument_id == 1 else 'Synthetic SIPP'),
                                               identifier='SYNTHETIC-CASH', security_name='Synthetic cash', is_cash=True))
                    for iid, value in ((instrument_id, 1000 + batch_id * 100), (cash_id, 50)):
                        session.add(HoldingSnapshot(import_batch_id=batch_id, instrument_id=iid,
                                                    investment_label='Synthetic fixture', quantity=10,
                                                    last_price=value / 10, last_price_ccy='GBP',
                                                    value=value, value_ccy='GBP', value_gbp=value))
            await session.commit()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new disposable directory outside repo')
    parser.add_argument('--port', type=int, default=8127)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if any((REPO / name).exists() for name in ('.env', 'backend/.env')):
        parser.error('Use an isolated worktree without .env; private dotenv reads prohibited')
    output = args.output.resolve()
    if output.is_relative_to(REPO):
        parser.error('Output must be outside repository')
    if not (args.dist / 'index.html').is_file():
        parser.error('An existing built frontend is required')
    # Before ANY application imports: local factory engine is in-memory, and
    # no global public app/passkey store is constructed by rehearsal.create_app.
    os.environ['PORTFOLIO_DATABASE_URL'] = 'sqlite+aiosqlite:///:memory:'
    os.environ['PORTFOLIO_DEPLOYMENT_MODE'] = 'local'
    sys.path.insert(0, str(REPO / 'backend'))
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    database = output / 'synthetic.db'
    asyncio.run(create_synthetic_database(database))
    print(f'SYNTHETIC zero-order preview: http://127.0.0.1:{args.port}; fixture: {database}', flush=True)
    if not args.prepare_only:
        from verify_analysis_ui import serve
        serve(database, args.dist.resolve(), args.port)


if __name__ == '__main__':
    main()
