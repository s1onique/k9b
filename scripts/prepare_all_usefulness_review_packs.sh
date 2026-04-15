#!/usr/bin/env bash
set -Eeuo pipefail

RUNS_DIR="${1:-runs}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
EXPORT_SCRIPT="${EXPORT_SCRIPT:-scripts/export_next_check_usefulness_review.py}"

if [[ ! -d "$RUNS_DIR" ]]; then
  echo "ERROR: runs dir not found: $RUNS_DIR" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" && ! -f "$PYTHON_BIN" ]]; then
  echo "ERROR: python not found: $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -f "$EXPORT_SCRIPT" ]]; then
  echo "ERROR: export script not found: $EXPORT_SCRIPT" >&2
  exit 1
fi

EXTERNAL_ANALYSIS_DIR="$RUNS_DIR/health/external-analysis"
if [[ ! -d "$EXTERNAL_ANALYSIS_DIR" ]]; then
  echo "ERROR: external-analysis dir not found: $EXTERNAL_ANALYSIS_DIR" >&2
  exit 1
fi

tmp_runs="$(mktemp)"
tmp_ok="$(mktemp)"
tmp_fail="$(mktemp)"
cleanup() {
  rm -f "$tmp_runs" "$tmp_ok" "$tmp_fail"
}
trap cleanup EXIT

find "$EXTERNAL_ANALYSIS_DIR" -maxdepth 1 -type f -name '*-next-check-execution-*.json' \
  | sed -E 's#^.*/(.*)-next-check-execution-[0-9]+\.json#\1#' \
  | sort -u > "$tmp_runs"

total_runs="$(wc -l < "$tmp_runs" | tr -d ' ')"
echo "Discovered $total_runs run(s) with next-check execution artifacts."

if [[ "$total_runs" -eq 0 ]]; then
  echo "Nothing to export."
  exit 0
fi

while IFS= read -r run_id; do
  [[ -z "$run_id" ]] && continue

  out_path="$RUNS_DIR/health/diagnostic-packs/$run_id/next_check_usefulness_review.json"
  echo
  echo "==> Exporting $run_id"

  if "$PYTHON_BIN" "$EXPORT_SCRIPT" --runs-dir "$RUNS_DIR" --run-id "$run_id"; then
    if [[ -f "$out_path" ]]; then
      entry_count="$(
        jq -r '(.entries | length) // 0' "$out_path" 2>/dev/null || echo "unknown"
      )"
      echo "$run_id|$out_path|$entry_count" >> "$tmp_ok"
      echo "OK: $out_path (entries=$entry_count)"
    else
      echo "$run_id|missing_output" >> "$tmp_fail"
      echo "FAIL: exporter returned success but output file is missing: $out_path" >&2
    fi
  else
    echo "$run_id|export_failed" >> "$tmp_fail"
    echo "FAIL: export command failed for $run_id" >&2
  fi
done < "$tmp_runs"

ok_count="$(wc -l < "$tmp_ok" | tr -d ' ')"
fail_count="$(wc -l < "$tmp_fail" | tr -d ' ')"

echo
echo "===== SUMMARY ====="
echo "Successful exports: $ok_count"
echo "Failed exports:     $fail_count"

if [[ "$ok_count" -gt 0 ]]; then
  echo
  echo "Generated review packs:"
  awk -F'|' '{printf "- %s -> %s (entries=%s)\n", $1, $2, $3}' "$tmp_ok"
fi

if [[ "$fail_count" -gt 0 ]]; then
  echo
  echo "Failures:"
  awk -F'|' '{printf "- %s [%s]\n", $1, $2}' "$tmp_fail" >&2
  exit 2
fi
