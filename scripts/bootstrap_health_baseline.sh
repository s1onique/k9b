#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"

usage() {
  cat <<'EOF'
Usage:
  bootstrap_health_baseline.sh --context <kube-context> [options]

Required:
  --context CONTEXT               Kubernetes context to snapshot and use as baseline source

Optional:
  --output PATH                   Baseline output path
                                  default: runs/health-baseline.local.json
  --snapshot-out PATH             Snapshot artifact path
                                  default: snapshots/baseline-source.json
  --min-version VERSION           Override min Kubernetes version
  --max-version VERSION           Override max Kubernetes version
  --watch-release NS/NAME         Include only this Helm release (repeatable)
  --crd-family FAMILY             Include only this CRD family (repeatable)
  --include-all-releases          Include every Helm release found in the snapshot
  --include-all-crd-families      Include every CRD family found in the snapshot
  --expected-drift CSV            expected_drift list, comma-separated
                                  default: watched_helm_release
  --ignored-drift CSV             ignored_drift list, comma-separated
                                  default: missing_evidence
  --why TEXT                      Override generic baseline rationale text prefix
  -h, --help                      Show help

Examples:
  scripts/bootstrap_health_baseline.sh \
    --context my-prod-cluster \
    --output runs/health-baseline.local.json \
    --snapshot-out snapshots/baseline-source.json \
    --watch-release kube-system/observability \
    --watch-release platform/cluster-ops \
    --crd-family monitoring.coreos.com \
    --crd-family cert-manager.io \
    --min-version v1.29.0 \
    --max-version v1.29.99

  scripts/bootstrap_health_baseline.sh \
    --context my-prod-cluster \
    --include-all-releases \
    --include-all-crd-families
EOF
}

CONTEXT=""
OUTPUT_PATH="runs/health-baseline.local.json"
SNAPSHOT_OUT="snapshots/baseline-source.json"
MIN_VERSION=""
MAX_VERSION=""
INCLUDE_ALL_RELEASES=0
INCLUDE_ALL_CRD_FAMILIES=0
EXPECTED_DRIFT="watched_helm_release"
IGNORED_DRIFT="missing_evidence"
WHY_PREFIX="Bootstrapped from a known-good reference cluster snapshot"
declare -a WATCH_RELEASES=()
declare -a CRD_FAMILIES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --context)
      CONTEXT="$2"
      shift 2
      ;;
    --output)
      OUTPUT_PATH="$2"
      shift 2
      ;;
    --snapshot-out)
      SNAPSHOT_OUT="$2"
      shift 2
      ;;
    --min-version)
      MIN_VERSION="$2"
      shift 2
      ;;
    --max-version)
      MAX_VERSION="$2"
      shift 2
      ;;
    --watch-release)
      WATCH_RELEASES+=("$2")
      shift 2
      ;;
    --crd-family)
      CRD_FAMILIES+=("$2")
      shift 2
      ;;
    --include-all-releases)
      INCLUDE_ALL_RELEASES=1
      shift
      ;;
    --include-all-crd-families)
      INCLUDE_ALL_CRD_FAMILIES=1
      shift
      ;;
    --expected-drift)
      EXPECTED_DRIFT="$2"
      shift 2
      ;;
    --ignored-drift)
      IGNORED_DRIFT="$2"
      shift 2
      ;;
    --why)
      WHY_PREFIX="$2"
      shift 2
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

if [[ -z "$CONTEXT" ]]; then
  echo "Error: --context is required" >&2
  usage >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Error: expected interpreter at $PYTHON" >&2
  echo "Create the project venv first." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")" "$(dirname "$SNAPSHOT_OUT")"

echo "Collecting snapshot from context..."
"$PYTHON" -m k8s_diag_agent.cli snapshot --context "$CONTEXT" --output "$SNAPSHOT_OUT"

WATCH_RELEASES_JSON="$("$PYTHON" - <<'PY' "${WATCH_RELEASES[@]}"
import json, sys
print(json.dumps(sys.argv[1:]))
PY
)"

CRD_FAMILIES_JSON="$("$PYTHON" - <<'PY' "${CRD_FAMILIES[@]}"
import json, sys
print(json.dumps(sys.argv[1:]))
PY
)"

"$PYTHON" - <<'PY' \
  "$SNAPSHOT_OUT" \
  "$OUTPUT_PATH" \
  "$MIN_VERSION" \
  "$MAX_VERSION" \
  "$INCLUDE_ALL_RELEASES" \
  "$INCLUDE_ALL_CRD_FAMILIES" \
  "$EXPECTED_DRIFT" \
  "$IGNORED_DRIFT" \
  "$WHY_PREFIX" \
  "$WATCH_RELEASES_JSON" \
  "$CRD_FAMILIES_JSON"
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

snapshot_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
min_version_arg = sys.argv[3].strip()
max_version_arg = sys.argv[4].strip()
include_all_releases = sys.argv[5] == "1"
include_all_crd_families = sys.argv[6] == "1"
expected_drift_csv = sys.argv[7].strip()
ignored_drift_csv = sys.argv[8].strip()
why_prefix = sys.argv[9].strip()
watch_releases = set(json.loads(sys.argv[10]))
crd_families_requested = set(json.loads(sys.argv[11]))

data = json.loads(snapshot_path.read_text(encoding="utf-8"))
metadata = data.get("metadata", {})
control_plane_version = str(metadata.get("control_plane_version") or "unknown")

helm_releases_raw = data.get("helm_releases") or []
crds_raw = data.get("crds") or []

def csv_to_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]

def crd_name_to_family(name: str) -> str | None:
    parts = name.split(".")
    if len(parts) < 2:
        return None
    return ".".join(parts[1:])

selected_releases: list[dict[str, Any]] = []
for item in helm_releases_raw:
    if not isinstance(item, dict):
        continue
    release_key = f"{item.get('namespace', 'default')}/{item.get('name', '')}".strip("/")
    if watch_releases:
        if release_key not in watch_releases:
            continue
    elif not include_all_releases:
        continue
    chart_version = str(item.get("chart_version") or "unknown")
    selected_releases.append(
        {
            "release": release_key,
            "allowed_versions": [chart_version],
            "why": f"{why_prefix}: release {release_key} currently runs chart version {chart_version}.",
            "next_check": f"Reconcile Helm drift for {release_key} only after confirming the intended chart version in platform manifests.",
        }
    )

families_found: dict[str, dict[str, Any]] = {}
for item in crds_raw:
    if not isinstance(item, dict):
        continue
    name = str(item.get("name") or "")
    family = crd_name_to_family(name)
    if not family:
        continue
    if crd_families_requested:
        if family not in crd_families_requested:
            continue
    elif not include_all_crd_families:
        continue
    if family in families_found:
        continue
    storage_version = item.get("storage_version")
    served_versions = item.get("served_versions") or []
    version_hint = str(storage_version or ",".join(str(v) for v in served_versions) or "unknown")
    families_found[family] = {
        "family": family,
        "why": f"{why_prefix}: CRD family {family} is present on the reference cluster (versions: {version_hint}).",
        "next_check": f"Confirm CRD family {family} remains served and storage-compatible across intended peer clusters.",
    }

min_version = min_version_arg or control_plane_version
max_version = max_version_arg or control_plane_version

baseline = {
    "control_plane_version_range": {
        "min_version": min_version,
        "max_version": max_version,
        "why": f"{why_prefix}: reference control plane version is {control_plane_version}. Widen this window manually if you support upgrade skew.",
        "next_check": "Review supported Kubernetes upgrade skew and widen the allowed window before enforcing across the fleet.",
    },
    "watched_releases": selected_releases,
    "required_crd_families": sorted(families_found.values(), key=lambda item: item["family"]),
    "expected_drift": csv_to_list(expected_drift_csv),
    "ignored_drift": csv_to_list(ignored_drift_csv),
    "peer_roles": {},
}

output_path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")

print(f"Baseline written to {output_path}")
print(f"Reference control plane version: {control_plane_version}")
print(f"Watched releases captured: {len(selected_releases)}")
print(f"CRD families captured: {len(families_found)}")
if min_version == max_version == control_plane_version:
    print("Note: min/max version were set to the exact current cluster version; widen manually if needed.")
PY

echo
echo "Next:"
echo "1. Review $OUTPUT_PATH"
echo "2. Prune noisy releases / CRD families"
echo "3. Point runs/health-config.local.json at this baseline"
echo "4. Run one health loop iteration"
