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


@dataclass(frozen=True)
class ExternalAnalysisArtifact:
    tool_name: str
    run_id: str
    cluster_label: str
    source_artifact: str | None
    summary: str | None
    findings: tuple[str, ...] = field(default_factory=tuple)
    suggested_next_checks: tuple[str, ...] = field(default_factory=tuple)
    status: ExternalAnalysisStatus = ExternalAnalysisStatus.PENDING
    raw_output: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    artifact_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "tool_name": self.tool_name,
            "run_id": self.run_id,
            "cluster_label": self.cluster_label,
            "source_artifact": self.source_artifact,
            "summary": self.summary,
            "findings": list(self.findings),
            "suggested_next_checks": list(self.suggested_next_checks),
            "status": self.status.value,
            "raw_output": self.raw_output,
            "timestamp": self.timestamp.isoformat(),
            "artifact_path": self.artifact_path,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> ExternalAnalysisArtifact:
        status_raw = str(raw.get("status") or ExternalAnalysisStatus.PENDING.value)
        status = ExternalAnalysisStatus(status_raw)
        return cls(
            tool_name=str(raw.get("tool_name") or ""),
            run_id=str(raw.get("run_id") or ""),
            cluster_label=str(raw.get("cluster_label") or ""),
            source_artifact=str(raw.get("source_artifact")) if raw.get("source_artifact") else None,
            summary=str(raw.get("summary")) if raw.get("summary") else None,
            findings=tuple(str(item) for item in raw.get("findings") or []),
            suggested_next_checks=tuple(str(item) for item in raw.get("suggested_next_checks") or []),
            status=status,
            raw_output=str(raw.get("raw_output")) if raw.get("raw_output") else None,
            timestamp=datetime.fromisoformat(str(raw.get("timestamp"))) if raw.get("timestamp") else datetime.now(UTC),
            artifact_path=str(raw.get("artifact_path")) if raw.get("artifact_path") else None,
        )


def write_external_analysis_artifact(path: Path, artifact: ExternalAnalysisArtifact) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")
    return path
