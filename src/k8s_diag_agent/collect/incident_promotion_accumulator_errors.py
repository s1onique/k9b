"""Accumulator error types and workset state.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION01-ACCUMULATOR-SPLIT-AND-RANGE-GATE-TRUTH01.

:mod:`incident_promotion_accumulator` owns the
:class:`RunPromotionAccumulator` dataclass. The error types and
the workset state enum are declared here in a focused module
under the hard 500-line size cap so the main accumulator file
stays below the cap.
"""

from __future__ import annotations

from enum import StrEnum


class PromotionWorksetState(StrEnum):
    """Explicit workset state for promotion-to-diagnosis propagation.

    SEAM01 R2: State is EXPLICIT, not inferred from ID tuple emptiness.

    State matrix:
    - VALID + IDs:     explicit current-run diagnosis
    - VALID + empty:   successful stop; zero store operations
    - INVALID:         blocked diagnosis; zero store operations
    - NOT_APPLICABLE: store scan may be used if configured.
    """

    VALID = "valid"
    """Workset is valid for diagnosis propagation."""

    INVALID = "invalid"
    """Workset is invalid; diagnosis must be blocked."""

    NOT_APPLICABLE = "not_applicable"
    """Workset not applicable; store scan may be used if configured."""


class AccumulatorAccessModeError(ValueError):
    """Raised when a batch violates the run-scoped access-mode contract.

    The accumulator refuses to accept a batch whose
    ``incident_access_mode`` disagrees with the running value. The
    dispatcher is responsible for routing every batch through a
    single access-mode boundary; mixing backend and local batches
    in one run is a fail-closed contract violation. The exception
    carries the rejected batch and the running state so callers
    can introspect the drift.
    """

    def __init__(
        self,
        message: str,
        *,
        running_mode: str,
        rejected_mode: str,
    ) -> None:
        super().__init__(message)
        self.running_mode = running_mode
        self.rejected_mode = rejected_mode


__all__ = [
    "AccumulatorAccessModeError",
    "PromotionWorksetState",
]