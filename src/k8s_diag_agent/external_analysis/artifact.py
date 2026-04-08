"""Typed artifacts for external analysis tool outputs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


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
    NEXT_CHECK_APPROVAL = "next-check-approval"
    NEXT_CHECK_EXECUTION = "next-check-execution"


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

    def to_dict(self) -> dict[str, object]:
        return {
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
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> ExternalAnalysisArtifact:
        status_raw = str(raw.get("status") or ExternalAnalysisStatus.PENDING.value)
        status = ExternalAnalysisStatus(status_raw)
        purpose_raw = str(raw.get("purpose") or ExternalAnalysisPurpose.MANUAL.value)
        purpose = ExternalAnalysisPurpose(purpose_raw)
        payload_raw = raw.get("payload")
        payload = dict(payload_raw) if isinstance(payload_raw, Mapping) else None
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
            timestamp=datetime.fromisoformat(str(raw.get("timestamp"))) if raw.get("timestamp") else datetime.now(UTC),
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
        )


def write_external_analysis_artifact(path: Path, artifact: ExternalAnalysisArtifact) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")
    return path
