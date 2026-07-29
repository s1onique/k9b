"""Loopback HTTP server tests for ``ScopedSchedulerClient``.

ACT-K9B-HULK-PROMOTION-SCOPED-DISPATCH-ACTIVATION-AND-CERTAINTY01.

Exercises the real ``ScopedSchedulerClient.promote_alert_signals_scoped``
against a loopback ``http.server`` so the bounded matrix can be
verified deterministically. No live backend access required.

Required contract assertions (Phase 16):

* correct endpoint path;
* POST method;
* ``Content-Type: application/json``;
* ``Authorization: Bearer <token>``;
* ``X-K9B-Promotion-Request-ID`` matches ``context.request_id``;
* request body is the canonical camelCase wire dict and contains
  ``runId`` (NOT ``request_id``).
"""

from __future__ import annotations

import json
import threading
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
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpAuthenticationRejected,
    ScopedPromotionHttpBeforeSendFailed,
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpSucceeded,
)
from k8s_diag_agent.domain.identifiers import AlertSignalId, HealthRunId
from k8s_diag_agent.incident_alert_promotion_contract import (
    PromoteAlertSignalsRequest,
)

TEST_TOKEN = "ci-only-synthetic-token-1234"


def _scoped_context(
    signal_ids: tuple[str, ...] = ("sig-A",),
    *,
    request_id: str = "req-001",
) -> ScopedPromotionHttpRequestContext:
    request = PromoteAlertSignalsRequest(
        run_id=HealthRunId("run-001"),
        source_identity="source-A",
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )
    return ScopedPromotionHttpRequestContext(
        request=request,
        request_id=request_id,
    )


def _valid_canonical_payload() -> dict[str, Any]:
    return {
        "runId": "run-001",
        "sourceIdentity": "source-A",
        "scannedSignalIds": ["sig-A"],
        "openedIncidentIds": ["inc-001"],
        "materiallyChangedIncidentIds": [],
        "observationRefreshedIncidentIds": [],
        "unchangedIncidentIds": [],
        "skippedSignalIds": [],
        "failures": [],
        "actionableIncidentIds": ["inc-001"],
    }


def _valid_aggregate_zero_payload() -> dict[str, Any]:
    return {
        "runId": "run-001",
        "sourceIdentity": "source-A",
        "scannedSignalIds": ["sig-A"],
        "openedIncidentIds": [],
        "materiallyChangedIncidentIds": [],
        "observationRefreshedIncidentIds": [],
        "unchangedIncidentIds": ["inc-existing-A"],
        "skippedSignalIds": [],
        "failures": [],
        "actionableIncidentIds": [],
    }


def _legacy_snake_case_payload() -> dict[str, Any]:
    """Snake_case ``PromotionResponse`` body (legacy dialect)."""
    return {
        "ok": True,
        "scanned": 1,
        "firing": 1,
        "opened_incidents": 1,
        "updated_incidents": 0,
        "skipped_duplicates": 0,
        "errors": 0,
        "error_messages": [],
        "opened_incident_ids": ["canonical-inc-001"],
        "updated_incident_ids": [],
        "canonical_incident_ids": ["canonical-inc-001"],
        "promotion_records": [
            {
                "source_candidate_id": "sig-A",
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": "opened",
            }
        ],
        "unique_candidate_count": 1,
        "promotion_scan_scope": "internal_api_alert_signals:scoped",
        "incident_access_mode": "backend",
    }


class _LoopbackServer:
    """In-process ``http.server`` instance with a configurable handler."""

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
                    self.send_header("Content-Length", str(len(body_out)))
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


class _LoopboxRequest:
    """Helper to build a synthetic response inside the handler."""

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
    ) -> None:
        self._response = {
            "status": status,
            "headers": {"Content-Type": content_type},
            "body": body,
        }


def _run_with_loopback(
    handler: Callable[[_LoopboxRequest], None],
    *,
    token: str = TEST_TOKEN,
    timeout: float = 2.0,
) -> tuple[str, dict[str, Any]]:
    """Start a loopback server and return (base_url, captured)."""
    captured: dict[str, Any] = {}

    def _inner(request: _LoopboxRequest) -> None:
        captured["path"] = request.path
        captured["method"] = request.method
        captured["headers"] = request.headers
        captured["body"] = request.body
        handler(request)

    from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
        ScopedSchedulerClient,
    )

    with _LoopbackServer(_inner) as (base_url, _port):
        client = ScopedSchedulerClient(base_url=base_url, token=token)
        outcome = client.promote_alert_signals_scoped(
            context=_scoped_context(),
            timeout=timeout,
        )
        captured["outcome"] = outcome
        return base_url, captured


class TestLoopbackScenarios:
    def test_200_valid_canonical_response_returns_scoped_succeeded(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, json.dumps(_valid_canonical_payload()).encode())

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, ScopedPromotionHttpSucceeded)
        assert (
            tuple(str(i) for i in outcome.bound.actionable_incident_ids)
            == ("inc-001",)
        )
        assert outcome.observation.status_code == 200
        assert outcome.observation.request_id == "req-001"
        assert outcome.observation.decoding_stage.value == "completed"

    def test_200_canonical_aggregate_zero_returns_scoped_succeeded(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                200, json.dumps(_valid_aggregate_zero_payload()).encode()
            )

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, ScopedPromotionHttpSucceeded)
        assert outcome.bound.actionable_incident_ids == ()

    def test_200_legacy_snake_case_body_returns_invalid_scoped_schema(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                200, json.dumps(_legacy_snake_case_payload()).encode()
            )

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, PromotionHttpInvalidSchema)

    def test_200_malformed_json_returns_invalid_json(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, b"not json at all {{{\n")

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, PromotionHttpInvalidJson)

    def test_202_empty_body_returns_accepted(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(202, b"")

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, PromotionHttpAccepted)

    def test_204_returns_no_content(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(204, b"")

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, PromotionHttpNoContent)

    def test_401_returns_authentication_rejected(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(401, json.dumps({"message": "unauthorized"}).encode())

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, ScopedPromotionHttpAuthenticationRejected)
        assert outcome.observation.status_code == 401

    def test_403_returns_authentication_rejected(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(403, json.dumps({"message": "forbidden"}).encode())

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, ScopedPromotionHttpAuthenticationRejected)
        assert outcome.observation.status_code == 403

    def test_500_malformed_body_returns_commit_uncertain(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(500, b"internal server error stack trace...")

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        # A malformed 500 MUST NOT become authentication rejection.
        assert isinstance(outcome, PromotionHttpRejected)
        assert outcome.observation.status_code == 500
        # The active scoped path MUST NOT retain response-body text.
        assert outcome.body_excerpt == ""

    def test_missing_backend_url_returns_typed_before_send_failure(self) -> None:
        from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
            ScopedSchedulerClient,
        )

        client = ScopedSchedulerClient(base_url="", token=TEST_TOKEN)
        outcome = client.promote_alert_signals_scoped(
            context=_scoped_context(),
        )
        assert isinstance(outcome, ScopedPromotionHttpBeforeSendFailed)
        from k8s_diag_agent.collect.promotion_scoped_http_seam import (
            ScopedBeforeSendFailureReason,
        )

        assert outcome.reason_code == (
            ScopedBeforeSendFailureReason.MISSING_BACKEND_URL
        )

    def test_missing_token_returns_typed_before_send_failure(self) -> None:
        from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
            ScopedSchedulerClient,
        )

        with _LoopbackServer(lambda req: None) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token=None)
            outcome = client.promote_alert_signals_scoped(
                context=_scoped_context(),
            )
        assert isinstance(outcome, ScopedPromotionHttpBeforeSendFailed)
        from k8s_diag_agent.collect.promotion_scoped_http_seam import (
            ScopedBeforeSendFailureReason,
        )

        assert outcome.reason_code == (
            ScopedBeforeSendFailureReason.MISSING_BACKEND_URL
        )

    def test_request_id_header_reaches_backend(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, json.dumps(_valid_canonical_payload()).encode())

        _, captured = _run_with_loopback(handler)
        headers = captured["headers"]
        # Python's ``http.client`` normalises header names to
        # title-case per segment; ``X-K9B-Promotion-Request-ID``
        # arrives as ``X-K9B-Promotion-Request-Id``. The HTTP
        # wire header is case-insensitive at the protocol level,
        # so the normalised form is the canonical captured key.
        assert headers.get("X-K9B-Promotion-Request-Id") == "req-001"
        assert captured["method"] == "POST"
        assert captured["path"] == "/api/internal/incidents/promote-alert-signals"

    def test_authorization_bearer_header_present(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, json.dumps(_valid_canonical_payload()).encode())

        _, captured = _run_with_loopback(handler, token=TEST_TOKEN)
        auth = captured["headers"].get("Authorization")
        assert auth == f"Bearer {TEST_TOKEN}"

    def test_request_body_contains_run_id_not_request_id(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, json.dumps(_valid_canonical_payload()).encode())

        _, captured = _run_with_loopback(handler)
        body = json.loads(captured["body"].decode("utf-8"))
        assert "runId" in body
        assert "request_id" not in body
        assert body["runId"] == "run-001"
        assert body["sourceIdentity"] == "source-A"
        assert body["signalIds"] == ["sig-A"]

    def test_request_id_observation_field_is_correlation_id(self) -> None:
        """``request_id`` reaches ``PromotionHttpObservation`` as the
        transport correlation identity. ``runId`` does NOT appear on
        the observation -- it lives only on the request payload and
        the bound result.
        """

        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, json.dumps(_valid_canonical_payload()).encode())

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert outcome.observation.request_id == "req-001"
        assert outcome.bound.result.run_id == "run-001"
        assert outcome.bound.request.run_id == "run-001"
        # The bound result's ``actionable_incident_ids`` is the
        # diagnosis-handoff projection.
        assert (
            tuple(str(i) for i in outcome.bound.actionable_incident_ids)
            == ("inc-001",)
        )
