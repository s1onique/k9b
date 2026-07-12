"""Lifecycle HTTP endpoint tests for
ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.

Covers the internal diagnosis-loop-transition endpoint
(``handle_diagnosis_loop_transition``) and the in-process idempotency
contract. The scheduler-side backend dispatch tests
(``record_diagnosis_loop_*`` against an in-process HTTP backend) and
the higher-level idempotency tests live in
``test_automatic_diagnosis_authority_seam01_dispatch.py``. Shared
helpers live in ``tests/unit/authority_seam_support.py``.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
"""

from __future__ import annotations

import os

from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store
from k8s_diag_agent.ui.server_incident_diagnosis_lifecycle_handler import (
    handle_diagnosis_loop_transition,
)
from tests.unit.authority_seam_support import (
    BuildHandler,
    StubHandler,
    canonical_incident,
    encode,
    reset_env,
)

__all__ = ["reset_env"]


class TestLifecycleEndpoint:
    def test_missing_token_returns_401(self) -> None:
        handler = StubHandler()
        handler.headers = {"Content-Length": "0"}
        os.environ.pop("K9B_INTERNAL_API_TOKEN", None)
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        real = BuildHandler(headers={"Content-Length": "0"})
        from k8s_diag_agent.ui import server_incident_internal_auth

        valid = server_incident_internal_auth._validate_internal_token(real)
        assert valid is False
        os.environ.pop("K9B_INCIDENT_STORE_BACKEND", None)

    def test_handler_applies_started_transition(self) -> None:
        store = IncidentStore()
        set_incident_store(store)
        incident = canonical_incident("incident-lifecycle")
        store._incidents[incident.incident_id] = incident
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        body = encode({
            "schemaVersion": 1,
            "incidentId": "incident-lifecycle",
            "transition": "started",
            "collectorRunId": "collector-1",
            "occurredAt": "2026-07-12T10:00:00+00:00",
            "payload": {},
        })
        real = BuildHandler(
            headers={
                "Authorization": "Bearer test-token",
                "Content-Length": str(len(body)),
            },
            body=body,
        )
        handle_diagnosis_loop_transition(real)
        assert real.sent, "handler did not send a response"
        body_out, status = real.sent[-1]
        assert status == 200
        assert body_out["applied"] is True
        assert body_out["idempotentReplay"] is False

    def test_handler_applies_failed_transition(self) -> None:
        store = IncidentStore()
        set_incident_store(store)
        incident = canonical_incident("incident-failed")
        store._incidents[incident.incident_id] = incident
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        body = encode({
            "schemaVersion": 1,
            "incidentId": "incident-failed",
            "transition": "failed",
            "collectorRunId": "collector-1",
            "occurredAt": "2026-07-12T10:00:00+00:00",
            "payload": {"unavailable_reason": "case_file_error"},
        })
        real = BuildHandler(
            headers={
                "Authorization": "Bearer test-token",
                "Content-Length": str(len(body)),
            },
            body=body,
        )
        handle_diagnosis_loop_transition(real)
        body_out, status = real.sent[-1]
        assert status == 200
        assert body_out["applied"] is True

    def test_handler_applies_completed_transition(self) -> None:
        store = IncidentStore()
        set_incident_store(store)
        incident = canonical_incident("incident-completed")
        store._incidents[incident.incident_id] = incident
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        body = encode({
            "schemaVersion": 1,
            "incidentId": "incident-completed",
            "transition": "completed",
            "collectorRunId": "collector-1",
            "occurredAt": "2026-07-12T10:00:00+00:00",
            "payload": {
                "review_packet_name": "review.json",
                "checks_requested": 4,
                "checks_run": 3,
                "checks_rejected": 1,
                "decision": "stop_root_cause_found",
            },
        })
        real = BuildHandler(
            headers={
                "Authorization": "Bearer test-token",
                "Content-Length": str(len(body)),
            },
            body=body,
        )
        handle_diagnosis_loop_transition(real)
        body_out, status = real.sent[-1]
        assert status == 200
        assert body_out["applied"] is True

    def test_idempotent_replay_returns_true(self) -> None:
        store = IncidentStore()
        set_incident_store(store)
        incident = canonical_incident("incident-replay")
        store._incidents[incident.incident_id] = incident
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        body = encode({
            "schemaVersion": 1,
            "incidentId": "incident-replay",
            "transition": "started",
            "collectorRunId": "collector-1",
            "diagnosisRunId": "run-replay",
            "occurredAt": "2026-07-12T10:00:00+00:00",
            "payload": {},
        })
        first = BuildHandler(
            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
            body=body,
        )
        handle_diagnosis_loop_transition(first)
        body1, status1 = first.sent[-1]
        assert status1 == 200
        assert body1["idempotentReplay"] is False
        second = BuildHandler(
            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
            body=body,
        )
        handle_diagnosis_loop_transition(second)
        body2, status2 = second.sent[-1]
        assert status2 == 200
        assert body2["idempotentReplay"] is True

    def test_unknown_transition_returns_400(self) -> None:
        set_incident_store(IncidentStore())
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        body = encode({
            "schemaVersion": 1,
            "incidentId": "incident-bad",
            "transition": "wat",
            "collectorRunId": "c",
            "occurredAt": "2026-07-12T10:00:00+00:00",
        })
        handler = BuildHandler(
            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
            body=body,
        )
        handle_diagnosis_loop_transition(handler)
        body_out, status = handler.sent[-1]
        assert status == 400
        assert "transition" in body_out.get("message", "").lower()

    def test_unsupported_schema_version_returns_400(self) -> None:
        set_incident_store(IncidentStore())
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        body = encode({
            "schemaVersion": 99,
            "incidentId": "x",
            "transition": "started",
            "collectorRunId": "c",
            "occurredAt": "2026-07-12T10:00:00+00:00",
        })
        handler = BuildHandler(
            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
            body=body,
        )
        handle_diagnosis_loop_transition(handler)
        body_out, status = handler.sent[-1]
        assert status == 400
        assert "schema" in body_out.get("message", "").lower()

    def test_malformed_json_returns_400(self) -> None:
        set_incident_store(IncidentStore())
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        body = b"{not valid json"
        handler = BuildHandler(
            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
            body=body,
        )
        handle_diagnosis_loop_transition(handler)
        body_out, status = handler.sent[-1]
        assert status == 400
        assert "json" in body_out.get("message", "").lower()

    def test_unknown_incident_returns_404(self) -> None:
        set_incident_store(IncidentStore())
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        body = encode({
            "schemaVersion": 1,
            "incidentId": "incident-missing",
            "transition": "started",
            "collectorRunId": "c",
            "occurredAt": "2026-07-12T10:00:00+00:00",
        })
        handler = BuildHandler(
            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
            body=body,
        )
        handle_diagnosis_loop_transition(handler)
        body_out, status = handler.sent[-1]
        assert status == 404
        assert body_out["reasonCode"] == "incident_not_found"

    def test_invalid_run_id_returns_400(self) -> None:
        set_incident_store(IncidentStore())
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "memory"
        body = encode({
            "schemaVersion": 1,
            "incidentId": "incident-1",
            "transition": "started",
            "collectorRunId": "",
            "occurredAt": "2026-07-12T10:00:00+00:00",
        })
        handler = BuildHandler(
            headers={"Authorization": "Bearer test-token", "Content-Length": str(len(body))},
            body=body,
        )
        handle_diagnosis_loop_transition(handler)
        body_out, status = handler.sent[-1]
        assert status == 400
        assert "collectorrunid" in body_out.get("message", "").replace(" ", "").lower()
