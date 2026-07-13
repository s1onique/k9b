"""Branded identifiers shared by health-run orchestration boundaries.

The aliases in this module intentionally use :class:`typing.NewType` so
semantically different identifiers cannot be interchanged silently by static
type checking while remaining strings on JSON and persistence boundaries.
"""

from __future__ import annotations

from typing import NewType

HealthRunId = NewType("HealthRunId", str)
"""Identity of one scheduler health run."""

AlertSignalId = NewType("AlertSignalId", str)
"""Canonical identity of one persisted normalized alert-signal artifact."""

AlertSignalBatchId = NewType("AlertSignalBatchId", str)
"""Identity of an explicitly bounded alert-signal ingestion batch."""

AutomaticDiagnosisCollectorRunId = NewType(
    "AutomaticDiagnosisCollectorRunId", str
)
"""Identity of one synchronous automatic-diagnosis collector execution."""

__all__ = [
    "AlertSignalBatchId",
    "AlertSignalId",
    "AutomaticDiagnosisCollectorRunId",
    "HealthRunId",
]
