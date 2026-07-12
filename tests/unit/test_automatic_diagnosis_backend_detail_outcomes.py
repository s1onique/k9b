"""Unit tests for the backend incident-detail lookup outcome algebra.

Covers the invariant from
ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01: a successful HTTP 200
response cannot be converted into ``BackendIncidentNotFound`` through
any parser/schema/deserialization/identity failure.

These tests use a fake :class:`BackendIncidentClient` to exercise the
canonical lookup function directly; no real network calls are made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_backend_detail_lookup import (
    BackendIncidentHttpResponse,
    BackendIncidentTransportError,
    lookup_backend_incident,
)
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentFound,
    BackendIncidentLookupFailed,
    BackendIncidentLookupFailureCode,
    BackendIncidentNotFound,
)
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_parser import (
    SUPPORTED_PAYLOAD_TYPE,
    SUPPORTED_SCHEMA_VERSION,
)
from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentStatus,
)
from k8s_diag_agent.domain.incident_lifecycle import IncidentId

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeClient:
    """Programmable :class:`BackendIncidentClient` implementation."""

    response: BackendIncidentHttpResponse | None = None
    error: Exception | None = None
    calls: list[IncidentId] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

    def fetch_incident(
        self,
        incident_id: IncidentId,
        *,
        timeout: float = 30.0,
    ) -> BackendIncidentHttpResponse:
        self.calls.append(incident_id)
        if self.error is not None:
            raise self.error
        assert self.response is not None, "FakeClient response must be set"
        return self.response


def _canonical_incident_payload(
    incident_id: str = "incident-abc",
) -> dict[str, Any]:
    """Build a valid wrapped canonical payload as the backend would emit."""
    return {
        "schema_version": str(SUPPORTED_SCHEMA_VERSION),
        "payload_type": SUPPORTED_PAYLOAD_TYPE,
        "incident": {
            "incident_id": incident_id,
            "source_candidate_id": "candidate-xyz",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "nginx-pod",
            "class": "PodCrashLoop",
            "severity": "high",
            "status": IncidentStatus.OPEN.value,
            "first_observed_at": "2026-07-12T10:00:00+00:00",
            "last_observed_at": "2026-07-12T10:30:00+00:00",
            "signal_count": 1,
            "evidence_count": 0,
        },
    }


def _expected_incident(
    incident_id: str = "incident-abc",
) -> Incident:
    """Build the canonical :class:`Incident` that should deserialize."""
    return Incident.from_dict(_canonical_incident_payload(incident_id)["incident"])


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


class TestCanonicalFound:
    def test_200_with_canonical_payload_returns_backend_incident_found(self) -> None:
        """200 + canonical payload → BackendIncidentFound."""
        payload = _canonical_incident_payload("incident-abc")
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode_payload(payload),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentFound)
        assert outcome.requested_incident_id == IncidentId("incident-abc")
        assert outcome.http_status == 200
        assert outcome.payload_type == SUPPORTED_PAYLOAD_TYPE
        assert outcome.payload_schema_version == SUPPORTED_SCHEMA_VERSION

    def _encode_payload(self, payload: dict[str, Any]) -> bytes:
        import json

        return json.dumps(payload).encode("utf-8")

    def test_found_outcome_contains_requested_branded_incident_id(self) -> None:
        """Found outcome must retain the branded IncidentId (not bare str)."""
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode_payload(_canonical_incident_payload("incident-abc")),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentFound)
        assert outcome.requested_incident_id == IncidentId("incident-abc")
        # The branded type is distinct from a bare str at type-check time.
        assert isinstance(outcome.requested_incident_id, str)

    def test_found_outcome_contains_deserialized_domain_incident(self) -> None:
        """Found outcome must carry a real deserialized ``Incident``."""
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode_payload(_canonical_incident_payload("incident-abc")),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentFound)
        assert isinstance(outcome.incident, Incident)
        assert outcome.incident.incident_id == "incident-abc"
        assert outcome.incident.status == IncidentStatus.OPEN


# ---------------------------------------------------------------------------
# 2. Genuine not-found
# ---------------------------------------------------------------------------


class TestNotFound:
    def test_404_returns_backend_incident_not_found(self) -> None:
        """404 → BackendIncidentNotFound (the ONLY path)."""
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=404,
                body=b"",
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-missing"))
        assert isinstance(outcome, BackendIncidentNotFound)
        assert outcome.requested_incident_id == IncidentId("incident-missing")
        assert outcome.http_status == 404


# ---------------------------------------------------------------------------
# 3. Status code mapping
# ---------------------------------------------------------------------------


class TestStatusClassification:
    @pytest.mark.parametrize(
        "status_code,expected_code",
        [
            (401, BackendIncidentLookupFailureCode.UNAUTHORIZED),
            (403, BackendIncidentLookupFailureCode.FORBIDDEN),
            (400, BackendIncidentLookupFailureCode.HTTP_CLIENT_ERROR),
            (418, BackendIncidentLookupFailureCode.HTTP_CLIENT_ERROR),
            (429, BackendIncidentLookupFailureCode.HTTP_CLIENT_ERROR),
            (500, BackendIncidentLookupFailureCode.BACKEND_ERROR),
            (502, BackendIncidentLookupFailureCode.BACKEND_ERROR),
            (503, BackendIncidentLookupFailureCode.BACKEND_ERROR),
        ],
    )
    def test_non_200_non_404_status_maps_to_failure(
        self, status_code: int, expected_code: BackendIncidentLookupFailureCode
    ) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=status_code,
                body=b"",
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed), (
            f"Expected BackendIncidentLookupFailed for status {status_code}, "
            f"got {type(outcome).__name__}"
        )
        assert outcome.failure_code == expected_code
        assert outcome.http_status == status_code

    @pytest.mark.parametrize("status_code", [204, 301, 302, 304])
    def test_unexpected_2xx_3xx_maps_to_transport_error(self, status_code: int) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=status_code,
                body=b"",
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.TRANSPORT_ERROR


# ---------------------------------------------------------------------------
# 4. Transport errors
# ---------------------------------------------------------------------------


class TestTransportErrors:
    def test_timeout_returns_transport_error(self) -> None:
        client = FakeClient(
            error=BackendIncidentTransportError(
                "request to backend timed out",
                exception_type="TimeoutError",
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.TRANSPORT_ERROR
        assert outcome.exception_type == "TimeoutError"

    def test_connection_failure_returns_transport_error(self) -> None:
        client = FakeClient(
            error=BackendIncidentTransportError(
                "connection refused",
                exception_type="ConnectionRefusedError",
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.TRANSPORT_ERROR
        assert outcome.exception_type == "ConnectionRefusedError"

    def test_unexpected_exception_returns_transport_error_not_not_found(self) -> None:
        """Defensive: unexpected client exceptions must NOT become not-found."""
        client = FakeClient(error=RuntimeError("boom"))
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.TRANSPORT_ERROR
        assert outcome.exception_type == "RuntimeError"
        # Crucially, NOT a BackendIncidentNotFound.
        assert not isinstance(outcome, BackendIncidentNotFound)


# ---------------------------------------------------------------------------
# 5. Body / JSON / envelope / schema failures
# ---------------------------------------------------------------------------


class TestBodyFailures:
    def _encode(self, payload: Any) -> bytes:
        import json

        return json.dumps(payload).encode("utf-8")

    def test_200_empty_body_returns_invalid_json(self) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(http_status=200, body=b"")
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.INVALID_JSON
        assert outcome.http_status == 200

    def test_200_malformed_json_returns_invalid_json(self) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=b"{not valid json",
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.INVALID_JSON

    def test_200_json_array_returns_invalid_payload(self) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode([{"x": 1}]),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.INVALID_PAYLOAD

    def test_200_missing_envelope_returns_invalid_payload(self) -> None:
        """Bare aggregate without envelope must be rejected."""
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode(
                    {
                        "incident_id": "incident-abc",
                        "first_observed_at": "2026-07-12T10:00:00+00:00",
                        "last_observed_at": "2026-07-12T10:30:00+00:00",
                    }
                ),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.INVALID_PAYLOAD

    def test_200_wrong_payload_type_returns_invalid_payload(self) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode(
                    {
                        "schema_version": str(SUPPORTED_SCHEMA_VERSION),
                        "payload_type": "incident-internal-summary",
                        "incident": {"incident_id": "incident-abc"},
                    }
                ),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.INVALID_PAYLOAD

    def test_200_unsupported_schema_version_returns_unsupported_schema(self) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode(
                    {
                        "schema_version": "999",
                        "payload_type": SUPPORTED_PAYLOAD_TYPE,
                        "incident": {"incident_id": "incident-abc"},
                    }
                ),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.UNSUPPORTED_SCHEMA
        assert outcome.http_status == 200

    def test_200_missing_incident_aggregate_returns_invalid_payload(self) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode(
                    {
                        "schema_version": str(SUPPORTED_SCHEMA_VERSION),
                        "payload_type": SUPPORTED_PAYLOAD_TYPE,
                        # Missing incident aggregate
                    }
                ),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.INVALID_PAYLOAD

    def test_200_non_object_incident_aggregate_returns_invalid_payload(self) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode(
                    {
                        "schema_version": str(SUPPORTED_SCHEMA_VERSION),
                        "payload_type": SUPPORTED_PAYLOAD_TYPE,
                        "incident": "not-a-dict",
                    }
                ),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.INVALID_PAYLOAD

    def test_200_aggregate_with_only_incident_id_returns_invalid_payload(self) -> None:
        """Arbitrary dict with incident_id must NOT be accepted as an incident."""
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode(
                    {
                        "schema_version": str(SUPPORTED_SCHEMA_VERSION),
                        "payload_type": SUPPORTED_PAYLOAD_TYPE,
                        "incident": {"incident_id": "incident-abc"},
                    }
                ),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        # Fails on missing canonical fields, classified as invalid_payload
        # by the parser (envelope OK, aggregate rejected).
        assert outcome.failure_code in (
            BackendIncidentLookupFailureCode.INVALID_PAYLOAD,
            BackendIncidentLookupFailureCode.DESERIALIZATION_FAILED,
        )


# ---------------------------------------------------------------------------
# 6. Deserialization failures
# ---------------------------------------------------------------------------


class TestDeserializationFailures:
    def _encode(self, payload: Any) -> bytes:
        import json

        return json.dumps(payload).encode("utf-8")

    def test_200_aggregate_missing_canonical_fields_returns_deserialization_failed(
        self,
    ) -> None:
        """Aggregate missing canonical fields → DESERIALIZATION_FAILED."""
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode(
                    {
                        "schema_version": str(SUPPORTED_SCHEMA_VERSION),
                        "payload_type": SUPPORTED_PAYLOAD_TYPE,
                        "incident": {
                            "incident_id": "incident-abc",
                            "first_observed_at": "2026-07-12T10:00:00+00:00",
                            # Missing all other canonical fields
                        },
                    }
                ),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.DESERIALIZATION_FAILED

    def test_200_aggregate_with_bad_status_returns_deserialization_failed(self) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode(
                    {
                        "schema_version": str(SUPPORTED_SCHEMA_VERSION),
                        "payload_type": SUPPORTED_PAYLOAD_TYPE,
                        "incident": {
                            "incident_id": "incident-abc",
                            "source_candidate_id": "cand",
                            "namespace": "default",
                            "object_kind": "Pod",
                            "object_name": "p",
                            "class": "PodCrashLoop",
                            "severity": "high",
                            "status": "not-a-real-status",
                            "first_observed_at": "2026-07-12T10:00:00+00:00",
                            "last_observed_at": "2026-07-12T10:30:00+00:00",
                        },
                    }
                ),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.DESERIALIZATION_FAILED


# ---------------------------------------------------------------------------
# 7. Identity mismatch
# ---------------------------------------------------------------------------


class TestIdentityMismatch:
    def _encode(self, payload: Any) -> bytes:
        import json

        return json.dumps(payload).encode("utf-8")

    def test_200_payload_with_different_incident_id_returns_identity_mismatch(
        self,
    ) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=self._encode(
                    _canonical_incident_payload("incident-other")
                ),
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        assert outcome.failure_code == BackendIncidentLookupFailureCode.IDENTITY_MISMATCH


# ---------------------------------------------------------------------------
# 8. Negative invariant: no malformed-200 ever produces NotFound
# ---------------------------------------------------------------------------


class TestNoFalseAbsence:
    """No malformed 200 response can become ``BackendIncidentNotFound``."""

    @pytest.mark.parametrize(
        "body,label",
        [
            (b"", "empty"),
            (b"{not valid json", "malformed"),
            (b"[1, 2, 3]", "array"),
            (b'{"incident_id": "x"}', "bare_minimum"),
            (b'{"schema_version": "1", "payload_type": "wrong"}', "wrong_type"),
            (
                b'{"schema_version": "999", "payload_type": "incident-internal-detail", "incident": {}}',
                "wrong_schema",
            ),
            (
                b'{"schema_version": "1", "payload_type": "incident-internal-detail"}',
                "missing_incident",
            ),
        ],
    )
    def test_malformed_200_never_returns_not_found(
        self, body: bytes, label: str
    ) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(http_status=200, body=body)
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert not isinstance(outcome, BackendIncidentNotFound), (
            f"[{label}] malformed 200 must not produce BackendIncidentNotFound; "
            f"got {type(outcome).__name__}"
        )
        # And it must be a typed failure, not a propagated exception.
        assert isinstance(outcome, BackendIncidentLookupFailed)


# ---------------------------------------------------------------------------
# 9. Bounded diagnostic projection
# ---------------------------------------------------------------------------


class TestBoundedDiagnostics:
    def test_failure_detail_is_truncated_to_bound(self) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=b"{not valid json",
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.failure_code == BackendIncidentLookupFailureCode.INVALID_JSON
        assert diagnostic.http_status == 200
        # Detail is bounded (sanitize_disposition_detail caps at 512 chars).
        assert diagnostic.detail is not None
        assert len(diagnostic.detail) <= 512

    def test_failure_diagnostic_carries_requested_incident_id(self) -> None:
        client = FakeClient(
            response=BackendIncidentHttpResponse(
                http_status=200,
                body=b"{not valid",
            )
        )
        outcome = lookup_backend_incident(client, IncidentId("incident-abc"))
        assert isinstance(outcome, BackendIncidentLookupFailed)
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.requested_incident_id == IncidentId("incident-abc")
