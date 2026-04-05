"""Machine-checkable schema definitions and validators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Dict, Iterable, List


FIXTURE_SCHEMA: Dict[str, Any] = {
    "required": ["id", "timestamp", "namespace", "workload", "signals"],
}

ASSESSMENT_SCHEMA: Dict[str, Any] = {
    "required": [
        "observed_signals",
        "findings",
        "hypotheses",
        "next_evidence_to_collect",
        "recommended_action",
        "safety_level",
    ],
}


def _require_keys(data: Dict[str, Any], required: Iterable[str]) -> None:
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"Missing keys: {', '.join(missing)}")


@dataclass
class FixtureValidator:
    schema: ClassVar[Dict[str, Any]] = FIXTURE_SCHEMA

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> None:
        _require_keys(data, cls.schema["required"])
        workload = data.get("workload")
        if not isinstance(workload, dict) or "name" not in workload:
            raise ValueError("Workload must include name and kind.")
        signals = data.get("signals")
        if not isinstance(signals, dict):
            raise ValueError("signals section must be an object.")


@dataclass
class AssessmentValidator:
    schema: ClassVar[Dict[str, Any]] = ASSESSMENT_SCHEMA

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> None:
        _require_keys(data, cls.schema["required"])
        if not isinstance(data.get("observed_signals"), list):
            raise ValueError("observed_signals must be a list.")
        if not isinstance(data.get("hypotheses"), list):
            raise ValueError("hypotheses must be a list.")
