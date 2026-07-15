"""Closed union of automatic-diagnosis selection outcomes.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 domain model.

The previous contract consumed ``canonical_incident_ids`` as an
optional sequence. Empty values silently collapsed to "store scan"
through boolean truthiness, and failed promotions were interpreted
as "no IDs were propagated, so scan for them". This module
replaces that pattern with three typed variants and one
:func:`reduce_diagnosis_selection` helper that the diagnosis
collector invokes from a single, auditable dispatch point.

Variants:

* :class:`DiagnosisSelectionFromPromotion` -- promotion succeeded,
  dispatcher supplies the diagnosis IDs. Empty IDs are
  authoritative zero-work.
* :class:`DiagnosisSelectionUnavailable` -- promotion produced a
  ``PromotionRejected`` or ``PromotionCommitUnknown`` outcome;
  the collector MUST NOT scan the global store.
* :class:`DiagnosisSelectionWithoutPromotion` -- a scheduled
  scan-only run legitimately opted into non-promotion selection.
  The collector may scan, but ONLY through the explicit named
  policy path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .promotion_outcomes import (
        PromotionCommitUnknown,
        PromotionRejected,
    )


class NoPromotionSelectionReason(StrEnum):
    """Why a run is allowed to scan without a promotion attempt.

    Closed enumeration; free-form strings are not permitted.
    """

    SCHEDULED_SCAN_RUN = "scheduled_scan_run"
    """Operator-scheduled scan-only run."""

    EXPLICIT_NON_PROMOTION_MODE = "explicit_non_promotion_mode"
    """Configuration flag mandates the run is non-promotional."""


class DiagnosisSelectionSource(StrEnum):
    """Origin of the IDs (or the missing/empty IDs) handed to diagnosis.

    Five values, no collapse:

    * ``promotion`` -- IDs came from a successful promotion.
    * ``explicit_nonpromotion`` -- IDs (possibly empty) are explicitly
      allowed by a non-promotion policy.
    * ``store_scan_policy`` -- a store scan is being performed under
      an explicit policy. (Reserved for future variants; current
      dispatch keeps scans on the ``explicit_nonpromotion`` path.)
    * ``unavailable_due_to_rejected_promotion`` -- promotion was
      rejected, no IDs may be supplied, no scan may be triggered.
    * ``unavailable_due_to_commit_unknown`` -- promotion commit
      status is unknown; reconciliation is required.
    """

    PROMOTION = "promotion"
    EXPLICIT_NON_PROMOTION = "explicit_nonpromotion"
    STORE_SCAN_POLICY = "store_scan_policy"
    UNAVAILABLE_DUE_TO_REJECTED_PROMOTION = "unavailable_due_to_rejected_promotion"
    UNAVAILABLE_DUE_TO_COMMIT_UNKNOWN = "unavailable_due_to_commit_unknown"


@dataclass(frozen=True, slots=True)
class DiagnosisSelectionFromPromotion:
    """Authoritative diagnosis IDs from a successful promotion.

    ``incident_ids=()`` is allowed and represents authoritative zero
    work; it MUST NOT be reinterpreted as a fallback trigger.
    """

    promotion_run_id: str
    incident_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.promotion_run_id:
            raise ValueError(
                "DiagnosisSelectionFromPromotion requires a promotion_run_id"
            )

    @property
    def source(self) -> DiagnosisSelectionSource:
        """Selection source: always ``promotion``."""
        return DiagnosisSelectionSource.PROMOTION

    @property
    def selected_incident_count(self) -> int:
        """Count of canonical IDs handed to the diagnosis collector."""
        return len(self.incident_ids)


@dataclass(frozen=True, slots=True)
class DiagnosisSelectionUnavailable:
    """Promotion did not succeed; no IDs may be consumed.

    Carries the underlying outcome so the dispatcher can render the
    correct telemetry (commit unknown => reconciliation required,
    rejection => no commit).
    """

    outcome: PromotionRejected | PromotionCommitUnknown

    def __post_init__(self) -> None:
        if self.outcome is None:
            raise ValueError(
                "DiagnosisSelectionUnavailable requires the underlying outcome"
            )

    @property
    def source(self) -> DiagnosisSelectionSource:
        """Selection source derived from the carried outcome."""
        from .promotion_outcomes import (
            PromotionCommitUnknown,
            PromotionRejected,
        )

        if isinstance(self.outcome, PromotionCommitUnknown):
            return DiagnosisSelectionSource.UNAVAILABLE_DUE_TO_COMMIT_UNKNOWN
        if isinstance(self.outcome, PromotionRejected):
            return DiagnosisSelectionSource.UNAVAILABLE_DUE_TO_REJECTED_PROMOTION
        raise ValueError(
            "DiagnosisSelectionUnavailable accepts only PromotionRejected or "
            "PromotionCommitUnknown; got "
            f"{type(self.outcome).__name__}"
        )


@dataclass(frozen=True, slots=True)
class DiagnosisSelectionWithoutPromotion:
    """Diagnosis IDs supplied without a promotion attempt.

    This is the ONLY variant that permits a store scan, and only
    when the configured :class:`StoreScanPolicy` is
    :attr:`StoreScanPolicy.EXPLICIT_NON_PROMOTION`.
    """

    reason: NoPromotionSelectionReason

    def __post_init__(self) -> None:
        if self.reason is None:
            raise ValueError(
                "DiagnosisSelectionWithoutPromotion requires a reason"
            )

    @property
    def source(self) -> DiagnosisSelectionSource:
        """Selection source."""
        return DiagnosisSelectionSource.EXPLICIT_NON_PROMOTION


class DiagnosisRunIdentityMismatchError(ValueError):
    """Raised when a diagnosis selection's run identity disagrees with the caller's.

    Required validation points
    (ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01):

    * :attr:`DiagnosisSelectionFromPromotion.promotion_run_id`
    * :attr:`DiagnosisSelectionUnavailable.outcome.run_id` -- carries the
      underlying :class:`PromotionSucceeded`, :class:`PromotionRejected`,
      or :class:`PromotionCommitUnknown` ``run_id``

    must all equal the ``scheduler_run_id`` passed to
    :func:`run_automatic_diagnosis_loop` (or the ``run_id`` passed to
    :func:`build_diagnosis_selection`).

    The validator is **fail-closed**: when the caller cannot prove the
    comparison (because ``scheduler_run_id`` is ``None`` / empty AND the
    selection carries a promotion-derived ``run_id``), the seam
    raises rather than silently accepting the cross-run laundry.
    Inheritance from :class:`ValueError` preserves compatibility with
    assertions that catch :class:`ValueError`.

    The error class owns its message: every rejection emits one
    canonical diagnostic so different call sites cannot diverge on
    free-form text. Callers supply only structured keyword arguments.
    """

    def __init__(
        self,
        *,
        expected_run_id: str,
        actual_run_id: str,
    ) -> None:
        self.expected_run_id = expected_run_id
        self.actual_run_id = actual_run_id
        super().__init__(
            "diagnosis selection run identity mismatch: "
            f"expected {expected_run_id!r}, "
            f"got {actual_run_id!r}"
        )


# Closed union
DiagnosisSelection = (
    DiagnosisSelectionFromPromotion
    | DiagnosisSelectionUnavailable
    | DiagnosisSelectionWithoutPromotion
)


def selection_source(
    selection: DiagnosisSelection,
) -> DiagnosisSelectionSource:
    """Return the canonical :class:`DiagnosisSelectionSource` for a selection.

    Centralized projection so the same value is emitted from every
    dispatch point.
    """
    return selection.source


def selection_run_id(selection: DiagnosisSelection) -> str | None:
    """Return the promotion-derived ``run_id`` carried by a selection.

    ``DiagnosisSelectionWithoutPromotion`` carries no promotion-derived
    run_id and returns ``None``. The result feeds the dispatch-seam
    validator so it rejects cross-run laundering regardless of which
    selection variant the caller supplied.
    """
    if isinstance(selection, DiagnosisSelectionFromPromotion):
        return selection.promotion_run_id
    if isinstance(selection, DiagnosisSelectionUnavailable):
        return selection.outcome.run_id
    return None


def store_scan_performed(selection: DiagnosisSelection) -> bool:
    """Return True if the selection permits a store scan.

    Only :class:`DiagnosisSelectionWithoutPromotion` permits a store
    scan, and only when the caller passes the explicit
    :class:`StoreScanPolicy`. Promoting this decision into a helper
    eliminates truthiness fallbacks at the seam.
    """
    return isinstance(selection, DiagnosisSelectionWithoutPromotion)


__all__ = [
    "DiagnosisRunIdentityMismatchError",
    "DiagnosisSelection",
    "DiagnosisSelectionFromPromotion",
    "DiagnosisSelectionUnavailable",
    "DiagnosisSelectionWithoutPromotion",
    "DiagnosisSelectionSource",
    "NoPromotionSelectionReason",
    "selection_run_id",
    "selection_source",
    "store_scan_performed",
]
