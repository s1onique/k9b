#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
SRC_PATH="$ROOT/src"
export PYTHONPATH="$SRC_PATH:$PYTHONPATH"

RUNS_DIR="runs/health"
CONFIG_PATH="runs/health-config.local.json"
BASELINE_FALLBACK="runs/health-baseline.json"
RUN_ID=""
OUTPUT_PATH=""
INCLUDE_FULL_JSON=0

usage() {
  cat <<'USAGE'
Usage: make_health_digest.sh [options]

Create an LLM-friendly markdown digest from health-loop artifacts.

Options:
  --run-id ID              Use a specific run_id. If omitted, infer latest from assessments.
  --runs-dir PATH          Health runs directory (default: runs/health)
  --config PATH            Local health config path (default: runs/health-config.local.json)
  --output PATH            Write digest to file instead of stdout
  --include-full-json      Append compact JSON excerpts for each artifact
  -h, --help               Show this help
USAGE
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --run-id)
        RUN_ID="$2"
        shift 2
        ;;
      --runs-dir)
        RUNS_DIR="$2"
        shift 2
        ;;
      --config)
        CONFIG_PATH="$2"
        shift 2
        ;;
      --output)
        OUTPUT_PATH="$2"
        shift 2
        ;;
      --include-full-json)
        INCLUDE_FULL_JSON=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
}

infer_latest_run_id() {
  local assessments_dir="$RUNS_DIR/assessments"
  "$PYTHON" - "$assessments_dir" <<'PY'
import os, re, sys
root = sys.argv[1]
if not os.path.isdir(root):
    print("")
    raise SystemExit(0)
run_ids = set()
for name in os.listdir(root):
    if not name.endswith('.json'):
        continue
    m = re.match(r'(.+-\d{8}T\d{6}Z)-[^/]+\.json$', name)
    if m:
        run_ids.add(m.group(1))
print(sorted(run_ids)[-1] if run_ids else "")
PY
}

require_cmd "$PYTHON"
parse_args "$@"

if [[ -z "$RUN_ID" ]]; then
  RUN_ID="$(infer_latest_run_id)"
fi

if [[ -z "$RUN_ID" ]]; then
  echo "Unable to infer run_id. Pass --run-id explicitly." >&2
  exit 1
fi

TMP_OUT="$(mktemp)"
trap 'rm -f "$TMP_OUT"' EXIT

"$PYTHON" - "$ROOT" "$RUNS_DIR" "$CONFIG_PATH" "$BASELINE_FALLBACK" "$RUN_ID" "$INCLUDE_FULL_JSON" > "$TMP_OUT" <<'PY'
from __future__ import annotations
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

root = Path(sys.argv[1])
runs_dir = Path(sys.argv[2])
config_path = Path(sys.argv[3])
baseline_fallback = Path(sys.argv[4])
run_id = sys.argv[5]
include_full_json = sys.argv[6] == "1"

src_path = root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from k8s_diag_agent.security import sanitize_payload


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def code(text: str) -> str:
    return f"`{text}`"


def bullets(items: list[str], indent: str = "- ") -> str:
    if not items:
        return f"{indent[:-2]}none" if indent.endswith("- ") else "none"
    return "\n".join(f"{indent}{item}" for item in items)


def compact(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return str(obj)


def artifact_paths(kind: str) -> list[Path]:
    return sorted(Path(p) for p in glob.glob(str(runs_dir / kind / f"{run_id}-*.json")))

config = load_json(config_path) if config_path.exists() else None
baseline_path_value = ""
if isinstance(config, dict):
    baseline_path_value = str(config.get("baseline_policy_path") or "")
if baseline_path_value:
    baseline_path = Path(baseline_path_value)
    if not baseline_path.is_absolute():
        baseline_path = config_path.parent / baseline_path
else:
    baseline_path = baseline_fallback
baseline = load_json(baseline_path) if baseline_path.exists() else None

assessments = [(p, load_json(p)) for p in artifact_paths("assessments")]
drilldowns = [(p, load_json(p)) for p in artifact_paths("drilldowns")]
triggers = [(p, load_json(p)) for p in artifact_paths("triggers")]
comparisons = [(p, load_json(p)) for p in artifact_paths("comparisons")]
history_path = runs_dir / "history.json"
history = load_json(history_path) if history_path.exists() else None

safe_config: Mapping[str, Any] = sanitize_payload(config) if isinstance(config, Mapping) else {}
safe_baseline: Mapping[str, Any] = sanitize_payload(baseline) if isinstance(baseline, Mapping) else {}
safe_history: Mapping[str, Any] = sanitize_payload(history) if isinstance(history, Mapping) else {}

out: list[str] = []
out.append("# Health Loop Digest")
out.append("")
out.append(f"- run_id: {code(run_id)}")
out.append(f"- generated_at_utc: {code(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))}")
out.append(f"- runs_dir: {code(str(runs_dir))}")
out.append("")
out.append("## Operator Task")
out.append("")
out.extend([
    "Review this health-loop run and answer:",
    "1. Which clusters look unhealthy or suspicious?",
    "2. What evidence supports that assessment?",
    "3. What are the top grounded hypotheses per affected cluster?",
    "4. What next low-risk checks should the operator run?",
    "5. Which triggers/noise should be tuned in config or baseline policy?",
])
out.append("")

out.append("## Config Summary")
out.append("")
if isinstance(config, dict):
    config_values = safe_config
    out.append(
        f"- run_label: {code(str(config_values.get('run_label') or config_values.get('run_id') or 'unknown'))}"
    )
    out.append(f"- collector_version: {code(str(config_values.get('collector_version') or 'unknown'))}")
    out.append(f"- output_dir: {code(str(config_values.get('output_dir') or 'runs'))}")
    targets = config_values.get("targets") if isinstance(config_values.get("targets"), list) else []
    out.append("- targets:")
    if targets:
        for t in targets:
            if isinstance(t, dict):
                out.append(
                    f"  - label={t.get('label','?')} context={t.get('context','?')} monitor_health={t.get('monitor_health', True)}"
                )
    else:
        out.append("  - none")
    triggers_cfg = config_values.get("comparison_triggers") if isinstance(config_values.get("comparison_triggers"), dict) else {}
    out.append("- comparison_triggers:")
    if triggers_cfg:
        for k, v in triggers_cfg.items():
            out.append(f"  - {k}={v}")
    else:
        out.append("  - none")
    manual_pairs = config_values.get("manual_pairs") if isinstance(config_values.get("manual_pairs"), list) else []
    out.append("- manual_pairs:")
    if manual_pairs:
        for pair in manual_pairs:
            if isinstance(pair, dict):
                out.append(f"  - {pair.get('primary','?')} -> {pair.get('secondary','?')}")
    else:
        out.append("  - none")
    out.append(f"- baseline_policy_path: {code(str(baseline_path))}")
else:
    out.append(f"- config file not found or invalid: {code(str(config_path))}")
out.append("")

out.append("## Baseline Summary")
out.append("")
if isinstance(baseline, dict):
    baseline_values = safe_baseline
    cvr = baseline_values.get("control_plane_version_range") if isinstance(
        baseline_values.get("control_plane_version_range"), dict
    ) else {}
    out.append(
        f"- control_plane_version_range: {code(str(cvr.get('min_version','?')))} .. {code(str(cvr.get('max_version','?')))}"
    )
    watched = baseline_values.get("watched_releases") if isinstance(
        baseline_values.get("watched_releases"), list
    ) else []
    out.append("- watched_releases:")
    if watched:
        for item in watched:
            if isinstance(item, dict):
                allowed = item.get("allowed_versions") if isinstance(item.get("allowed_versions"), list) else []
                out.append(f"  - {item.get('release','?')} allowed={','.join(map(str, allowed))}")
    else:
        out.append("  - none")
    crds = baseline_values.get("required_crd_families") if isinstance(
        baseline_values.get("required_crd_families"), list
    ) else []
    out.append("- required_crd_families:")
    if crds:
        for item in crds:
            if isinstance(item, dict):
                out.append(f"  - {item.get('family','?')}")
    else:
        out.append("  - none")
    ignored = baseline_values.get("ignored_drift") if isinstance(
        baseline_values.get("ignored_drift"), list
    ) else []
    out.append(f"- ignored_drift: {', '.join(map(str, ignored)) if ignored else 'none'}")
else:
    out.append(f"- baseline file not found or invalid: {code(str(baseline_path))}")
out.append("")

out.append("## Assessment Summary")
out.append("")
if not assessments:
    out.append("No assessment artifacts found for this run.")
else:
    for path, data in assessments:
        out.append(f"### {path.name}")
        if not isinstance(data, dict):
            out.append("- invalid JSON")
            out.append("")
            continue
        safe_data = sanitize_payload(data)
        assessment = safe_data.get("assessment") if isinstance(safe_data.get("assessment"), dict) else {}
        findings = assessment.get("findings") if isinstance(assessment.get("findings"), list) else []
        hypotheses = assessment.get("hypotheses") if isinstance(assessment.get("hypotheses"), list) else []
        out.append(
            f"- cluster_label: {code(str(safe_data.get('cluster_label') or safe_data.get('label') or safe_data.get('cluster') or 'unknown'))}"
        )
        out.append(f"- run_label: {code(str(safe_data.get('run_label') or 'unknown'))}")
        out.append(f"- run_id: {code(str(safe_data.get('run_id') or 'unknown'))}")
        out.append(f"- snapshot_path: {code(str(safe_data.get('snapshot_path') or ''))}")
        out.append(f"- findings_count: {len(findings)}")
        out.append(f"- hypotheses_count: {len(hypotheses)}")
        out.append(f"- overall_confidence: {code(str(assessment.get('overall_confidence') or ''))}")
        out.append(f"- safety_level: {code(str(assessment.get('safety_level') or ''))}")
        out.append("- top_findings:")
        if findings:
            for f in findings[:10]:
                if isinstance(f, dict):
                    out.append(f"  - {f.get('description') or f.get('text') or ''}")
                else:
                    out.append(f"  - {f}")
        else:
            out.append("  - none")
        out.append("- top_hypotheses:")
        if hypotheses:
            for h in hypotheses[:10]:
                if isinstance(h, dict):
                    out.append(f"  - [{h.get('confidence','?')}] {h.get('description') or ''}")
                else:
                    out.append(f"  - {h}")
        else:
            out.append("  - none")
        ra = assessment.get("recommended_action") if isinstance(
            assessment.get("recommended_action"), dict
        ) else {}
        out.append(f"- recommended_action: {ra.get('description') or ra.get('type') or ''}")
        out.append("")
        if include_full_json:
            out.append("```json")
            out.append(compact(sanitize_payload(data)))
            out.append("```")
            out.append("")

out.append("## Drilldown Summary")
out.append("")
if not drilldowns:
    out.append("No drilldown artifacts found for this run.")
else:
    for path, data in drilldowns:
        out.append(f"### {path.name}")
        if not isinstance(data, dict):
            out.append("- invalid JSON")
            out.append("")
            continue
        safe_data = sanitize_payload(data)
        reasons = safe_data.get("trigger_reasons") if isinstance(safe_data.get("trigger_reasons"), list) else []
        affected_ns = safe_data.get("affected_namespaces") if isinstance(safe_data.get("affected_namespaces"), list) else []
        affected_wl = safe_data.get("affected_workloads") if isinstance(safe_data.get("affected_workloads"), list) else []
        warning_events = safe_data.get("warning_events") if isinstance(safe_data.get("warning_events"), list) else []
        non_running = safe_data.get("non_running_pods") if isinstance(safe_data.get("non_running_pods"), list) else []
        pod_desc = safe_data.get("pod_descriptions") if isinstance(safe_data.get("pod_descriptions"), list) else []
        rollout = safe_data.get("rollout_status") if isinstance(safe_data.get("rollout_status"), list) else []
        missing = safe_data.get("missing_evidence") if isinstance(safe_data.get("missing_evidence"), list) else []
        out.append(f"- cluster_label: {code(str(safe_data.get('cluster_label') or safe_data.get('label') or 'unknown'))}")
        out.append("- trigger_reasons:")
        if reasons:
            for r in reasons:
                out.append(f"  - {r}")
        else:
            out.append("  - none")
        out.append(f"- affected_namespaces: {', '.join(map(str, affected_ns)) if affected_ns else ''}")
        out.append(f"- affected_workloads: {', '.join(map(str, affected_wl)) if affected_wl else ''}")
        out.append(f"- warning_events_count: {len(warning_events)}")
        out.append(f"- non_running_pods_count: {len(non_running)}")
        out.append(f"- pod_descriptions_count: {len(pod_desc)}")
        out.append(f"- rollout_status_count: {len(rollout)}")
        out.append(f"- missing_evidence: {', '.join(map(str, missing)) if missing else ''}")
        out.append("")
        if include_full_json:
            out.append("```json")
            out.append(compact(sanitize_payload(data)))
            out.append("```")
            out.append("")

out.append("## Trigger Artifacts")
out.append("")
if not triggers:
    out.append("No trigger artifacts found for this run.")
else:
    for path, data in triggers:
        out.append(f"### {path.name}")
        safe_data = sanitize_payload(data)
        if isinstance(safe_data, Mapping):
            for k, v in safe_data.items():
                out.append(f"- {k}: {compact(v)}")
        else:
            out.append(f"- invalid JSON: {compact(safe_data)}")
        out.append("")

out.append("## Comparison Artifacts")
out.append("")
if not comparisons:
    out.append("No comparison artifacts found for this run.")
else:
    for path, data in comparisons:
        out.append(f"### {path.name}")
        safe_data = sanitize_payload(data)
        if isinstance(safe_data, Mapping):
            for k, v in safe_data.items():
                out.append(f"- {k}: {compact(v)}")
        else:
            out.append(f"- invalid JSON: {compact(safe_data)}")
        out.append("")

out.append("## Health History Excerpt")
out.append("")
if isinstance(history, dict):
    for key, value in safe_history.items():
        out.append(f"### {key}")
        if isinstance(value, Mapping):
            for k, v in value.items():
                out.append(f"- {k}: {compact(v)}")
        else:
            out.append(f"- {compact(value)}")
        out.append("")
else:
    out.append(f"No history file found or invalid at {code(str(history_path))}.")
    out.append("")

out.append("## Questions For The LLM")
out.append("")
out.extend([
    "Please review this run and answer in a structured way:",
    "1. Which clusters look unhealthy, suspicious, or noisy?",
    "2. Which findings are most strongly supported by evidence versus weakly supported?",
    "3. For each suspicious cluster, what are the top grounded hypotheses?",
    "4. What low-risk next checks should the operator run next?",
    "5. Which triggers, thresholds, watched Helm releases, or baseline expectations should be tuned?",
    "6. Which parts of the output look like noise versus genuine operator value?",
])

print("\n".join(out))
PY

if [[ -n "$OUTPUT_PATH" ]]; then
  mkdir -p "$(dirname "$OUTPUT_PATH")"
  cp "$TMP_OUT" "$OUTPUT_PATH"
  echo "Digest written to $OUTPUT_PATH"
else
  cat "$TMP_OUT"
fi
