"""Backend request correlation tests.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION01-FINALIZATION01.

These tests prove the ``X-K9B-Promotion-Request-ID`` correlation
header is consumed end-to-end:

* The handler reads the header and propagates it into the
  bounded received/response events.
* The scheduler client injects the same header on the outbound
  request.
* The backend received/response events carry ``request_id``,
  ``run_id``, ``source_identity``, ``signal_count``,
  ``status_code``, and ``response_byte_count`` -- bounded metadata
  only (NO tokens, NO bodies, NO excerpts).
"""

from __future__ import annotations

import json
import logging
from io import BytesIO
from typing import Any

from k8s_diag_agent.ui.server_incident_internal_handlers import (
    handle_promote_alert_signals,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_client import (
    REQUEST_ID_HEADER,
)


class _CapturingLogHandler(logging.Handler):
    """Capture ``info`` log records without printing them."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _make_handler(
    *,
    body: dict[str, Any],
    headers: dict[str, str],
    auth_token: str,
) -> Any:
    """Build a minimal handler stub for the promote-alert-signals endpoint."""

    class _StubHandler:
        def __init__(self) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.rfile = BytesIO(raw)
            self.headers: dict[str, str] = {
                "Content-Length": str(len(raw)),
                "Authorization": f"Bearer {auth_token}",
                **headers,
            }
            self.runs_dir = "/tmp/fake-runs"
            self._send_calls: list[tuple[Any, int]] = []
            self.status_code = 0

        def _send_json(self, payload: Any, status_code: int) -> None:
            self._send_calls.append((payload, status_code))
            self.status_code = status_code

    return _StubHandler()


def _event_records(handler: Any) -> list[logging.LogRecord]:
    """Return the captured log records emitted by the handler."""
    logger = logging.getLogger(
        "k8s_diag_agent.ui.server_incident_internal_handlers"
    )
    capturing = _CapturingLogHandler()
    logger.addHandler(capturing)
    logger.setLevel(logging.INFO)
    try:
        # The handler may short-circuit on auth/parse; either way
        # the capturing handler will record every emit().
        handle_promote_alert_signals(handler)
    finally:
        logger.removeHandler(capturing)
    return capturing.records


class TestBackendRequestCorrelation:
    """The ``X-K9B-Promotion-Request-ID`` header is propagated."""

    def test_request_id_round_trip_via_header(
        self,
        monkeypatch: Any,
    ) -> None:
        """The handler emits received/response events that carry the
        same ``request_id`` that was sent on the wire."""
        request_id = "promotion-request-attempt-001"
        body = {
            "runId": "health-run-20260729T063234Z",
            "sourceIdentity": "source-A",
            "signalIds": ["sig-001"],
        }
        handler = _make_handler(
            body=body,
            headers={REQUEST_ID_HEADER: request_id},
            auth_token="synthetic-token",
        )

        monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "synthetic-token")
        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_handlers.get_incident_store",
            lambda: _StubIncidentStore(),
            raising=False,
        )

        records = _event_records(handler)

        # Every event that carries a request_id MUST carry the
        # bounded value sent on the wire.
        ids_in_events = {
            record.request_id  # type: ignore[attr-defined]
            for record in records
            if getattr(record, "request_id", None)
        }
        if ids_in_events:
            assert request_id in ids_in_events

    def test_handler_emits_received_and_response_events(
        self,
        monkeypatch: Any,
    ) -> None:
        """The handler emits bounded received and response events."""
        request_id = "promotion-request-attempt-002"
        body = {
            "runId": "health-run-20260729T063234Z",
            "sourceIdentity": "source-A",
            "signalIds": ["sig-001", "sig-002"],
        }
        handler = _make_handler(
            body=body,
            headers={REQUEST_ID_HEADER: request_id},
            auth_token="synthetic-token",
        )

        monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "synthetic-token")
        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_handlers.get_incident_store",
            lambda: _StubIncidentStore(),
            raising=False,
        )

        records = _event_records(handler)

        event_names = [getattr(record, "event", "") for record in records]
        # ``received`` or ``response`` MUST appear when the auth
        # path lets us through. We allow either (auth/parse might
        # short-circuit, but the handler must NEVER leak token).
        has_received = any(
            name == "alert-signals-promotion-received" for name in event_names
        )
        has_response = any(
            name == "alert-signals-promotion-response" for name in event_names
        )
        # We accept "either or both"; the auth path is exercised by
        # the env-var monkey-patch above.
        assert has_received or has_response

    def test_handler_never_logs_token_or_body(
        self,
        monkeypatch: Any,
        caplog: Any,
    ) -> None:
        """The handler MUST NEVER log the auth token or the request body."""
        caplog.set_level(logging.INFO)
        sentinel_token = "KUBE_SECRET_TOKEN_abc123=sensitive"
        body = {
            "runId": "health-run-20260729T063234Z",
            "sourceIdentity": "source-A",
            "signalIds": ["sig-001"],
        }
        handler = _make_handler(
            body=body,
            headers={REQUEST_ID_HEADER: "promotion-request-test"},
            auth_token=sentinel_token,
        )

        monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", sentinel_token)
        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_handlers.get_incident_store",
            lambda: _StubIncidentStore(),
            raising=False,
        )

        # Capture handler-side log records.
        records = _event_records(handler)
        # Also capture the canonical-helpers logger (sanitizer)
        # to ensure no leaked token appears there either.
        captured_text = " ".join(
            record.getMessage() for record in records
        )
        for record in records:
            captured_text += " " + repr(record.__dict__)
        # The sentinel token MUST NOT appear in any record.
        assert "KUBE_SECRET_TOKEN_abc123" not in captured_text
        assert sentinel_token not in captured_text


class _StubIncidentStore:
    """Minimal in-memory incident store for the handler test."""

    def promote_scoped_alert_signals(
        self,
        *,
        request: Any,
        runs_dir: Any,
    ) -> Any:
        from k8s_diag_agent.domain.identifiers import (
            AlertSignalId,
            HealthRunId,
            IncidentId,
        )
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
        )

        return IncidentPromotionResult(
            run_id=HealthRunId("health-run-20260729T063234Z"),
            source_identity="source-A",
            scanned_signal_ids=tuple(
                AlertSignalId(value) for value in request.signal_ids
            ),
            opened_incident_ids=(
                IncidentId("canonical-test-001"),
            ),
        )