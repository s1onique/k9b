"""Shared helpers for the ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
test modules.

This module is intentionally *not* a ``test_*`` file, so pytest does not
collect it directly. It hosts the fixtures, canonical builders, and
minimal handler stand-ins shared between:

* ``test_automatic_diagnosis_authority_seam01.py`` (aggregate evaluator
  + processor regressions), and
* ``test_automatic_diagnosis_authority_seam01_endpoint.py`` (lifecycle
  endpoint + backend dispatch + idempotency/concurrency).

Splitting keeps each test file under the LLM-friendly size threshold
while sharing a single source of truth for the fixtures.
"""

from __future__ import annotations

import io
import json
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, NoReturn

import pytest

from k8s_diag_agent.collect.incident_diagnosis_backend_detail_parser import (
    SUPPORTED_PAYLOAD_TYPE,
    SUPPORTED_SCHEMA_VERSION,
)
from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentStatus,
)
from k8s_diag_agent.collect.incident_store_provider import (
    set_incident_store,
)


@pytest.fixture(autouse=True)
def reset_env(monkeypatch: pytest.MonkeyPatch) -> Iterable[None]:
    """Reset the incident store and env vars between tests.

    Imported (and thereby auto-registered) by each test module.
    """
    set_incident_store(None)
    for var in (
        "K9B_INCIDENT_PROMOTION_MODE",
        "K9B_BACKEND_INTERNAL_URL",
        "K9B_INTERNAL_API_TOKEN",
        "K9B_INCIDENT_STORE_BACKEND",
        "K9B_PROCESS_ROLE",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
    set_incident_store(None)


def canonical_incident(
    incident_id: str = "incident-abc",
    status: IncidentStatus = IncidentStatus.OPEN,
) -> Incident:
    """Build a canonical :class:`Incident` aggregate."""
    now = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)
    return Incident(
        incident_id=incident_id,
        source_candidate_id="candidate-xyz",
        namespace="default",
        object_kind="Pod",
        object_name="nginx-pod",
        raw_object_kind="Pod",
        candidate_class="health",
        severity="warning",
        status=status,
        first_observed_at=now,
        last_observed_at=now,
        signal_count=1,
        evidence_count=0,
    )


def canonical_payload(incident_id: str = "incident-abc") -> dict[str, Any]:
    return {
        "schema_version": str(SUPPORTED_SCHEMA_VERSION),
        "payload_type": SUPPORTED_PAYLOAD_TYPE,
        "incident": {
            "incident_id": incident_id,
            "source_candidate_id": "candidate-xyz",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "nginx-pod",
            "class": "health",
            "severity": "warning",
            "status": IncidentStatus.OPEN.value,
            "first_observed_at": "2026-07-12T10:00:00+00:00",
            "last_observed_at": "2026-07-12T10:30:00+00:00",
            "signal_count": 1,
            "evidence_count": 0,
        },
    }


def encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def never_called(**kwargs: Any) -> Any:  # pragma: no cover - helper
    raise AssertionError("lifecycle failure should not be reached")


class StubEligibility:
    """Stub eligibility result used by the processor regression tests."""

    def __init__(self, *, eligible: bool, reason: str) -> None:
        self.eligible = eligible
        self.reason = reason
        self.budget_diagnostics: tuple[Any, ...] = ()
        self.status: str | None = None
        self.has_suggested_checks: bool = False
        self.auto_pass_count: int = 0


class StubHandler:
    """Mimics the BaseHTTPRequestHandler surface used by the handler."""

    def __init__(self, payload: dict[str, Any] | None = None, status: int = 200) -> None:
        self._payload = payload or {}
        self._status = status
        self.sent: list[tuple[dict[str, Any], int]] = []
        self.headers: dict[str, str] = {}

    def _send_json(self, payload: dict[str, Any], status: int) -> None:
        self.sent.append((payload, status))


class BuildHandler:
    """Minimal stand-in for ``HealthUIRequestHandler`` used by the
    lifecycle handler. Implements only the surface the handler actually
    calls: ``headers`` (mapping), ``rfile.read()``, ``_send_json()``."""

    def __init__(
        self,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> None:
        self.headers = headers or {}
        self._body = body or b""
        # The production handler reads the request body via
        # ``handler.rfile.read(length)``; back it with a BytesIO so the
        # endpoint tests exercise the real request-parsing path.
        self.rfile = io.BytesIO(self._body)
        self.sent: list[tuple[dict[str, Any], int]] = []

    def _send_json(self, payload: dict[str, Any], status: int) -> None:
        self.sent.append((payload, status))


class RecordingHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that records lifecycle requests.

    When no explicit ``response_body`` override is configured, the
    handler models a backend that collapses idempotent deliveries: the
    first delivery for a given identity key reports
    ``idempotentReplay=false`` and subsequent identical deliveries
    report ``idempotentReplay=true``. This lets the client-side tests
    prove they surface backend-reported idempotency.
    """

    recorded: list[dict[str, Any]] = []
    status: int = 200
    response_body: dict[str, Any] | None = None
    _seen_keys: set[tuple[Any, ...]] = set()

    def log_message(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        return

    def do_POST(self) -> None:  # noqa: N802 - HTTP verb
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {}
        RecordingHandler.recorded.append(
            {
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": body,
            }
        )
        if RecordingHandler.response_body is not None:
            response = dict(RecordingHandler.response_body)
        else:
            key = (
                body.get("incidentId"),
                body.get("transition"),
                body.get("collectorRunId"),
                body.get("diagnosisRunId"),
            )
            replay = key in RecordingHandler._seen_keys
            RecordingHandler._seen_keys.add(key)
            response = {
                "schemaVersion": 1,
                "applied": True,
                "idempotentReplay": replay,
            }
        body_bytes = json.dumps(response).encode("utf-8")
        self.send_response(RecordingHandler.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)


def start_backend_server(
    *,
    response_status: int = 200,
    response_body: dict[str, Any] | None = None,
) -> tuple[ThreadingHTTPServer, str, Callable[[], None]]:
    """Spin up a localhost HTTP server with a recording handler."""
    RecordingHandler.recorded.clear()
    RecordingHandler.status = response_status
    RecordingHandler.response_body = response_body
    RecordingHandler._seen_keys = set()
    server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    def shutdown() -> None:
        server.shutdown()
        server.server_close()

    return server, base_url, shutdown


def forbidden_lookup(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError(
        "aggregate evaluator performed an incident lookup (forbidden)"
    )
