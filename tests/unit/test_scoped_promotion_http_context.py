"""Tests for the typed scoped HTTP request context and success variant.

ACT-K9B-HULK-PROMOTION-SCOPED-DISPATCH-ACTIVATION-AND-CERTAINTY01.

Covers the bounded identity separation between ``run_id`` (domain)
and ``request_id`` (transport correlation) and the typed invariants
on ``ScopedPromotionHttpRequestContext``.

The single canonical request authority is
:class:`PromoteAlertSignalsRequest`; the context wraps it directly.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpObservation,
    PromotionResponseDecodingStage,
    RequestTransmissionState,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    MAX_REQUEST_ID_LENGTH,
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpSucceeded,
)
from k8s_diag_agent.domain.identifiers import AlertSignalId, HealthRunId
from k8s_diag_agent.domain.incident_lifecycle import IncidentId
from k8s_diag_agent.incident_alert_promotion_binding import (
    BoundScopedPromotionResult,
)
from k8s_diag_agent.incident_alert_promotion_contract import (
    IncidentPromotionResult,
    PromoteAlertSignalsRequest,
)


def _observation() -> PromotionHttpObservation:
    return PromotionHttpObservation(
        request_id="req-001",
        request_transmission=RequestTransmissionState.RESPONSE_COMPLETED,
        status_code=200,
        content_type="application/json",
        declared_content_length=128,
        response_byte_count=128,
        response_body_sha256="abc123",
        decoding_stage=PromotionResponseDecodingStage.COMPLETED,
        elapsed_milliseconds=12,
    )


def _request(
    *,
    signal_ids: tuple[str, ...] = ("sig-A",),
) -> PromoteAlertSignalsRequest:
    return PromoteAlertSignalsRequest(
        run_id=HealthRunId("run-001"),
        source_identity="source-A",
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )


def _bound() -> BoundScopedPromotionResult:
    request = _request()
    result = IncidentPromotionResult(
        run_id=request.run_id,
        source_identity=request.source_identity,
        scanned_signal_ids=tuple(
            AlertSignalId(value) for value in request.signal_ids
        ),
        opened_incident_ids=(IncidentId("inc-001"),),
    )
    return BoundScopedPromotionResult(request=request, result=result)


class TestScopedPromotionHttpRequestContext:
    def test_minimal_context_construction(self) -> None:
        request = _request()
        ctx = ScopedPromotionHttpRequestContext(
            request=request,
            request_id="req-001",
        )
        # Single canonical request authority: the same object
        # flows through every accessor without reconstruction.
        assert ctx.request is request
        assert ctx.run_id is request.run_id
        assert ctx.source_identity == request.source_identity
        assert ctx.signal_ids == request.signal_ids

    def test_run_and_request_id_remain_distinct(self) -> None:
        request = _request()
        ctx = ScopedPromotionHttpRequestContext(
            request=request,
            request_id="req-001",
        )
        assert str(ctx.run_id) != ctx.request_id
        assert isinstance(ctx.run_id, str)
        assert isinstance(ctx.request_id, str)
        # ``request_id`` MUST never be promoted into the request
        # payload -- it is a transport correlation identity.
        assert ctx.request.run_id == HealthRunId("run-001")

    def test_empty_request_id_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ScopedPromotionHttpRequestContext(
                request=_request(),
                request_id="",
            )
        assert "request_id" in str(exc_info.value)

    def test_overlong_request_id_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ScopedPromotionHttpRequestContext(
                request=_request(),
                request_id="r" * (MAX_REQUEST_ID_LENGTH + 1),
            )
        assert "request_id" in str(exc_info.value)

    def test_non_request_type_rejected(self) -> None:
        with pytest.raises(TypeError) as exc_info:
            ScopedPromotionHttpRequestContext(
                request="not a PromoteAlertSignalsRequest",  # type: ignore[arg-type]
                request_id="req-001",
            )
        assert "PromoteAlertSignalsRequest" in str(exc_info.value)

    def test_request_id_propagates_into_observation(self) -> None:
        ctx = ScopedPromotionHttpRequestContext(
            request=_request(),
            request_id="req-correlation-12345",
        )
        observation = PromotionHttpObservation(
            request_id=ctx.request_id,
            request_transmission=RequestTransmissionState.RESPONSE_COMPLETED,
            status_code=200,
            content_type="application/json",
            declared_content_length=64,
            response_byte_count=64,
            response_body_sha256=None,
            decoding_stage=PromotionResponseDecodingStage.COMPLETED,
            elapsed_milliseconds=10,
        )
        assert observation.request_id == "req-correlation-12345"


class TestScopedPromotionHttpSucceeded:
    def test_succeeded_holds_observation_and_bound(self) -> None:
        observation = _observation()
        bound = _bound()
        outcome = ScopedPromotionHttpSucceeded(
            observation=observation,
            bound=bound,
        )
        assert outcome.observation is observation
        assert outcome.bound is bound
        assert outcome.bound.actionable_incident_ids == (
            IncidentId("inc-001"),
        )
