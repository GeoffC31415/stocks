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
