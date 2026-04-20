#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${1:?usage: $0 <run_id>}"
RUNS_DIR="${2:-runs/health}"
API="${3:-http://localhost:8080}"

echo "== API compact + selected source =="
curl -s "$API/api/run?run_id=$RUN_ID" | jq '{
  runId,
  compact: .alertmanagerCompact,
  source: .alertmanagerSources.sources[0]
}'

echo
echo "== Snapshot source provenance =="
jq '{status, captured_at, source}' "$RUNS_DIR/${RUN_ID}-alertmanager-snapshot.json"

echo
echo "== Compact attribution =="
jq '{status, source, alert_count, state_counts, affected_clusters, by_cluster}' \
  "$RUNS_DIR/${RUN_ID}-alertmanager-compact.json"

echo
echo "== Snapshot sample alerts =="
jq '{
  alert_count,
  active_count: ([.alerts[] | select(.state=="active")] | length),
  sample: [.alerts[] | {alertname, state, namespace, service}][0:10]
}' "$RUNS_DIR/${RUN_ID}-alertmanager-snapshot.json"

echo
echo "== Backend code search =="
grep -Rni "by_cluster\\|affected_clusters\\|alertmanager-compact\\|snapshot-written\\|source" \
  src/k8s_diag_agent/external_analysis src/k8s_diag_agent/health src/k8s_diag_agent/ui | head -120 || true
