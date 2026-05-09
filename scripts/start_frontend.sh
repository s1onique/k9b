#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT/frontend"

# Validate npm is available
if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is not available in PATH" >&2
  exit 1
fi

cd "$FRONTEND_DIR"

# Fail loudly if dependencies are missing (they should be baked into the image)
if [ ! -d node_modules ]; then
  echo "Error: node_modules not found." >&2
  echo "Dependencies are installed at image build time." >&2
  echo "Rebuild the frontend image and ensure compose does not bind-mount ./frontend over /app/frontend." >&2
  exit 1
fi

FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

echo "Starting Vite dev server on $FRONTEND_HOST:$FRONTEND_PORT"
exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
