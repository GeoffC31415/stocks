"""Synthetic reliability/provenance contracts; never connects to brokers."""
import pytest

from app.services.sync_runner import RunReport, StepResult


@pytest.mark.parametrize(('steps', 'files', 'outcome'), [
    ([StepResult('Import files', 'no_op')], [], 'no_op'),
    ([StepResult('Trading 212', 'skipped')], [], 'disabled'),
    ([StepResult('Trading 212', 'ok')], [], 'complete'),
    ([StepResult('Trading 212', 'ok'), StepResult('HL', 'failed')], [], 'partial'),
    ([StepResult('HL', 'failed')], [], 'failed'),
    ([StepResult('Import files', 'unchanged')], [{'status': 'rejected'}], 'failed'),
])
def test_aggregate_never_hides_failure(steps, files, outcome):
    report = RunReport('2026-09-29T10:00:00+00:00', steps=steps, files=files)
    assert report.to_json()['outcome'] == outcome
    assert report.ok == (outcome not in {'partial', 'failed'})


async def test_cli_returns_failure_for_partial_success(tmp_path, monkeypatch, capsys):
    from argparse import Namespace
    from contextlib import asynccontextmanager

    from app import sync_cli

    async def init():
        pass

    @asynccontextmanager
    async def sessions():
        yield object()

    async def run(*args, **kwargs):
        return RunReport('2026-09-29T10:00:00+00:00', steps=[
            StepResult('Trading 212', 'ok'), StepResult('HL', 'failed')])

    monkeypatch.setattr(sync_cli, 'init_db', init)
    monkeypatch.setattr(sync_cli, 'SessionLocal', sessions)
    monkeypatch.setattr(sync_cli, '_run_sync_all_locked', run)
    args = Namespace(no_fetch=True, include_downloads=False, no_trading212=True, dry_run=False, json=True)
    assert await sync_cli._run_locked(args) == 1
    assert 'partial' in capsys.readouterr().out


async def test_freshness_survives_failure_and_unchanged_is_new_observation(tmp_path):
    import json

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.sync_runner import run_sync_all
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async def fetched(inbox):
        return StepResult('Barclays', 'unchanged', sections={'holdings': {
            'status': 'unchanged', 'verified_at': '2026-09-29T10:00:00+00:00',
            'valuation_at': '2026-09-29', 'coverage': 'complete',
            'reason_code': 'verified_unchanged', 'action_code': 'none'}})
    async def fails(inbox):
        return StepResult('Barclays', 'failed')
    try:
        async with async_sessionmaker(engine)() as session:
            await run_sync_all(session, inbox=tmp_path, fetchers=[('Barclays', fetched)], include_trading212=False)
            report = await run_sync_all(session, inbox=tmp_path, fetchers=[('Barclays', fails)], include_trading212=False)
        freshness = json.loads((tmp_path / 'last-sync.json').read_text())['freshness']['Barclays']['holdings']
        assert freshness['verified_at'] == '2026-09-29T10:00:00+00:00'
        assert freshness['last_attempt_at'] == report.started_at
        assert freshness['status'] == 'failed'
        assert freshness['reason_code'] == 'provider_failed'
        assert freshness['action_code'] == 'retry'
        assert freshness['valuation_at'] == '2026-09-29'
    finally:
        await engine.dispose()


async def test_inbox_failure_still_runs_independent_provider_and_finishes(tmp_path, monkeypatch):
    import json

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.services.sync_runner as runner
    async def broken(*args, **kwargs):
        raise PermissionError('PRIVATE_SENTINEL')
    async def trading(session):
        return StepResult('Trading 212', 'ok')
    monkeypatch.setattr(runner, 'sync_inbox', broken)
    monkeypatch.setattr(runner, '_trading212_step', trading)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with async_sessionmaker(engine)() as session:
            report = await runner.run_sync_all(session, inbox=tmp_path)
        assert report.outcome == 'partial'
        persisted = json.loads((tmp_path / 'last-sync.json').read_text())
        assert persisted['finished_at']
        assert 'PRIVATE_SENTINEL' not in json.dumps(persisted)
        assert report.steps[-1].status == 'ok'
    finally:
        await engine.dispose()


def test_public_status_retains_only_safe_provenance():
    from app.services.sync_control import public_report
    report = RunReport('2026-09-29T10:00:00+00:00', freshness={'Barclays': {'holdings': {
        'last_attempt_at': '2026-09-29T10:00:00+00:00', 'verified_at': '2026-09-28T10:00:00+00:00',
        'valuation_at': '2026-09-28', 'coverage': 'complete', 'status': 'failed',
        'reason_code': 'PRIVATE_SENTINEL', 'action_code': 'retry', 'secret': 'PRIVATE_SENTINEL'}}})
    public = public_report(report.to_json())
    assert public['schema_version'] == 2
    assert public['outcome'] == report.outcome
    assert public['freshness']['Barclays']['holdings']['verified_at'] == '2026-09-28T10:00:00+00:00'
    assert 'PRIVATE_SENTINEL' not in str(public)


async def test_cancelled_run_publishes_terminal_failure(tmp_path, monkeypatch):
    import asyncio
    import json

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.sync_runner import run_sync_all
    async def cancel(inbox):
        raise asyncio.CancelledError()
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with async_sessionmaker(engine)() as session:
            with pytest.raises(asyncio.CancelledError):
                await run_sync_all(session, inbox=tmp_path, fetchers=[('Barclays', cancel)], include_trading212=False)
        report = json.loads((tmp_path / 'last-sync.json').read_text())
        assert report['finished_at']
        assert report['outcome'] == 'failed'
    finally:
        await engine.dispose()


def test_section_failure_changes_aggregate_even_with_changed_holdings():
    report = RunReport('2026-09-29T10:00:00+00:00', steps=[StepResult('Trading 212', 'ok', sections={
        'holdings': {'status': 'imported'}, 'orders': {'status': 'failed', 'reason_code': 'permission_denied'}})])
    assert report.outcome == 'partial'
    assert report.ok is False


async def test_runner_accepts_staged_hl_pair_transport(tmp_path, monkeypatch):
    import datetime as dt
    import sys
    from dataclasses import dataclass
    from types import ModuleType

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.sync_runner import run_sync_all
    module = ModuleType('app.services.hl_sync_service')
    @dataclass
    class FetchedHLPair:
        holdings: bytes
        orders: bytes
        observed_at: dt.datetime
        @property
        def as_of(self):
            return self.observed_at.date()
    called = []
    async def import_pair(session, holdings, orders, *, as_of):
        called.append((holdings, orders, as_of))
        return {'snapshot': 'unchanged', 'orders': 'unchanged', 'orders_imported': 0}
    module.FetchedHLPair = FetchedHLPair
    module.import_pair = import_pair
    monkeypatch.setitem(sys.modules, module.__name__, module)
    async def fetch(inbox):
        return FetchedHLPair(b'synthetic holdings', b'synthetic activity', dt.datetime(2026, 9, 29, tzinfo=dt.UTC))
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with async_sessionmaker(engine)() as session:
            report = await run_sync_all(session, inbox=tmp_path, fetchers=[('Hargreaves Lansdown', fetch)], include_trading212=False)
        assert len(called) == 1
        assert report.steps[0].status == 'unchanged'
        assert report.freshness['Hargreaves Lansdown']['holdings']['verified_at'] == '2026-09-29T00:00:00+00:00'
        assert report.steps[0].sections['orders']['coverage'] == 'complete'
    finally:
        await engine.dispose()


def test_atomic_status_fsyncs_directory(tmp_path, monkeypatch):
    import os
    import stat

    from app.services.sync_control import atomic_json
    synced = []
    original = os.fsync
    def sync(fd):
        synced.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        return original(fd)
    monkeypatch.setattr(os, 'fsync', sync)
    atomic_json(tmp_path / 'status.json', {'schema_version': 2})
    assert synced == [False, True]


def test_nonobject_status_is_ignored(tmp_path):
    from app.services.sync_runner import read_last_sync
    (tmp_path / 'last-sync.json').write_text('[]')
    assert read_last_sync(tmp_path) is None


@pytest.mark.parametrize(('stamp', 'expected'), [('@1790789502', '2026-09-30T17:31:42+00:00'), ('n/a', None), ('@99999999999999999999999', None)])
def test_next_run_reads_fixed_timer_without_service_action(monkeypatch, stamp, expected):
    import subprocess

    from app.services import sync_control
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=stamp)
    monkeypatch.setattr(sync_control.subprocess, 'run', run)
    assert sync_control.next_run_at() == expected
    assert calls == [['/usr/bin/systemctl', 'show', 'stocks-sync.timer', '--property=NextElapseUSecRealtime', '--value', '--timestamp=unix']]


def test_unavailable_section_is_not_a_verified_unchanged_check():
    from app.services.sync_freshness import verified_sections
    sections = verified_sections({'holdings': 'skipped', 'orders': 'unchanged'}, '2026-09-29T10:00:00+00:00', '2026-09-29')
    assert sections['holdings']['status'] == 'needs_attention'
    assert sections['holdings']['verified_at'] is None
    assert sections['holdings']['reason_code'] == 'partial_coverage'
    report = RunReport('2026-09-29T10:00:00+00:00', steps=[StepResult('Trading 212', 'unchanged', sections=sections)])
    assert report.outcome == 'partial'


async def test_status_write_failure_does_not_abort_provider(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.services.sync_runner as runner
    def denied(*args, **kwargs):
        raise PermissionError('PRIVATE_SENTINEL')
    async def trading(session):
        return StepResult('Trading 212', 'ok')
    monkeypatch.setattr(runner, 'atomic_json', denied)
    monkeypatch.setattr(runner, '_trading212_step', trading)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with async_sessionmaker(engine)() as session:
            report = await runner.run_sync_all(session, inbox=tmp_path)
        assert report.finished_at
        assert report.outcome == 'partial'
        assert any(s.name == 'Trading 212' and s.status == 'ok' for s in report.steps)
        assert any(s.detail == 'status_write_failed' for s in report.steps)
    finally:
        await engine.dispose()


async def test_attempt_is_persisted_before_broker_await(tmp_path):
    import json

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.sync_runner import run_sync_all
    async def inspect(inbox):
        status = json.loads((tmp_path / 'last-sync.json').read_text())
        assert status['freshness']['Barclays']['holdings']['last_attempt_at'] == status['started_at']
        assert status['freshness']['Barclays']['holdings']['verified_at'] is None
        return StepResult('Barclays', 'failed')
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with async_sessionmaker(engine)() as session:
            report = await run_sync_all(session, inbox=tmp_path, fetchers=[('Barclays', inspect)], include_trading212=False)
        assert report.steps[0].detail is None
    finally:
        await engine.dispose()


async def test_pair_acknowledgment_failure_is_committed_with_attention(tmp_path):
    import datetime as dt

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from test_barclays_sync_service import ACCOUNT, DAY, pair

    from app.models import AccountAlias, Base, ImportBatch
    from app.services.barclays_sync_service import FetchedPair
    from app.services.sync_runner import run_sync_all
    h, o = pair()
    def denied():
        raise PermissionError('PRIVATE_SENTINEL')
    async def fetched(inbox):
        return FetchedPair(h, o, dt.datetime.combine(DAY, dt.time(18), dt.UTC), denied)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add(AccountAlias(source='barclays_orders', source_account_name='Investment ISA', canonical_account_name=ACCOUNT))
            await session.commit()
            report = await run_sync_all(session, inbox=tmp_path, fetchers=[('Barclays', fetched)], include_trading212=False)
            assert await session.scalar(select(func.count()).select_from(ImportBatch)) == 1
        assert report.steps[0].status == 'committed_with_attention'
        assert report.outcome == 'partial'
        assert report.freshness['Barclays']['holdings']['verified_at'] is not None
    finally:
        await engine.dispose()


async def test_terminal_publication_failure_is_visible_in_surviving_private_status(tmp_path, monkeypatch):
    import json

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.services.sync_runner as runner
    from app.services.sync_control import atomic_json
    monkeypatch.setattr(runner.settings, 'sync_status_dir', tmp_path / 'public')
    def write(path, payload, **kwargs):
        if path.parent.name == 'public' and payload.get('finished_at'):
            raise PermissionError('synthetic')
        return atomic_json(path, payload, **kwargs)
    monkeypatch.setattr(runner, 'atomic_json', write)
    async def trading(session):
        return StepResult('Trading 212', 'ok')
    monkeypatch.setattr(runner, '_trading212_step', trading)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with async_sessionmaker(engine)() as session:
            report = await runner.run_sync_all(session, inbox=tmp_path)
        assert report.outcome == 'partial'
        assert json.loads((tmp_path / 'last-sync.json').read_text())['outcome'] == 'partial'
    finally:
        await engine.dispose()


async def test_empty_inbox_is_not_verified_unchanged(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.sync_runner import run_sync_all
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with async_sessionmaker(engine)() as session:
            report = await run_sync_all(session, inbox=tmp_path, include_trading212=False)
        assert report.to_json()['outcome'] == 'no_op'
        assert report.steps[0].status == 'no_op'
    finally:
        await engine.dispose()
