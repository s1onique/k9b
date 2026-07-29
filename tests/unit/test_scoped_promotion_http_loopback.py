"""Loopback HTTP server tests for ``ScopedSchedulerClient``.

ACT-K9B-HULK-PROMOTION-SCOPED-CLIENT-TYPED-HTTP-SEAM01.

Exercises the real ``ScopedSchedulerClient.promote_alert_signals_scoped``
against a loopback ``http.server`` so the success / error matrix
can be verified deterministically. No live backend access required.

The matrix is intentionally bounded to the cases that prove the
typed boundary:

* 200 valid canonical response -> ``ScopedPromotionHttpSucceeded``
* 200 canonical aggregate successful zero -> ``ScopedPromotionHttpSucceeded``
* 200 invalid scoped schema (legacy snake_case body) -> ``PromotionHttpInvalidSchema``
* 200 invalid JSON -> ``PromotionHttpInvalidJson``
* 200 empty body -> typed empty-body uncertainty
* 202 empty body -> ``PromotionHttpAccepted``
* 204 -> ``PromotionHttpNoContent``
* 401 -> ``PromotionHttpRejected``
* 500 malformed body -> ``PromotionHttpRejected``
* backend URL not configured -> ``PromotionHttpTransportFailureBeforeSend``
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
    PromotionHttpTransportFailureBeforeSend,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpSucceeded,
)
from k8s_diag_agent.domain.identifiers import AlertSignalId, HealthRunId


def _scoped_context(
    signal_ids: tuple[str, ...] = ("sig-A",),
    *,
    request_id: str = "req-001",
) -> ScopedPromotionHttpRequestContext:
    return ScopedPromotionHttpRequestContext(
        run_id=HealthRunId("run-001"),
        request_id=request_id,
        source_identity="source-A",
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
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
    url_path: str = "/api/internal/incidents/promote-alert-signals",
) -> tuple[str, Any]:
    """Start a loopback server and return (base_url, response)."""
    captured: dict[str, Any] = {}

    def _inner(request: _LoopboxRequest) -> None:
        captured["path"] = request.path
        captured["headers"] = request.headers
        captured["body"] = request.body
        handler(request)

    with _LoopbackServer(_inner) as (base_url, _port):
        from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
            ScopedSchedulerClient,
        )

        client = ScopedSchedulerClient(base_url=base_url, token=None)
        outcome = client.promote_alert_signals_scoped(
            context=_scoped_context(),
            timeout=2.0,
        )
        captured["outcome"] = outcome
        return base_url, captured


class TestLoopbackScenarios:
    def test_200_valid_canonical_response_returns_scoped_succeeded(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, json.dumps(_valid_canonical_payload()).encode())

        base_url, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, ScopedPromotionHttpSucceeded)
        assert outcome.bound.result.actionable_incident_ids == (
            "inc-001",
        ) or [str(i) for i in outcome.bound.result.actionable_incident_ids] == [
            "inc-001"
        ]
        assert outcome.bound.actionable_incident_ids == (
            "inc-001",
        ) or [str(i) for i in outcome.bound.actionable_incident_ids] == [
            "inc-001"
        ]
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

    def test_200_empty_body_returns_typed_empty_body_uncertainty(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, b"")

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        # 200 + empty body is typed empty-body uncertainty, NOT a
        # successful zero.
        assert not isinstance(outcome, ScopedPromotionHttpSucceeded)
        assert outcome.observation.status_code == 200
        assert outcome.observation.decoding_stage.value == "empty_body"

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

    def test_401_returns_rejected(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(
                401,
                json.dumps({"message": "unauthorized"}).encode(),
            )

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, PromotionHttpRejected)
        assert outcome.observation.status_code == 401

    def test_500_malformed_body_returns_rejected(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(500, b"internal server error stack trace...")

        _, captured = _run_with_loopback(handler)
        outcome = captured["outcome"]
        assert isinstance(outcome, PromotionHttpRejected)
        assert outcome.observation.status_code == 500
        assert outcome.body_excerpt  # type excerpt preserved for diagnostics

    def test_backend_url_missing_returns_before_send_failure(self) -> None:
        from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
            ScopedSchedulerClient,
        )

        client = ScopedSchedulerClient(base_url="", token=None)
        outcome = client.promote_alert_signals_scoped(
            context=_scoped_context(),
        )
        assert isinstance(outcome, PromotionHttpTransportFailureBeforeSend)

    def test_request_id_appears_in_observation(self) -> None:
        def handler(request: _LoopboxRequest) -> None:
            request.respond(200, json.dumps(_valid_canonical_payload()).encode())

        # Use a unique request_id to verify it propagates into the
        # transport observation.
        from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
            ScopedSchedulerClient,
        )

        with _LoopbackServer(handler) as (base_url, _port):
            client = ScopedSchedulerClient(base_url=base_url, token=None)
            outcome = client.promote_alert_signals_scoped(
                context=_scoped_context(request_id="req-unique-xyz"),
            )
        assert outcome.observation.request_id == "req-unique-xyz"
