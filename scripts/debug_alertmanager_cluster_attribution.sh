#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${1:?usage: $0 <run_id>}"
RUNS_DIR="${2:-runs/health}"
API="${3:-http://localhost:8080}"

echo "== API compact + source =="
curl -s "$API/api/run?run_id=$RUN_ID" | jq '{
  runId,
  compact: .alertmanagerCompact,
  sources: .alertmanagerSources.sources
}'

echo
echo "== Snapshot source provenance =="
jq '{status, captured_at, source}' "$RUNS_DIR/${RUN_ID}-alertmanager-snapshot.json"

echo
echo "== Compact attribution =="
jq '{status, alert_count, state_counts, affected_clusters, by_cluster, source}' \
  "$RUNS_DIR/${RUN_ID}-alertmanager-compact.json"

echo
echo "== Snapshot sample alerts =="
jq '{
  alert_count,
  active_count: ([.alerts[] | select(.state=="active")] | length),
  sample: [.alerts[] | {alertname, state, namespace, service}][0:10]
}' "$RUNS_DIR/${RUN_ID}-alertmanager-snapshot.json"

echo
echo "== ui-index matching objects =="
jq --arg run "$RUN_ID" '.. | objects | select(.runId? == $run or .run_id? == $run)' \
  "$RUNS_DIR/ui-index.json"
