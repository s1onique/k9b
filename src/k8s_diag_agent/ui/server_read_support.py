"""Read-only support helpers for the UI server.

This module contains read-only helper functions extracted from server.py.
These helpers perform no mutation and are used by server_reads.py to build
read-side payloads.

Extraction: Cluster/drilldown helpers moved to server_read_clusters.py.
            Next-check/execution helpers moved to server_read_next_checks.py.
Re-exported here for backward compatibility with existing callers.

Keep behavior unchanged: no logic changes, no response shape changes.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..security.deanonymization import deanonymize_review_enrichment
from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

# Re-export cluster/drilldown helpers from extraction module for backward compatibility
from .server_read_clusters import (  # noqa: F401 - backward compatibility
    _build_clusters_and_drilldown_availability,
    _build_clusters_from_review,
    _build_drilldown_availability_from_review,
    _build_review_enrichment_status_for_past_run,
    _load_alertmanager_review_artifacts,
    _merge_alertmanager_review_into_history_entry,
)

# Re-export next-check/execution helpers from extraction module for backward compatibility
from .server_read_next_checks import (  # noqa: F401 - backward compatibility
    _build_execution_history,
    _build_queue_from_plan,
    _find_next_check_plan,
    _scan_execution_artifacts_for_queue,
)

logger = logging.getLogger(__name__)


def _get_field_with_fallback(data: dict[str, object], *keys: str) -> object | None:
    """Get a value from dict with fallback keys, preserving false/0 values.

    Checks each key in order and returns the first one that exists (even if falsy).
    Returns None if no key is found.
    """
    for key in keys:
        if key in data:
            return data[key]
    return None


def _get_field_with_default(data: dict[str, object], default: object, *keys: str) -> object:
    """Get a value from dict with fallback keys, returning default if not found.

    Checks each key in order and returns the first one that exists (even if falsy).
    Returns the provided default value if no key is found.
    """
    for key in keys:
        if key in data:
            return data[key]
    return default


def _count_run_artifacts(artifacts_dir: Path, run_id: str) -> int:
    """Count artifacts belonging to a specific run in a directory."""
    if not artifacts_dir.exists():
        return 0

    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return 0
        return 0

    count = 0
    # SECURITY: run_id validated by validate_run_id() before glob construction
    glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
    for artifact_file in artifacts_dir.glob(glob_pattern):
        count += 1
    return count


def _load_proposals_for_run(
    proposals_dir: Path, run_id: str
) -> tuple[list[dict[str, object]], int]:
    """Load proposals for a specific run and return proposals data + count.

    This function uses typed HealthProposal readers as the preferred path.
    Legacy dict compatibility is preserved for valid JSON objects that don't
    pass HealthProposal.from_dict() validation (e.g., artifacts from older
    schema versions with missing optional fields).

    Future cleanup: Remove legacy fallback once artifact schema migration is complete.
    """
    # Import here to avoid circular imports at module level
    from ..health.artifact_readers import try_read_health_proposal_artifact

    proposals: list[dict[str, object]] = []

    if not proposals_dir.exists():
        return proposals, 0

    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return empty result
        return proposals, 0

    # SECURITY: run_id validated by validate_run_id() before glob construction
    glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
    for proposal_file in sorted(proposals_dir.glob(glob_pattern)):
        # Try typed reader first (preferred path)
        proposal = try_read_health_proposal_artifact(
            proposal_file,
            run_id=run_id,
            artifact_kind="proposal",
            log_failures=True,
        )
        if proposal is not None:
            proposals.append(proposal.to_dict())
            continue

        # Legacy fallback: if typed reader fails, try to preserve valid JSON objects
        # This handles artifacts from older schema versions that may be missing optional fields
        try:
            raw = json.loads(proposal_file.read_text(encoding="utf-8"))
            # Only preserve dict-shaped objects (not arrays, strings, etc.)
            if isinstance(raw, dict):
                proposals.append(raw)
        except (OSError, json.JSONDecodeError):
            # Malformed JSON already logged by typed reader above
            # Skip unreadable files silently (logged by typed reader if file exists)
            pass

    return proposals, len(proposals)


def _scan_external_analysis(
    external_analysis_dir: Path, run_id: str
) -> dict[str, object]:
    """Scan external-analysis directory for artifacts belonging to a run."""
    entries: list[dict[str, object]] = []
    counts: dict[str, int] = {}

    if not external_analysis_dir.exists():
        return {"count": 0, "status_counts": [], "artifacts": entries}

    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return empty result
        return {"count": 0, "status_counts": [], "artifacts": entries}

    # SECURITY: run_id validated by validate_run_id() before glob construction
    glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
    for artifact_file in sorted(external_analysis_dir.glob(glob_pattern)):
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            status = str(artifact_data.get("status", "unknown")).lower()
            counts[status] = counts.get(status, 0) + 1

            entries.append({
                "tool_name": artifact_data.get("tool_name", "unknown"),
                "cluster_label": artifact_data.get("cluster_label"),
                "run_id": artifact_data.get("run_id"),
                "run_label": artifact_data.get("run_label"),
                "status": status,
                "summary": artifact_data.get("summary"),
                "findings": artifact_data.get("findings", []),
                "suggested_next_checks": artifact_data.get("suggested_next_checks", []),
                "timestamp": artifact_data.get("timestamp"),
                "artifact_path": str(artifact_file.relative_to(external_analysis_dir.parent)),
                "duration_ms": artifact_data.get("duration_ms"),
                "provider": artifact_data.get("provider"),
                "purpose": artifact_data.get("purpose"),
                "payload": artifact_data.get("payload"),
                "error_summary": artifact_data.get("error_summary"),
                "skip_reason": artifact_data.get("skip_reason"),
            })
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Skipped malformed external-analysis artifact: %s",
                artifact_file.name,
                extra={
                    "run_id": run_id,
                    "artifact_kind": "external-analysis",
                    "scan_name": "_scan_external_analysis",
                    "error": str(exc),
                },
                exc_info=True,
            )
            continue

    status_counts = [{"status": status, "count": count} for status, count in sorted(counts.items())]

    return {"count": len(entries), "status_counts": status_counts, "artifacts": entries}


def _load_notifications_for_run(
    notifications_dir: Path, run_id: str
) -> tuple[list[dict[str, object]], int]:
    """Load notifications for a specific run."""
    notifications: list[dict[str, object]] = []

    if not notifications_dir.exists():
        return notifications, 0

    for notif_file in sorted(notifications_dir.glob("*.json")):
        try:
            notif_data = json.loads(notif_file.read_text(encoding="utf-8"))
            if not isinstance(notif_data, dict):
                continue

            # Filter by run_id if present
            notif_run_id = notif_data.get("run_id")
            if notif_run_id and notif_run_id != run_id:
                continue

            notifications.append({
                "kind": notif_data.get("kind", "info"),
                "summary": notif_data.get("summary", ""),
                "timestamp": notif_data.get("timestamp", ""),
                "run_id": notif_run_id,
                "cluster_label": notif_data.get("cluster_label"),
                "context": notif_data.get("context"),
                "details": notif_data.get("details", []),
                "artifact_path": str(notif_file.relative_to(notifications_dir.parent)),
            })
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Skipped malformed notification artifact: %s",
                notif_file.name,
                extra={
                    "run_id": run_id,
                    "artifact_kind": "notification",
                    "scan_name": "_load_notifications_for_run",
                    "error": str(exc),
                },
                exc_info=True,
            )
            continue

    return notifications, len(notifications)


@dataclass(frozen=True)
class RunArtifactIndex:
    """Per-run artifact index for efficient reuse across multiple lookups.

    This replaces multiple independent directory scans with a single scan,
    then classifies and indexes artifacts by purpose for O(1) lookup.
    """
    run_id: str
    artifacts: tuple[dict[str, object], ...] = field(default_factory=tuple)
    # Classification by purpose (extracted from artifact purpose field)
    review_enrichment: tuple[dict[str, object], ...] = field(default_factory=tuple)
    next_check_plan: tuple[dict[str, object], ...] = field(default_factory=tuple)
    next_check_execution: tuple[dict[str, object], ...] = field(default_factory=tuple)
    # Alertmanager review artifacts: mapping source_artifact -> latest review
    # (derived from NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW purpose artifacts)
    alertmanager_reviews_by_source: dict[str, dict[str, object]] = field(default_factory=dict)
    # Telemetry
    artifacts_considered: int = 0
    alertmanager_reviews_indexed: int = 0
    source: str = "file_scan"  # "file_scan" | "index"


def _build_run_artifact_index(
    external_analysis_dir: Path, run_id: str
) -> RunArtifactIndex:
    """Build a per-run artifact index with single directory scan.

    This function scans the external-analysis directory once for artifacts
    belonging to a run, classifies them by purpose, and returns an index
    that can be reused for lookups without additional disk I/O.

    Telemetry is preserved:
    - source="file_scan" when scanned from disk
    - artifacts_considered: count of all run artifacts scanned
    - alertmanager_reviews_indexed: count of Alertmanager review artifacts indexed
    - artifacts by purpose for efficient lookup

    Args:
        external_analysis_dir: Path to external-analysis directory
        run_id: The run ID to filter by

    Returns:
        RunArtifactIndex with classified artifacts and telemetry
    """
    from ..external_analysis.artifact import ExternalAnalysisPurpose

    artifacts: list[dict[str, object]] = []
    review_enrichment: list[dict[str, object]] = []
    next_check_plan: list[dict[str, object]] = []
    next_check_execution: list[dict[str, object]] = []
    # Alertmanager review artifacts: mapping source_artifact -> latest review
    alertmanager_reviews_by_source: dict[str, dict[str, object]] = {}

    if not external_analysis_dir.exists():
        return RunArtifactIndex(run_id=run_id, artifacts_considered=0, source="file_scan")

    # Validate run_id at function boundary for safe glob construction
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return empty index
        return RunArtifactIndex(run_id=run_id, artifacts_considered=0, source="file_scan")

    # SECURITY: run_id validated by validate_run_id() before glob construction
    glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
    for artifact_file in sorted(external_analysis_dir.glob(glob_pattern)):
        filename = artifact_file.stem

        # CRITICAL: Enforce prefix boundary to prevent run_id collision
        # e.g., run_id="run-2024" should NOT match "run-20240-..."
        # Only match if run_id is followed by "-" or is the entire stem (exact match)
        if len(filename) > len(validated_run_id) and filename[len(validated_run_id)] != "-":
            continue

        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            # Preserve artifact path for provenance (k9b artifact-first design)
            artifact_data["artifact_path"] = str(artifact_file.relative_to(external_analysis_dir.parent))

            artifacts.append(artifact_data)

            # Classify by purpose
            purpose = str(artifact_data.get("purpose", ""))
            if purpose == "review-enrichment":
                review_enrichment.append(artifact_data)
            elif purpose == "next-check-planning":
                next_check_plan.append(artifact_data)
            elif purpose == "next-check-execution":
                next_check_execution.append(artifact_data)
            # Index Alertmanager review artifacts by source_artifact (latest per source)
            # Accept both formal purpose constant and legacy literal for backward compatibility
            formal_purpose = ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value
            if purpose == formal_purpose or purpose == "next-check-execution-alertmanager-review":
                source_artifact = artifact_data.get("source_artifact")
                if isinstance(source_artifact, str):
                    # Get review timestamp for determining "latest"
                    reviewed_at = artifact_data.get("reviewed_at", "")
                    existing = alertmanager_reviews_by_source.get(source_artifact)
                    if existing is None or reviewed_at > existing.get("reviewed_at", ""):
                        alertmanager_reviews_by_source[source_artifact] = artifact_data
            # Other artifact types are kept in artifacts list but not indexed by purpose

        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Skipped malformed artifact in index scan: %s",
                artifact_file.name,
                extra={
                    "run_id": run_id,
                    "artifact_kind": "external-analysis",
                    "scan_name": "_build_run_artifact_index",
                    "error": str(exc),
                },
                exc_info=True,
            )
            continue

    return RunArtifactIndex(
        run_id=run_id,
        artifacts=tuple(artifacts),
        review_enrichment=tuple(review_enrichment),
        next_check_plan=tuple(next_check_plan),
        next_check_execution=tuple(next_check_execution),
        alertmanager_reviews_by_source=alertmanager_reviews_by_source,
        artifacts_considered=len(artifacts),
        alertmanager_reviews_indexed=len(alertmanager_reviews_by_source),
        source="file_scan",
    )


def _find_review_enrichment(
    external_analysis_dir: Path, run_id: str, artifact_index: RunArtifactIndex | None = None
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
                logger.warning(
                    "Skipped malformed review-enrichment artifact: %s",
                    artifact_file.name,
                    extra={
                        "run_id": run_id,
                        "artifact_kind": "review-enrichment",
                        "scan_name": "_find_review_enrichment",
                        "error": str(exc),
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
    artifact_index: RunArtifactIndex | None = None,
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
    external_analysis_dir: Path, run_id: str, artifact_index: RunArtifactIndex | None = None
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
                logger.warning(
                    "Skipped malformed artifact in llm_stats scan: %s",
                    artifact_file.name,
                    extra={
                        "run_id": run_id,
                        "artifact_kind": "external-analysis",
                        "scan_name": "_build_llm_stats_for_run",
                        "error": str(exc),
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


def _build_proposal_status_summary(proposals: list[dict[str, object]]) -> dict[str, object]:
    """Build proposal status summary from proposals list."""
    counts: dict[str, int] = {}

    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        status = str(proposal.get("status", "unknown")).lower()
        counts[status] = counts.get(status, 0) + 1

    status_counts = [{"status": status, "count": count} for status, count in sorted(counts.items())]

    return {"status_counts": status_counts}
