#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# --- Validate prerequisites ---

if [[ ! -d "${BACKEND_DIR}" ]]; then
  echo "ERROR: Backend directory not found: ${BACKEND_DIR}" >&2
  exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "ERROR: Virtualenv Python not found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required but not installed." >&2
  exit 1
fi

cd "${FRONTEND_DIR}"
if [[ ! -d "node_modules" ]]; then
  echo "Installing frontend dependencies..."
  npm install
fi

# --- Start backend in background ---

echo "Starting backend on http://0.0.0.0:${BACKEND_PORT} ..."
cd "${BACKEND_DIR}"
"${VENV_PYTHON}" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "${BACKEND_PORT}" &
BACKEND_PID=$!

# Give backend a moment to start
sleep 2

# --- Start frontend in foreground ---

echo "Starting frontend on http://0.0.0.0:${FRONTEND_PORT} ..."
cd "${FRONTEND_DIR}"
exec npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT}"
