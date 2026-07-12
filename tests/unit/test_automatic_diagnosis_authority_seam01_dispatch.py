"""Scheduler-side backend dispatch + idempotency tests for
ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.

Covers:

* ``record_diagnosis_loop_*`` in backend mode — authenticated HTTP POST
  against an in-process ``ThreadingHTTPServer``-based stub backend.
* Failure translation: 404 → ``incident_not_found``, 5xx →
  ``backend_error``, transport errors must NOT fall back to the local
  store.
* Idempotency: repeated deliveries collapse into one apply plus N-1
  replays; concurrent overlapping deliveries apply exactly once;
  same-key+different-payload → 409 conflict.

The lifecycle HTTP endpoint tests live in
``test_automatic_diagnosis_authority_seam01_endpoint.py``. Shared
helpers live in ``tests/unit/authority_seam_support.py``.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
"""

from __future__ import annotations

import socket
import threading
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_authority_seam import (
    LifecycleWriteApplied,
    LifecycleWriteFailed,
    LifecycleWriteRejected,
    record_diagnosis_loop_completed,
    record_diagnosis_loop_failed,
    record_diagnosis_loop_started,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store
from tests.unit.authority_seam_support import (
    RecordingHandler,
    canonical_incident,
    reset_env,
    start_backend_server,
)

__all__ = ["reset_env"]


class TestBackendModeDispatch:
    def test_backend_mode_lifecycle_calls_internal_api(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _server, base_url, shutdown = start_backend_server()
        try:
            monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
            monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", base_url)
            monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
            monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
            monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
            outcome = record_diagnosis_loop_started(
                incident_id="incident-backend",
                run_id="run-x",
                collector_run_id="collector-x",
            )
            assert isinstance(outcome, LifecycleWriteApplied)
            assert outcome.http_status == 200
            assert outcome.idempotent_replay is False
            assert RecordingHandler.recorded, "no request recorded"
            req = RecordingHandler.recorded[-1]
            assert req["path"] == "/api/internal/incidents/diagnosis-loop-transition"
            assert "Bearer test-token" in req["headers"].get("Authorization", "")
            body = req["body"]
            assert body["schemaVersion"] == 1
            assert body["incidentId"] == "incident-backend"
            assert body["transition"] == "started"
            assert body["diagnosisRunId"] == "run-x"
        finally:
            shutdown()

    def test_backend_mode_lifecycle_404_returns_incident_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _server, base_url, shutdown = start_backend_server(
            response_status=404,
            response_body={
                "schemaVersion": 1,
                "applied": False,
                "reasonCode": "incident_not_found",
            },
        )
        try:
            monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
            monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", base_url)
            monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
            monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
            monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
            outcome = record_diagnosis_loop_completed(
                incident_id="incident-missing",
                run_id="run-x",
                collector_run_id="collector-x",
            )
            assert isinstance(outcome, LifecycleWriteFailed)
            assert outcome.reason_code == "incident_not_found"
        finally:
            shutdown()

    def test_backend_mode_5xx_returns_backend_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _server, base_url, shutdown = start_backend_server(
            response_status=500,
            response_body={"schemaVersion": 1, "message": "boom"},
        )
        try:
            monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
            monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", base_url)
            monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
            monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
            monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
            outcome = record_diagnosis_loop_failed(
                incident_id="incident-1",
                run_id="run-1",
                collector_run_id="collector-1",
                unavailable_reason="case_file_error",
            )
            assert isinstance(outcome, LifecycleWriteFailed)
            assert outcome.reason_code == "backend_error"
        finally:
            shutdown()

    def test_backend_mode_transport_error_does_not_fall_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Backend transport failure must NOT fall back to the local store."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        base_url = f"http://127.0.0.1:{port}"

        store = IncidentStore()
        set_incident_store(store)
        store._incidents["incident-1"] = canonical_incident("incident-1")

        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
        monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", base_url)
        monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
        monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
        monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")

        outcome = record_diagnosis_loop_started(
            incident_id="incident-1",
            run_id="run-1",
            collector_run_id="collector-1",
        )
        assert isinstance(outcome, (LifecycleWriteFailed, LifecycleWriteRejected))

    def test_backend_mode_missing_token_returns_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
        monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", "http://127.0.0.1:1")
        monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
        monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
        outcome = record_diagnosis_loop_started(
            incident_id="incident-1", run_id="r", collector_run_id="c"
        )
        assert isinstance(outcome, LifecycleWriteFailed)
        assert outcome.reason_code == "missing_internal_token"


class TestIdempotency:
    def test_repeated_lifecycle_deliveries_collapse(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _server, base_url, shutdown = start_backend_server()
        try:
            monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
            monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", base_url)
            monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
            monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
            monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")
            seen: list[bool] = []
            for _ in range(3):
                outcome = record_diagnosis_loop_started(
                    incident_id="incident-rep",
                    run_id="run-1",
                    collector_run_id="collector-1",
                )
                assert isinstance(outcome, LifecycleWriteApplied)
                seen.append(outcome.idempotent_replay)
            assert seen.count(False) == 1
            assert seen.count(True) == 2
        finally:
            shutdown()

    def test_concurrent_duplicate_deliveries_apply_once(self) -> None:
        """Overlapping identical deliveries must not both apply.

        ``ThreadingHTTPServer`` dispatches requests on separate threads,
        so this fires overlapping deliveries directly against the
        handler and asserts exactly one fresh apply plus N-1 idempotent
        replays and no conflict.
        """
        import os as _os

        from k8s_diag_agent.ui.server_incident_diagnosis_lifecycle_handler import (
            handle_diagnosis_loop_transition,
        )
        from tests.unit.authority_seam_support import BuildHandler, encode

        store = IncidentStore()
        set_incident_store(store)
        incident = canonical_incident("incident-concurrent")
        store._incidents[incident.incident_id] = incident
        _os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        _os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        try:
            body = encode({
                "schemaVersion": 1,
                "incidentId": "incident-concurrent",
                "transition": "started",
                "collectorRunId": "collector-1",
                "diagnosisRunId": "run-conc",
                "occurredAt": "2026-07-12T10:00:00+00:00",
                "payload": {},
            })
            n = 8
            results: list[tuple[dict[str, Any], int]] = []
            results_lock = threading.Lock()
            barrier = threading.Barrier(n)

            def deliver() -> None:
                handler = BuildHandler(
                    headers={
                        "Authorization": "Bearer test-token",
                        "Content-Length": str(len(body)),
                    },
                    body=body,
                )
                barrier.wait()
                handle_diagnosis_loop_transition(handler)
                with results_lock:
                    results.append(handler.sent[-1])

            threads = [threading.Thread(target=deliver) for _ in range(n)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(results) == n
            assert all(status == 200 for _, status in results)
            replays = [payload["idempotentReplay"] for payload, _ in results]
            assert replays.count(False) == 1
            assert replays.count(True) == n - 1
        finally:
            _os.environ.pop("K9B_INTERNAL_API_TOKEN", None)
            _os.environ.pop("K9B_INCIDENT_STORE_BACKEND", None)

    def test_same_key_different_payload_conflicts(self) -> None:
        """Same idempotency key + different payload → 409 conflict."""
        import os as _os

        from k8s_diag_agent.collect.incident_store_provider import (
            set_incident_store,
        )
        from k8s_diag_agent.ui.server_incident_diagnosis_lifecycle_handler import (
            handle_diagnosis_loop_transition,
        )
        from tests.unit.authority_seam_support import BuildHandler, encode

        store = IncidentStore()
        set_incident_store(store)
        incident = canonical_incident("incident-conflict")
        store._incidents[incident.incident_id] = incident
        _os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        _os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        try:
            def _completed_body(review_packet_name: str) -> bytes:
                return encode({
                    "schemaVersion": 1,
                    "incidentId": "incident-conflict",
                    "transition": "completed",
                    "collectorRunId": "collector-1",
                    "diagnosisRunId": "run-conf",
                    "occurredAt": "2026-07-12T10:00:00+00:00",
                    "payload": {
                        "review_packet_name": review_packet_name,
                        "checks_requested": 1,
                        "checks_run": 1,
                        "checks_rejected": 0,
                        "decision": "stop_root_cause_found",
                    },
                })

            first_body = _completed_body("review-a.json")
            first = BuildHandler(
                headers={
                    "Authorization": "Bearer test-token",
                    "Content-Length": str(len(first_body)),
                },
                body=first_body,
            )
            handle_diagnosis_loop_transition(first)
            body1, status1 = first.sent[-1]
            assert status1 == 200
            assert body1["applied"] is True
            assert body1["idempotentReplay"] is False

            second_body = _completed_body("review-b.json")
            second = BuildHandler(
                headers={
                    "Authorization": "Bearer test-token",
                    "Content-Length": str(len(second_body)),
                },
                body=second_body,
            )
            handle_diagnosis_loop_transition(second)
            body2, status2 = second.sent[-1]
            assert status2 == 409
            assert body2["applied"] is False
            assert body2["reasonCode"] == "transition_replay_mismatch"
        finally:
            _os.environ.pop("K9B_INTERNAL_API_TOKEN", None)
            _os.environ.pop("K9B_INCIDENT_STORE_BACKEND", None)
