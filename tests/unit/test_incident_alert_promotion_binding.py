"""Tests for :class:`BoundScopedPromotionResult`.

ACT-K9B-HULK-PROMOTION-SCOPED-WIRE-DIALECT-CONVERGENCE01.

Covers the request-relative binding invariants:

* run/source identity match between request and response;
* non-empty request scope;
* ``scanned_signal_ids`` exactly match the requested signals in
  stable first-occurrence order;
* ``skipped_signal_ids`` and ``failures[*].signal_id`` are
  subsets of the request;
* the two ID collections above are disjoint;
* the actionable incident projection excludes refreshed and
  unchanged outcomes;
* successful zero (every request has a categorisation record;
  ``actionable_incident_ids`` is empty) is allowed and bound.

Also exercises an end-to-end producer-to-client roundtrip at the
typed contract level (no actual backend artefacts are required):
a hand-built typed ``IncidentPromotionResult`` is serialised via
``to_wire_dict``, parsed via ``from_wire_dict``, and bound to its
producing request with zero hand-authored intermediate
dictionaries.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from k8s_diag_agent.domain.identifiers import AlertSignalId, HealthRunId
from k8s_diag_agent.domain.incident_lifecycle import IncidentId
from k8s_diag_agent.incident_alert_promotion_binding import (
    BoundScopedPromotionResult,
)
from k8s_diag_agent.incident_alert_promotion_contract import (
    IncidentPromotionFailure,
    IncidentPromotionResult,
    PromoteAlertSignalsRequest,
    PromotionScopeError,
)


def _request(
    *,
    run_id: str = "run-001",
    source_identity: str = "source-A",
    signal_ids: tuple[str, ...] = ("sig-001",),
) -> PromoteAlertSignalsRequest:
    return PromoteAlertSignalsRequest(
        run_id=HealthRunId(run_id),
        source_identity=source_identity,
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )


def _result_from_request(
    request: PromoteAlertSignalsRequest,
    **overrides: Any,
) -> IncidentPromotionResult:
    """Build a result whose run/source identity matches the request."""
    base: dict[str, Any] = {
        "run_id": request.run_id,
        "source_identity": request.source_identity,
        "scanned_signal_ids": tuple(
            AlertSignalId(value) for value in request.signal_ids
        ),
    }
    base.update(overrides)
    return IncidentPromotionResult(**base)


class TestRunAndSourceIdentity:
    def test_match_binds(self) -> None:
        request = _request(
            run_id="run-001",
            source_identity="source-A",
            signal_ids=("sig-001",),
        )
        result = _result_from_request(
            request,
            opened_incident_ids=(IncidentId("inc-001"),),
        )
        bound = BoundScopedPromotionResult(request=request, result=result)
        assert bound.requested_signal_count == 1
        assert bound.actionable_incident_ids == (IncidentId("inc-001"),)

    def test_run_id_mismatch_raises(self) -> None:
        request = _request(
            run_id="run-001",
            source_identity="source-A",
            signal_ids=("sig-001",),
        )
        result = _result_from_request(
            request,
            run_id=HealthRunId("run-different"),
        )
        with pytest.raises(PromotionScopeError) as exc_info:
            BoundScopedPromotionResult(request=request, result=result)
        assert "run_id" in str(exc_info.value)

    def test_source_identity_mismatch_raises(self) -> None:
        request = _request(
            run_id="run-001",
            source_identity="source-A",
            signal_ids=("sig-001",),
        )
        result = _result_from_request(
            request,
            source_identity="source-B",
        )
        with pytest.raises(PromotionScopeError) as exc_info:
            BoundScopedPromotionResult(request=request, result=result)
        assert "source_identity" in str(exc_info.value)


class TestNonEmptyScope:
    def test_empty_request_signal_ids_rejected(self) -> None:
        """A zero-signal request MUST NOT produce a bound successful
        promotion; it belongs to the no-promotion path.

        The dataclass ``__post_init__`` would also reject empty
        ``signal_ids`` here, but the binding layer is the
        consumer-facing gate that rejects the empty scope after
        the contract dataclass has been relaxed via
        ``object.__setattr__`` for this test.
        """
        request = _request(signal_ids=("sig-001",))
        # Force an empty signal_ids tuple by bypassing the
        # ``__post_init__`` validator.
        empty_request = object.__new__(PromoteAlertSignalsRequest)
        object.__setattr__(empty_request, "run_id", request.run_id)
        object.__setattr__(
            empty_request, "source_identity", request.source_identity
        )
        object.__setattr__(empty_request, "signal_ids", ())
        result = _result_from_request(empty_request)
        with pytest.raises(PromotionScopeError) as exc_info:
            BoundScopedPromotionResult(request=empty_request, result=result)
        assert "non-empty" in str(exc_info.value).lower()


class TestScannedSignalScope:
    def test_scanned_matches_request_in_order(self) -> None:
        request = _request(
            signal_ids=("sig-A", "sig-B", "sig-C"),
        )
        result = _result_from_request(request)
        bound = BoundScopedPromotionResult(request=request, result=result)
        assert (
            tuple(str(value) for value in result.scanned_signal_ids)
            == ("sig-A", "sig-B", "sig-C")
        )
        assert bound.requested_signal_count == 3

    def test_missing_requested_signal_raises(self) -> None:
        request = _request(
            signal_ids=("sig-A", "sig-B", "sig-C"),
        )
        # Drop the last signal from the response.
        result = _result_from_request(
            request,
            scanned_signal_ids=(
                AlertSignalId("sig-A"),
                AlertSignalId("sig-B"),
            ),
        )
        with pytest.raises(PromotionScopeError) as exc_info:
            BoundScopedPromotionResult(request=request, result=result)
        assert "scanned_signal_ids" in str(exc_info.value)

    def test_extra_scanned_signal_raises(self) -> None:
        request = _request(signal_ids=("sig-A",))
        result = _result_from_request(
            request,
            scanned_signal_ids=(
                AlertSignalId("sig-A"),
                AlertSignalId("sig-extra"),
            ),
        )
        with pytest.raises(PromotionScopeError) as exc_info:
            BoundScopedPromotionResult(request=request, result=result)
        assert "scanned_signal_ids" in str(exc_info.value)

    def test_scanned_order_mismatch_raises(self) -> None:
        # Order is authoritative: a sorted-by-name response is not
        # acceptable when the request ordered the signals.
        request = _request(signal_ids=("sig-A", "sig-B", "sig-C"))
        result = _result_from_request(
            request,
            scanned_signal_ids=(
                AlertSignalId("sig-A"),
                AlertSignalId("sig-C"),
                AlertSignalId("sig-B"),
            ),
        )
        with pytest.raises(PromotionScopeError):
            BoundScopedPromotionResult(request=request, result=result)


class TestSkippedAndFailureSubset:
    def test_skipped_signal_subset_passes(self) -> None:
        request = _request(signal_ids=("sig-A", "sig-B"))
        result = _result_from_request(
            request,
            skipped_signal_ids=(AlertSignalId("sig-B"),),
        )
        BoundScopedPromotionResult(request=request, result=result)

    def test_skipped_signal_outside_request_rejected(self) -> None:
        request = _request(signal_ids=("sig-A",))
        result = _result_from_request(
            request,
            skipped_signal_ids=(AlertSignalId("sig-rogue"),),
        )
        with pytest.raises(PromotionScopeError) as exc_info:
            BoundScopedPromotionResult(request=request, result=result)
        assert "skipped_signal_ids" in str(exc_info.value)

    def test_failure_signal_subset_passes(self) -> None:
        request = _request(signal_ids=("sig-A", "sig-B"))
        result = _result_from_request(
            request,
            failures=(
                IncidentPromotionFailure(
                    signal_id=AlertSignalId("sig-A"),
                    reason_code="upstream_timeout",
                ),
            ),
        )
        BoundScopedPromotionResult(request=request, result=result)

    def test_failure_signal_outside_request_rejected(self) -> None:
        request = _request(signal_ids=("sig-A",))
        result = _result_from_request(
            request,
            failures=(
                IncidentPromotionFailure(
                    signal_id=AlertSignalId("sig-rogue"),
                    reason_code="upstream_timeout",
                ),
            ),
        )
        with pytest.raises(PromotionScopeError) as exc_info:
            BoundScopedPromotionResult(request=request, result=result)
        assert "failures" in str(exc_info.value)

    def test_skipped_and_failed_overlap_rejected(self) -> None:
        """A signal cannot be both skipped and failed in the same
        atomic request.
        """
        request = _request(signal_ids=("sig-A",))
        result = _result_from_request(
            request,
            skipped_signal_ids=(AlertSignalId("sig-A"),),
            failures=(
                IncidentPromotionFailure(
                    signal_id=AlertSignalId("sig-A"),
                    reason_code="upstream_timeout",
                ),
            ),
        )
        with pytest.raises(PromotionScopeError) as exc_info:
            BoundScopedPromotionResult(request=request, result=result)
        assert "overlap" in str(exc_info.value)


class TestActionableProjection:
    def test_actionable_ids_excludes_refreshed_and_unchanged(self) -> None:
        request = _request(
            signal_ids=("sig-A", "sig-B", "sig-C"),
        )
        result = _result_from_request(
            request,
            opened_incident_ids=(IncidentId("inc-opened"),),
            materially_changed_incident_ids=(IncidentId("inc-changed"),),
            observation_refreshed_incident_ids=(IncidentId("inc-refresh"),),
            unchanged_incident_ids=(IncidentId("inc-unchanged"),),
        )
        bound = BoundScopedPromotionResult(request=request, result=result)
        # Stable first-occurrence union of opened + materially changed.
        assert bound.actionable_incident_ids == (
            IncidentId("inc-opened"),
            IncidentId("inc-changed"),
        )

    def test_successful_zero_binds_with_empty_actionable(self) -> None:
        request = _request(signal_ids=("sig-A", "sig-B"))
        result = _result_from_request(
            request,
            unchanged_incident_ids=(
                IncidentId("inc-existing-A"),
                IncidentId("inc-existing-B"),
            ),
        )
        bound = BoundScopedPromotionResult(request=request, result=result)
        assert bound.actionable_incident_ids == ()


class TestProducerToClientRoundtrip:
    """Producer-to-client compatibility at the typed contract level.

    Builds a typed ``IncidentPromotionResult``, serialises it via
    ``to_wire_dict`` (the canonical camelCase backend producer),
    parses the wire dict back via ``from_wire_dict`` (the strict
    scoped decoder), and binds the parsed result to the original
    ``PromoteAlertSignalsRequest``. No hand-authored intermediate
    dictionaries are involved; every dict on the wire is owned by
    the canonical ``IncidentPromotionResult`` contract.
    """

    def test_roundtrip_through_canonical_wire_dict(self) -> None:
        request = _request(
            run_id="run-001",
            source_identity="source-A",
            signal_ids=("sig-A", "sig-B"),
        )
        typed = _result_from_request(
            request,
            opened_incident_ids=(IncidentId("inc-opened"),),
            observation_refreshed_incident_ids=(IncidentId("inc-refresh"),),
        )
        # Producer.
        wire: Mapping[str, object] = typed.to_wire_dict()
        # Client decoder.
        parsed = IncidentPromotionResult.from_wire_dict(wire)
        # Bind.
        bound = BoundScopedPromotionResult(request=request, result=parsed)
        assert bound.requested_signal_count == 2
        assert bound.actionable_incident_ids == (IncidentId("inc-opened"),)
        # The roundtrip preserves the actionable projection.
        assert bound.result.actionable_incident_ids == (
            IncidentId("inc-opened"),
        )

    def test_29_signal_many_to_one_production_shape(self) -> None:
        """29 signals converge on one canonical incident.

        Producer: ``IncidentPromotionResult`` with one opened
        incident for sig-000; the remaining 28 signals are
        observation-only refreshes of the same canonical incident.
        Per the scoped contract each canonical incident has ONE
        category (the most severe), so the refreshed category list
        is empty here (the opened signal wins).

        The full roundtrip exercises the canonical contract with
        zero hand-authored intermediate dicts.
        """
        signal_ids = tuple(f"sig-{i:03d}" for i in range(29))
        request = _request(
            run_id="run-001",
            source_identity="source-A",
            signal_ids=signal_ids,
        )
        typed = _result_from_request(
            request,
            opened_incident_ids=(IncidentId("canonical-inc-001"),),
        )
        parsed = IncidentPromotionResult.from_wire_dict(typed.to_wire_dict())
        assert parsed.scanned_signal_ids == tuple(
            AlertSignalId(value) for value in signal_ids
        )
        bound = BoundScopedPromotionResult(request=request, result=parsed)
        assert bound.requested_signal_count == 29
        assert bound.actionable_incident_ids == (
            IncidentId("canonical-inc-001"),
        )

    def test_34_signal_production_shape(self) -> None:
        """34 signals converge on two canonical incidents.

        Two canonical incidents are opened (canonical-inc-001 from
        sig-000, canonical-inc-002 from sig-001); the remaining 32
        signals are observation-only refreshes of canonical-inc-002.
        Per the scoped contract each canonical incident has ONE
        category (the most severe), so the refreshed category list
        is empty here.
        """
        signal_ids = tuple(f"sig-{i:03d}" for i in range(34))
        request = _request(
            run_id="run-001",
            source_identity="source-A",
            signal_ids=signal_ids,
        )
        typed = _result_from_request(
            request,
            opened_incident_ids=(
                IncidentId("canonical-inc-001"),
                IncidentId("canonical-inc-002"),
            ),
        )
        parsed = IncidentPromotionResult.from_wire_dict(typed.to_wire_dict())
        assert parsed.scanned_signal_ids == tuple(
            AlertSignalId(value) for value in signal_ids
        )
        bound = BoundScopedPromotionResult(request=request, result=parsed)
        assert bound.requested_signal_count == 34
        assert bound.actionable_incident_ids == (
            IncidentId("canonical-inc-001"),
            IncidentId("canonical-inc-002"),
        )
