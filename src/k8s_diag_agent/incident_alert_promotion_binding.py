"""Request-relative binding for the scoped current-run promotion result.

ACT-K9B-HULK-PROMOTION-SCOPED-WIRE-DIALECT-CONVERGENCE01.

:class:`BoundScopedPromotionResult` binds a validated
:class:`IncidentPromotionResult` to the
:class:`PromoteAlertSignalsRequest` that produced it.

The scoped path (``POST /api/internal/incidents/promote-alert-signals``)
returns the canonical camelCase ``IncidentPromotionResult.to_wire_dict()``
contract. This binding type is the consumer-facing typed value for
that endpoint. It MUST NOT be wired to the legacy
``/promote-candidates`` endpoint, which uses the snake_case
``PromotionResponse`` shape.

Construction invariants:

* ``result.run_id == request.run_id``.
* ``result.source_identity == request.source_identity``.
* ``request.signal_ids`` is non-empty (a zero-signal request does
  NOT produce a bound successful promotion; it belongs to the
  no-promotion path).
* ``result.scanned_signal_ids`` is exactly the requested signal
  IDs in stable first-occurrence order: equal length, equal
  content, no requested signal silently disappearing, no
  unrequested signal present.
* ``result.skipped_signal_ids`` is a subset of ``request.signal_ids``.
* ``result.failures[*].signal_id`` is a subset of
  ``request.signal_ids``.
* ``result.skipped_signal_ids`` and
  ``set(result.failures[*].signal_id)`` are disjoint -- a signal
  cannot be both skipped and failed in the same atomic request.
* The backend producer preserves the request signal order, so
  ordered equality is enforced. Order is authoritative.

Authoritative success:

* every invariant above holds,
* wire parsing via :meth:`IncidentPromotionResult.from_wire_dict`
  already passed,
* all category invariants enforced by the parser (pairwise
  disjoint categories, ``actionableIncidentIds`` matches opened
  plus materially changed, every ID is a safe bounded string)
  hold.

A successful zero is allowed: every request has a categorisation
record, but ``actionable_incident_ids`` is empty when the result
contains only refreshed, unchanged, or skipped outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass

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
        requested_set = set(self.request.signal_ids)
        skipped_set = set(self.result.skipped_signal_ids)
        if not skipped_set.issubset(requested_set):
            outside = sorted(
                str(value) for value in skipped_set - requested_set
            )
            raise PromotionScopeError(
                "scoped promotion result.skipped_signal_ids contains "
                f"IDs outside the request scope: {outside}"
            )

        # 5. Every ``failures[*].signal_id`` is a subset of the
        # request.
        failure_signal_set = {
            str(failure.signal_id) for failure in self.result.failures
        }
        if not failure_signal_set.issubset(requested_set):
            outside = sorted(failure_signal_set - requested_set)
            raise PromotionScopeError(
                "scoped promotion result.failures contains signalIds "
                f"outside the request scope: {outside}"
            )

        # 6. ``skipped_signal_ids`` and failure signal IDs MUST be
        # disjoint: a signal cannot be both skipped and failed in
        # the same atomic request.
        overlap = skipped_set & failure_signal_set
        if overlap:
            raise PromotionScopeError(
                "scoped promotion result has overlapping skipped and "
                f"failed signal IDs: {sorted(str(value) for value in overlap)}"
            )

    @property
    def actionable_incident_ids(self) -> tuple[object, ...]:
        """The diagnosis-handoff projection from the bound result.

        Defined as the stable first-occurrence union of
        ``opened_incident_ids`` and ``materially_changed_incident_ids``.
        Excludes refreshed, unchanged, skipped, and failed outcomes.
        """
        return self.result.actionable_incident_ids

    @property
    def requested_signal_count(self) -> int:
        """Number of distinct requested signal IDs."""
        return len(self.request.signal_ids)


__all__ = ["BoundScopedPromotionResult"]
