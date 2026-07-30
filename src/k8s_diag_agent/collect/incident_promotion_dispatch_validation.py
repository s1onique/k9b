"""Strict response validation for the dispatcher.

ACT-K9B-HULK-PROMOTION-DISPATCHER-RESPONSIBILITY-SPLIT01.

This module owns the SINGLE strict R4 validation contract that the
backend-mode dispatcher enforces before any state mutation.  The
fail-closed invariants:

* ``promotion_mode == 'backend-api'``: reject synthesized
  ``<aggregate>`` source IDs -- every record MUST map back to a real
  candidate/incident pair (no inferred placeholders).
* Any ``promotion_outcome`` not in the allowed set raises.
* Non-zero opened/updated counts require at least one
  ``canonical_incident_id`` on ``promotion_records``.
* Empty ``promotion_records`` is permitted only when both opened and
  updated counts are zero.

``PromotionResponseValidationError`` is the typed contract raised
when any invariant fails.  The active scoped dispatcher does NOT
consume this validator -- it consumes the closed typed handoff
directly.
"""

from __future__ import annotations

from .incident_promotion_dispatch_constants import MODE_BACKEND_API


class PromotionResponseValidationError(ValueError):
    """Raised when a promotion response payload is fail-closed invalid.

    The strict backend contract (R4 task 8) rejects:

    * Malformed ``promotion_outcome`` values not in the typed enum.
    * Missing ``canonical_incident_id`` for non-zero opened/updated
      counts.
    * Synthesized ``<aggregate>`` candidate IDs in strict backend mode.

    These errors MUST surface as typed contracts so the orchestrator
    can detect dispatcher regressions deterministically.
    """

    def __init__(
        self,
        message: str,
        *,
        promotion_records: tuple[dict[str, str | None], ...] = (),
        opened_incident_ids: tuple[str, ...] = (),
        updated_incident_ids: tuple[str, ...] = (),
        promotion_mode: str = "",
    ) -> None:
        super().__init__(message)
        self.promotion_records = promotion_records
        self.opened_incident_ids = opened_incident_ids
        self.updated_incident_ids = updated_incident_ids
        self.promotion_mode = promotion_mode


_ALLOWED_PROMOTION_OUTCOMES: frozenset[str] = frozenset({
    "opened",
    "updated",
    "skipped_duplicate",
    "noop",
})


def validate_promotion_response_records(
    *,
    promotion_mode: str,
    promotion_records: tuple[dict[str, str | None], ...],
    opened_incident_ids: tuple[str, ...] = (),
    updated_incident_ids: tuple[str, ...] = (),
) -> None:
    """Validate a promotion response payload under the strict R4 contract.

    Failure modes:

    * ``promotion_mode == 'backend-api'``: reject synthesized
      ``<aggregate>`` source IDs -- every record MUST map back to a
      real candidate/incident pair (no inferred placeholders).
    * Any ``promotion_outcome`` not in the allowed set raises.
    * Non-zero opened/updated counts require at least one
      ``canonical_incident_id`` to be carried by ``promotion_records``.
    * Empty ``promotion_records`` is permitted only when both opened
      and updated counts are zero.
    """
    if promotion_mode == MODE_BACKEND_API:
        for raw in promotion_records:
            source_id = raw.get("source_candidate_id") or ""
            if source_id.startswith("<") and source_id.endswith(">"):
                raise PromotionResponseValidationError(
                    "Backend strict contract forbids synthesized aggregate "
                    "candidate_id mapping.",
                    promotion_records=promotion_records,
                    opened_incident_ids=opened_incident_ids,
                    updated_incident_ids=updated_incident_ids,
                    promotion_mode=promotion_mode,
                )

    seen_canonical: set[str] = set()
    for raw in promotion_records:
        outcome = str(raw.get("promotion_outcome") or "")
        if outcome not in _ALLOWED_PROMOTION_OUTCOMES:
            raise PromotionResponseValidationError(
                f"Unknown promotion_outcome: {outcome!r} not in "
                f"{sorted(_ALLOWED_PROMOTION_OUTCOMES)}",
                promotion_records=promotion_records,
                opened_incident_ids=opened_incident_ids,
                updated_incident_ids=updated_incident_ids,
                promotion_mode=promotion_mode,
            )
        canonical = raw.get("canonical_incident_id")
        if canonical:
            seen_canonical.add(str(canonical))

    non_zero_counts = bool(opened_incident_ids) or bool(updated_incident_ids)
    if non_zero_counts and not seen_canonical:
        raise PromotionResponseValidationError(
            "Non-zero opened/updated counts require authoritative canonical "
            "incident IDs on promotion_records.",
            promotion_records=promotion_records,
            opened_incident_ids=opened_incident_ids,
            updated_incident_ids=updated_incident_ids,
            promotion_mode=promotion_mode,
        )


__all__ = [
    "PromotionResponseValidationError",
    "validate_promotion_response_records",
]