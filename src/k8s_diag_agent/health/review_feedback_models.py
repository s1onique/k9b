"""Artifact models for health review feedback.

Separated from review_feedback.py to keep the quality scoring logic
in a focused module under 300 lines.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _normalize_text(value: Any | None) -> str | None:
    """Normalize a value to a trimmed string or None."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


@dataclass(frozen=True)
class DrilldownSelection:
    """Selected drilldown context for health review."""

    context: str
    label: str
    severity: int
    reasons: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    warning_event_count: int
    non_running_pod_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context,
            "label": self.label,
            "severity": self.severity,
            "reasons": list(self.reasons),
            "missing_evidence": list(self.missing_evidence),
            "warning_event_count": self.warning_event_count,
            "non_running_pod_count": self.non_running_pod_count,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> DrilldownSelection:
        if not isinstance(raw, Mapping):
            raise ValueError("Drilldown selection must be a mapping")
        return cls(
            context=str(raw.get("context") or ""),
            label=str(raw.get("label") or ""),
            severity=int(raw.get("severity") or 0),
            reasons=tuple(str(item) for item in raw.get("reasons") or ()),
            missing_evidence=tuple(str(item) for item in raw.get("missing_evidence") or ()),
            warning_event_count=int(raw.get("warning_event_count") or 0),
            non_running_pod_count=int(raw.get("non_running_pod_count") or 0),
        )


@dataclass(frozen=True)
class QualityMetric:
    """Quality metric for a specific dimension of health review."""

    dimension: str
    level: str
    score: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "level": self.level,
            "score": self.score,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> QualityMetric:
        if not isinstance(raw, Mapping):
            raise ValueError("Quality metric must be a mapping")
        return cls(
            dimension=str(raw.get("dimension") or ""),
            level=str(raw.get("level") or ""),
            score=int(raw.get("score") or 0),
            detail=str(raw.get("detail") or ""),
        )
