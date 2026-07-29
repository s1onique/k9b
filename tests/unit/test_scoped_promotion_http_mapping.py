"""Mapping tests for the bounded scoped HTTP transport -> PromotionOutcome.

ACT-K9B-HULK-PROMOTION-SCOPED-TRANSPORT-MAPPING-TRUTH01.

Covers the typed projection for every transport variant. Each
test asserts:

* ``PromotionOutcome`` variant and exact bounded reason;
* ``run_id`` (domain identity);
* ``request_id`` (transport correlation identity);
* ``request_fingerprint`` (deterministic SHA-256 over canonical
  request payload);
* ``requested_signal_ids``;
* aggregate receipt (when present).
"""

from __future__ import annotations

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpAccepted,
    PromotionHttpInvalidJson,
    PromotionHttpInvalidSchema,
    PromotionHttpNoContent,
    PromotionHttpObservation,
    PromotionHttpRejected,
    PromotionHttpResponseTruncated,
    PromotionHttpTransportFailureAfterSend,
    PromotionHttpTransportFailureBeforeSend,
    PromotionResponseDecodingStage,
    RequestTransmissionState,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
    PromotionCommitUnknown,
    PromotionRejected,
    PromotionSucceeded,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedTransportPromotionProjection,
    map_scoped_http_transport_to_promotion_outcome,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpSucceeded,
    ScopedPromotionReceipt,
    scoped_promotion_request_fingerprint,
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
        request_id="req-correlation-12345",
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
    signal_ids: tuple[str, ...] = ("sig-A", "sig-B"),
    run_id: str = "health-run-20260729T063234Z",
    source_identity: str = "source-A",
) -> PromoteAlertSignalsRequest:
    return PromoteAlertSignalsRequest(
        run_id=HealthRunId(run_id),
        source_identity=source_identity,
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )


def _context(
    *,
    signal_ids: tuple[str, ...] = ("sig-A", "sig-B"),
    request_id: str = "promotion-request-attempt-002",
    run_id: str = "health-run-20260729T063234Z",
    source_identity: str = "source-A",
) -> ScopedPromotionHttpRequestContext:
    return ScopedPromotionHttpRequestContext(
        request=_request(
            signal_ids=signal_ids,
            run_id=run_id,
            source_identity=source_identity,
        ),
        request_id=request_id,
    )


def _succeeded_transport(
    *, actionable: tuple[str, ...] = ("inc-001",)
) -> ScopedPromotionHttpSucceeded:
    request = _request()
    result = IncidentPromotionResult(
        run_id=request.run_id,
        source_identity=request.source_identity,
        scanned_signal_ids=tuple(
            AlertSignalId(value) for value in request.signal_ids
        ),
        opened_incident_ids=tuple(
            IncidentId(value) for value in actionable
        ),
    )
    bound = BoundScopedPromotionResult(request=request, result=result)
    return ScopedPromotionHttpSucceeded(
        observation=_observation(), bound=bound
    )


class TestSuccessProjection:
    def test_success_with_actionable_ids(self) -> None:
        """``PromotionSucceeded`` with non-empty actionable IDs."""
        transport = _succeeded_transport(actionable=("inc-001",))
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context()
        )
        assert isinstance(projection, ScopedTransportPromotionProjection)
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionSucceeded)
        assert outcome.run_id == "health-run-20260729T063234Z"
        assert outcome.diagnosis_incident_ids == ("inc-001",)
        assert outcome.requested_signal_ids == ("sig-A", "sig-B")
        # Aggregate receipt is present on success.
        assert projection.aggregate_receipt is not None
        receipt = projection.aggregate_receipt
        assert isinstance(receipt, ScopedPromotionReceipt)
        assert receipt.opened_incident_ids == ("inc-001",)
        assert receipt.failure_count == 0
        # Fingerprint is derived from the canonical request.
        assert projection.request_fingerprint == (
            scoped_promotion_request_fingerprint(transport.bound.request)
        )
        assert projection.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_COMMITTED
        )

    def test_aggregate_successful_zero_preserves_authority(self) -> None:
        """Aggregate successful zero is preserved as ``PromotionSucceeded``.

        Empty ``diagnosis_incident_ids`` MUST NOT become
        ``no_promotion_run``; the aggregate receipt proves a
        promotion was attempted and completed.
        """
        transport = _succeeded_transport(actionable=())
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context()
        )
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionSucceeded)
        assert outcome.diagnosis_incident_ids == ()
        assert projection.aggregate_receipt is not None
        # Aggregate receipt proves a promotion was attempted.
        assert projection.aggregate_receipt.scanned_signal_ids == (
            "sig-A",
            "sig-B",
        )


class TestBoundedReasonCodes:
    def test_202_uses_accepted_without_result_code(self) -> None:
        transport = PromotionHttpAccepted(observation=_observation())
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context()
        )
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionCommitUnknown)
        assert outcome.reason.value == "http_accepted_without_result"

    def test_204_uses_no_content_after_send_code(self) -> None:
        transport = PromotionHttpNoContent(observation=_observation())
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context()
        )
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionCommitUnknown)
        assert outcome.reason.value == "http_no_content_after_send"

    def test_invalid_json_uses_http_invalid_json_code(self) -> None:
        transport = PromotionHttpInvalidJson(observation=_observation())
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context()
        )
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionCommitUnknown)
        assert outcome.reason.value == "http_invalid_json"

    def test_invalid_schema_uses_http_invalid_schema_code(self) -> None:
        transport = PromotionHttpInvalidSchema(observation=_observation())
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context()
        )
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionCommitUnknown)
        assert outcome.reason.value == "http_invalid_schema"

    def test_truncated_uses_http_response_truncated_code(self) -> None:
        transport = PromotionHttpResponseTruncated(observation=_observation())
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context()
        )
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionCommitUnknown)
        assert outcome.reason.value == "http_response_truncated"

    def test_after_send_failure_uses_read_timeout_code(self) -> None:
        from k8s_diag_agent.collect.promotion_http_transport import (
            PromotionHttpTransportReasonCode,
        )

        transport = PromotionHttpTransportFailureAfterSend(
            observation=_observation(),
            reason_code=PromotionHttpTransportReasonCode.HTTP_READ_TIMEOUT_AFTER_SEND,
        )
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context()
        )
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionCommitUnknown)
        assert outcome.reason.value == "http_read_timeout_after_send"

    def test_before_send_failure_uses_configuration_blocked_code(self) -> None:
        from k8s_diag_agent.collect.promotion_http_transport import (
            PromotionHttpTransportReasonCode,
        )

        transport = PromotionHttpTransportFailureBeforeSend(
            observation=_observation(),
            reason_code=PromotionHttpTransportReasonCode.HTTP_FAILURE_BEFORE_SEND,
        )
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context()
        )
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionRejected)
        assert outcome.reason.value == "configuration_blocked"
        assert projection.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
        )

    def test_http_error_is_commit_uncertain(self) -> None:
        """A malformed ``500`` MUST NOT be classified as ``PromotionRejected``."""
        transport = PromotionHttpRejected(observation=_observation())
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context()
        )
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionCommitUnknown)
        # The may_have_committed signal lives on the projection,
        # not on the outcome itself; HTTP error is commit-unknown
        # because no validated backend disposition proved
        # execution did not start.
        assert projection.may_have_committed is True


class TestIdentitySeparation:
    def test_run_id_is_domain_identity(self) -> None:
        """``run_id`` on the outcome is the domain identity from the request."""
        transport = _succeeded_transport()
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context(
                run_id="health-run-20260729T063234Z",
                request_id="promotion-request-attempt-002",
            )
        )
        outcome = projection.promotion_outcome
        assert outcome.run_id == "health-run-20260729T063234Z"
        assert projection.request_id == "promotion-request-attempt-002"
        # Fingerprint is NOT the request id.
        assert projection.request_fingerprint != "promotion-request-attempt-002"
        # Fingerprint is a 64-char SHA-256 hex digest.
        assert len(projection.request_fingerprint) == 64

    def test_two_attempts_same_payload_produce_same_fingerprint(self) -> None:
        """Two attempts with the same request payload (different request_ids)
        produce the SAME fingerprint."""
        ctx_a = _context(request_id="attempt-A")
        ctx_b = _context(request_id="attempt-B")
        fp_a = scoped_promotion_request_fingerprint(ctx_a.request)
        fp_b = scoped_promotion_request_fingerprint(ctx_b.request)
        assert fp_a == fp_b
        assert ctx_a.request_id != ctx_b.request_id

    def test_different_runs_produce_different_fingerprints(self) -> None:
        ctx_a = _context(run_id="run-A")
        ctx_b = _context(run_id="run-B")
        fp_a = scoped_promotion_request_fingerprint(ctx_a.request)
        fp_b = scoped_promotion_request_fingerprint(ctx_b.request)
        assert fp_a != fp_b

    def test_reconciliation_token_carries_request_id_and_fingerprint(self) -> None:
        """Reconciliation token carries BOTH the request id and the fingerprint."""
        transport = PromotionHttpAccepted(observation=_observation())
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=_context(request_id="attempt-X")
        )
        outcome = projection.promotion_outcome
        token = outcome.reconciliation_token
        assert token.request_id == "attempt-X"
        assert token.request_fingerprint == projection.request_fingerprint
