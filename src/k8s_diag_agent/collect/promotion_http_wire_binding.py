"""Request-relative binding for the strict wire result.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B.

``BoundPromotionHttpWireResult`` binds a validated
:class:`PromotionHttpWireResult` to the request that produced it.
The exact coverage is enforced in ``__post_init__`` so an unbound
instance cannot exist.

Coverage rule:

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
from .promotion_http_wire_types import PromotionHttpWireValidationError


@dataclass(frozen=True, slots=True)
class BoundPromotionHttpWireResult:
    """A :class:`PromotionHttpWireResult` bound to its request.

    Construction enforces the exact coverage invariant in
    ``__post_init__``. There is no public ``validate_*`` step --
    an unbound instance cannot exist.
    """

    result: PromotionHttpWireResult
    requested_signal_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.result, PromotionHttpWireResult):
            raise PromotionHttpWireValidationError(
                "BoundPromotionHttpWireResult.result MUST be a "
                "PromotionHttpWireResult"
            )
        if not isinstance(self.requested_signal_ids, tuple):
            raise PromotionHttpWireValidationError(
                "requested_signal_ids MUST be a tuple"
            )
        for signal_id in self.requested_signal_ids:
            if not isinstance(signal_id, str) or not signal_id:
                raise PromotionHttpWireValidationError(
                    "requested_signal_ids MUST contain non-empty strings"
                )
        # Construction-time coverage validation: every requested
        # signal must be categorised exactly once.
        requested_list = list(self.requested_signal_ids)
        if len(set(requested_list)) != len(requested_list):
            raise PromotionHttpWireValidationError(
                "requested_signal_ids MUST be unique"
            )
        categorised = sorted(
            record.source_candidate_id
            for record in self.result.promotion_records
        )
        if categorised != sorted(requested_list):
            raise PromotionHttpWireValidationError(
                "promotion_records MUST cover exactly the requested "
                "signal IDs"
            )

    @property
    def requested_signal_count(self) -> int:
        """Number of distinct requested signal IDs."""
        return len(self.requested_signal_ids)

    def categorised_source_ids(self) -> tuple[str, ...]:
        """Source candidate IDs from every record, in input order."""
        return tuple(
            record.source_candidate_id for record in self.result.promotion_records
        )


__all__ = ["BoundPromotionHttpWireResult"]
