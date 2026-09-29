"""Serialize explicit synthetic input through the real backend public v2 boundary.

Run from the repo root with the shared backend venv. Never reads worker state,
credentials, auth stores or a database. stdout is the committed frontend fixture.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'backend'))
from app.services.sync_control import public_report

section = dict(last_attempt_at='2026-09-29T18:29:00Z',
               verified_at='2026-09-01T18:30:00Z', valuation_at='2026-09-01',
               coverage='partial', status='failed', reason_code='provider_failed',
               action_code='retry')
report = public_report(dict(started_at='2026-09-29T18:29:00Z',
                            finished_at='2026-09-29T18:30:00Z', ok=False,
                            outcome='partial', freshness={'Trading 212': {'holdings': section}},
                            steps=[dict(name='Trading 212', status='failed',
                                        sections={'holdings': section})], files=[]))
print(json.dumps(report, indent=2))
