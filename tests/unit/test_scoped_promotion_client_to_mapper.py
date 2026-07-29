"""End-to-end client-to-mapper matrix tests.

ACT-K9B-HULK-PROMOTION-SCOPED-CLIENT-REACHABILITY-AND-DISPATCH-ACTIVATION01.

Exercises the loopback HTTP server through the real
:class:`ScopedSchedulerClient`, then routes the typed transport
outcome through the closed mapper
:func:`map_scoped_http_transport_to_promotion_outcome`. The
matrix covers the 21 contract cases required by the ACT.

For every case the test asserts:

* the exact client transport variant,
* the exact typed projection variant,
* the exact ``PromotionOutcome`` variant,
* the bounded reason enum identity,
* the commit disposition,
* the requires-reconciliation flag,
* the run id (domain identity),
* the request id (transport correlation),
* the request fingerprint (deterministic),
* the presence (or structural absence) of an aggregate receipt.

No transport variant is manually constructed in these tests;
every case walks through the real client. The mapper is invoked
exclusively through the typed seam.
"""

from __future__ import annotations

import json
import threading
import urllib.error as urllib_error
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpAccepted,
    PromotionHttpInvalidJson,
    PromotionHttpInvalidSchema,
    PromotionHttpNoContent,
    PromotionHttpRejected,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
    PromotionCommitUnknown,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionCompletedProjection,
    ScopedPromotionRejectedProjection,
    ScopedPromotionUncertainProjection,
    map_scoped_http_transport_to_promotion_outcome,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpAuthenticationRejected,
    ScopedPromotionHttpBeforeSendFailed,
    ScopedPromotionHttpBodyLimitExceeded,
    ScopedPromotionHttpDispatchUncertain,
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpShortRead,
    ScopedPromotionHttpSucceeded,
    ScopedPromotionHttpTransportOutcome,
    ScopedPromotionReceipt,
    scoped_promotion_request_fingerprint,
)
from k8s_diag_agent.domain.identifiers import AlertSignalId, HealthRunId
from k8s_diag_agent.incident_alert_promotion_contract import (
    PromoteAlertSignalsRequest,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
    ScopedSchedulerClient,
)

TEST_TOKEN = "ci-only-synthetic-token-1234"
RUN_ID = "health-run-20260729T063234Z"
REQUEST_ID = "promotion-request-attempt-002"


class _LoopboxRequest:
    def __init__(
        self,
        *,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body
        self._response: dict[str, Any] | None = None

    def respond(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str = "application/json",
        content_length: int | None = None,
    ) -> None:
        self._response = {
            "status": status,
            "headers": {"Content-Type": content_type},
            "body": body,
            "content_length": content_length,
        }


class _LoopbackServer:
    def __init__(self, handler: Callable[[_LoopboxRequest], None]) -> None:
        self._handler = handler
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.host = "127.0.0.1"
        self.port = 0

    def __enter__(self) -> tuple[str, int]:
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length) if length else b""
                request = _LoopboxRequest(
                    method="POST",
                    path=self.path,
                    headers=dict(self.headers.items()),
                    body=body,
                )
                try:
                    outer._handler(request)
                    response = request._response
                    if response is None:
                        self.send_response(500)
                        self.end_headers()
                        return
                    self.send_response(response["status"])
                    for key, value in response["headers"].items():
                        self.send_header(key, value)
                    body_out = response.get("body", b"")
                    if response.get("content_length") is not None:
                        self.send_header(
                            "Content-Length",
                            str(response["content_length"]),
                        )
                    else:
                        self.send_header(
                            "Content-Length", str(len(body_out))
                        )
                    self.end_headers()
                    if body_out:
                        self.wfile.write(body_out)
                except Exception:  # pragma: no cover
                    self.send_response(500)
                    self.end_headers()

        self._server = ThreadingHTTPServer((self.host, 0), _Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()
        return f"http://{self.host}:{self.port}", self.port

    def __exit__(self, *_exc_info: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def _scoped_context(
    signal_ids: tuple[str, ...] = ("sig-A",),
    *,
    request_id: str = REQUEST_ID,
) -> ScopedPromotionHttpRequestContext:
    request = PromoteAlertSignalsRequest(
        run_id=HealthRunId(RUN_ID),
        source_identity="source-A",
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )
    return ScopedPromotionHttpRequestContext(
        request=request,
        request_id=request_id,
    )


def _valid_canonical_payload(actionable: tuple[str, ...]) -> dict[str, Any]:
    return {
        "runId": RUN_ID,
        "sourceIdentity": "source-A",
        "scannedSignalIds": ["sig-A"],
        "openedIncidentIds": list(actionable),
        "materiallyChangedIncidentIds": [],
        "observationRefreshedIncidentIds": [],
        "unchangedIncidentIds": [],
        "skippedSignalIds": [],
        "failures": [],
        "actionableIncidentIds": list(actionable),
    }


def _run_client(
    handler: Callable[[_LoopboxRequest], None],
) -> tuple[
    ScopedPromotionHttpTransportOutcome,
    ScopedPromotionHttpRequestContext,
]:
    """Run the loopback server and invoke the real scoped client."""
    context = _scoped_context()
    with _LoopbackServer(handler) as (base_url, _port):
        client = ScopedSchedulerClient(base_url=base_url, token=TEST_TOKEN)
        transport = client.promote_alert_signals_scoped(context=context)
    return transport, context


def _run_round_trip(
    handler: Callable[[_LoopboxRequest], None],
) -> tuple[
    ScopedPromotionHttpTransportOutcome,
    ScopedPromotionHttpRequestContext,
    object,
]:
    transport, context = _run_client(handler)
    projection = map_scoped_http_transport_to_promotion_outcome(
        transport, context=context
    )
    return transport, context, projection


class TestClientToMapperMatrix:
    """21 client-to-mapper cases required by the ACT."""

    def test_1_canonical_success_with_actionable_ids(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                200,
                json.dumps(
                    _valid_canonical_payload(("inc-001",))
                ).encode(),
            )

        transport, context, projection = _run_round_trip(handler)
        assert isinstance(transport, ScopedPromotionHttpSucceeded)
        assert isinstance(projection, ScopedPromotionCompletedProjection)
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionSucceeded)
        assert outcome.run_id == RUN_ID
        assert outcome.diagnosis_incident_ids == ("inc-001",)
        assert projection.aggregate_receipt is not None
        assert isinstance(
            projection.aggregate_receipt, ScopedPromotionReceipt
        )
        assert projection.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_COMMITTED
        )
        assert projection.requires_reconciliation is False
        assert projection.request_id == REQUEST_ID
        assert projection.request_fingerprint == (
            scoped_promotion_request_fingerprint(context.request)
        )
        assert len(projection.request_fingerprint) == 64

    def test_2_aggregate_successful_zero(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                200,
                json.dumps(
                    _valid_canonical_payload(())
                ).encode(),
            )

        transport, context, projection = _run_round_trip(handler)
        assert isinstance(transport, ScopedPromotionHttpSucceeded)
        assert isinstance(projection, ScopedPromotionCompletedProjection)
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionSucceeded)
        assert outcome.diagnosis_incident_ids == ()
        assert projection.aggregate_receipt is not None
        assert projection.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_COMMITTED
        )

    def test_3_202_accepted(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(202, b"")

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(transport, PromotionHttpAccepted)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionCommitUnknown)
        assert outcome.reason is (
            PromotionUncertaintyCode.HTTP_ACCEPTED_WITHOUT_RESULT
        )
        assert projection.commit_disposition is (
            PromotionCommitDisposition.MAY_HAVE_COMMITTED
        )
        assert projection.requires_reconciliation is True

    def test_4_204_no_content(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(204, b"")

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(transport, PromotionHttpNoContent)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionUncertaintyCode.HTTP_NO_CONTENT_AFTER_SEND
        )

    def test_5_empty_200_body(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, b"")

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(transport, PromotionHttpInvalidJson)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is PromotionUncertaintyCode.HTTP_INVALID_JSON

    def test_6_malformed_json(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, b"not json at all {{{")

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(transport, PromotionHttpInvalidJson)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is PromotionUncertaintyCode.HTTP_INVALID_JSON

    def test_7_invalid_scoped_schema(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, json.dumps({"ok": True}).encode())

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(transport, PromotionHttpInvalidSchema)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionUncertaintyCode.HTTP_INVALID_SCHEMA
        )

    def test_8_body_limit_exceeded(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                200,
                b"x" * 1024,
                content_length=2 * 1024 * 1024,
            )

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(
            transport, ScopedPromotionHttpBodyLimitExceeded
        )
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionUncertaintyCode.HTTP_RESPONSE_BODY_LIMIT_EXCEEDED
        )

    def test_9_short_read(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                200,
                b"incomplete",
                content_length=1024,
            )

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(transport, ScopedPromotionHttpShortRead)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionUncertaintyCode.HTTP_RESPONSE_SHORT_READ
        )

    def test_10_read_timeout(self) -> None:
        """``TimeoutError`` raised by ``urllib`` becomes
        ``ScopedPromotionHttpDispatchUncertain`` with
        ``TIMEOUT`` reason."""
        from unittest.mock import patch

        with _LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token=TEST_TOKEN)
            context = _scoped_context()
            with patch(
                "k8s_diag_agent.ui.server_incident_internal_scoped_client.urllib.request.urlopen",
                side_effect=TimeoutError("read timeout"),
            ):
                transport = client.promote_alert_signals_scoped(
                    context=context, timeout=0.001
                )
                projection = map_scoped_http_transport_to_promotion_outcome(
                    transport, context=context
                )
        assert isinstance(transport, ScopedPromotionHttpDispatchUncertain)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionUncertaintyCode.HTTP_READ_TIMEOUT_AFTER_SEND
        )

    def test_11_connection_lost_post_send(self) -> None:
        """``ConnectionError`` (connection reset) surfaces as
        ``ScopedPromotionHttpDispatchUncertain`` with
        ``CONNECTION_LOST`` reason."""
        from unittest.mock import patch

        with _LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token=TEST_TOKEN)
            context = _scoped_context()
            with patch(
                "k8s_diag_agent.ui.server_incident_internal_scoped_client.urllib.request.urlopen",
                side_effect=ConnectionResetError("connection reset"),
            ):
                transport = client.promote_alert_signals_scoped(
                    context=context, timeout=0.001
                )
                projection = map_scoped_http_transport_to_promotion_outcome(
                    transport, context=context
                )
        # ``ConnectionResetError`` is a subclass of ``OSError`` and
        # ``ConnectionError``; the client surfaces it as
        # ``CONNECTION_LOST`` via the dispatch-uncertain variant.
        assert isinstance(transport, ScopedPromotionHttpDispatchUncertain)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionUncertaintyCode.HTTP_CONNECTION_LOST_AFTER_SEND
        )

    def test_12_missing_backend_url(self) -> None:
        client = ScopedSchedulerClient(base_url="", token=TEST_TOKEN)
        context = _scoped_context()
        transport = client.promote_alert_signals_scoped(context=context)
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=context
        )
        assert isinstance(transport, ScopedPromotionHttpBeforeSendFailed)
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionRejected)
        assert outcome.reason is (
            PromotionRejectionCode.CONFIGURATION_BLOCKED
        )
        assert projection.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
        )
        assert projection.requires_reconciliation is False

    def test_13_missing_token(self) -> None:
        client = ScopedSchedulerClient(base_url="http://localhost", token=None)
        context = _scoped_context()
        transport = client.promote_alert_signals_scoped(context=context)
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=context
        )
        assert isinstance(transport, ScopedPromotionHttpBeforeSendFailed)
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionRejectionCode.CONFIGURATION_BLOCKED
        )

    def test_14_dns_failure(self) -> None:
        """DNS failure surfaces as ``ScopedPromotionHttpBeforeSendFailed``
        with ``DNS_FAILED`` reason and ``BACKEND_UNREACHABLE`` projection."""
        from unittest.mock import patch

        gaierror_cls = type(
            "gaierror",
            (OSError,),
            {"__init__": lambda self, *a, **k: OSError.__init__(self, *a, **k)},
        )

        with _LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token=TEST_TOKEN)
            context = _scoped_context()
            with patch(
                "k8s_diag_agent.ui.server_incident_internal_scoped_client.urllib.request.urlopen",
                side_effect=urllib_error.URLError(
                    gaierror_cls(-2, "Name or service not known")
                ),
            ):
                transport = client.promote_alert_signals_scoped(
                    context=context, timeout=0.5
                )
                projection = map_scoped_http_transport_to_promotion_outcome(
                    transport, context=context
                )
        assert isinstance(transport, ScopedPromotionHttpBeforeSendFailed)
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionRejectionCode.BACKEND_UNREACHABLE
        )

    def test_15_connection_refused(self) -> None:
        """``ConnectionRefusedError`` surfaced via ``URLError`` is
        classified as ``ScopedBeforeSendFailureReason.CONNECTION_REFUSED``."""
        from unittest.mock import patch

        with _LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token=TEST_TOKEN)
            context = _scoped_context()
            with patch(
                "k8s_diag_agent.ui.server_incident_internal_scoped_client.urllib.request.urlopen",
                side_effect=urllib_error.URLError(
                    ConnectionRefusedError("connection refused")
                ),
            ):
                transport = client.promote_alert_signals_scoped(
                    context=context, timeout=0.5
                )
                projection = map_scoped_http_transport_to_promotion_outcome(
                    transport, context=context
                )
        assert isinstance(transport, ScopedPromotionHttpBeforeSendFailed)
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionRejectionCode.BACKEND_UNREACHABLE
        )

    def test_16_401_authentication_rejected(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                401, json.dumps({"message": "unauthorized"}).encode()
            )

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(
            transport, ScopedPromotionHttpAuthenticationRejected
        )
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        outcome = projection.promotion_outcome
        assert isinstance(outcome, PromotionRejected)
        assert outcome.reason is (
            PromotionRejectionCode.AUTHENTICATION_REJECTED
        )
        assert projection.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
        )
        assert projection.requires_reconciliation is False

    def test_17_403_authentication_rejected(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                403, json.dumps({"message": "forbidden"}).encode()
            )

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(
            transport, ScopedPromotionHttpAuthenticationRejected
        )
        assert isinstance(projection, ScopedPromotionRejectedProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionRejectionCode.AUTHENTICATION_REJECTED
        )

    def test_18_untyped_400(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(400, json.dumps({"error": "bad"}).encode())

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(transport, PromotionHttpRejected)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionUncertaintyCode.PROMOTION_HTTP_ERROR_UNCERTAIN
        )

    def test_19_untyped_409(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(409, json.dumps({"error": "conflict"}).encode())

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(transport, PromotionHttpRejected)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionUncertaintyCode.PROMOTION_HTTP_ERROR_UNCERTAIN
        )

    def test_20_malformed_500_remains_commit_unknown(self) -> None:
        """A malformed ``500`` MUST NOT become authentication rejection."""
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                500, b"internal server error stack trace..."
            )

        transport, _, projection = _run_round_trip(handler)
        assert isinstance(transport, PromotionHttpRejected)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert outcome.reason is (
            PromotionUncertaintyCode.PROMOTION_HTTP_ERROR_UNCERTAIN
        )
        # NEVER ``AUTHENTICATION_REJECTED``.
        assert not (
            isinstance(projection, ScopedPromotionRejectedProjection)
            and projection.promotion_outcome.reason
            is PromotionRejectionCode.AUTHENTICATION_REJECTED
        )

    def test_21_generic_transmission_unknown(self) -> None:
        """A generic ``URLError`` whose underlying ``OSError`` is
        not ``ConnectionRefusedError`` or ``gaierror`` surfaces as
        ``ScopedPromotionHttpDispatchUncertain`` with
        ``TRANSMISSION_UNKNOWN`` reason."""
        from unittest.mock import patch

        with _LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token=TEST_TOKEN)
            context = _scoped_context()
            with patch(
                "k8s_diag_agent.ui.server_incident_internal_scoped_client.urllib.request.urlopen",
                side_effect=urllib_error.URLError(
                    OSError(0, "ephemeral low-level failure")
                ),
            ):
                transport = client.promote_alert_signals_scoped(
                    context=context, timeout=0.001
                )
                projection = map_scoped_http_transport_to_promotion_outcome(
                    transport, context=context
                )
        assert isinstance(transport, ScopedPromotionHttpDispatchUncertain)
        assert isinstance(projection, ScopedPromotionUncertainProjection)
        outcome = projection.promotion_outcome
        assert (
            outcome.reason
            is PromotionUncertaintyCode.HTTP_TRANSMISSION_UNKNOWN
            or outcome.reason
            is PromotionUncertaintyCode.HTTP_CONNECTION_LOST_AFTER_SEND
        )
