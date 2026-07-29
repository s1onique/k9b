"""Tests for the typed scoped HTTP request context and success variant.

ACT-K9B-HULK-PROMOTION-SCOPED-CLIENT-TYPED-HTTP-SEAM01.

Covers the bounded identity separation between ``run_id`` (domain)
and ``request_id`` (transport correlation) and the typed invariants
on ``ScopedPromotionHttpRequestContext``.
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
    MAX_SIGNAL_IDS,
    MAX_SOURCE_IDENTITY_LENGTH,
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
        ctx = ScopedPromotionHttpRequestContext(
            run_id=HealthRunId("run-001"),
            request_id="req-001",
            source_identity="source-A",
            signal_ids=(AlertSignalId("sig-A"),),
        )
        assert ctx.run_id == HealthRunId("run-001")
        assert ctx.request_id == "req-001"
        assert ctx.source_identity == "source-A"
        assert ctx.signal_ids == (AlertSignalId("sig-A"),)

    def test_empty_request_id_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ScopedPromotionHttpRequestContext(
                run_id=HealthRunId("run-001"),
                request_id="",
                source_identity="source-A",
                signal_ids=(AlertSignalId("sig-A"),),
            )
        assert "request_id" in str(exc_info.value)

    def test_overlong_request_id_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ScopedPromotionHttpRequestContext(
                run_id=HealthRunId("run-001"),
                request_id="r" * (MAX_REQUEST_ID_LENGTH + 1),
                source_identity="source-A",
                signal_ids=(AlertSignalId("sig-A"),),
            )
        assert "request_id" in str(exc_info.value)

    def test_empty_source_identity_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ScopedPromotionHttpRequestContext(
                run_id=HealthRunId("run-001"),
                request_id="req-001",
                source_identity="",
                signal_ids=(AlertSignalId("sig-A"),),
            )
        assert "source_identity" in str(exc_info.value)

    def test_overlong_source_identity_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ScopedPromotionHttpRequestContext(
                run_id=HealthRunId("run-001"),
                request_id="req-001",
                source_identity="s" * (MAX_SOURCE_IDENTITY_LENGTH + 1),
                signal_ids=(AlertSignalId("sig-A"),),
            )
        assert "source_identity" in str(exc_info.value)

    def test_empty_signal_ids_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ScopedPromotionHttpRequestContext(
                run_id=HealthRunId("run-001"),
                request_id="req-001",
                source_identity="source-A",
                signal_ids=(),
            )
        assert "signal_ids" in str(exc_info.value)

    def test_duplicate_signal_ids_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ScopedPromotionHttpRequestContext(
                run_id=HealthRunId("run-001"),
                request_id="req-001",
                source_identity="source-A",
                signal_ids=(
                    AlertSignalId("sig-A"),
                    AlertSignalId("sig-A"),
                ),
            )
        assert "unique" in str(exc_info.value)

    def test_overlimit_signal_ids_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ScopedPromotionHttpRequestContext(
                run_id=HealthRunId("run-001"),
                request_id="req-001",
                source_identity="source-A",
                signal_ids=tuple(
                    AlertSignalId(f"sig-{i:03d}")
                    for i in range(MAX_SIGNAL_IDS + 1)
                ),
            )
        assert "signal_ids" in str(exc_info.value)

    def test_non_str_signal_id_rejected(self) -> None:
        """Non-string signal IDs (e.g. ``int``) are rejected.

        Note: ``AlertSignalId`` is a ``NewType`` alias over ``str``,
        so the runtime check is against the underlying ``str`` type.
        """
        with pytest.raises(TypeError) as exc_info:
            ScopedPromotionHttpRequestContext(
                run_id=HealthRunId("run-001"),
                request_id="req-001",
                source_identity="source-A",
                signal_ids=(123,),  # type: ignore[arg-type]
            )
        assert "AlertSignalId" in str(exc_info.value)

    def test_run_and_request_id_remain_distinct(self) -> None:
        ctx = ScopedPromotionHttpRequestContext(
            run_id=HealthRunId("run-001"),
            request_id="req-001",
            source_identity="source-A",
            signal_ids=(AlertSignalId("sig-A"),),
        )
        # The two identities are distinct fields with distinct
        # semantics: ``run_id`` is a domain ``HealthRunId`` (str
        # alias), ``request_id`` is a transport correlation string.
        assert str(ctx.run_id) != ctx.request_id
        assert isinstance(ctx.run_id, str)
        assert isinstance(ctx.request_id, str)


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
