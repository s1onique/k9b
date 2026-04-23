"""Typed artifacts for external analysis tool outputs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

from ..datetime_utils import now_utc, parse_iso_to_utc
from ..identity.artifact import new_artifact_id


class ExternalAnalysisStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExternalAnalysisPurpose(StrEnum):
    MANUAL = "manual"
    AUTO_DRILLDOWN = "auto-drilldown"
    REVIEW_ENRICHMENT = "review-enrichment"
    NEXT_CHECK_PLANNING = "next-check-planning"
    NEXT_CHECK_PROMOTION = "next-check-promotion"
    NEXT_CHECK_APPROVAL = "next-check-approval"
    NEXT_CHECK_EXECUTION = "next-check-execution"
    NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW = "next-check-execution-alertmanager-review"
    NEXT_CHECK_EXECUTION_USEFULNESS_REVIEW = "next-check-execution-usefulness-review"
    DIAGNOSTIC_PACK_REVIEW = "diagnostic-pack-review"


class UsefulnessClass(StrEnum):
    USEFUL = "useful"
    PARTIAL = "partial"
    NOISY = "noisy"
    EMPTY = "empty"


class AlertmanagerRelevanceClass(StrEnum):
    """Operator judgment on whether Alertmanager influence was relevant for the executed check."""
    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    NOISY = "noisy"
    UNSURE = "unsure"


class ReviewStage(StrEnum):
    INITIAL_TRIAGE = "initial_triage"
    FOCUSED_INVESTIGATION = "focused_investigation"
    PARITY_VALIDATION = "parity_validation"
    FOLLOW_UP = "follow_up"
    UNKNOWN = "unknown"


class Workstream(StrEnum):
    INCIDENT = "incident"
    EVIDENCE = "evidence"
    DRIFT = "drift"
    UNKNOWN = "unknown"


class ProblemClass(StrEnum):
    WORKLOAD_FAILURE = "workload_failure"
    READINESS_PROBE = "readiness_probe"
    LIVENESS_PROBE = "liveness_probe"
    CRASHLOOP = "crashloop"
    IMAGE_PULL = "image_pull"
    JOB_FAILURE = "job_failure"
    NODE_CONDITION = "node_condition"
    PLATFORM_DRIFT = "platform_drift"
    NETWORKING = "networking"
    STORAGE = "storage"
    UNKNOWN = "unknown"


class JudgmentScope(StrEnum):
    RUN_CONTEXT = "run_context"
    PATTERN_LEVEL = "pattern_level"


class ReviewerConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _coerce_optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _parse_optional_enum(
    value: object | None,
    enum_type: type[StrEnum],
) -> StrEnum | None:
    """Parse an optional enum value from raw input."""
    if value is None:
        return None
    try:
        return enum_type(str(value))
    except ValueError:
        return None


def _parse_timestamp_field(value: object | None) -> datetime:
    """Parse timestamp field from dict.

    - If value is None/missing: use current time (default behavior)
    - If value is an invalid string: raise ValueError (fail fast on corrupt data)
    """
    if value is None:
        # Missing timestamp: use current time
        return now_utc()
    parsed = parse_iso_to_utc(value)
    if parsed is not None:
        return parsed
    # Invalid timestamp format: fail fast
    raise ValueError(f"Invalid timestamp format: {value!r}")


class PackRefreshStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed-out"


@dataclass(frozen=True)
class ExternalAnalysisArtifact:
    tool_name: str
    run_id: str
    cluster_label: str
    run_label: str = ""
    source_artifact: str | None = None
    summary: str | None = None
    findings: tuple[str, ...] = field(default_factory=tuple)
    suggested_next_checks: tuple[str, ...] = field(default_factory=tuple)
    status: ExternalAnalysisStatus = ExternalAnalysisStatus.PENDING
    raw_output: str | None = None
    stdout_truncated: bool | None = None
    stderr_truncated: bool | None = None
    timed_out: bool | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    artifact_path: str | None = None
    provider: str | None = None
    duration_ms: int | None = None
    purpose: ExternalAnalysisPurpose = ExternalAnalysisPurpose.MANUAL
    payload: dict[str, object] | None = None
    error_summary: str | None = None
    skip_reason: str | None = None
    output_bytes_captured: int | None = None
    pack_refresh_status: PackRefreshStatus | None = None
    pack_refresh_warning: str | None = None
    usefulness_class: UsefulnessClass | None = None
    usefulness_summary: str | None = None
    # Context fields for stage-aware usefulness feedback
    review_stage: ReviewStage | None = None
    workstream: Workstream | None = None
    problem_class: ProblemClass | None = None
    judgment_scope: JudgmentScope | None = None
    reviewer_confidence: ReviewerConfidence | None = None
    # Immutable artifact identity (UUIDv7)
    artifact_id: str | None = field(default_factory=new_artifact_id)
    # Alertmanager relevance judgment from operator feedback
    alertmanager_relevance: AlertmanagerRelevanceClass | None = None
    alertmanager_relevance_summary: str | None = None
    # Alertmanager provenance snapshot - preserved when execution is triggered by Alertmanager-ranked queue item
    alertmanager_provenance: dict[str, object] | None = None
    # Provider-assisted interpretation payload (e.g., alertmanagerEvidenceReferences from review enrichment)
    interpretation: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "tool_name": self.tool_name,
            "run_label": self.run_label,
            "run_id": self.run_id,
            "cluster_label": self.cluster_label,
            "source_artifact": self.source_artifact,
            "summary": self.summary,
            "findings": list(self.findings),
            "suggested_next_checks": list(self.suggested_next_checks),
            "status": self.status.value,
            "raw_output": self.raw_output,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "timed_out": self.timed_out,
            "timestamp": self.timestamp.isoformat(),
            "artifact_path": self.artifact_path,
            "provider": self.provider,
            "duration_ms": self.duration_ms,
            "purpose": self.purpose.value,
            "payload": self.payload,
            "error_summary": self.error_summary,
            "skip_reason": self.skip_reason,
            "output_bytes_captured": self.output_bytes_captured,
            "pack_refresh_status": self.pack_refresh_status.value if self.pack_refresh_status else None,
            "pack_refresh_warning": self.pack_refresh_warning,
            "artifact_id": self.artifact_id,
        }
        if self.usefulness_class is not None:
            result["usefulness_class"] = self.usefulness_class.value
        if self.usefulness_summary is not None:
            result["usefulness_summary"] = self.usefulness_summary
        if self.review_stage is not None:
            result["review_stage"] = self.review_stage.value
        if self.workstream is not None:
            result["workstream"] = self.workstream.value
        if self.problem_class is not None:
            result["problem_class"] = self.problem_class.value
        if self.judgment_scope is not None:
            result["judgment_scope"] = self.judgment_scope.value
        if self.reviewer_confidence is not None:
            result["reviewer_confidence"] = self.reviewer_confidence.value
        if self.alertmanager_relevance is not None:
            result["alertmanager_relevance"] = self.alertmanager_relevance.value
        if self.alertmanager_relevance_summary is not None:
            result["alertmanager_relevance_summary"] = self.alertmanager_relevance_summary
        if self.alertmanager_provenance is not None:
            result["alertmanager_provenance"] = self.alertmanager_provenance
        if self.interpretation is not None:
            result["interpretation"] = self.interpretation
        return result

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> ExternalAnalysisArtifact:
        status_raw = str(raw.get("status") or ExternalAnalysisStatus.PENDING.value)
        status = ExternalAnalysisStatus(status_raw)
        purpose_raw = str(raw.get("purpose") or ExternalAnalysisPurpose.MANUAL.value)
        purpose = ExternalAnalysisPurpose(purpose_raw)
        payload_raw = raw.get("payload")
        payload = dict(payload_raw) if isinstance(payload_raw, Mapping) else None
        pack_refresh_status_raw = raw.get("pack_refresh_status")
        pack_refresh_status: PackRefreshStatus | None = None
        if pack_refresh_status_raw:
            try:
                pack_refresh_status = PackRefreshStatus(str(pack_refresh_status_raw))
            except ValueError:
                pass
        usefulness_class_raw = raw.get("usefulness_class")
        usefulness_class: UsefulnessClass | None = None
        if usefulness_class_raw:
            try:
                usefulness_class = UsefulnessClass(str(usefulness_class_raw))
            except ValueError:
                pass
        review_stage = cast(ReviewStage | None, _parse_optional_enum(raw.get("review_stage"), ReviewStage))
        workstream = cast(Workstream | None, _parse_optional_enum(raw.get("workstream"), Workstream))
        problem_class = cast(ProblemClass | None, _parse_optional_enum(raw.get("problem_class"), ProblemClass))
        judgment_scope = cast(JudgmentScope | None, _parse_optional_enum(raw.get("judgment_scope"), JudgmentScope))
        reviewer_confidence = cast(ReviewerConfidence | None, _parse_optional_enum(raw.get("reviewer_confidence"), ReviewerConfidence))
        alertmanager_relevance = cast(AlertmanagerRelevanceClass | None, _parse_optional_enum(raw.get("alertmanager_relevance"), AlertmanagerRelevanceClass))
        artifact_id = str(raw.get("artifact_id")) if raw.get("artifact_id") else None
        raw_provenance = raw.get("alertmanager_provenance")
        if isinstance(raw_provenance, dict):
            alertmanager_provenance: dict[str, object] | None = dict(raw_provenance)
        else:
            alertmanager_provenance = None
        raw_interpretation = raw.get("interpretation")
        interpretation: dict[str, object] | None = dict(raw_interpretation) if isinstance(raw_interpretation, dict) else None
        return cls(
            tool_name=str(raw.get("tool_name") or ""),
            run_id=str(raw.get("run_id") or ""),
            cluster_label=str(raw.get("cluster_label") or ""),
            run_label=str(raw.get("run_label") or ""),
            source_artifact=str(raw.get("source_artifact")) if raw.get("source_artifact") else None,
            summary=str(raw.get("summary")) if raw.get("summary") else None,
            findings=tuple(str(item) for item in raw.get("findings") or []),
            suggested_next_checks=tuple(str(item) for item in raw.get("suggested_next_checks") or []),
            status=status,
            raw_output=str(raw.get("raw_output")) if raw.get("raw_output") else None,
            timestamp=_parse_timestamp_field(raw.get("timestamp")),
            artifact_path=str(raw.get("artifact_path")) if raw.get("artifact_path") else None,
            provider=str(raw.get("provider")) if raw.get("provider") else None,
            duration_ms=_coerce_optional_int(raw.get("duration_ms")),
            purpose=purpose,
            payload=payload,
            error_summary=str(raw.get("error_summary")) if raw.get("error_summary") else None,
            skip_reason=str(raw.get("skip_reason")) if raw.get("skip_reason") else None,
            stdout_truncated=bool(raw.get("stdout_truncated")) if raw.get("stdout_truncated") is not None else None,
            stderr_truncated=bool(raw.get("stderr_truncated")) if raw.get("stderr_truncated") is not None else None,
            timed_out=bool(raw.get("timed_out")) if raw.get("timed_out") is not None else None,
            output_bytes_captured=_coerce_optional_int(raw.get("output_bytes_captured")),
            pack_refresh_status=pack_refresh_status,
            pack_refresh_warning=str(raw.get("pack_refresh_warning")) if raw.get("pack_refresh_warning") else None,
            usefulness_class=usefulness_class,
            usefulness_summary=str(raw.get("usefulness_summary")) if raw.get("usefulness_summary") else None,
            review_stage=review_stage,
            workstream=workstream,
            problem_class=problem_class,
            judgment_scope=judgment_scope,
            reviewer_confidence=reviewer_confidence,
            artifact_id=artifact_id,
            alertmanager_relevance=alertmanager_relevance,
            alertmanager_relevance_summary=str(raw.get("alertmanager_relevance_summary")) if raw.get("alertmanager_relevance_summary") else None,
            alertmanager_provenance=alertmanager_provenance,
            interpretation=interpretation,
        )


def write_external_analysis_artifact(path: Path, artifact: ExternalAnalysisArtifact) -> Path:
    """Write an external analysis artifact to disk.

    External analysis artifacts are immutable: once written, they must not be overwritten.
    This function rejects writes to an existing path to enforce the immutability contract.

    The immutability contract means that the same path (run_id + cluster_label + tool_name
    combination) should never be written twice. This protects against accidental overwrites
    that could lose audit trail information.

    Mutable exceptions (NOT covered by this guard):
    - history.json
    - alertmanager-source-registry.json
    - ui-index.json
    - diagnostic-packs/latest/
    - other explicitly documented mutable/derived artifacts

    Raises:
        FileExistsError: If the artifact path already exists (immutability guarantee)
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Reject overwrite: fail fast if path already exists (immutability contract)
    if path.exists():
        raise FileExistsError(
            f"External analysis artifact already exists at {path}; "
            f"immutability contract violated for run_id={artifact.run_id}, "
            f"cluster_label={artifact.cluster_label}, tool_name={artifact.tool_name}"
        )

    path.write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")
    return path
