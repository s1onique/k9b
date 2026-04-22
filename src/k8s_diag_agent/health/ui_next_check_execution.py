"""Next-check execution history and classification logic for UI rendering.

This module extracts the cohesive logic for next-check execution history assembly
and execution result classification (success/failure) from health snapshots.

Separated from ui.py to provide a crisp canonical home for:
- Execution-history dataclasses (FailureFollowUp, ResultInterpretation, NextCheckExecutionRecord)
- Success/failure classification helpers
- Result interpretation helpers
- Usefulness-review loading / joining
- _build_next_check_execution_history
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    UsefulnessClass,
)
from ..external_analysis.utils import artifact_matches_run
from .ui_shared import _relative_path

if TYPE_CHECKING:
    pass


# Execution history limit
_NEXT_CHECK_EXECUTION_HISTORY_LIMIT = 5


# Failure classification constants
_FAILURE_CLASS_TIMED_OUT = "timed-out"
_FAILURE_CLASS_COMMAND_UNAVAILABLE = "command-unavailable"
_FAILURE_CLASS_CONTEXT_UNAVAILABLE = "context-unavailable"
_FAILURE_CLASS_COMMAND_FAILED = "command-failed"
_FAILURE_CLASS_BLOCKED_BY_GATING = "blocked-by-gating"
_FAILURE_CLASS_APPROVAL_MISSING = "approval-missing-or-stale"
_FAILURE_CLASS_UNKNOWN = "unknown-failure"

_FAILURE_ACTIONS: dict[str, str] = {
    _FAILURE_CLASS_TIMED_OUT: "Retry candidate",
    _FAILURE_CLASS_COMMAND_UNAVAILABLE: "Inspect artifact output",
    _FAILURE_CLASS_CONTEXT_UNAVAILABLE: "Open cluster detail",
    _FAILURE_CLASS_COMMAND_FAILED: "Inspect artifact output",
    _FAILURE_CLASS_BLOCKED_BY_GATING: "Open cluster detail",
    _FAILURE_CLASS_APPROVAL_MISSING: "Review approval state",
    _FAILURE_CLASS_UNKNOWN: "Inspect artifact output",
}

_FAILURE_DEFAULT_SUMMARIES: dict[str, str] = {
    _FAILURE_CLASS_TIMED_OUT: "Command timed out.",
    _FAILURE_CLASS_COMMAND_UNAVAILABLE: "kubectl is unavailable on this host.",
    _FAILURE_CLASS_CONTEXT_UNAVAILABLE: "Unable to resolve the cluster context.",
    _FAILURE_CLASS_COMMAND_FAILED: "Command returned a non-zero exit code.",
    _FAILURE_CLASS_BLOCKED_BY_GATING: "Candidate was blocked by planner gating.",
    _FAILURE_CLASS_APPROVAL_MISSING: "Candidate requires operator approval.",
    _FAILURE_CLASS_UNKNOWN: "Execution failed without details.",
}


# Result classification constants
_RESULT_CLASS_USEFUL = "useful-signal"
_RESULT_CLASS_EMPTY = "empty-result"
_RESULT_CLASS_NOISY = "noisy-result"
_RESULT_CLASS_INCONCLUSIVE = "inconclusive"
_RESULT_CLASS_PARTIAL = "partial-result"

_RESULT_SUMMARIES: dict[str, str] = {
    _RESULT_CLASS_USEFUL: "Command captured signal-rich output that can guide the diagnosis.",
    _RESULT_CLASS_EMPTY: "Command completed without producing output.",
    _RESULT_CLASS_NOISY: "Command emitted warnings or noise alongside the output.",
    _RESULT_CLASS_INCONCLUSIVE: "Output is limited; it is unclear whether it contains useful signal.",
    _RESULT_CLASS_PARTIAL: "Output was truncated or interrupted before completion.",
}

_RESULT_ACTIONS: dict[str, str] = {
    _RESULT_CLASS_USEFUL: "Correlate this evidence with the target symptom.",
    _RESULT_CLASS_EMPTY: "Rerun with a broader selector or check that the target exists.",
    _RESULT_CLASS_NOISY: "Inspect the artifact for warnings before trusting the signal.",
    _RESULT_CLASS_INCONCLUSIVE: "Open the artifact to confirm whether the result is actionable.",
    _RESULT_CLASS_PARTIAL: "Download the artifact to review the full output or rerun with a higher limit.",
}

_RESULT_USEFUL_OUTPUT_THRESHOLD = 256
_RESULT_USEFUL_FAMILIES = {
    "kubectl-logs",
    "kubectl-describe",
}
_RESULT_NOISE_KEYWORDS = ("warning", "warn", "error", "failed", "denied")


# Usefulness class to result class mapping
_USE_TO_RESULT_CLASS_MAP: dict[str, str] = {
    "useful": _RESULT_CLASS_USEFUL,
    "partial": _RESULT_CLASS_PARTIAL,
    "noisy": _RESULT_CLASS_NOISY,
    "empty": _RESULT_CLASS_EMPTY,
}


@dataclass(frozen=True)
class FailureFollowUp:
    """Represents failure classification and suggested operator action."""

    failure_class: str | None
    failure_summary: str | None
    suggested_next_operator_move: str | None


@dataclass(frozen=True)
class ResultInterpretation:
    """Represents successful execution result interpretation."""

    result_class: str
    result_summary: str | None
    suggested_next_operator_move: str | None


@dataclass(frozen=True)
class NextCheckExecutionRecord:
    """Represents a next-check execution record for tracking."""

    candidate_id: str | None
    candidate_index: int | None
    artifact_path: str | None
    timestamp: datetime
    status: str
    timed_out: bool | None
    follow_up: FailureFollowUp | None
    result_interpretation: ResultInterpretation | None


def _classify_execution_failure(artifact: ExternalAnalysisArtifact) -> FailureFollowUp | None:
    """Classify a failed execution artifact into a failure category with suggested action."""
    if artifact.status == ExternalAnalysisStatus.SUCCESS:
        return None
    summary = artifact.error_summary or artifact.summary
    normalized = (summary or "").lower()
    if artifact.timed_out:
        failure_class = _FAILURE_CLASS_TIMED_OUT
    elif summary and (
        "kubectl is unavailable" in normalized
        or "command runner not found" in normalized
        or "no such file or directory" in normalized
    ):
        failure_class = _FAILURE_CLASS_COMMAND_UNAVAILABLE
    elif summary and "context" in normalized and any(
        token in normalized for token in ("missing", "unavailable", "not found")
    ):
        failure_class = _FAILURE_CLASS_CONTEXT_UNAVAILABLE
    elif summary:
        failure_class = _FAILURE_CLASS_COMMAND_FAILED
    else:
        failure_class = _FAILURE_CLASS_UNKNOWN
    failure_summary = summary or _FAILURE_DEFAULT_SUMMARIES.get(failure_class)
    suggested = _FAILURE_ACTIONS.get(failure_class)
    return FailureFollowUp(failure_class, failure_summary, suggested)


def _looks_noisy(output: str) -> bool:
    """Check if output contains noise keywords."""
    normalized = output.lower()
    return any(keyword in normalized for keyword in _RESULT_NOISE_KEYWORDS)


def _coerce_int_value(value: object | None) -> int:
    """Coerce a value to int, returning 0 for None or invalid values."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _classify_execution_success(artifact: ExternalAnalysisArtifact) -> ResultInterpretation | None:
    """Classify a successful execution artifact into a result category."""
    if artifact.status != ExternalAnalysisStatus.SUCCESS:
        return None
    payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
    timed_out = bool(artifact.timed_out or payload.get("timedOut"))
    stdout_truncated = bool(artifact.stdout_truncated or payload.get("stdoutTruncated"))
    stderr_truncated = bool(artifact.stderr_truncated or payload.get("stderrTruncated"))
    truncated = stdout_truncated or stderr_truncated
    bytes_captured = (
        artifact.output_bytes_captured
        if artifact.output_bytes_captured is not None
        else _coerce_int_value(payload.get("outputBytesCaptured"))
    )
    raw_output = str(artifact.raw_output or "").strip()
    has_output = bool(bytes_captured) or bool(raw_output)
    command_family = str(payload.get("commandFamily") or "").lower()

    if timed_out:
        result_class = _RESULT_CLASS_PARTIAL
    elif not has_output:
        result_class = _RESULT_CLASS_EMPTY
    elif truncated:
        result_class = _RESULT_CLASS_PARTIAL
    elif raw_output and _looks_noisy(raw_output):
        result_class = _RESULT_CLASS_NOISY
    elif bytes_captured >= _RESULT_USEFUL_OUTPUT_THRESHOLD or command_family in _RESULT_USEFUL_FAMILIES:
        result_class = _RESULT_CLASS_USEFUL
    else:
        result_class = _RESULT_CLASS_INCONCLUSIVE

    summary = _RESULT_SUMMARIES.get(result_class) or "Command output requires review."
    suggested = _RESULT_ACTIONS.get(result_class)
    return ResultInterpretation(result_class, summary, suggested)


def _map_usefulness_to_result_class(usefulness: UsefulnessClass) -> str:
    """Map persisted usefulness class to UI result class for backward compatibility."""
    return _USE_TO_RESULT_CLASS_MAP.get(usefulness.value, _RESULT_CLASS_INCONCLUSIVE)


def _apply_result_interpretation(candidate: dict[str, object], interpretation: ResultInterpretation | None) -> None:
    """Apply result interpretation fields to a candidate dict in-place."""
    if not interpretation:
        return
    candidate["resultClass"] = interpretation.result_class
    candidate["resultSummary"] = interpretation.result_summary
    candidate["suggestedNextOperatorMove"] = interpretation.suggested_next_operator_move


def _apply_failure_follow_up(candidate: dict[str, object], follow_up: FailureFollowUp | None) -> None:
    """Apply failure follow-up fields to a candidate dict in-place."""
    if not follow_up or not follow_up.failure_class:
        return
    candidate["failureClass"] = follow_up.failure_class
    candidate["failureSummary"] = follow_up.failure_summary
    candidate["suggestedNextOperatorMove"] = follow_up.suggested_next_operator_move


def _classify_blocked_candidate(candidate: Mapping[str, object]) -> FailureFollowUp | None:
    """Classify a blocked candidate into a failure category with suggested action.

    Checks queue status, approval state, and gating reasons to determine
    whether a candidate is blocked and how to advise the operator.
    """
    queue_status = str(candidate.get("queueStatus") or "")
    if queue_status == "duplicate-or-stale":
        return None
    requires_approval = bool(candidate.get("requiresOperatorApproval"))
    approval_state = str(candidate.get("approvalState") or "").lower()
    if requires_approval and approval_state not in ("approved", "not-required"):
        if approval_state == "approval-stale":
            summary = "Approval is stale; reapprove this candidate."
        elif approval_state == "approval-orphaned":
            summary = "Approval record is orphaned; reapprove the candidate."
        else:
            summary = "Candidate requires operator approval before execution."
        return FailureFollowUp(
            _FAILURE_CLASS_APPROVAL_MISSING,
            summary,
            _FAILURE_ACTIONS[_FAILURE_CLASS_APPROVAL_MISSING],
        )
    if queue_status in ("failed", "approval-needed", "safe-ready", "approved-ready"):
        gating_reason = candidate.get("gatingReason") or candidate.get("blockingReason")
        reason_text = str(gating_reason).strip() if gating_reason else ""
        if reason_text:
            summary = f"Gating reason: {reason_text}"
            return FailureFollowUp(
                _FAILURE_CLASS_BLOCKED_BY_GATING,
                summary,
                _FAILURE_ACTIONS[_FAILURE_CLASS_BLOCKED_BY_GATING],
            )
    return None


def _determine_execution_state(record: NextCheckExecutionRecord | None) -> str:
    """Determine the execution state string from a record."""
    if not record:
        return "unexecuted"
    if record.timed_out:
        return "timed-out"
    if record.status == ExternalAnalysisStatus.SUCCESS.value:
        return "executed-success"
    return "executed-failed"


def _derive_outcome_status(approval_state: str | None, execution_state: str) -> str:
    """Derive the outcome status based on approval and execution states."""
    if execution_state == "executed-success":
        return "executed-success"
    if execution_state in ("executed-failed", "timed-out"):
        return "executed-failed"
    if approval_state == "approval-stale":
        return "approval-stale"
    if approval_state == "approved":
        return "approved"
    if approval_state == "approval-required":
        return "approval-required"
    if approval_state == "not-required":
        return "not-used"
    return approval_state or "unknown"


def _latest_outcome_artifact(
    record: NextCheckExecutionRecord | None,
    approval_path: str | None,
    approval_timestamp: str | None,
    root_dir: Path,
) -> tuple[str | None, str | None]:
    """Find the most recent outcome artifact path and timestamp."""
    from ..datetime_utils import parse_iso_to_utc

    latest_time: datetime | None = None
    latest_path: str | None = None
    if record:
        latest_time = record.timestamp
        latest_path = _relative_path(root_dir, record.artifact_path)
    if approval_timestamp:
        parsed = parse_iso_to_utc(approval_timestamp)
        if parsed and (latest_time is None or parsed > latest_time):
            latest_time = parsed
            latest_path = approval_path
    timestamp = latest_time.isoformat() if latest_time else None
    return latest_path, timestamp


def _collect_next_check_execution_records(
    artifacts: Sequence[ExternalAnalysisArtifact], run_id: str
) -> tuple[dict[str, NextCheckExecutionRecord], dict[int, NextCheckExecutionRecord]]:
    """Collect next-check execution records by candidate ID and index."""
    by_id: dict[str, NextCheckExecutionRecord] = {}
    by_index: dict[int, NextCheckExecutionRecord] = {}
    for artifact in sorted(artifacts, key=lambda item: item.timestamp):
        if (
            artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION
            or not artifact_matches_run(artifact, run_id)
        ):
            continue
        payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
        raw_id = payload.get("candidateId")
        raw_index = payload.get("candidateIndex")
        candidate_id = raw_id if isinstance(raw_id, str) and raw_id else None
        candidate_index = raw_index if isinstance(raw_index, int) else None
        follow_up = _classify_execution_failure(artifact)
        result_interpretation = _classify_execution_success(artifact)
        record = NextCheckExecutionRecord(
            candidate_id=candidate_id,
            candidate_index=candidate_index,
            artifact_path=str(artifact.artifact_path) if artifact.artifact_path else None,
            timestamp=artifact.timestamp,
            status=artifact.status.value,
            timed_out=artifact.timed_out,
            follow_up=follow_up,
            result_interpretation=result_interpretation,
        )
        if candidate_id:
            existing = by_id.get(candidate_id)
            if existing is None or record.timestamp >= existing.timestamp:
                by_id[candidate_id] = record
        if candidate_index is not None:
            existing = by_index.get(candidate_index)
            if existing is None or record.timestamp >= existing.timestamp:
                by_index[candidate_index] = record
    return by_id, by_index


def _load_usefulness_review_artifacts(
    artifacts: Sequence[ExternalAnalysisArtifact],
) -> dict[str, dict[str, object]]:
    """Discover usefulness review artifacts and return latest per source execution artifact.

    Scans artifacts for review artifacts matching:
    - purpose = NEXT_CHECK_EXECUTION_USEFULNESS_REVIEW

    Returns a dict mapping source_artifact path -> latest review artifact data.
    If multiple reviews exist for the same source, returns the most recent one.
    """
    reviews_by_source: dict[str, dict[str, object]] = {}

    for artifact in artifacts:
        if artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_USEFULNESS_REVIEW:
            continue

        source_artifact = artifact.source_artifact
        if not source_artifact:
            continue

        # Get reviewed_at timestamp for determining "latest"
        review_dict = artifact.to_dict()
        reviewed_at = str(review_dict.get("reviewed_at") or artifact.timestamp.isoformat())
        existing = reviews_by_source.get(source_artifact)
        existing_reviewed_at: str = str(existing.get("reviewed_at", "")) if existing else ""
        if existing is None or reviewed_at > existing_reviewed_at:
            review_dict["reviewed_at"] = reviewed_at
            reviews_by_source[source_artifact] = review_dict

    return reviews_by_source


def _build_next_check_execution_history(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
    run_id: str,
    limit: int = _NEXT_CHECK_EXECUTION_HISTORY_LIMIT,
) -> list[dict[str, object]]:
    """Build the next-check execution history for UI rendering.

    Iterates over execution artifacts, classifies success/failure, merges usefulness
    reviews, and returns a structured list of execution entries suitable for the UI.
    """
    entries: list[dict[str, object]] = []

    # Pre-load usefulness review artifacts for merging into entries
    usefulness_reviews_by_source = _load_usefulness_review_artifacts(artifacts)

    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if (
            artifact.purpose != ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION
            or not artifact_matches_run(artifact, run_id)
        ):
            continue
        payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
        follow_up = _classify_execution_failure(artifact)
        # Determine pack refresh status from artifact or default to None
        pack_refresh_status: str | None = None
        if artifact.pack_refresh_status:
            pack_refresh_status = artifact.pack_refresh_status.value
        artifact_path_str = _relative_path(root_dir, artifact.artifact_path)
        entry: dict[str, object] = {
            "timestamp": artifact.timestamp.isoformat(),
            "clusterLabel": artifact.cluster_label,
            "candidateDescription": payload.get("candidateDescription"),
            "commandFamily": payload.get("commandFamily"),
            "status": artifact.status.value,
            "durationMs": artifact.duration_ms,
            "artifactPath": artifact_path_str,
            "timedOut": artifact.timed_out,
            "stdoutTruncated": artifact.stdout_truncated,
            "stderrTruncated": artifact.stderr_truncated,
            "outputBytesCaptured": artifact.output_bytes_captured,
            "packRefreshStatus": pack_refresh_status,
            "packRefreshWarning": artifact.pack_refresh_warning,
            # Provenance fields for traceability
            "candidateId": payload.get("candidateId"),
            "candidateIndex": payload.get("candidateIndex"),
        }

        # Get the execution artifact path for review lookup
        raw_artifact_path = artifact.artifact_path
        if raw_artifact_path:
            try:
                execution_artifact_path = str(Path(raw_artifact_path).relative_to(root_dir))
            except ValueError:
                execution_artifact_path = str(raw_artifact_path)
        else:
            execution_artifact_path = ""

        # Check for usefulness review artifact first (new immutability pattern)
        usefulness_review = usefulness_reviews_by_source.get(execution_artifact_path)
        if usefulness_review is not None:
            usefulness_class = usefulness_review.get("usefulness_class")
            if isinstance(usefulness_class, str):
                try:
                    usefulness_enum = UsefulnessClass(usefulness_class)
                    entry["usefulnessClass"] = usefulness_enum.value
                    usefulness_summary = usefulness_review.get("usefulness_summary")
                    if usefulness_summary:
                        entry["usefulnessSummary"] = usefulness_summary
                except ValueError:
                    pass  # Invalid usefulness class, fall through

        # Fall back to legacy embedded usefulness fields on execution artifact
        elif artifact.usefulness_class is not None:
            entry["usefulnessClass"] = artifact.usefulness_class.value
            if artifact.usefulness_summary:
                entry["usefulnessSummary"] = artifact.usefulness_summary

        # Include Alertmanager relevance judgment if available
        if artifact.alertmanager_relevance is not None:
            entry["alertmanagerRelevance"] = artifact.alertmanager_relevance.value
            if artifact.alertmanager_relevance_summary:
                entry["alertmanagerRelevanceSummary"] = artifact.alertmanager_relevance_summary
        # Thread Alertmanager provenance from execution artifact
        if artifact.alertmanager_provenance is not None:
            entry["alertmanagerProvenance"] = artifact.alertmanager_provenance

        if follow_up and follow_up.failure_class:
            entry["failureClass"] = follow_up.failure_class
            entry["failureSummary"] = follow_up.failure_summary
            entry["suggestedNextOperatorMove"] = follow_up.suggested_next_operator_move
        else:
            # Use persisted usefulness or compute from output
            if artifact.usefulness_class is None and usefulness_review is None:
                success_interpretation = _classify_execution_success(artifact)
                if success_interpretation:
                    entry["resultClass"] = success_interpretation.result_class
                    entry["resultSummary"] = success_interpretation.result_summary
                    entry["suggestedNextOperatorMove"] = (
                        success_interpretation.suggested_next_operator_move
                    )
            else:
                # Persisted usefulness exists - use it as the result interpretation
                usefulness_class_for_result = entry.get("usefulnessClass")
                if isinstance(usefulness_class_for_result, str):
                    try:
                        usefulness_enum = UsefulnessClass(usefulness_class_for_result)
                        entry["resultClass"] = _map_usefulness_to_result_class(usefulness_enum)
                    except ValueError:
                        entry["resultClass"] = _RESULT_CLASS_INCONCLUSIVE
                entry["resultSummary"] = entry.get("usefulnessSummary")
        entries.append(entry)
        if len(entries) >= limit:
            break
    return entries
