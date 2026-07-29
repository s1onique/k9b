"""Request-relative binding for the strict wire result.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B-CORRECTION01.

:class:`BoundPromotionHttpWireResult` binds a validated
:class:`PromotionHttpWireResult` to the request that produced it.

The bound type is **success-only**:

* ``result.ok`` MUST be ``True``. A backend rejection enters a
  different typed disposition; it cannot enter the
  :class:`BoundPromotionHttpWireResult` success path.

The bound type is **request-counter matched**:

* ``result.scanned`` MUST equal ``len(requested_signal_ids)``.
* ``result.unique_candidate_count`` MUST equal
  ``len(requested_signal_ids)``.
* ``len(result.promotion_records)`` MUST equal
  ``len(requested_signal_ids)`` (one-record-per-request).

The bound type is **exact-coverage**:

* every requested signal ID is represented in
  ``promotion_records`` exactly once (via ``source_candidate_id``);
* no unrequested signal appears in the records.

This permits multiple alert observations to converge on one
canonical incident (the 1-inserted / 28-identity-matched
production case): the unique constraint applies to
``source_candidate_id`` only, never to ``canonical_incident_id``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .promotion_http_wire_decode import PromotionHttpWireResult
from .promotion_http_wire_semantics import validate_identifier_tuple
from .promotion_http_wire_types import PromotionHttpWireValidationError


@dataclass(frozen=True, slots=True)
class BoundPromotionHttpWireResult:
    """A :class:`PromotionHttpWireResult` bound to its request.

    Construction enforces the success-only, counter-matched, and
    exact-coverage invariants in ``__post_init__``. There is no
    public ``validate_*`` step -- an unbound instance cannot
    exist.
    """

    result: PromotionHttpWireResult
    requested_signal_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.result, PromotionHttpWireResult):
            raise PromotionHttpWireValidationError(
                "BoundPromotionHttpWireResult.result MUST be a "
                "PromotionHttpWireResult"
            )

        # 1. SUCCESS-ONLY ----------------------------------------------
        # The bound type is an authoritative successful wire
        # result. A backend rejection must enter a different typed
        # disposition (e.g. PromotionHttpRejected) and is never
        # permitted here.
        if not self.result.ok:
            raise PromotionHttpWireValidationError(
                "BoundPromotionHttpWireResult requires ok=True; "
                "backend rejections MUST enter a different typed "
                "disposition"
            )

        # 2. REQUEST-COUNTER MATCHED -----------------------------------
        validate_identifier_tuple(
            self.requested_signal_ids,
            field_name="requested_signal_ids",
        )
        expected_count = len(self.requested_signal_ids)
        if self.result.scanned != expected_count:
            raise PromotionHttpWireValidationError(
                f"scanned MUST equal request count: "
                f"{self.result.scanned} != {expected_count}"
            )
        if self.result.unique_candidate_count != expected_count:
            raise PromotionHttpWireValidationError(
                f"unique_candidate_count MUST equal request count: "
                f"{self.result.unique_candidate_count} != {expected_count}"
            )
        if len(self.result.promotion_records) != expected_count:
            raise PromotionHttpWireValidationError(
                f"promotion_records count MUST equal request count: "
                f"{len(self.result.promotion_records)} != {expected_count}"
            )

        # 3. EXACT COVERAGE (one record per requested signal) ---------
        if len(set(self.requested_signal_ids)) != len(self.requested_signal_ids):
            raise PromotionHttpWireValidationError(
                "requested_signal_ids MUST be unique"
            )
        categorised = sorted(
            record.source_candidate_id
            for record in self.result.promotion_records
        )
        if categorised != sorted(self.requested_signal_ids):
            raise PromotionHttpWireValidationError(
                "promotion_records MUST cover exactly the requested "
                "signal IDs"
            )

    @property
    def requested_signal_count(self) -> int:
        """Number of distinct requested signal IDs."""
        return len(self.requested_signal_ids)

    def categorised_source_ids(self) -> tuple[str, ...]:
        """Source candidate IDs from every record, in record order."""
        return tuple(
            record.source_candidate_id for record in self.result.promotion_records
        )


__all__ = ["BoundPromotionHttpWireResult"]
