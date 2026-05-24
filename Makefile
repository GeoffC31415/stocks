.PHONY: lint format typecheck check

lint:
	.venv/bin/ruff check backend/

format:
	.venv/bin/ruff format backend/

typecheck:
	.venv/bin/mypy backend/app/ backend/alembic/

check: lint format typecheck
	.venv/bin/ruff format --check backend/
