#!/usr/bin/env bash
set -euo pipefail

cd /app || exit 1

service="${1:-backend}"
shift || true

# Expose the UI port by default so compose/Podman can bind it from outside the container.
export HEALTH_UI_HOST="${HEALTH_UI_HOST:-0.0.0.0}"
export HEALTH_UI_PORT="${HEALTH_UI_PORT:-8080}"

case "$service" in
  backend)
    exec ./scripts/start_backend.sh "$@"
    ;;
  scheduler)
    exec ./scripts/run_health_scheduler.py "$@"
    ;;
  *)
    exec "$service" "$@"
    ;;
esac
