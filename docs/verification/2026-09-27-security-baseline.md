# Security implementation baseline

Clean worktree at 77160ef876db6bce8317d227e46678e7b1fe45cf, Surface, before merging any implementation.

## Backend

Executed full backend/tests using existing development Python3.11 interpreter/dependencies read-only, PYTHONDONTWRITEBYTECODE=1, database override sqlite+aiosqlite:///:memory:, BaseSettings dotenv disabled before app import, pytest cache disabled. Result: 826 passed, 7 failed, 1 warning (76.98s).

Failures:
- test_hl_parser::test_parse_hl_holdings_csv_bytes: absent private data/HL-Summary.csv.
- test_hl_parser::test_parse_hl_activity_csv_bytes_skips_cash_events: absent private data/hl-portfolio-summary.csv.
- test_portfolio_returns::test_portfolio_return_endpoint_is_registered_with_response_schema: route enumeration StopIteration.
- test_snapshot_attribution::test_snapshot_attribution_endpoint_is_registered_with_response_schema: route enumeration StopIteration.
- test_surface_installer::test_check_finds_uv_outside_normal_terminal_path: installed stocks.service correctly causes first-install refusal.
- test_surface_installer::test_check_is_read_only_with_real_synthetic_database: installed stocks.service correctly causes first-install refusal.
- test_ui_rehearsal::test_rehearsal_uses_its_own_read_only_database_and_blocks_writes: FastAPI _IncludedRouter lacks path.

JUnit evidence /tmp/stocks-security-backend-baseline.xml. No fabricated private fixtures. No live database used.

## Frontend

npm ci --ignore-scripts --silent; npm run typecheck passed. npm test -- --run --reporter=dot: 188 passed, 2 failed; 57 files passed, 2 failed (51.83s). Existing Recharts dimension and table whitespace warnings.

Failures:
- AllocationDonut::uses invested value in the centre instead of repeating a technical HHI headline: expected £10k, received £10.0k.
- formatters::uses compact axes including millions and explicit signed outcomes: expected £250k, received £250.0k.

These are recorded baseline failures, not a clean-suite claim or permission to ignore new failures. Re-run on candidate and compare exact test identities; dependency/runtime differences may affect the result.
