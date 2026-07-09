"""Pure incident lifecycle type definitions.

This module contains lightweight type definitions without business logic:
- IncidentStatus: lifecycle state enum
- IncidentSignal: signal that contributed to an incident

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO autonomous root-cause claims
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class IncidentStatus(StrEnum):
    """Lifecycle states for incidents."""

    OPEN = "open"
    COLLECTING_EVIDENCE = "collecting_evidence"
    READY_FOR_REVIEW = "ready_for_review"
    INVESTIGATING = "investigating"
    SUPPRESSED = "suppressed"
    DUPLICATE = "duplicate"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class IncidentSignal:
    """Signal that contributed to the incident."""

    source: str
    reason: str
    message: str
    captured_at: datetime
    run_id: str | None = None
    detector_id: str | None = None
    finding_id: str | None = None
    fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "source": self.source,
            "reason": self.reason,
            "message": self.message,
            "captured_at": self.captured_at.isoformat(),
        }
        for opt in ("run_id", "detector_id", "finding_id", "fingerprint"):
            val = getattr(self, opt)
            if val is not None:
                result[opt] = val
        return result


__all__ = [
    "IncidentStatus",
    "IncidentSignal",
]
