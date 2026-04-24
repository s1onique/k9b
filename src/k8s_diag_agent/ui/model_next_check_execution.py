"""View models for next-check execution history (UI model module).

This module contains next-check execution history view model dataclasses extracted from model.py.
It exists to enable incremental modularization without changing behavior.

Dependency direction: model_next_check_execution.py -> model_primitives.py, model_alertmanager.py
model.py imports from model_next_check_execution.py for re-export compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .model_alertmanager import (
    AlertmanagerProvenanceView,
    _build_alertmanager_provenance_view,
)
from .model_primitives import (
    _coerce_optional_bool,
    _coerce_optional_int,
    _coerce_optional_str,
    _coerce_str,
)


@dataclass(frozen=True)
class NextCheckExecutionHistoryEntryView:
    """View model for a single next-check execution history entry."""
    timestamp: str
    cluster_label: str | None
    candidate_description: str | None
    command_family: str | None
    status: str
    duration_ms: int | None
    artifact_path: str | None
    timed_out: bool | None
    stdout_truncated: bool | None
    stderr_truncated: bool | None
    output_bytes_captured: int | None
    pack_refresh_status: str | None = None
    pack_refresh_warning: str | None = None
    failure_class: str | None = None
    failure_summary: str | None = None
    suggested_next_operator_move: str | None = None
    result_class: str | None = None
    result_summary: str | None = None
    usefulness_class: str | None = None
    usefulness_summary: str | None = None
    # Provenance fields for traceability
    candidate_id: str | None = None
    candidate_index: int | None = None
    # Alertmanager provenance snapshot (preserved from ranked queue item)
    alertmanager_provenance: AlertmanagerProvenanceView | None = None
    # Alertmanager relevance judgment from operator feedback
    alertmanager_relevance: str | None = None
    alertmanager_relevance_summary: str | None = None
    # Artifact identity for immutability traceability
    artifact_id: str | None = None
    # Usefulness review artifact identity fields
    usefulness_artifact_id: str | None = None
    usefulness_artifact_path: str | None = None
    usefulness_reviewed_at: str | None = None


def _build_execution_history_view(
    raw: object | None,
) -> tuple[NextCheckExecutionHistoryEntryView, ...]:
    """Build tuple of NextCheckExecutionHistoryEntryView from raw JSON data."""
    if not isinstance(raw, Sequence):
        return ()
    entries: list[NextCheckExecutionHistoryEntryView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        provenance_raw = entry.get("alertmanagerProvenance") or entry.get("alertmanager_provenance")
        provenance = _build_alertmanager_provenance_view(provenance_raw)
        entries.append(
            NextCheckExecutionHistoryEntryView(
                timestamp=_coerce_str(entry.get("timestamp")),
                cluster_label=_coerce_optional_str(entry.get("clusterLabel")),
                candidate_description=_coerce_optional_str(entry.get("candidateDescription")),
                command_family=_coerce_optional_str(entry.get("commandFamily")),
                status=_coerce_str(entry.get("status")),
                duration_ms=_coerce_optional_int(entry.get("durationMs")),
                artifact_path=_coerce_optional_str(entry.get("artifactPath")),
                timed_out=_coerce_optional_bool(entry.get("timedOut")),
                stdout_truncated=_coerce_optional_bool(entry.get("stdoutTruncated")),
                stderr_truncated=_coerce_optional_bool(entry.get("stderrTruncated")),
                output_bytes_captured=_coerce_optional_int(entry.get("outputBytesCaptured")),
                pack_refresh_status=_coerce_optional_str(entry.get("packRefreshStatus")),
                pack_refresh_warning=_coerce_optional_str(entry.get("packRefreshWarning")),
                failure_class=_coerce_optional_str(entry.get("failureClass")),
                failure_summary=_coerce_optional_str(entry.get("failureSummary")),
                suggested_next_operator_move=_coerce_optional_str(entry.get("suggestedNextOperatorMove")),
                result_class=_coerce_optional_str(entry.get("resultClass")),
                result_summary=_coerce_optional_str(entry.get("resultSummary")),
                usefulness_class=_coerce_optional_str(entry.get("usefulnessClass")),
                usefulness_summary=_coerce_optional_str(entry.get("usefulnessSummary")),
                # Provenance fields for traceability
                candidate_id=_coerce_optional_str(entry.get("candidateId")),
                candidate_index=_coerce_optional_int(entry.get("candidateIndex")),
                # Alertmanager provenance snapshot (preserved from ranked queue item)
                alertmanager_provenance=provenance,
                # Alertmanager relevance judgment from operator feedback
                alertmanager_relevance=_coerce_optional_str(entry.get("alertmanagerRelevance")),
                alertmanager_relevance_summary=_coerce_optional_str(entry.get("alertmanagerRelevanceSummary")),
                # Artifact identity for immutability traceability
                artifact_id=_coerce_optional_str(entry.get("artifactId")),
                # Usefulness review artifact identity fields
                usefulness_artifact_id=_coerce_optional_str(entry.get("usefulnessArtifactId")),
                usefulness_artifact_path=_coerce_optional_str(entry.get("usefulnessArtifactPath")),
                usefulness_reviewed_at=_coerce_optional_str(entry.get("usefulnessReviewedAt")),
            )
        )
    return tuple(entries)
