"""Request-relative binding for the scoped current-run promotion result.

ACT-K9B-HULK-PROMOTION-SCOPED-WIRE-DIALECT-CONVERGENCE01.
ACT-K9B-HULK-PROMOTION-SCOPED-CLIENT-TYPED-HTTP-SEAM01.

:class:`BoundScopedPromotionResult` binds a validated
:class:`IncidentPromotionResult` to the
:class:`PromoteAlertSignalsRequest` that produced it.

The scoped path (``POST /api/internal/incidents/promote-alert-signals``)
returns the canonical camelCase ``IncidentPromotionResult.to_wire_dict()``
contract. This binding type is the consumer-facing typed value for
that endpoint. It MUST NOT be wired to the legacy
``/promote-candidates`` endpoint, which uses the snake_case
``PromotionResponse`` shape.

Aggregate semantics (not per-signal outcome accounting)
--------------------------------------------------------

The canonical scoped wire is **aggregate**: it carries the
scanned signal IDs, four per-category incident ID lists, and the
skipped/failed signal IDs. It does NOT carry a per-signal
``record.outcome`` mapping. ``BoundScopedPromotionResult``
therefore proves the following aggregate properties and nothing
more:

* run identity match between request and response;
* source identity match between request and response;
* non-empty request scope;
* exact scanned-signal scope match in stable first-occurrence
  order;
* subset and disjoint invariants over ``skipped_signal_ids`` and
  ``failures[*].signal_id`` (these are the only two ID lists that
  retain signal identity);
* all aggregate category invariants enforced by the parser
  (pairwise disjoint categories, ``actionableIncidentIds`` matches
  opened plus materially changed, every ID is a safe bounded
  string).

The binding does NOT independently prove that every requested
signal had a per-signal incident disposition. The fact that 29
signals converge on one canonical incident lives inside the
backend execution and is erased by the aggregate response.

Authoritative success:

* every invariant above holds,
* wire parsing via :meth:`IncidentPromotionResult.from_wire_dict`
  already passed,
* all category invariants enforced by the parser hold.

Scoped aggregate successful zero: ``request.signal_ids`` is
non-empty, ``result.scanned_signal_ids`` exactly equals the
request, and ``actionable_incident_ids`` is empty. The transport
MUST have completed and the body MUST have parsed successfully;
``204 No Content`` / empty / unknown shapes are NOT aggregate
successful zero.
"""

from __future__ import annotations

from dataclasses import dataclass

from .domain.identifiers import AlertSignalId
from .domain.incident_lifecycle import IncidentId
from .incident_alert_promotion_contract import (
    IncidentPromotionResult,
    PromoteAlertSignalsRequest,
    PromotionScopeError,
)


@dataclass(frozen=True, slots=True)
class BoundScopedPromotionResult:
    """A :class:`IncidentPromotionResult` bound to its producing request.

    Construction enforces the run/source identity match, the
    exact scanned-signal scope match, the non-empty request
    scope, and the subset/disjoint rules over
    ``skipped_signal_ids`` and ``failures``. There is no public
    ``validate_*`` step -- an unbound instance cannot exist.
    """

    request: PromoteAlertSignalsRequest
    result: IncidentPromotionResult

    def __post_init__(self) -> None:
        if not isinstance(self.request, PromoteAlertSignalsRequest):
            raise PromotionScopeError(
                "BoundScopedPromotionResult.request MUST be a "
                "PromoteAlertSignalsRequest"
            )
        if not isinstance(self.result, IncidentPromotionResult):
            raise PromotionScopeError(
                "BoundScopedPromotionResult.result MUST be an "
                "IncidentPromotionResult"
            )

        # 1. Run and source identity MUST match between request
        # and response.
        if self.result.run_id != self.request.run_id:
            raise PromotionScopeError(
                "scoped promotion result.run_id MUST equal "
                "request.run_id"
            )
        if self.result.source_identity != self.request.source_identity:
            raise PromotionScopeError(
                "scoped promotion result.source_identity MUST equal "
                "request.source_identity"
            )

        # 2. The request scope MUST be non-empty. A zero-signal
        # request does NOT produce a bound successful promotion.
        if not self.request.signal_ids:
            raise PromotionScopeError(
                "scoped promotion request.signal_ids MUST be non-empty; "
                "empty requests belong to the no-promotion path"
            )

        # 3. The response MUST cover exactly the requested
        # signals in stable first-occurrence order: equal length,
        # equal content, no requested signal silently disappearing,
        # no unrequested signal present.
        if self.result.scanned_signal_ids != self.request.signal_ids:
            raise PromotionScopeError(
                "scoped promotion result.scanned_signal_ids MUST equal "
                "request.signal_ids exactly"
            )

        # 4. ``skipped_signal_ids`` is a subset of the request.
        # Compare on the typed ``AlertSignalId`` value directly so
        # equality semantics are owned by the typed wrapper, not by
        # an accidental ``str(...)`` coercion at the boundary.
        requested_signal_set = set(self.request.signal_ids)
        skipped_signal_set = set(self.result.skipped_signal_ids)
        if not skipped_signal_set.issubset(requested_signal_set):
            outside = sorted(
                str(value) for value in skipped_signal_set - requested_signal_set
            )
            raise PromotionScopeError(
                "scoped promotion result.skipped_signal_ids contains "
                f"IDs outside the request scope: {outside}"
            )

        # 5. Every ``failures[*].signal_id`` is a subset of the
        # request. Compare on the typed ``AlertSignalId`` value
        # directly; ``str(...)`` coercion is reserved for logging
        # and JSON projection.
        failure_signal_set = {
            failure.signal_id for failure in self.result.failures
        }
        if not failure_signal_set.issubset(requested_signal_set):
            outside = sorted(
                str(value) for value in failure_signal_set - requested_signal_set
            )
            raise PromotionScopeError(
                "scoped promotion result.failures contains signalIds "
                f"outside the request scope: {outside}"
            )

        # 6. ``skipped_signal_ids`` and failure signal IDs MUST be
        # disjoint: a signal cannot be both skipped and failed in
        # the same atomic request.
        overlap = skipped_signal_set & failure_signal_set
        if overlap:
            raise PromotionScopeError(
                "scoped promotion result has overlapping skipped and "
                f"failed signal IDs: {sorted(str(value) for value in overlap)}"
            )

    @property
    def actionable_incident_ids(self) -> tuple[IncidentId, ...]:
        """The diagnosis-handoff projection from the bound result.

        Defined as the stable first-occurrence union of
        ``opened_incident_ids`` and ``materially_changed_incident_ids``.
        Excludes refreshed, unchanged, skipped, and failed outcomes.

        The return type is the typed ``IncidentId`` sequence, not a
        loose ``object`` tuple; every consumer that traverses this
        list gets the bounded wrapper.
        """
        return self.result.actionable_incident_ids

    @property
    def requested_signal_count(self) -> int:
        """Number of distinct requested signal IDs."""
        return len(self.request.signal_ids)

    @property
    def requested_signal_ids(self) -> tuple[AlertSignalId, ...]:
        """Typed requested signal IDs."""
        return self.request.signal_ids


__all__ = ["BoundScopedPromotionResult"]
