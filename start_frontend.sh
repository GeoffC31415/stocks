#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"

if [[ ! -d "${FRONTEND_DIR}" ]]; then
  echo "Frontend directory not found: ${FRONTEND_DIR}" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but not installed." >&2
  exit 1
fi

cd "${FRONTEND_DIR}"
if [[ ! -d "node_modules" ]]; then
  echo "node_modules not found. Installing dependencies..."
  npm install
fi

exec npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT:-5173}"
