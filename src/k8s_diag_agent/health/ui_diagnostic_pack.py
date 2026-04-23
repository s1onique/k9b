"""Diagnostic-pack and Alertmanager artifact serialization.

This module owns the canonical home for:
- Diagnostic-pack artifact reading and serialization
- Diagnostic-pack review artifact reading and serialization
- Alertmanager compact artifact serialization
- Alertmanager sources inventory serialization

Separated from ui.py to provide a crisp seam between diagnostic-pack/Alertmanager
serialization and orchestration/planning/execution logic.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..external_analysis.alertmanager_artifact import (
    read_alertmanager_compact,
    read_alertmanager_sources,
)
from ..external_analysis.alertmanager_source_actions import (
    merge_source_overrides,
    read_source_overrides,
)
from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisPurpose
from ..external_analysis.utils import artifact_matches_run
from .ui_shared import _relative_path

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


# Directory name for stable "latest" diagnostic pack mirror files
LATEST_PACK_DIR_NAME = "latest"

# Timestamp pattern for diagnostic-pack filenames
_DIAGNOSTIC_PACK_TIMESTAMP_PATTERN = re.compile(r"\d{8}T\d{6}Z")


def _find_diagnostic_pack_review_artifact(
    artifacts: Sequence[ExternalAnalysisArtifact], run_id: str
) -> ExternalAnalysisArtifact | None:
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if (
            artifact.purpose == ExternalAnalysisPurpose.DIAGNOSTIC_PACK_REVIEW
            and artifact_matches_run(artifact, run_id)
        ):
            return artifact
    return None


def _normalize_sequence(
    payload: Mapping[str, object], *keys: str
) -> tuple[str, ...]:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return _coerce_sequence(value)
    return ()


def _coerce_sequence(value: object | None) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(str(item) for item in value)
    if value is None:
        return ()
    return (str(value),)


def _serialize_diagnostic_pack_review(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
    run_id: str,
) -> dict[str, object] | None:
    artifact = _find_diagnostic_pack_review_artifact(artifacts, run_id)
    if not artifact:
        return None
    payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
    provider_review_raw = payload.get("provider_review") or payload.get("providerReview")
    provider_review = dict(provider_review_raw) if isinstance(provider_review_raw, Mapping) else None
    return {
        "timestamp": artifact.timestamp.isoformat(),
        "summary": payload.get("summary") or artifact.summary,
        "majorDisagreements": _normalize_sequence(
            payload, "major_disagreements", "majorDisagreements"
        ),
        "missingChecks": _normalize_sequence(
            payload, "missing_checks", "missingChecks"
        ),
        "rankingIssues": _normalize_sequence(
            payload, "ranking_issues", "rankingIssues"
        ),
        "genericChecks": _normalize_sequence(
            payload, "generic_checks", "genericChecks"
        ),
        "recommendedNextActions": _normalize_sequence(
            payload,
            "recommended_next_actions",
            "recommendedNextActions",
        ),
        "driftMisprioritized": bool(
            payload.get("drift_misprioritized") or payload.get("driftMisprioritized")
        ),
        "confidence": payload.get("confidence"),
        "providerStatus": payload.get("provider_status") or artifact.status.value,
        "providerSummary": payload.get("provider_summary") or artifact.summary,
        "providerErrorSummary": payload.get("provider_error_summary") or artifact.error_summary,
        "providerSkipReason": payload.get("provider_skip_reason") or artifact.skip_reason,
        "providerReview": provider_review,
        "artifactPath": _relative_path(root_dir, artifact.artifact_path),
    }


def _serialize_diagnostic_pack(
    root_dir: Path, run_id: str, run_label: str
) -> dict[str, object] | None:
    packs_dir = root_dir / "diagnostic-packs"
    if not packs_dir.is_dir():
        return None
    glob_pattern = f"diagnostic-pack-{run_id}-*.zip"
    latest_path: Path | None = None
    latest_time: datetime | None = None
    for candidate in packs_dir.glob(glob_pattern):
        if not candidate.is_file():
            continue
        parsed_timestamp: datetime | None = None
        match = _DIAGNOSTIC_PACK_TIMESTAMP_PATTERN.search(candidate.name)
        if match:
            try:
                parsed_timestamp = datetime.strptime(match.group(0), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except ValueError:
                parsed_timestamp = None
        entry_time = parsed_timestamp
        if entry_time is None:
            try:
                entry_time = datetime.fromtimestamp(candidate.stat().st_mtime, UTC)
            except OSError:
                entry_time = None
        if entry_time is None:
            continue
        if latest_time is None or entry_time > latest_time:
            latest_path = candidate
            latest_time = entry_time
    if not latest_path:
        return None
    label_value = run_label.strip() if run_label and run_label.strip() else None

    # Look for the stable "latest" mirror files
    latest_mirror_dir = packs_dir / LATEST_PACK_DIR_NAME
    review_bundle_path: Path | None = None
    review_input_14b_path: Path | None = None
    if latest_mirror_dir.is_dir():
        bundle_candidate = latest_mirror_dir / "review_bundle.json"
        if bundle_candidate.is_file():
            review_bundle_path = bundle_candidate
        input_candidate = latest_mirror_dir / "review_input_14b.json"
        if input_candidate.is_file():
            review_input_14b_path = input_candidate

    result: dict[str, object] = {
        "path": _relative_path(root_dir, latest_path),
        "timestamp": latest_time.isoformat() if latest_time else None,
        "label": label_value,
    }

    # Add mirrored review files if they exist
    if review_bundle_path:
        result["review_bundle_path"] = _relative_path(root_dir, review_bundle_path)
    if review_input_14b_path:
        result["review_input_14b_path"] = _relative_path(root_dir, review_input_14b_path)

    # Additive semantic metadata: the review paths above point to the mutable latest/ mirror
    # This flag signals to API/UI consumers that these paths are NOT immutable references.
    if review_bundle_path or review_input_14b_path:
        result["isMirror"] = True

    return result


def _serialize_alertmanager_compact(output_dir: Path, run_id: str) -> dict[str, object] | None:
    """Read and serialize Alertmanager compact artifact for UI."""
    compact = read_alertmanager_compact(output_dir / f"{run_id}-alertmanager-compact.json")
    if compact is None:
        return None

    # Build by_cluster summaries
    by_cluster: list[dict[str, Any]] = []
    for summary in compact.by_cluster:
        by_cluster.append({
            "cluster": summary.cluster,
            "alert_count": summary.alert_count,
            "severity_counts": {str(k): v for k, v in summary.severity_counts},
            "state_counts": {str(k): v for k, v in summary.state_counts},
            "top_alert_names": list(summary.top_alert_names),
            "affected_namespaces": list(summary.affected_namespaces),
            "affected_services": list(summary.affected_services),
        })

    return {
        "status": compact.status,
        "alert_count": compact.alert_count,
        "severity_counts": {str(k): v for k, v in compact.severity_counts},
        "state_counts": {str(k): v for k, v in compact.state_counts},
        "top_alert_names": list(compact.top_alert_names),
        "affected_namespaces": list(compact.affected_namespaces),
        "affected_clusters": list(compact.affected_clusters),
        "affected_services": list(compact.affected_services),
        "truncated": compact.truncated,
        "captured_at": compact.captured_at,
        "by_cluster": by_cluster,
    }


def _serialize_alertmanager_sources(output_dir: Path, run_id: str) -> dict[str, object] | None:
    """Read and serialize Alertmanager sources inventory artifact for UI."""
    inventory = read_alertmanager_sources(output_dir / f"{run_id}-alertmanager-sources.json")
    if inventory is None:
        return None

    # Load operator overrides and compute effective states (run-scoped)
    overrides_path = output_dir / f"{run_id}-alertmanager-source-overrides.json"
    overrides = read_source_overrides(overrides_path)
    effective_states: dict[str, str] = {}
    if overrides:
        effective_states = merge_source_overrides(overrides)

    # Load the durable cross-run registry for promoted/disabled sources
    from ..external_analysis.alertmanager_source_registry import (
        RegistryDesiredState,
        read_source_registry,
    )
    registry = read_source_registry(output_dir)

    sources = []
    for source in inventory.sources.values():
        source_id = source.source_id
        cluster_context = source.cluster_context or "unknown"

        # Apply run-scoped override effective state if present
        effective_state = effective_states.get(source_id)

        # Track whether this source was promoted via registry
        promoted_via_registry = False
        if registry:
            from ..external_analysis.alertmanager_source_registry import build_canonical_registry_key
            registry_key = build_canonical_registry_key(
                cluster_context=cluster_context,
                cluster_label=source.cluster_label,
                canonical_identity=source.canonical_identity,
            )
            entry = registry.entries.get(registry_key)
            if entry:
                if entry.desired_state == RegistryDesiredState.MANUAL:
                    if not effective_state:
                        effective_state = "manual"
                    promoted_via_registry = True
                elif entry.desired_state == RegistryDesiredState.DISABLED:
                    continue

        source_data: dict[str, Any] = {
            "source_id": source_id,
            "endpoint": source.endpoint,
            "namespace": source.namespace,
            "name": source.name,
            "origin": source.origin.value,
            "state": source.state.value,
            "discovered_at": source.discovered_at.isoformat() if source.discovered_at else None,
            "verified_at": source.verified_at.isoformat() if source.verified_at else None,
            "last_check": source.last_check.isoformat() if source.last_check else None,
            "last_error": source.last_error,
            "verified_version": source.verified_version,
            "confidence_hints": list(source.confidence_hints),
            "canonical_identity": source.canonical_identity,
            "cluster_label": source.cluster_label,
            "cluster_context": source.cluster_context,
        }

        if source.manual_source_mode.value != "not-manual":
            source_data["manual_source_mode"] = source.manual_source_mode.value
        elif promoted_via_registry:
            source_data["manual_source_mode"] = "operator-promoted"

        if effective_state:
            source_data["effective_state"] = effective_state

        sources.append(source_data)

    return {
        "sources": sources,
        "total_count": len(sources),
        "discovery_timestamp": inventory.discovered_at.isoformat() if inventory.discovered_at else None,
        "cluster_context": inventory.cluster_context,
        "_has_overrides": bool(overrides),
        "_has_registry": registry is not None and len(registry.entries) > 0,
    }


# Re-export constants for consumers that need them
__all__ = [
    "_serialize_diagnostic_pack",
    "_serialize_diagnostic_pack_review",
    "_find_diagnostic_pack_review_artifact",
    "_serialize_alertmanager_compact",
    "_serialize_alertmanager_sources",
    "LATEST_PACK_DIR_NAME",
]
