"""Deployment-skew contract tests for backend incident-detail parsing.

Pins the contract that, when the backend is older than the scheduler
expectation (e.g. schema version mismatch, payload-type drift), the
typed lookup MUST convert the anomaly into a typed
:data:`BackendIncidentLookupFailed` with the precise failure code
``backend_incident_unsupported_schema`` (or, if the wrapper itself is
malformed, ``backend_incident_invalid_payload``).

It MUST NEVER collapse the anomaly into
:data:`BackendIncidentNotFound`. The deployment-skew regression is
exactly the false-absence scenario that
ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01 was opened to fix.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from k8s_diag_agent.collect.incident_diagnosis_backend_detail_lookup import (
    BackendIncidentHttpResponse,
    lookup_backend_incident,
)
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentLookupFailed,
    BackendIncidentLookupFailureCode,
    BackendIncidentNotFound,
)
from k8s_diag_agent.domain.incident_lifecycle import IncidentId


@dataclass
class _FakeClient:
    response: BackendIncidentHttpResponse

    def fetch_incident(
        self,
        incident_id: IncidentId,
        *,
        timeout: float = 30.0,
    ) -> BackendIncidentHttpResponse:
        return self.response


def _wrap(body: bytes, http_status: int = 200) -> BackendIncidentHttpResponse:
    return BackendIncidentHttpResponse(http_status=http_status, body=body)


# ---------------------------------------------------------------------------
# 1. Schema-version drift
# ---------------------------------------------------------------------------


class TestUnsupportedSchemaVersion:
    def test_schema_version_999_yields_unsupported_schema_failure(self) -> None:
        """A future schema version MUST become UNSUPPORTED_SCHEMA, not
        BackendIncidentNotFound, not Found."""
        payload = {
            "schema_version": "999",
            "payload_type": "incident-internal-detail",
            "incident": {
                "incident_id": "incident-abc",
                "first_observed_at": "2026-07-12T10:00:00+00:00",
                "last_observed_at": "2026-07-12T10:30:00+00:00",
            },
        }
        client = _FakeClient(
            response=_wrap(json.dumps(payload).encode("utf-8"))
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == (
            BackendIncidentLookupFailureCode.UNSUPPORTED_SCHEMA
        )
        # Crucially, NOT a not-found outcome.
        assert not isinstance(outcome, BackendIncidentNotFound)

    def test_schema_version_int_2_yields_unsupported_schema_failure(self) -> None:
        payload = {
            "schema_version": 2,
            "payload_type": "incident-internal-detail",
            "incident": {"incident_id": "incident-abc"},
        }
        client = _FakeClient(
            response=_wrap(json.dumps(payload).encode("utf-8"))
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == (
            BackendIncidentLookupFailureCode.UNSUPPORTED_SCHEMA
        )

    def test_schema_version_negative_yields_invalid_payload(self) -> None:
        payload = {
            "schema_version": "-1",
            "payload_type": "incident-internal-detail",
            "incident": {"incident_id": "incident-abc"},
        }
        client = _FakeClient(
            response=_wrap(json.dumps(payload).encode("utf-8"))
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        # Negative integers parse via int() but the parser rejects
        # them as not equal to the supported value 1.
        assert outcome.failure_code in (
            BackendIncidentLookupFailureCode.UNSUPPORTED_SCHEMA,
            BackendIncidentLookupFailureCode.INVALID_PAYLOAD,
        )

    def test_schema_version_with_nonsense_type_yields_invalid_payload(
        self,
    ) -> None:
        payload = {
            "schema_version": ["not", "a", "string"],
            "payload_type": "incident-internal-detail",
            "incident": {"incident_id": "incident-abc"},
        }
        client = _FakeClient(
            response=_wrap(json.dumps(payload).encode("utf-8"))
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == (
            BackendIncidentLookupFailureCode.INVALID_PAYLOAD
        )


# ---------------------------------------------------------------------------
# 2. Payload-type drift
# ---------------------------------------------------------------------------


class TestUnknownPayloadType:
    def test_unknown_payload_type_yields_invalid_payload(self) -> None:
        payload = {
            "schema_version": "1",
            "payload_type": "incident-internal-summary-or-other",
            "incident": {"incident_id": "incident-abc"},
        }
        client = _FakeClient(
            response=_wrap(json.dumps(payload).encode("utf-8"))
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == (
            BackendIncidentLookupFailureCode.INVALID_PAYLOAD
        )
        assert not isinstance(outcome, BackendIncidentNotFound)

    def test_missing_payload_type_yields_invalid_payload(self) -> None:
        payload = {
            "schema_version": "1",
            # No payload_type
            "incident": {"incident_id": "incident-abc"},
        }
        client = _FakeClient(
            response=_wrap(json.dumps(payload).encode("utf-8"))
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == (
            BackendIncidentLookupFailureCode.INVALID_PAYLOAD
        )

    def test_empty_string_payload_type_yields_invalid_payload(self) -> None:
        payload = {
            "schema_version": "1",
            "payload_type": "",
            "incident": {"incident_id": "incident-abc"},
        }
        client = _FakeClient(
            response=_wrap(json.dumps(payload).encode("utf-8"))
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == (
            BackendIncidentLookupFailureCode.INVALID_PAYLOAD
        )


# ---------------------------------------------------------------------------
# 3. Missing envelope entirely (older backend without envelope)
# ---------------------------------------------------------------------------


class TestLegacyBareAggregate:
    def test_bare_aggregate_without_envelope_yields_invalid_payload(
        self,
    ) -> None:
        """A bare canonical-shaped aggregate (no envelope) used to be
        accepted by the legacy parser; the canonical parser must
        classify it as INVALID_PAYLOAD (deployment skew) instead of
        silently accepting it."""
        payload = {
            "incident_id": "incident-abc",
            "source_candidate_id": "candidate-xyz",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "nginx-pod",
            "class": "PodCrashLoop",
            "severity": "high",
            "status": "open",
            "first_observed_at": "2026-07-12T10:00:00+00:00",
            "last_observed_at": "2026-07-12T10:30:00+00:00",
        }
        client = _FakeClient(
            response=_wrap(json.dumps(payload).encode("utf-8"))
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        # The canonical parser must reject the bare aggregate
        # (no payload_type / schema_version envelope) as INVALID_PAYLOAD
        # because the deployment is older than the scheduler expectation.
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == (
            BackendIncidentLookupFailureCode.INVALID_PAYLOAD
        )
        # Crucially, NOT a not-found outcome.
        assert not isinstance(outcome, BackendIncidentNotFound)


# ---------------------------------------------------------------------------
# 4. Genuine 404 must still emit NotFound
# ---------------------------------------------------------------------------


class TestGenuine404IsNotMisreadAsSkew:
    def test_genuine_404_with_empty_body_emits_not_found(self) -> None:
        """A real 404 must still be classified as NotFound; deployment
        skew NEVER becomes NotFound."""
        client = _FakeClient(
            response=_wrap(b"", http_status=404)
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentNotFound)
        assert outcome.http_status == 404

    def test_genuine_404_with_error_body_emits_not_found(self) -> None:
        body = b'{"error":"incident not found","trace_id":"abc"}'
        client = _FakeClient(
            response=_wrap(body, http_status=404)
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentNotFound)
