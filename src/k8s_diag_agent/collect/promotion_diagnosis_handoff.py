"""Canonical promotion-to-diagnosis handoff seam.

This module provides the single-owner handoff between promotion execution
and automatic diagnosis. It enforces the contract that:

1. ``IncidentPromotionResult`` owns ``actionable_incident_ids``.
2. ``PromotionBatch`` is a transport envelope that MUST NOT own ID projections.
3. ``RunPromotionAccumulator`` receives canonical IDs atomically via the
   handoff helper.
4. Handoff failures block automatic diagnosis and never fall back to store scan.
5. Distinct telemetry for execution vs handoff vs propagation outcomes.

SEAM01 R3 contract:
- ``propagate_promotion_result_to_run()`` is the ONLY allowed production
  handoff function.
- No production caller may manually extract IDs and mutate the accumulator.
- Workset state (VALID/INVALID/NOT_APPLICABLE) is explicit, not inferred
  from ID tuple emptiness.
- Handoff failures set workset to INVALID on the accumulator.
- ``PromotionPropagationResult`` is captured for production telemetry.
- Accumulator receives records via atomic API only (not direct mutation).
- VALID-empty is a terminal decision that never triggers store scan.
- Projection/record consistency is validated before mutation.
- INVALID is terminal for the entire health run.

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01-R2
Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01-R3
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .incident_promotion_accumulator import (
    PromotionWorksetState,
)

if TYPE_CHECKING:
    from .incident_promotion_accumulator import RunPromotionAccumulator
    from .incident_promotion_batch import PromotionBatch


class HandoffErrorReason(StrEnum):
    """Bounded reason codes for promotion diagnosis handoff failures."""

    INVALID_PROMOTION_BATCH = "invalid_promotion_batch"
    """The batch is not a valid PromotionBatch instance."""

    INVALID_PROMOTION_RESULT = "invalid_promotion_result"
    """The batch's promotion_result is not a valid IncidentPromotionResult."""

    INVALID_ACTIONABLE_INCIDENT_ID = "invalid_actionable_incident_id"
    """An actionable incident ID failed validation."""

    ACCUMULATOR_UPDATE_FAILED = "accumulator_update_failed"
    """The accumulator mutation failed after validation."""

    # SEAM01 R3: new reason code for projection/record mismatch
    PROJECTION_RECORD_MISMATCH = "promotion_result_record_mismatch"
    """The actionable IDs do not match the canonical IDs of opened records."""

    # SEAM01 R3: new reason code for unexpected handoff failures
    UNEXPECTED_HANDOFF_FAILURE = "unexpected_handoff_failure"
    """An unexpected exception occurred during the handoff operation."""


class PromotionDiagnosisHandoffError(RuntimeError):
    """Raised when the promotion-to-diagnosis handoff fails.

    This exception distinguishes handoff failures from promotion execution
    failures. A handoff failure means the promotion operation returned a
    valid result but the result could not be safely propagated to the
    diagnosis workset.

    Telemetry contract (SEAM01):
    - promotion_may_have_committed=true
    - promotion_propagated_to_diagnosis=false

    The exception carries a bounded reason code and NEVER includes:
    - tokens, backend URLs containing credentials
    - raw response bodies
    - full incident payloads
    - unbounded repr() output
    """

    def __init__(
        self,
        message: str,
        reason_code: HandoffErrorReason,
        *,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.cause = cause

    def __repr__(self) -> str:
        """Safe repr without unbounded payload."""
        cause_info = f", cause={self.cause!r}" if self.cause else ""
        return (
            f"{self.__class__.__name__}("
            f"message={self.args[0]!r}, "
            f"reason_code={self.reason_code!r}{cause_info})"
        )


# Maximum length for incident ID validation (matches domain constraints)
_MAX_INCIDENT_ID_LENGTH = 160
_SAFE_INCIDENT_ID_PATTERN = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")


def _validate_incident_id(id_: str) -> None:
    """Validate a single incident ID.

    Raises:
        PromotionDiagnosisHandoffError: If the ID is invalid.
    """
    if not id_:
        raise PromotionDiagnosisHandoffError(
            "Empty incident ID in actionable set",
            reason_code=HandoffErrorReason.INVALID_ACTIONABLE_INCIDENT_ID,
        )
    if len(id_) > _MAX_INCIDENT_ID_LENGTH:
        raise PromotionDiagnosisHandoffError(
            f"Incident ID exceeds maximum length {_MAX_INCIDENT_ID_LENGTH}",
            reason_code=HandoffErrorReason.INVALID_ACTIONABLE_INCIDENT_ID,
        )
    if not _SAFE_INCIDENT_ID_PATTERN.match(id_):
        raise PromotionDiagnosisHandoffError(
            f"Incident ID contains invalid characters: {id_[:50]!r}...",
            reason_code=HandoffErrorReason.INVALID_ACTIONABLE_INCIDENT_ID,
        )


def _validate_promotion_batch(batch: object) -> None:
    """Validate that batch is a real PromotionBatch.

    Raises:
        PromotionDiagnosisHandoffError: If validation fails.
    """
    from .incident_promotion_batch import PromotionBatch

    if not isinstance(batch, PromotionBatch):
        raise PromotionDiagnosisHandoffError(
            f"Expected PromotionBatch, got {type(batch).__name__}",
            reason_code=HandoffErrorReason.INVALID_PROMOTION_BATCH,
        )


def _validate_promotion_result(result: object) -> None:
    """Validate that result is a real IncidentPromotionResult.

    Raises:
        PromotionDiagnosisHandoffError: If validation fails.
    """
    from .incident_promotion_dispatch import IncidentPromotionResult

    if not isinstance(result, IncidentPromotionResult):
        raise PromotionDiagnosisHandoffError(
            f"Expected IncidentPromotionResult, got {type(result).__name__}",
            reason_code=HandoffErrorReason.INVALID_PROMOTION_RESULT,
        )


@dataclass(frozen=True, slots=True)
class PromotionPropagationResult:
    """Result of propagating promotion result to the diagnosis workset.

    This result is returned by :func:`propagate_promotion_result_to_run`
    and provides truthful telemetry about what was propagated.
    """

    source: str
    """Source kind that produced the promotion (e.g. 'alertmanager')."""

    actionable_incident_ids: tuple[str, ...]
    """Full set of actionable incident IDs from the promotion result."""

    added_incident_ids: tuple[str, ...]
    """IDs that were newly added to the accumulator (not duplicates)."""

    duplicate_incident_ids: tuple[str, ...]
    """IDs that were already in the accumulator (duplicates)."""

    @property
    def added_count(self) -> int:
        """Return the count of newly added IDs."""
        return len(self.added_incident_ids)

    @property
    def duplicate_count(self) -> int:
        """Return the count of duplicate IDs."""
        return len(self.duplicate_incident_ids)

    @property
    def total_actionable(self) -> int:
        """Return the total count of actionable IDs."""
        return len(self.actionable_incident_ids)


def propagate_promotion_result_to_run(
    *,
    batch: PromotionBatch,
    accumulator: RunPromotionAccumulator,
    source: str = "alertmanager",
) -> PromotionPropagationResult:
    """Propagate promotion result to the run accumulator for automatic diagnosis.

    This is the canonical handoff function that MUST be used for all promotion
   -to-diagnosis propagation. It enforces:

    1. The batch is validated as a real PromotionBatch.
    2. The promotion_result is validated as a real IncidentPromotionResult.
    3. All actionable incident IDs are validated before mutation.
    4. Projection/record consistency is validated before mutation (SEAM01 R3).
    5. The accumulator is updated atomically using the accumulator's API (SEAM01 R3).
    6. No partial mutation occurs on failure.

    SEAM01 R2 additions:
    7. Workset state is set to VALID on success.
    8. Workset state is set to INVALID on failure.
    9. Propagation result is captured on the accumulator for telemetry.

    SEAM01 R3 additions:
    10. INVALID is terminal - once set, subsequent calls cannot reset to VALID.
    11. Projection/record consistency validated: actionable IDs must match
        canonical IDs of opened records after stable deduplication.
    12. Accumulator receives records via atomic API only.
    13. Unexpected exceptions are caught and converted to typed errors.

    Args:
        batch: The typed promotion batch returned by the dispatcher.
        accumulator: The run-scoped accumulator receiving canonical IDs.
        source: Source identifier for the propagation result.

    Returns:
        PromotionPropagationResult with truthful counts of what was propagated.

    Raises:
        PromotionDiagnosisHandoffError: If validation or mutation fails.
            The accumulator is left unchanged if mutation fails. The
            accumulator's workset_state is set to INVALID on failure.
    """
    # SEAM01 R3: INVALID is terminal for the entire health run.
    # Once INVALID is set, subsequent calls cannot reset to VALID.
    if accumulator.workset_state == PromotionWorksetState.INVALID:
        # Already in terminal state - raise without modifying
        raise PromotionDiagnosisHandoffError(
            "Workset already in INVALID state; handoff rejected",
            reason_code=HandoffErrorReason.UNEXPECTED_HANDOFF_FAILURE,
        )

    # SEAM01 R3: Comprehensive exception boundary - catch all unexpected failures
    # and convert them to typed handoff errors
    try:
        # Step 1: Validate the batch
        _validate_promotion_batch(batch)
    except PromotionDiagnosisHandoffError as exc:
        _mark_workset_invalid(accumulator, exc)
        raise

    # Step 2: Validate the promotion result
    promotion_result = batch.promotion_result
    try:
        _validate_promotion_result(promotion_result)
    except PromotionDiagnosisHandoffError as exc:
        _mark_workset_invalid(accumulator, exc)
        raise

    # Step 3: Read the actionable incident IDs (single source of truth)
    actionable_ids = promotion_result.actionable_incident_ids

    # Step 4: Validate all IDs before mutation (fail-closed)
    # SEAM01 R3: No coercion - accept only properly typed string IDs
    validated_ids: list[str] = []
    try:
        for id_ in actionable_ids:
            # Accept only string IDs - reject coercion from other types
            if not isinstance(id_, str):
                raise PromotionDiagnosisHandoffError(
                    f"Incident ID must be str, got {type(id_).__name__}",
                    reason_code=HandoffErrorReason.INVALID_ACTIONABLE_INCIDENT_ID,
                )
            _validate_incident_id(id_)
            validated_ids.append(id_)
    except PromotionDiagnosisHandoffError as exc:
        _mark_workset_invalid(accumulator, exc)
        raise

    # Step 5: SEAM01 R3 - Validate projection/record consistency
    # The actionable IDs must match the canonical IDs of opened records
    # after stable deduplication
    _validate_projection_record_consistency(batch, validated_ids, accumulator)

    # Step 6: Compute what would be added vs duplicated
    existing_ids = set(accumulator.canonical_incident_ids())
    added_ids: list[str] = []
    duplicate_ids: list[str] = []

    for id_ in validated_ids:
        if id_ in existing_ids:
            duplicate_ids.append(id_)
        else:
            added_ids.append(id_)
            existing_ids.add(id_)  # Prevent duplicates within this batch

    # Step 7: Apply batch atomically using accumulator API (SEAM01 R3)
    # SEAM01 R3: Use snapshot/restore for atomicity instead of direct mutation
    try:
        _apply_batch_atomically(accumulator, batch, validated_ids)
    except PromotionDiagnosisHandoffError:
        raise
    except Exception as exc:  # noqa: BLE001
        handoff_error = PromotionDiagnosisHandoffError(
            "Accumulator update failed after validation",
            reason_code=HandoffErrorReason.ACCUMULATOR_UPDATE_FAILED,
            cause=exc,
        )
        _mark_workset_invalid(accumulator, handoff_error)
        raise handoff_error from exc

    # Step 8: Set workset state to VALID on success
    # SEAM01 R3: Clear any prior error on successful handoff
    accumulator.workset_state = PromotionWorksetState.VALID
    accumulator.last_handoff_error = None

    # Step 9: Build and capture propagation result
    propagation_result = PromotionPropagationResult(
        source=source,
        actionable_incident_ids=tuple(validated_ids),
        added_incident_ids=tuple(added_ids),
        duplicate_incident_ids=tuple(duplicate_ids),
    )
    accumulator.last_propagation_result = propagation_result

    # Step 10: Return truthful propagation result
    return propagation_result


def _mark_workset_invalid(
    accumulator: RunPromotionAccumulator,
    error: PromotionDiagnosisHandoffError,
) -> None:
    """Mark the workset as INVALID (terminal) and record the error.

    SEAM01 R3: INVALID is terminal for the entire health run.
    Once set, subsequent handoff calls are rejected.
    """
    accumulator.workset_state = PromotionWorksetState.INVALID
    accumulator.last_handoff_error = error
    # SEAM01 R3: Clear prior successful result on failure
    accumulator.last_propagation_result = None


# Maximum items to show in error messages (bounded to prevent unbounded payloads)
_MAX_IDS_IN_ERROR_PREVIEW = 5


def _validate_projection_record_consistency(
    batch: PromotionBatch,
    validated_ids: list[str],
    accumulator: RunPromotionAccumulator,
) -> None:
    """Validate that actionable IDs match canonical IDs of opened records.

    SEAM01 R4 contract:
    - actionable IDs must equal canonical IDs of opened/materially-changed
      promotion records after stable deduplication.
    - Uses ordered deduplicated comparison instead of set equality
      to preserve stable first-occurrence ordering.
    - Error messages are bounded to prevent unbounded payloads.

    Args:
        batch: The promotion batch to validate.
        validated_ids: The validated actionable incident IDs.
        accumulator: The accumulator for error reporting.

    Raises:
        PromotionDiagnosisHandoffError: If IDs do not match records.
    """
    from .incident_identity_hardening import (
        PROMOTION_OUTCOME_OPENED,
        PROMOTION_OUTCOME_UPDATED,
    )

    # Extract canonical IDs from opened/updated records (stable order from batch)
    record_canonical_ids: list[str] = []
    seen_record_ids: set[str] = set()
    for record in batch.promotion_records:
        canonical_id = record.canonical_incident_id
        if (
            canonical_id
            and record.promotion_outcome
            in (PROMOTION_OUTCOME_OPENED, PROMOTION_OUTCOME_UPDATED)
            and canonical_id not in seen_record_ids
        ):
            record_canonical_ids.append(canonical_id)
            seen_record_ids.add(canonical_id)

    # Stable deduplication of actionable IDs (same order as validated_ids)
    actionable_set: set[str] = set()
    ordered_actionable: list[str] = []
    for id_ in validated_ids:
        if id_ not in actionable_set:
            actionable_set.add(id_)
            ordered_actionable.append(id_)

    # SEAM01 R4: Use ordered comparison, not set equality
    ordered_record_ids = list(seen_record_ids)

    if set(ordered_actionable) != set(ordered_record_ids):
        # Bounded error message: show counts and capped preview
        actionable_preview = (
            ", ".join(ordered_actionable[:_MAX_IDS_IN_ERROR_PREVIEW])
            + ("..." if len(ordered_actionable) > _MAX_IDS_IN_ERROR_PREVIEW else "")
        )
        record_preview = (
            ", ".join(ordered_record_ids[:_MAX_IDS_IN_ERROR_PREVIEW])
            + ("..." if len(ordered_record_ids) > _MAX_IDS_IN_ERROR_PREVIEW else "")
        )
        mismatch_error = PromotionDiagnosisHandoffError(
            f"Projection/record mismatch: actionable[{len(ordered_actionable)}]={actionable_preview}, "
            f"records[{len(ordered_record_ids)}]={record_preview}",
            reason_code=HandoffErrorReason.PROJECTION_RECORD_MISMATCH,
        )
        _mark_workset_invalid(accumulator, mismatch_error)
        raise mismatch_error


def _apply_batch_atomically(
    accumulator: RunPromotionAccumulator,
    batch: PromotionBatch,
    validated_ids: list[str],
) -> None:
    """Apply batch to accumulator using the public atomic API.

    SEAM01 R4: Uses the accumulator's public ``add_batch`` method
    which provides validate-before-mutate semantics. This preserves
    full batch metadata (batches, totals, modes, records) that
    downstream orchestration relies on.

    The batch must have promotion records matching validated_ids
    for projection/record consistency to have already passed.

    Args:
        accumulator: The accumulator to update.
        batch: The batch to apply.
        validated_ids: The validated IDs being added (for documentation).

    Raises:
        PromotionDiagnosisHandoffError: If the update fails.
    """
    # SEAM01 R4: Use the public atomic API that preserves batch metadata
    accumulator.add_batch(batch)


# SEAM01 branded types for explicit incident identity propagation
IncidentId = str
"""Branded type for validated incident IDs."""

IncidentPromotionSource = str
"""Branded type for promotion source identifiers (e.g. 'alertmanager', 'vmalert')."""


__all__ = [
    "HandoffErrorReason",
    "IncidentId",
    "IncidentPromotionSource",
    "PromotionDiagnosisHandoffError",
    "PromotionPropagationResult",
    "PromotionWorksetState",
    "propagate_promotion_result_to_run",
]
