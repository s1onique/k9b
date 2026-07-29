"""Shared support for the scoped client-to-mapper test modules.

ACT-K9B-HULK-PROMOTION-TYPED-DISPATCH-RESULT-AND-SUMMARY-CONVERGENCE01.

Defines the loopback server, the scoped context factory, and the
canonical payload generators used by every focused test module.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpRequestContext,
)
from k8s_diag_agent.domain.identifiers import AlertSignalId, HealthRunId
from k8s_diag_agent.incident_alert_promotion_contract import (
    PromoteAlertSignalsRequest,
)

TEST_TOKEN = "ci-only-synthetic-token-1234"
RUN_ID = "health-run-20260729T063234Z"
REQUEST_ID = "promotion-request-attempt-002"


def scoped_context(
    signal_ids: tuple[str, ...] = ("sig-A",),
    *,
    request_id: str = REQUEST_ID,
) -> ScopedPromotionHttpRequestContext:
    """Build a canonical scoped request context for tests."""
    request = PromoteAlertSignalsRequest(
        run_id=HealthRunId(RUN_ID),
        source_identity="source-A",
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )
    return ScopedPromotionHttpRequestContext(
        request=request,
        request_id=request_id,
    )


def valid_canonical_payload(actionable: tuple[str, ...]) -> dict[str, Any]:
    """Build a canonical success payload with the given actionable IDs."""
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
        content_length: int | None = None,
    ) -> None:
        self._response = {
            "status": status,
            "headers": {"Content-Type": content_type},
            "body": body,
            "content_length": content_length,
        }


class LoopbackServer:
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


def run_client(
    handler: Callable[[_LoopboxRequest], None],
) -> tuple[
    ScopedPromotionHttpRequestContext,
    object,
]:
    """Run the loopback server and invoke the real scoped client.

    Returns the typed context and the typed transport outcome.
    """
    from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
        ScopedSchedulerClient,
    )

    context = scoped_context()
    with LoopbackServer(handler) as (base_url, _port):
        client = ScopedSchedulerClient(base_url=base_url, token=TEST_TOKEN)
        transport = client.promote_alert_signals_scoped(context=context)
    return context, transport


def run_round_trip(
    handler: Callable[[_LoopboxRequest], None],
) -> tuple[
    ScopedPromotionHttpRequestContext,
    object,
    object,
]:
    """Run the loopback server, the real client, and the typed mapper.

    Returns ``(context, transport, projection)``.
    """
    from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
        map_scoped_http_transport_to_promotion_outcome,
    )

    context, transport = run_client(handler)
    projection = map_scoped_http_transport_to_promotion_outcome(
        transport, context=context
    )
    return context, transport, projection
