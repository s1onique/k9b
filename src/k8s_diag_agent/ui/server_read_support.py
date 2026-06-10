"""Read-only support helpers for the UI server.

This module contains read-only helper functions extracted from server.py.
These helpers perform no mutation and are used by server_reads.py to build
read-side payloads.

Extraction: Cluster/drilldown helpers moved to server_read_clusters.py.
            Next-check/execution helpers moved to server_read_next_checks.py.
            LLM stats/review-enrichment helpers moved to server_read_llm_stats.py.
Re-exported here for backward compatibility with existing callers.

Keep behavior unchanged: no logic changes, no response shape changes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id
from .server_read_clusters import (  # noqa: F401 - backward compatibility
    _build_clusters_and_drilldown_availability,
    _build_clusters_from_review,
    _build_drilldown_availability_from_review,
    _build_review_enrichment_status_for_past_run,
    _load_alertmanager_review_artifacts,
    _merge_alertmanager_review_into_history_entry,
)
from .server_read_execution_history import (  # noqa: F401 - backward compatibility
    _build_execution_history,
    _get_field_with_default,
    _get_field_with_fallback,
)
from .server_read_llm_stats import (  # noqa: F401 - backward compatibility
    _build_llm_stats_for_run,
    _find_alias_mapping_from_review,
    _find_review_enrichment,
)
from .server_read_next_checks import (  # noqa: F401 - backward compatibility
    _build_queue_from_plan,
    _derive_execution_state_from_status,
    _find_next_check_plan,
    _match_overlay_to_candidate,
    _scan_execution_artifacts_for_queue,
)

logger = logging.getLogger(__name__)


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
            from ..security import sanitize_exception_message

            logger.warning(
                "Skipped malformed external-analysis artifact: %s",
                artifact_file.name,
                extra={
                    "run_id": run_id,
                    "artifact_kind": "external-analysis",
                    "scan_name": "_scan_external_analysis",
                    "error": sanitize_exception_message(exc),
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
            from ..security import sanitize_exception_message

            logger.warning(
                "Skipped malformed notification artifact: %s",
                notif_file.name,
                extra={
                    "run_id": run_id,
                    "artifact_kind": "notification",
                    "scan_name": "_load_notifications_for_run",
                    "error": sanitize_exception_message(exc),
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
            from ..security import sanitize_exception_message

            logger.warning(
                "Skipped malformed artifact in index scan: %s",
                artifact_file.name,
                extra={
                    "run_id": run_id,
                    "artifact_kind": "external-analysis",
                    "scan_name": "_build_run_artifact_index",
                    "error": sanitize_exception_message(exc),
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
