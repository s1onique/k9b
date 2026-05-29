"""Cluster and drilldown reconstruction helpers for the UI server.

This module contains functions for building clusters and drilldown availability
from review artifacts. Extracted from server_read_support.py for LLM-friendly
organization.

Keep behavior unchanged: no logic changes, no response shape changes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path

from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id, validate_safe_path_id

logger = logging.getLogger(__name__)


def _load_alertmanager_review_artifacts(
    external_analysis_dir: Path, run_id: str
) -> dict[str, dict[str, object]]:
    """Discover Alertmanager review artifacts and return latest per source execution artifact.

    Scans external-analysis/ for review artifacts matching:
    {run_id}-next-check-execution-alertmanager-review-*.json

    Returns a dict mapping source_artifact path -> latest review artifact data.
    If multiple reviews exist for the same source, returns the most recent one.

    Each review artifact is enriched with the review file's relative path as
    `artifact_path` so that callers can include the review artifact path in
    merged entries (not just the source artifact path).

    Args:
        external_analysis_dir: Path to external-analysis directory
        run_id: The run ID to filter by

    Returns:
        Dict mapping source artifact relative path -> latest review artifact data,
        with each review also containing `artifact_path` = relative path of the review file
    """
    from ..external_analysis.artifact import ExternalAnalysisPurpose

    reviews_by_source: dict[str, dict[str, object]] = {}

    if not external_analysis_dir.exists():
        return reviews_by_source

    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return empty result
        return reviews_by_source

    # Find all Alertmanager review artifacts for this run
    # SECURITY: run_id validated by validate_run_id() before glob construction
    glob_pattern = safe_run_artifact_glob(validated_run_id, "-next-check-execution-alertmanager-review-*.json")
    for review_file in external_analysis_dir.glob(glob_pattern):
        try:
            review_data = json.loads(review_file.read_text(encoding="utf-8"))
            if not isinstance(review_data, dict):
                continue

            purpose = review_data.get("purpose")
            # Accept both the formal purpose constant and the legacy literal for backward compatibility
            formal_purpose = ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value
            if purpose != formal_purpose and purpose != "next-check-execution-alertmanager-review":
                continue

            # Get source artifact path (the execution artifact this review is for)
            source_artifact = review_data.get("source_artifact")
            if not isinstance(source_artifact, str):
                continue

            # Inject the review file's relative path as artifact_path
            # This allows callers to include the review artifact path, not just the source
            review_data["artifact_path"] = str(review_file.relative_to(external_analysis_dir.parent))

            # Get review timestamp for determining "latest"
            reviewed_at = review_data.get("reviewed_at", "")
            existing = reviews_by_source.get(source_artifact)
            if existing is None or reviewed_at > existing.get("reviewed_at", ""):
                reviews_by_source[source_artifact] = review_data

        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Skipped malformed Alertmanager review artifact: %s",
                review_file.name,
                extra={
                    "run_id": run_id,
                    "artifact_kind": "alertmanager-review",
                    "scan_name": "_load_alertmanager_review_artifacts",
                    "error": str(exc),
                },
                exc_info=True,
            )
            continue

    return reviews_by_source


def _merge_alertmanager_review_into_history_entry(
    entry: Mapping[str, object], review: Mapping[str, object] | None
) -> dict[str, object]:
    """Merge Alertmanager review data into an execution history entry.

    If a review exists for this entry's source artifact, merge the relevance
    judgment and provenance into the entry for API serialization.

    Args:
        entry: The execution history entry dict
        review: The latest Alertmanager review artifact data, or None if no review

    Returns:
        Entry dict with alertmanager review fields merged in
    """
    if review is None:
        return dict(entry)

    # Create merged entry
    merged = dict(entry)

    # Add Alertmanager relevance judgment from review
    relevance = review.get("alertmanager_relevance")
    if isinstance(relevance, str):
        merged["alertmanagerRelevance"] = relevance

    summary = review.get("alertmanager_relevance_summary")
    if isinstance(summary, str):
        merged["alertmanagerRelevanceSummary"] = summary

    # Add provenance preserved from execution artifact
    provenance = review.get("alertmanager_provenance")
    if provenance is not None:
        merged["alertmanagerProvenance"] = provenance

    # Add review metadata
    reviewed_at = review.get("reviewed_at")
    if isinstance(reviewed_at, str):
        merged["alertmanagerReviewedAt"] = reviewed_at

    review_artifact = review.get("artifact_path") or review.get("source_artifact")
    if isinstance(review_artifact, str):
        merged["alertmanagerReviewArtifactPath"] = review_artifact

    return merged


def _build_clusters_and_drilldown_availability(
    run_id: str, review_data: dict[str, object], runs_dir: Path
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Build clusters list and drilldown availability from review artifact in a single pass.

    This is an optimized version that reads drilldown artifacts ONCE and produces
    both clusters data and drilldown availability data, avoiding redundant disk I/O.

    Previously this work was split into two functions (_build_clusters_from_review and
    _build_drilldown_availability_from_review) that each did their own glob + parse
    operations.

    Args:
        run_id: The run ID for artifact matching
        review_data: The review artifact data containing selected_drilldowns
        runs_dir: The base runs directory

    Returns:
        Tuple of (clusters list, drilldown availability dict)
    """
    clusters: list[dict[str, object]] = []
    selected_drilldowns = review_data.get("selected_drilldowns", [])

    if not isinstance(selected_drilldowns, list):
        selected_drilldowns = []

    # Phase 1: Read all drilldown artifacts for this run in a single pass
    # This replaces separate glob+parse operations in both _build_clusters_from_review
    # and _build_drilldown_availability_from_review.
    #
    # We use selected_drilldowns labels as authoritative and match drilldown artifacts
    # by exact "{run_id}-{label}-" prefix. For prefix collision handling (e.g. "cluster"
    # and "cluster-prod"), we prefer longest-label match.
    #
    # Artifact filename pattern: {run_id}-{cluster_label}-...
    # Example: health-run-20260501T063733Z-cluster-prod-a-diagnostic.json
    drilldown_data_by_label: dict[str, dict[str, object]] = {}
    drilldowns_dir = runs_dir / "health" / "drilldowns"

    # Phase 2: Build clusters using pre-loaded drilldown data
    total = len(selected_drilldowns)
    available = 0
    missing_labels: list[str] = []
    coverage: list[dict[str, object]] = []
    review_timestamp = review_data.get("timestamp", "")

    if drilldowns_dir.exists():
        try:
            validated_run_id = validate_run_id(run_id)
        except SecurityError:
            # Invalid run_id - cannot safely search, return empty results
            # Return empty clusters and empty drilldown availability
            drilldown_availability = {
                "total_clusters": total,
                "available": 0,
                "missing": total,
                "missing_clusters": [d.get("label", "unknown") for d in selected_drilldowns if isinstance(d, dict)],
                "coverage": [],
            }
            return clusters, drilldown_availability

        # SECURITY: run_id validated by validate_run_id() before glob construction
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
        for df in drilldowns_dir.glob(glob_pattern):
            try:
                df_data = json.loads(df.read_text(encoding="utf-8"))
                df_name = df.stem
                if not df_name.startswith(run_id + "-"):
                    continue

                # Extract potential label suffix: {run_id}-{potential_label}
                # We'll match this against authoritative selected_drilldowns labels
                potential_label = df_name[len(run_id) + 1:]

                # Find the best matching label from selected_drilldowns
                # Prefer longest match to handle prefix collisions (e.g. "cluster-prod" vs "cluster")
                best_match: str | None = None
                best_match_len = 0

                for drilldown in selected_drilldowns:
                    if not isinstance(drilldown, dict):
                        continue
                    label = drilldown.get("label", "")
                    if not isinstance(label, str) or not label:
                        continue

                    # Check if this artifact matches this label (exact prefix match)
                    expected_suffix = label + "-"
                    if potential_label.startswith(expected_suffix):
                        if len(label) > best_match_len:
                            best_match = label
                            best_match_len = len(label)

                # Store only if we found a matching label and it's not already stored
                # (first artifact wins for each label due to glob ordering)
                if best_match is not None and best_match not in drilldown_data_by_label:
                    drilldown_data_by_label[best_match] = {
                        "artifact": str(df.relative_to(runs_dir)),
                        "timestamp": df_data.get("timestamp"),
                    }
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Skipped malformed drilldown artifact: %s",
                    df.name,
                    extra={
                        "run_id": run_id,
                        "artifact_kind": "drilldown",
                        "scan_name": "_build_clusters_and_drilldown_availability",
                        "error": str(exc),
                    },
                    exc_info=True,
                )
                continue

    for drilldown in selected_drilldowns:
        if not isinstance(drilldown, dict):
            continue

        label = drilldown.get("label", "unknown")
        context = drilldown.get("context", "")

        # Use pre-loaded drilldown data instead of doing another glob+parse
        dd_info = drilldown_data_by_label.get(label)
        drilldown_artifact = None
        drilldown_timestamp = None
        is_available = False

        if dd_info is not None:
            drilldown_artifact = dd_info["artifact"]
            drilldown_timestamp = dd_info["timestamp"]
            is_available = True
            available += 1
        else:
            missing_labels.append(label)

        clusters.append({
            "label": label,
            "context": context,
            "cluster_class": "primary",
            "cluster_role": "worker",
            "baseline_cohort": "fleet",
            "node_count": drilldown.get("node_count", 0),
            "control_plane_version": "unknown",
            "health_rating": "degraded",  # Selected drilldowns indicate issues
            "warnings": drilldown.get("warning_event_count", 0),
            "non_running_pods": drilldown.get("non_running_pod_count", 0),
            "baseline_policy_path": "",
            "missing_evidence": drilldown.get("missing_evidence", []),
            "latest_run_timestamp": review_timestamp,
            "top_trigger_reason": drilldown.get("reasons", [None])[0] if drilldown.get("reasons") else None,
            "drilldown_available": is_available,
            "drilldown_timestamp": drilldown_timestamp,
            "artifact_paths": {
                "snapshot": None,
                "assessment": None,
                "drilldown": drilldown_artifact,
            },
        })

        # Build drilldown availability coverage entry
        coverage.append({
            "label": label,
            "context": context,
            "available": is_available,
            "timestamp": drilldown_timestamp or review_timestamp,
            "artifact_path": drilldown_artifact,
        })

    drilldown_availability = {
        "total_clusters": total,
        "available": available,
        "missing": max(total - available, 0),
        "missing_clusters": missing_labels,
        "coverage": coverage,
    }

    return clusters, drilldown_availability


def _build_clusters_from_review(
    run_id: str, review_data: dict[str, object], runs_dir: Path
) -> list[dict[str, object]]:
    """Build clusters list from review artifact's selected_drilldowns.

    NOTE: This function is kept for backward compatibility. For new code, prefer
    _build_clusters_and_drilldown_availability() which does both in a single pass.
    """
    clusters, _ = _build_clusters_and_drilldown_availability(run_id, review_data, runs_dir)
    return clusters


def _build_drilldown_availability_from_review(
    review_data: dict[str, object], drilldowns_dir: Path, run_id: str
) -> dict[str, object]:
    """Build drilldown availability from review clusters + drilldown artifacts."""
    selected_drilldowns = review_data.get("selected_drilldowns", [])
    if not isinstance(selected_drilldowns, list):
        selected_drilldowns = []

    total = len(selected_drilldowns)
    available = 0
    missing_labels: list[str] = []
    coverage: list[dict[str, object]] = []

    # Validate run_id at function boundary for safe glob construction
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return empty result
        return {
            "total_clusters": total,
            "available": 0,
            "missing": total,
            "missing_clusters": [d.get("label", "unknown") for d in selected_drilldowns if isinstance(d, dict)],
            "coverage": [],
        }

    # Check which drilldowns have artifacts
    existing_drilldowns = set()
    if drilldowns_dir.exists():
        # SECURITY: run_id validated by validate_run_id() before glob construction
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
        for df in drilldowns_dir.glob(glob_pattern):
            # Extract cluster label from filename pattern
            df_name = df.stem
            # Pattern: {run_id}-{cluster_label}-...
            if df_name.startswith(validated_run_id + "-"):
                cluster_label = df_name[len(validated_run_id) + 1:].split("-")[0]
                existing_drilldowns.add(cluster_label)

    for drilldown in selected_drilldowns:
        if not isinstance(drilldown, dict):
            continue

        label = drilldown.get("label", "unknown")
        context = drilldown.get("context", "")

        if label in existing_drilldowns:
            available += 1
            timestamp = review_data.get("timestamp")  # Use review timestamp as approximation
            available_flag = True
            # Find the actual artifact path - validate label for safe glob construction
            artifact_path = None
            try:
                validated_label = validate_safe_path_id(label, "label")
                # SECURITY: run_id and label validated before glob construction
                label_glob_pattern = safe_run_artifact_glob(validated_run_id, f"-{validated_label}-*.json")
                for df in drilldowns_dir.glob(label_glob_pattern):
                    artifact_path = str(df.relative_to(drilldowns_dir.parent))
                    break
            except SecurityError:
                # Invalid label - cannot safely search
                artifact_path = None
        else:
            timestamp = None
            artifact_path = None
            missing_labels.append(label)
            available_flag = False

        coverage.append({
            "label": label,
            "context": context,
            "available": available_flag,
            "timestamp": timestamp,
            "artifact_path": artifact_path,
        })

    return {
        "total_clusters": total,
        "available": available,
        "missing": max(total - available, 0),
        "missing_clusters": missing_labels,
        "coverage": coverage,
    }


def _build_review_enrichment_status_for_past_run(
    run_config: dict[str, object] | None,
) -> dict[str, object] | None:
    """Build review enrichment status for past runs using run-scoped config.

    This is a simplified version of health/ui's _build_review_enrichment_status
    that only checks run-level config (from review artifact), not current policy.
    For past runs, we want to show the status based on what was configured
    for that specific run, independent of the current policy.

    Args:
        run_config: The review_enrichment config dict from the review artifact,
                    or None if not present.

    Returns:
        Status dict with fields: status, reason, policyEnabled, providerConfigured,
        adapterAvailable, runEnabled, runProvider.
        Returns None only if run_config is None (no info available).
    """
    if run_config is None:
        return None

    enabled = run_config.get("enabled")
    provider = run_config.get("provider")

    # Strict boolean parsing: only treat actual booleans as authoritative.
    # Values like "false", 1, 0, or other junk are treated as unknown,
    # preventing misleading truth values.
    run_enabled: bool | None
    if isinstance(enabled, bool):
        run_enabled = enabled
    else:
        # Non-bool values (including "false", 1, 0) are treated as unknown
        run_enabled = None

    # Normalize values
    policy_enabled = True  # For past runs, we don't check current policy
    provider_configured = bool(provider)
    run_provider = str(provider).strip() if provider else None

    # Determine status based on run-level config
    if run_enabled is False:
        status = "disabled-for-run"
        reason = "Review enrichment was explicitly disabled for this run."
    elif run_enabled is None:
        status = "unknown"
        reason = "Review enrichment configuration is missing for this run."
    elif not run_provider:
        status = "provider-missing"
        reason = "Review enrichment was enabled but no provider was configured."
    else:
        # Enabled and has provider - but no artifact was produced
        status = "not-attempted"
        reason = (
            f"Review enrichment was enabled for '{run_provider}' in this run, "
            "but no artifact was recorded."
        )

    return {
        "status": status,
        "reason": reason,
        "provider": None,  # Current provider - not relevant for past runs
        "policyEnabled": policy_enabled,
        "providerConfigured": provider_configured,
        "adapterAvailable": None,  # Can't check without live adapter registry
        "runEnabled": run_enabled,
        "runProvider": run_provider,
    }
