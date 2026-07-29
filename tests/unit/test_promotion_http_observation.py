"""Tests for the typed HTTP transport observation.

ACT-K9B-HULK-PROMOTION-AMBIGUOUS-RESPONSE-TRANSPORT-TRUTH01-LOCAL-CONTRACT01.

The observation is the immutable metadata container every known
HTTP shape carries. Tests pin:

* closed enum membership;
* observation immutability (frozen dataclass);
* bounded SHA-256 projection without leaking the body;
* ``to_event_dict`` projection shape (operator event payload).
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpObservation,
    PromotionHttpTransportReasonCode,
    PromotionResponseDecodingStage,
    RequestTransmissionState,
    compute_response_sha256,
)


def _observation(**overrides: object) -> PromotionHttpObservation:
    base: dict[str, object] = {
        "request_id": "req-test-001",
        "request_transmission": RequestTransmissionState.RESPONSE_COMPLETED,
        "status_code": 200,
        "content_type": "application/json",
        "declared_content_length": 17,
        "response_byte_count": 17,
        "response_body_sha256": "deadbeef" * 8,
        "decoding_stage": PromotionResponseDecodingStage.COMPLETED,
        "elapsed_milliseconds": 12,
    }
    base.update(overrides)
    return PromotionHttpObservation(**base)


class TestClosedEnums:
    def test_request_transmission_is_closed(self) -> None:
        # The completed closed vocabulary replaces the legacy
        # ``BODY_SENT`` bucket with the conservative
        # ``DISPATCH_STARTED_TRANSMISSION_UNKNOWN`` discriminator
        # the active scoped path emits when ``urllib`` cannot prove
        # the body reached the backend. The legacy
        # ``BODY_SENT`` was reserved for instrumented transport
        # seams that prove flush; the active scoped path does NOT
        # claim that proof and so the post-send state is bounded
        # to the conservative unknown discriminator.
        members = set(RequestTransmissionState)
        assert members == {
            RequestTransmissionState.NOT_STARTED,
            RequestTransmissionState.HEADERS_SENT,
            RequestTransmissionState.DISPATCH_STARTED_TRANSMISSION_UNKNOWN,
            RequestTransmissionState.RESPONSE_STARTED,
            RequestTransmissionState.RESPONSE_COMPLETED,
        }

    def test_request_transmission_rejects_legacy_body_sent(self) -> None:
        # The legacy ``BODY_SENT`` discriminator was removed when
        # the post-send state was bounded to the conservative
        # unknown variant. The negative test proves the legacy
        # name is no longer a member of the closed vocabulary.
        assert not hasattr(RequestTransmissionState, "BODY_SENT")
        assert hasattr(
            RequestTransmissionState,
            "DISPATCH_STARTED_TRANSMISSION_UNKNOWN",
        )

    def test_decoding_stage_is_closed(self) -> None:
        members = set(PromotionResponseDecodingStage)
        assert members == {
            PromotionResponseDecodingStage.NOT_ATTEMPTED,
            PromotionResponseDecodingStage.EMPTY_BODY,
            PromotionResponseDecodingStage.JSON_DECODE,
            PromotionResponseDecodingStage.WIRE_SCHEMA,
            PromotionResponseDecodingStage.COMPLETED,
        }

    def test_transport_reason_codes_replace_ambiguous_catchall(self) -> None:
        members = set(PromotionHttpTransportReasonCode)
        # The closed union must NOT contain ``AMBIGUOUS_RESPONSE``;
        # that catch-all bucket is reserved for the invariant-
        # violation fallback only.
        assert "AMBIGUOUS_RESPONSE" not in {
            member.value for member in members
        }
        # The ACT's required bounded codes are present.
        expected = {
            "HTTP_ACCEPTED_WITHOUT_RESULT",
            "HTTP_NO_CONTENT_AFTER_SEND",
            "HTTP_EMPTY_SUCCESS_BODY",
            "HTTP_INVALID_JSON",
            "HTTP_INVALID_SCHEMA",
            "HTTP_RESPONSE_TRUNCATED",
            "HTTP_READ_TIMEOUT_AFTER_SEND",
            "HTTP_CONNECTION_LOST_AFTER_SEND",
            "HTTP_FAILURE_BEFORE_SEND",
            "UNEXPECTED_CLIENT_RESULT",
            "HTTP_ERROR_VALID_RESULT",
        }
        assert {member.value for member in members} == expected


class TestObservationImmutability:
    def test_observation_is_frozen(self) -> None:
        observation = _observation()
        with pytest.raises(Exception):
            observation.request_id = "tampered"

    def test_observation_to_event_dict_shape(self) -> None:
        observation = _observation()
        event = observation.to_event_dict()
        assert event["request_id"] == "req-test-001"
        assert event["request_transmission"] == "response_completed"
        assert event["status_code"] == 200
        assert event["content_type"] == "application/json"
        assert event["declared_content_length"] == 17
        assert event["response_byte_count"] == 17
        assert event["response_body_sha256"] == "deadbeef" * 8
        assert event["decoding_stage"] == "completed"
        assert event["elapsed_milliseconds"] == 12

    def test_compute_response_sha256_does_not_leak_body(self) -> None:
        sha = compute_response_sha256(b"secret")
        assert sha is not None
        assert isinstance(sha, str)
        # The function never returns the body itself.
        assert "secret" not in sha

    def test_compute_response_sha256_returns_none_for_empty(self) -> None:
        assert compute_response_sha256(b"") is None
        assert compute_response_sha256(None) is None


@pytest.mark.parametrize(
    "transmission",
    list(RequestTransmissionState),
)
def test_every_transmission_state_projects(transmission: RequestTransmissionState) -> None:
    observation = _observation(request_transmission=transmission)
    assert observation.to_event_dict()["request_transmission"] == transmission.value
