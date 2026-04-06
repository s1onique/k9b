#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT/frontend"

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is not available in PATH" >&2
  exit 1
fi

cd "$FRONTEND_DIR"

if [[ ! -d "node_modules" ]]; then
  echo "Installing frontend dependencies via npm ci"
  npm ci
fi

FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

echo "Starting Vite dev server on $FRONTEND_HOST:$FRONTEND_PORT"
exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
