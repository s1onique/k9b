"""Response decoding and scoped wire binding for the scoped HTTP seam.

ACT-K9B-HULK-PROMOTION-SCOPED-DISPATCH-ACTIVATION-AND-CERTAINTY01.

Owns:

* JSON decode of the bounded response body;
* ``IncidentPromotionResult.from_wire_dict`` parsing;
* ``BoundScopedPromotionResult`` construction from the parsed
  result + the canonical request context;
* Conversion of the body-read algebra into typed transport
  outcomes (``ScopedPromotionHttpSucceeded``,
  ``PromotionHttpInvalidJson``, ``PromotionHttpInvalidSchema``,
  ``PromotionHttpAccepted``, ``PromotionHttpNoContent``).

The active scoped path MUST NOT retain response-body text. The
bounded ``response_body_sha256`` and the bounded reason codes
are the only artifacts that flow back to the dispatcher.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpAccepted,
    PromotionHttpInvalidJson,
    PromotionHttpInvalidSchema,
    PromotionHttpNoContent,
    PromotionHttpObservation,
    PromotionResponseDecodingStage,
    RequestTransmissionState,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpSucceeded,
)
from k8s_diag_agent.incident_alert_promotion_binding import BoundScopedPromotionResult
from k8s_diag_agent.incident_alert_promotion_contract import (
    IncidentPromotionResult,
    PromotionScopeError,
)


@dataclass(frozen=True, slots=True)
class ScopedResponseObservation:
    """Per-response observation metadata carried into the typed outcome."""

    status_code: int | None
    content_type: str | None
    declared_content_length: int | None
    body_sha256: str | None
    elapsed_milliseconds: int


def _build_observation(
    *,
    context: ScopedPromotionHttpRequestContext,
    observation: ScopedResponseObservation,
    decoding_stage: PromotionResponseDecodingStage,
    response_byte_count: int,
    transmission: RequestTransmissionState = (
        RequestTransmissionState.RESPONSE_COMPLETED
    ),
) -> PromotionHttpObservation:
    return PromotionHttpObservation(
        request_id=context.request_id,
        request_transmission=transmission,
        status_code=observation.status_code,
        content_type=observation.content_type,
        declared_content_length=observation.declared_content_length,
        response_byte_count=response_byte_count,
        response_body_sha256=observation.body_sha256,
        decoding_stage=decoding_stage,
        elapsed_milliseconds=observation.elapsed_milliseconds,
    )


def _decode_payload(body: bytes) -> Mapping[str, Any] | None:
    """Attempt JSON decode; return ``None`` on failure or non-Mapping."""
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, Mapping):
        return None
    return decoded


def decode_scoped_body(
    *,
    context: ScopedPromotionHttpRequestContext,
    body: bytes,
    observation_meta: ScopedResponseObservation,
) -> ScopedPromotionHttpSucceeded | PromotionHttpInvalidJson | PromotionHttpInvalidSchema:
    """Decode a bounded body through the canonical typed pipeline.

    Returns the typed success variant on a complete round-trip,
    or one of the typed bounded uncertainty variants on any
    malformed / out-of-schema body.
    """
    payload = _decode_payload(body)
    if payload is None:
        obs = _build_observation(
            context=context,
            observation=observation_meta,
            decoding_stage=PromotionResponseDecodingStage.JSON_DECODE,
            response_byte_count=len(body),
        )
        return PromotionHttpInvalidJson(observation=obs)

    try:
        result = IncidentPromotionResult.from_wire_dict(payload)
    except PromotionScopeError as exc:
        obs = _build_observation(
            context=context,
            observation=observation_meta,
            decoding_stage=PromotionResponseDecodingStage.WIRE_SCHEMA,
            response_byte_count=len(body),
        )
        return PromotionHttpInvalidSchema(observation=obs, schema_error=str(exc))

    try:
        bound = BoundScopedPromotionResult(
            request=context.request,
            result=result,
        )
    except PromotionScopeError as exc:
        obs = _build_observation(
            context=context,
            observation=observation_meta,
            decoding_stage=PromotionResponseDecodingStage.WIRE_SCHEMA,
            response_byte_count=len(body),
        )
        return PromotionHttpInvalidSchema(
            observation=obs,
            schema_error=f"binding failed: {exc}",
        )

    obs = _build_observation(
        context=context,
        observation=observation_meta,
        decoding_stage=PromotionResponseDecodingStage.COMPLETED,
        response_byte_count=len(body),
    )
    return ScopedPromotionHttpSucceeded(observation=obs, bound=bound)


def accepted_outcome(
    *,
    context: ScopedPromotionHttpRequestContext,
    observation_meta: ScopedResponseObservation,
) -> PromotionHttpAccepted:
    """Build a ``202 Accepted`` typed outcome with the bounded metadata.

    ``202`` is always preserved as typed uncertainty even when the
    body resembles a completed canonical result. The body is NOT
    re-parsed for authoritative completion.
    """
    obs = _build_observation(
        context=context,
        observation=observation_meta,
        decoding_stage=PromotionResponseDecodingStage.EMPTY_BODY,
        response_byte_count=0,
    )
    return PromotionHttpAccepted(observation=obs)


def no_content_outcome(
    *,
    context: ScopedPromotionHttpRequestContext,
    observation_meta: ScopedResponseObservation,
) -> PromotionHttpNoContent:
    """Build a ``204 No Content`` typed outcome.

    ``204`` is never reinterpreted as aggregate successful zero.
    """
    obs = _build_observation(
        context=context,
        observation=observation_meta,
        decoding_stage=PromotionResponseDecodingStage.EMPTY_BODY,
        response_byte_count=0,
    )
    return PromotionHttpNoContent(observation=obs)


__all__ = [
    "ScopedResponseObservation",
    "accepted_outcome",
    "decode_scoped_body",
    "no_content_outcome",
]
