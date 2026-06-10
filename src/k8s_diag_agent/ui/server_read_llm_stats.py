"""LLM stats and review-enrichment helpers for the UI server.

This module extracts LLM stats computation and review-enrichment lookup helpers
from server_read_support.py to keep modules below 500 lines.

Extracted from: server_read_support.py
Kept for backward compatibility via re-exports in server_read_support.py.

Keep behavior unchanged: no logic changes, no response shape changes.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..security.deanonymization import deanonymize_review_enrichment
from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

logger = logging.getLogger(__name__)


def _find_review_enrichment(
    external_analysis_dir: Path, run_id: str, artifact_index: Any = None
) -> dict[str, object] | None:
    """Find and parse review enrichment artifact for a run.

    Uses artifact_index if provided for O(1) lookup, otherwise falls back
    to scanning the directory (for backward compatibility).

    Args:
        external_analysis_dir: Path to external-analysis directory (used if no index)
        run_id: The run ID to filter by
        artifact_index: Pre-built index for O(1) lookup (optional)

    Returns:
        Review enrichment data dict, or None if not found
    """
    # Use index for O(1) lookup if available
    if artifact_index is not None:
        artifacts: Sequence[dict[str, object]] = artifact_index.review_enrichment
    else:
        # Fall back to directory scan for backward compatibility
        if not external_analysis_dir.exists():
            return None

        # Validate run_id at function boundary for safe glob construction
        try:
            validated_run_id = validate_run_id(run_id)
        except SecurityError:
            # Invalid run_id - cannot safely search, return None
            return None

        _scan_artifacts: list[dict[str, object]] = []
        # SECURITY: run_id validated by validate_run_id() before glob construction
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-review-enrichment*.json")
        for artifact_file in sorted(external_analysis_dir.glob(glob_pattern)):
            try:
                artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                if isinstance(artifact_data, dict):
                    purpose = artifact_data.get("purpose")
                    if purpose == "review-enrichment":
                        artifact_data["artifact_path"] = str(artifact_file.relative_to(external_analysis_dir.parent))
                        _scan_artifacts.append(artifact_data)
            except (OSError, json.JSONDecodeError) as exc:
                from ..security import sanitize_exception_message
                sanitized_error = sanitize_exception_message(exc)
                logger.warning(
                    "Skipped malformed review-enrichment artifact: %s",
                    artifact_file.name,
                    extra={
                        "run_id": run_id,
                        "artifact_kind": "review-enrichment",
                        "scan_name": "_find_review_enrichment",
                        "error": sanitized_error,
                    },
                    exc_info=True,
                )
                continue
        artifacts = _scan_artifacts

    if not artifacts:
        return None

    # Take the first (sorted) matching artifact
    artifact_data = artifacts[0]

    raw_payload = artifact_data.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}

    def _list_from(*keys: str) -> list[str]:
        """Get a list from payload, checking multiple key variants."""
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [str(item) for item in value]
        return []

    # Get artifact path - use artifact_path if available, otherwise construct from index
    artifact_path = artifact_data.get("artifact_path")
    if not artifact_path and artifact_index is None:
        # Need to construct path from artifact data - not available without file scan
        artifact_path = None

    # Get alias mapping from artifact and apply de-anonymization for operator-facing UI
    # The alias_mapping is set by the llamacpp adapter when processing provider responses
    alias_mapping = artifact_data.get("alias_mapping")
    if isinstance(alias_mapping, dict) and alias_mapping:
        # Build the de-anonymized payload using the mapping
        # deanonymize_review_enrichment handles all text fields recursively
        deanon_payload = deanonymize_review_enrichment(dict(payload), alias_mapping)
        # Re-extract de-anonymized fields from the processed payload
        payload = deanon_payload

    return {
        "status": artifact_data.get("status", "unknown"),
        "provider": artifact_data.get("provider"),
        "timestamp": artifact_data.get("timestamp"),
        "summary": payload.get("summary") if isinstance(payload, dict) else artifact_data.get("summary"),
        # Check both camelCase (ui-index format) and snake_case (artifact format)
        "triageOrder": _list_from("triageOrder", "triage_order"),
        "topConcerns": _list_from("topConcerns", "top_concerns"),
        "evidenceGaps": _list_from("evidenceGaps", "evidence_gaps"),
        "nextChecks": _list_from("nextChecks", "next_checks"),
        "focusNotes": _list_from("focusNotes", "focus_notes"),
        "artifactPath": artifact_path,
        "errorSummary": artifact_data.get("error_summary"),
        "skipReason": artifact_data.get("skip_reason"),
        # Preserve alias_mapping for audit/debug if needed, but don't render it as UI text
        # Only include if present (backward compatibility with existing artifacts)
        **({"provider_alias_mapping": alias_mapping} if alias_mapping else {}),
    }


def _find_alias_mapping_from_review(
    external_analysis_dir: Path,
    run_id: str,
    artifact_index: Any = None,
) -> dict[str, str] | None:
    """Find alias_mapping from the review-enrichment artifact for this run.

    This is used as a fallback when a next-check plan artifact doesn't have
    its own alias_mapping. The review-enrichment artifact captures the mapping
    from the original drilldown anonymization and can be reused.

    Args:
        external_analysis_dir: Path to external-analysis directory
        run_id: The run ID to filter by
        artifact_index: Pre-built index for O(1) lookup (optional)

    Returns:
        The alias_mapping dict from the review-enrichment artifact, or None if not found
    """
    # Use index for O(1) lookup if available
    if artifact_index is not None:
        review_artifacts: Sequence[dict[str, object]] = artifact_index.review_enrichment
    else:
        # Fall back to directory scan for backward compatibility
        if not external_analysis_dir.exists():
            return None

        try:
            validated_run_id = validate_run_id(run_id)
        except SecurityError:
            return None

        _scan_review_artifacts: list[dict[str, object]] = []
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-review-enrichment*.json")
        for artifact_file in sorted(external_analysis_dir.glob(glob_pattern)):
            try:
                artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                if isinstance(artifact_data, dict) and artifact_data.get("purpose") == "review-enrichment":
                    _scan_review_artifacts.append(artifact_data)
            except (OSError, json.JSONDecodeError):
                continue
        review_artifacts = _scan_review_artifacts

    if not review_artifacts:
        return None

    # Take the first (sorted) matching artifact
    review_data = review_artifacts[0]
    alias_mapping = review_data.get("alias_mapping")
    if isinstance(alias_mapping, dict) and alias_mapping:
        return alias_mapping
    return None


def _parse_positive_int(value: object | None) -> int | None:
    """Parse a positive integer duration from various types.

    Returns None for missing, zero, negative, or non-numeric values.
    Only positive (> 0) durations are included in latency percentiles.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        int_val = int(value)
        return int_val if int_val > 0 else None
    if isinstance(value, str):
        try:
            int_val = int(value)
            return int_val if int_val > 0 else None
        except ValueError:
            return None
    return None


def _build_llm_stats_for_run(
    external_analysis_dir: Path, run_id: str, artifact_index: Any = None
) -> dict[str, object]:
    """Build external-analysis activity stats for a specific run.

    NOTE: Despite the name, this function counts ALL external-analysis artifacts
    with success/failed status, not just LLM calls. The "llm_stats" name is a legacy
    label from when external-analysis primarily meant LLM provider calls. In practice,
    it includes drilldown, review enrichment, next-check planning/execution, auto
    drilldown, and other status-bearing external-analysis activities.

    This naming is kept for backward compatibility (API contract), but the actual
    content reflects the broader scope of status-bearing external analysis.

    Uses artifact_index if provided for O(1) lookup, otherwise falls back
    to scanning the directory (for backward compatibility).

    Args:
        external_analysis_dir: Path to external-analysis directory (used if no index)
        run_id: The run ID to filter by
        artifact_index: Pre-built index for O(1) lookup (optional)

    Returns:
        Stats data dict with call counts, latency percentiles, and provider breakdown.
        Labeled as "llm_stats" for API contract, but includes all external-analysis.
    """
    total_calls = 0
    successful_calls = 0
    failed_calls = 0
    latest_timestamp: str | None = None
    provider_counts: dict[str, dict[str, int]] = {}
    # Collect positive durations only from successful calls for latency percentile computation
    successful_durations: list[int] = []

    if not external_analysis_dir.exists() and artifact_index is None:
        return {
            "totalCalls": 0,
            "successfulCalls": 0,
            "failedCalls": 0,
            "lastCallTimestamp": None,
            "p50LatencyMs": None,
            "p95LatencyMs": None,
            "p99LatencyMs": None,
            "providerBreakdown": [],
            "scope": "current_run",
        }

    # Use index for O(1) lookup if available
    # Declare type annotation to allow both tuple (from index) and list (from scan)
    artifacts: Sequence[dict[str, object]]
    if artifact_index is not None:
        artifacts = artifact_index.artifacts
    else:
        # Validate run_id at function boundary for safe glob construction
        try:
            validated_run_id = validate_run_id(run_id)
        except SecurityError:
            # Invalid run_id - cannot safely search, return empty stats
            return {
                "totalCalls": 0,
                "successfulCalls": 0,
                "failedCalls": 0,
                "lastCallTimestamp": None,
                "p50LatencyMs": None,
                "p95LatencyMs": None,
                "p99LatencyMs": None,
                "providerBreakdown": [],
                "scope": "current_run",
            }

        # Fall back to directory scan for backward compatibility
        _scan_llm_artifacts: list[dict[str, object]] = []
        # SECURITY: run_id validated by validate_run_id() before glob construction
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
        for artifact_file in sorted(external_analysis_dir.glob(glob_pattern)):
            filename = artifact_file.stem
            # Enforce prefix boundary to prevent run_id collision
            if len(filename) > len(validated_run_id) and filename[len(validated_run_id)] != "-":
                continue
            try:
                artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                if isinstance(artifact_data, dict):
                    _scan_llm_artifacts.append(artifact_data)
            except (OSError, json.JSONDecodeError) as exc:
                from ..security import sanitize_exception_message
                sanitized_error = sanitize_exception_message(exc)
                logger.warning(
                    "Skipped malformed artifact in llm_stats scan: %s",
                    artifact_file.name,
                    extra={
                        "run_id": run_id,
                        "artifact_kind": "external-analysis",
                        "scan_name": "_build_llm_stats_for_run",
                        "error": sanitized_error,
                    },
                    exc_info=True,
                )
                continue
        artifacts = _scan_llm_artifacts

    for artifact_data in artifacts:
        status = str(artifact_data.get("status", "")).lower()
        if status not in ("success", "failed"):
            continue

        total_calls += 1
        if status == "success":
            successful_calls += 1
            # Collect positive duration from successful calls for latency percentiles.
            # Prefer snake_case field name, fall back to camelCase for compatibility.
            # Only positive durations are included; zero/negative/missing yield None.
            duration_ms = artifact_data.get("duration_ms")
            duration = _parse_positive_int(duration_ms)
            if duration is None:
                duration = _parse_positive_int(artifact_data.get("durationMs"))
            if duration is not None:
                successful_durations.append(duration)
        if status == "failed":
            failed_calls += 1

        # Track latest timestamp
        timestamp = artifact_data.get("timestamp")
        if isinstance(timestamp, str) and timestamp:
            if latest_timestamp is None or timestamp > latest_timestamp:
                latest_timestamp = timestamp

        # Track provider breakdown
        provider = str(artifact_data.get("tool_name") or artifact_data.get("provider") or "unknown")
        if provider not in provider_counts:
            provider_counts[provider] = {"calls": 0, "failedCalls": 0}
        provider_counts[provider]["calls"] += 1
        if status == "failed":
            provider_counts[provider]["failedCalls"] += 1

    provider_breakdown = [
        {"provider": provider, "calls": data["calls"], "failedCalls": data["failedCalls"]}
        for provider, data in sorted(provider_counts.items())
    ]

    # Compute latency percentiles from successful call durations
    percentile_values: dict[str, int | None] = {
        "p50": None,
        "p95": None,
        "p99": None,
    }
    if successful_durations:
        float_durations = [float(value) for value in successful_durations]
        float_durations.sort()
        percentile_values["p50"] = _percentile_value(float_durations, 50)
        percentile_values["p95"] = _percentile_value(float_durations, 95)
        percentile_values["p99"] = _percentile_value(float_durations, 99)

    return {
        "totalCalls": total_calls,
        "successfulCalls": successful_calls,
        "failedCalls": failed_calls,
        "lastCallTimestamp": latest_timestamp,
        "p50LatencyMs": percentile_values["p50"],
        "p95LatencyMs": percentile_values["p95"],
        "p99LatencyMs": percentile_values["p99"],
        "providerBreakdown": provider_breakdown,
        "scope": "current_run",
    }


# Mirrors the algorithm in health/ui_llm_stats.py for consistency.
# Local duplication avoids a cross-module dependency from ui to health layer.
def _percentile_value(values: list[float], percentile: float) -> int | None:
    """Compute a percentile value from a sorted list of floats.

    Returns None if the input list is empty.
    Uses nearest-rank method: index = ceil(p/100 * n) - 1.
    """
    if not values:
        return None
    idx = math.ceil((percentile / 100) * len(values)) - 1
    idx = max(0, min(idx, len(values) - 1))
    return int(values[idx])
