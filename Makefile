.PHONY: lint format typecheck check

lint:
	.venv/bin/ruff check backend/

format:
	.venv/bin/ruff format backend/

typecheck:
	.venv/bin/mypy backend/app/ backend/alembic/

check: lint format typecheck
	.venv/bin/ruff format --check backend/

.PHONY: sync sync-dry
sync:
	PYTHONPATH=backend .venv/bin/python -m app.sync_cli $(ARGS)

sync-dry:
	PYTHONPATH=backend .venv/bin/python -m app.sync_cli --include-downloads --dry-run

# Default development feedback is deliberately a subset, not release acceptance.
PYTHON ?= .venv/bin/python
TEST_JOBS ?= 2
TEST_TIMINGS ?=
FAST_BACKEND_TESTS = \
	backend/tests/test_trading212.py \
	backend/tests/test_trading212_cash.py \
	backend/tests/test_trading212_api_compatibility.py \
	backend/tests/test_trading212_transactions.py \
	backend/tests/test_cash_flow_integration.py \
	backend/tests/test_portfolio_returns.py \
	backend/tests/test_gate_a_trading212.py
.PHONY: test test-fast test-backend-fast test-frontend-fast test-full test-backend test-frontend

test-backend-fast:
	$(PYTHON) scripts/test_t212_synthetic.py $(FAST_BACKEND_TESTS) -q

test-frontend-fast:
	npm --prefix frontend run test:fast

test-fast:
	@printf '%s\n' 'FAST DEVELOPMENT SUBSET: full browser/security/migration coverage requires make test-full.'
	$(MAKE) --no-print-directory -j2 test-backend-fast test-frontend-fast

test: test-fast

test-backend:
	$(PYTHON) scripts/test_backend.py --jobs=$(TEST_JOBS) $(if $(TEST_TIMINGS),--timings="$(TEST_TIMINGS)")

test-frontend:
	npm --prefix frontend run test:run

test-full:
	$(MAKE) --no-print-directory -j2 test-backend test-frontend
