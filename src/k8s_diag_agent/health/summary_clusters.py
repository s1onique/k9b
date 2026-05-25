"""Cluster health aggregation helpers for health summary building."""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id
from .utils import normalize_ref

logger = logging.getLogger(__name__)

_ASSESSMENT_PATTERN = re.compile(r"(?P<run_id>.+-\d{8}T\d{6}Z)-(?P<label>.+)-assessment\.json$")
_TIMESTAMP_LENGTH = 16  # YYYYMMDDTHHMMSSZ

# Constant suffix for assessment artifact glob pattern.
# REVIEWED: Fixed pattern, no user-controlled interpolation after run_id prefix.
_ASSESSMENT_SUFFIX = "-*-assessment.json"


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON file. Raises exceptions for caller to handle with logging."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return raw
    return {}


def _parse_assessment_filename(name: str) -> tuple[str, str] | None:
    match = _ASSESSMENT_PATTERN.match(name)
    if not match:
        return None
    return match.group("run_id"), match.group("label")


def _parse_run_timestamp(run_id: str) -> datetime | None:
    if len(run_id) < _TIMESTAMP_LENGTH:
        return None
    timestamp = run_id[-_TIMESTAMP_LENGTH:]
    try:
        return datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


def _discover_latest_run_id(assessments_dir: Path) -> str | None:
    if not assessments_dir.is_dir():
        return None
    candidates: dict[str, datetime] = {}
    for path in assessments_dir.iterdir():
        if not path.is_file():
            continue
        parsed = _parse_assessment_filename(path.name)
        if not parsed:
            continue
        run_id, _ = parsed
        timestamp = _parse_run_timestamp(run_id)
        if not timestamp:
            continue
        candidates[run_id] = max(timestamp, candidates.get(run_id, timestamp))
    if not candidates:
        return None
    latest = max(candidates.items(), key=lambda item: item[1])
    return latest[0]


def _load_history(history_path: Path) -> dict[str, Any]:
    if not history_path.exists():
        return {}
    try:
        raw = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _label_from_assessment_path(run_id: str, path: Path) -> str | None:
    name = path.name
    prefix = f"{run_id}-"
    suffix = "-assessment.json"
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None
    return name[len(prefix) : -len(suffix)]


def _lookup_history_field(history: Mapping[str, Any], label: str | None, *fields: str) -> Any | None:
    entry = _history_entry_for_label(history, label)
    if not isinstance(entry, dict):
        return None
    result: Any = entry
    for field in fields:
        if not isinstance(result, dict) or field not in result:
            return None
        result = result[field]
    return result


def _history_entry_for_label(history: Mapping[str, Any], label: str | None) -> dict[str, Any] | None:
    if not label:
        return None
    normalized = normalize_ref(label)
    for key, value in history.items():
        if normalize_ref(key) == normalized and isinstance(value, dict):
            return value
    return None


def _history_int(history: Mapping[str, Any], label: str | None, *fields: str) -> int | None:
    result = _lookup_history_field(history, label, *fields)
    if isinstance(result, int):
        return result
    if isinstance(result, str) and result.isdigit():
        return int(result)
    return None


def _history_list(history: Mapping[str, Any], label: str | None, field: str) -> tuple[str, ...] | None:
    entry = _history_entry_for_label(history, label)
    if not isinstance(entry, dict):
        return None
    raw = entry.get(field)
    if raw is not None and hasattr(raw, "__iter__") and not isinstance(raw, str):
        return tuple(str(item) for item in raw if item is not None)
    return None


def build_cluster_summaries(
    assessments_dir: Path, run_id: str, history: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Build cluster summary dictionaries from assessment files.

    This is the public entry point for cluster aggregation. Returns list of
    dicts with keys matching ClusterSummary field expectations.

    Args:
        assessments_dir: Directory containing assessment JSON files.
        run_id: Validated run identifier.
        history: Cluster history data mapping cluster labels to metadata.

    Returns:
        List of cluster summary dicts with keys:
            label, top_finding, findings_count, health_rating, warning_count,
            non_running_pods, missing_evidence, cluster_class, cluster_role,
            baseline_cohort, baseline_policy_path
    """
    summaries: list[dict[str, Any]] = []
    if not assessments_dir.is_dir():
        return summaries

    # Validate run_id before glob construction to prevent traversal/injection
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Return empty summaries on invalid run_id (safe fallback)
        return summaries

    # Use safe_run_artifact_glob for validated glob pattern construction
    glob_pattern = safe_run_artifact_glob(validated_run_id, _ASSESSMENT_SUFFIX)
    for path in sorted(assessments_dir.glob(glob_pattern)):
        label = _label_from_assessment_path(run_id, path)
        try:
            data = _load_json(path)
        except (OSError, json.JSONDecodeError):
            logger.warning("Skipped malformed assessment artifact: %s", path.name, exc_info=True)
            continue
        findings = data.get("findings") if isinstance(data, dict) else []
        top_finding = None
        if isinstance(findings, (list, tuple)) and findings:
            first = findings[0]
            if isinstance(first, dict):
                top_finding = first.get("description") or first.get("text")
            else:
                top_finding = str(first)
        summary_entry = {
            "label": label or "unknown",
            "top_finding": top_finding,
            "findings_count": len(findings) if isinstance(findings, (list, tuple)) else 0,
            "health_rating": _lookup_history_field(history, label, "health_rating"),
            "warning_count": _history_int(history, label, "warning_event_count"),
            "non_running_pods": _history_int(history, label, "pod_counts", "non_running"),
            "missing_evidence": _history_list(history, label, "missing_evidence"),
            "cluster_class": _lookup_history_field(history, label, "cluster_class"),
            "cluster_role": _lookup_history_field(history, label, "cluster_role"),
            "baseline_cohort": _lookup_history_field(history, label, "baseline_cohort"),
            "baseline_policy_path": _lookup_history_field(history, label, "baseline_policy_path"),
        }
        summaries.append(summary_entry)
    return summaries
