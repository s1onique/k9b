"""Typed scoped scheduler client facade.

ACT-K9B-HULK-PROMOTION-SCOPED-DISPATCH-ACTIVATION-AND-CERTAINTY01.

ACT-K9B-HULK-PROMOTION-SCOPED-HTTP-CLIENT-RESPONSIBILITY-SPLIT01.

Public client surface for the canonical scoped current-run
promotion path. The HTTP transport loop is split across focused
modules:

* :mod:`server_incident_internal_scoped_config` -- configuration
  validation and canonical endpoint construction;
* :mod:`server_incident_internal_scoped_request` -- request
  serialisation and header construction;
* :mod:`server_incident_internal_scoped_body` -- bounded body-read
  algebra and reason codes;
* :mod:`server_incident_internal_scoped_status` -- status-code
  -> typed-transport-variant mapping;
* :mod:`server_incident_internal_scoped_errors` -- typed
  ``URLError`` / ``TimeoutError`` / ``ConnectionError``
  classification;
* :mod:`server_incident_internal_scoped_execute` -- ``urlopen``
  execution and exception handling;
* :mod:`server_incident_internal_scoped_finalize` -- final
  observation reconstruction and timing authority;
* :mod:`server_incident_internal_scoped_response` -- JSON decode,
  wire schema parsing, and scoped result binding.

The facade owns only the public entry point, the dependency
injection (base URL, token, monotonic clock), and the
orchestration of the HTTP loop. The facade does NOT implement
request construction, status semantics, body reading, error
classification, or final observation reconstruction -- those
are delegated to the focused modules above.

The active scoped path emits typed scoped variants exclusively:
``ScopedPromotionHttpSucceeded``,
``ScopedPromotionHttpAuthenticationRejected``,
``ScopedPromotionHttpBodyLimitExceeded``,
``ScopedPromotionHttpShortRead``,
``ScopedPromotionHttpReadFailed``,
``ScopedPromotionHttpBeforeSendFailed``,
``ScopedPromotionHttpDispatchUncertain`` plus the generic
``PromotionHttp*`` semantic variants that originate inside the
response decoder (accepted, no-content, invalid-json,
invalid-schema, response-truncated). The legacy
``PromotionHttpTransportFailureBeforeSend`` and
``PromotionHttpTransportFailureAfterSend`` are intentionally NOT
emitted by the active scoped path.
"""

from __future__ import annotations

import urllib.request  # noqa: F401  (kept for test mock path)
from collections.abc import Callable

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionResponseDecodingStage,
    RequestTransmissionState,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedBeforeSendFailureReason,
    ScopedPromotionHttpBeforeSendFailed,
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpTransportOutcome,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_config import (
    RequestIdFactory,
    ScopedSchedulerBackendConfigError,
    ScopedSchedulerMissingTokenError,
    canonical_promote_endpoint,
    require_authenticated_config,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_execute import (
    execute_scoped_request,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_finalize import (
    MONOTONIC_CLOCK,
    build_observation,
    finalize_observation,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_request import (
    REQUEST_ID_HEADER,
    build_scoped_request,
)

__all__ = [
    "REQUEST_ID_HEADER",
    "RequestIdFactory",
    "ScopedSchedulerBackendConfigError",
    "ScopedSchedulerClient",
    "ScopedSchedulerMissingTokenError",
]


class ScopedSchedulerClient:
    """Typed HTTP client for the canonical scoped current-run path."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._base_url = base_url
        self._token = token
        self._clock: Callable[[], float] = clock or MONOTONIC_CLOCK

    def promote_alert_signals_scoped(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        timeout: float = 30.0,
    ) -> ScopedPromotionHttpTransportOutcome:
        """Submit the canonical scoped promotion scope and return
        the typed transport outcome.

        The canonical request is the single authority; this method
        MUST NOT reconstruct a second ``PromoteAlertSignalsRequest``.
        """
        try:
            base_url, token = require_authenticated_config(
                self._base_url, self._token
            )
        except ScopedSchedulerBackendConfigError:
            return _before_send_failed(
                context=context,
                reason_code=(
                    ScopedBeforeSendFailureReason.MISSING_BACKEND_URL
                ),
            )
        except ScopedSchedulerMissingTokenError:
            return _before_send_failed(
                context=context,
                reason_code=(
                    ScopedBeforeSendFailureReason.MISSING_INTERNAL_TOKEN
                ),
            )

        url = canonical_promote_endpoint(base_url)
        request = build_scoped_request(
            context=context,
            url=url,
            token=token,
        )
        # Capture the start time BEFORE the executor runs so the
        # final elapsed-time stamp reuses the same anchor.
        start = self._clock()
        typed_outcome = execute_scoped_request(
            context=context,
            request=request,
            timeout=timeout,
            clock=self._clock,
            start=start,
        )
        # Record the final elapsed time AFTER the transport variant
        # is constructed so the measurement covers the full HTTP
        # loop, body read, status classification, JSON decode,
        # wire parse, request/result binding, and the construction
        # of the typed transport variant.
        return finalize_observation(
            context=context,
            typed_outcome=typed_outcome,
            clock=self._clock,
            start=start,
        )


def _before_send_failed(
    *,
    context: ScopedPromotionHttpRequestContext,
    reason_code: ScopedBeforeSendFailureReason,
) -> ScopedPromotionHttpTransportOutcome:
    """Construct the typed before-send failure variant used by
    the facade for configuration errors.

    The variant is constructed without invoking the executor
    because no HTTP attempt was made; the elapsed time is
    exactly ``0`` because the configuration defect was
    detected before the request was built.
    """
    observation = build_observation(
        context=context,
        transmission=RequestTransmissionState.NOT_STARTED,
        status_code=None,
        content_type=None,
        declared_content_length=None,
        response_byte_count=0,
        body_sha256=None,
        decoding_stage=PromotionResponseDecodingStage.NOT_ATTEMPTED,
        elapsed_milliseconds_value=0,
    )
    return ScopedPromotionHttpBeforeSendFailed(
        observation=observation,
        reason_code=reason_code,
    )
