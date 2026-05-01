#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT/frontend"

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is not available in PATH" >&2
  exit 1
fi

cd "$FRONTEND_DIR"

# Compute package-lock.json hash for sentinel
LOCK_HASH=""
if command -v sha256sum >/dev/null 2>&1; then
  LOCK_HASH="$(sha256sum package-lock.json | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  LOCK_HASH="$(shasum -a 256 package-lock.json | awk '{print $1}')"
else
  echo "Error: Neither sha256sum nor shasum is available" >&2
  exit 1
fi

SENTINEL_FILE="node_modules/.package-lock.sha256"

# Check if we need to run npm ci
if [ ! -d node_modules ] || [ ! -f "$SENTINEL_FILE" ] || [ "$(cat "$SENTINEL_FILE" 2>/dev/null)" != "$LOCK_HASH" ]; then
  echo "Installing frontend dependencies via npm ci"
  npm ci
  mkdir -p node_modules
  echo "$LOCK_HASH" > "$SENTINEL_FILE"
else
  echo "Frontend dependencies already match package-lock.json; skipping npm ci"
fi

FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

echo "Starting Vite dev server on $FRONTEND_HOST:$FRONTEND_PORT"
exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
