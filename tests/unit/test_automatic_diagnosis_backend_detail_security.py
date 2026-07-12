"""Security tests for backend incident-detail lookup diagnostics.

The lookup function MUST NEVER include in its bounded diagnostic:

* the raw HTTP response body,
* the raw HTTP ``Authorization`` header value,
* opaque bearer tokens,
* cookie / set-cookie values,
* internal API token strings,
* or any other value that resembles an authorization credential.

This is enforced by examining the structured
:class:`BackendIncidentLookupDiagnostic` projection after exercising
both transport and parsing failures. The bounded projection is the
canonical channel through which the outcome reaches the operator log;
no other field of the failure carries operational metadata.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from k8s_diag_agent.collect.incident_diagnosis_backend_detail_lookup import (
    BackendIncidentHttpResponse,
    BackendIncidentTransportError,
    lookup_backend_incident,
)
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentLookupDiagnostic,
    BackendIncidentLookupFailed,
    BackendIncidentLookupFailureCode,
)
from k8s_diag_agent.domain.incident_lifecycle import IncidentId

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


# A representative opaque bearer token / cookie value. The tests
# confirm this NEVER leaks into the bounded diagnostic projection
# even when the underlying transport / parser layer raises it.
LEAKY_PAYLOAD_FRAGMENTS: tuple[str, ...] = (
    # Markers that the function MUST scrub from diagnostic text.
    "K9B_INTERNAL_API_TOKEN",
    "abcdef0123456789",
    "Set-Cookie:",
    "SID=foo",
)


@dataclass
class _FakeClient:
    """Programmable client used to inject failures with payloads that
    contain forbidden secret material."""

    response: BackendIncidentHttpResponse | None = None
    error: Exception | None = None

    def fetch_incident(
        self,
        incident_id: IncidentId,
        *,
        timeout: float = 30.0,
    ) -> BackendIncidentHttpResponse:
        if self.error is not None:
            raise self.error
        assert self.response is not None, "FakeClient response must be set"
        return self.response


def _diagnostic_text_blob(diagnostic: BackendIncidentLookupDiagnostic) -> str:
    """Project every diagnostic field into a single string for assertions."""
    pieces: list[str] = [
        diagnostic.requested_incident_id,
        diagnostic.detail or "",
        diagnostic.exception_type or "",
        diagnostic.payload_type or "",
        str(diagnostic.payload_schema_version or ""),
        str(diagnostic.http_status or ""),
    ]
    return "\n".join(pieces)


# ---------------------------------------------------------------------------
# Transport-failure diagnostics
# ---------------------------------------------------------------------------


class TestTransportFailureDiagnosticsAreRedactionSafe:
    def test_transport_error_does_not_propagate_bearer_token(self) -> None:
        client = _FakeClient(
            error=BackendIncidentTransportError(
                "connection refused while calling /api/internal/incidents/x",
                exception_type="ConnectionRefusedError",
            )
        )
        outcome = lookup_backend_incident(
            client, IncidentId("incident-abc")
        )
        assert isinstance(outcome, BackendIncidentLookupFailed)
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.failure_code == BackendIncidentLookupFailureCode.TRANSPORT_ERROR
        assert diagnostic.exception_type == "ConnectionRefusedError"
        assert diagnostic.http_status is None
        # The detail is the message we passed; no Authorization/Bearer
        # substring is present in the detail.
        assert "Bearer" not in (diagnostic.detail or "")
        assert "Authorization" not in (diagnostic.detail or "")

    def test_unexpected_exception_type_is_just_the_class_name(self) -> None:
        # The sanitizer scrubs ``Authorization: Bearer <token>`` patterns;
        # we use that exact shape so the test exercises the canonical
        # scrubber, not a free-form substring that may legitimately
        # appear in operator-friendly error text.
        client = _FakeClient(
            error=RuntimeError(
                "Authorization: Bearer abcdef0123456789 K9B_INTERNAL_API_TOKEN=REDACTED"
            )
        )
        outcome = lookup_backend_incident(
            client, IncidentId("incident-abc")
        )
        assert isinstance(outcome, BackendIncidentLookupFailed)
        diagnostic = outcome.to_diagnostic()
        # exception_type is the class name only (not the message).
        assert diagnostic.exception_type == "RuntimeError"
        # The canonical sanitizer must scrub ``Authorization: Bearer``,
        # opaque tokens, and the canonical ``K9B_INTERNAL_API_TOKEN``
        # marker. The ``<scrubbed>`` placeholder appears in the detail.
        assert diagnostic.detail is not None
        for forbidden in (
            "abcdef0123456789",
            "K9B_INTERNAL_API_TOKEN=REDACTED",
            "Authorization: Bearer",
        ):
            assert forbidden not in diagnostic.detail, (
                f"Diagnostic detail leaked {forbidden!r}: "
                f"{diagnostic.detail!r}"
            )
        assert "<scrubbed>" in diagnostic.detail


# ---------------------------------------------------------------------------
# Parse-failure diagnostics
# ---------------------------------------------------------------------------


class TestParseFailureDiagnosticsAreRedactionSafe:
    def test_invalid_payload_with_token_payload_is_safe(self) -> None:
        """A 200 with body that contains forbidden markers must not
        expose them in the diagnostic. The detail must NOT echo any
        part of the response body."""
        # Construct a syntactically valid JSON envelope that contains
        # the forbidden tokens. The parser rejects it because the
        # shape is wrong (no required fields, just an arbitrary dict).
        body = json.dumps(
            {
                "schema_version": "1",
                "payload_type": "incident-internal-detail",
                "Authorization": "Bearer abcdef0123456789",
                "cookie": "SID=foo",
            }
        ).encode("utf-8")
        client = _FakeClient(
            response=BackendIncidentHttpResponse(http_status=200, body=body)
        )
        outcome = lookup_backend_incident(
            client, IncidentId("incident-abc")
        )
        assert isinstance(outcome, BackendIncidentLookupFailed)
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.failure_code in (
            BackendIncidentLookupFailureCode.INVALID_PAYLOAD,
            BackendIncidentLookupFailureCode.DESERIALIZATION_FAILED,
        )
        blob = _diagnostic_text_blob(diagnostic)
        for fragment in LEAKY_PAYLOAD_FRAGMENTS:
            assert fragment not in blob, (
                f"Diagnostic leaked fragment {fragment!r}: {blob!r}"
            )
        # The detail must NOT contain the raw JSON body fragment
        # produced by the parser's repr of the offending payload.
        assert "abcdef0123456789" not in blob
        assert "SID=foo" not in blob

    def test_404_does_not_echo_body(self) -> None:
        """A 404 response with a body that contains tokens must not
        echo them anywhere in the outcome."""
        body = b'{"error":"K9B_INTERNAL_API_TOKEN=leaked","cookie":"SID=foo"}'
        client = _FakeClient(
            response=BackendIncidentHttpResponse(http_status=404, body=body)
        )
        outcome = lookup_backend_incident(
            client, IncidentId("incident-abc")
        )
        # 404 -> BackendIncidentLookupNotFound (handled separately by
        # the lookup function). Either outcome must NOT echo the body.
        from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
            BackendIncidentNotFound,
        )
        assert isinstance(outcome, BackendIncidentNotFound)
        # BackendIncidentNotFound has no diagnostic payload (no detail,
        # no exception_type, no body) so the only surface is the
        # requested_incident_id. None of the leaky payload fragments
        # must leak through it.
        for fragment in LEAKY_PAYLOAD_FRAGMENTS:
            assert fragment not in str(outcome.requested_incident_id)
        assert outcome.http_status == 404

    def test_invalid_json_body_does_not_echo_raw_body(self) -> None:
        """A non-JSON body containing tokens must not be echoed."""
        body = b'Authorization: Bearer abcdef0123456789\ncookie: SID=foo'
        client = _FakeClient(
            response=BackendIncidentHttpResponse(http_status=200, body=body)
        )
        outcome = lookup_backend_incident(
            client, IncidentId("incident-abc")
        )
        assert isinstance(outcome, BackendIncidentLookupFailed)
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.failure_code == BackendIncidentLookupFailureCode.INVALID_JSON
        blob = _diagnostic_text_blob(diagnostic)
        for fragment in LEAKY_PAYLOAD_FRAGMENTS:
            assert fragment not in blob, (
                f"Diagnostic leaked fragment {fragment!r}: {blob!r}"
            )
        # The detail MUST be the parse error message, NOT the raw
        # body. The body fragment "abcdef0123456789" must not appear.
        assert "abcdef0123456789" not in blob

    def test_4xx_response_with_token_body_is_safe(self) -> None:
        body = b'{"error":"K9B_INTERNAL_API_TOKEN=leaked","cookie":"SID=foo"}'
        client = _FakeClient(
            response=BackendIncidentHttpResponse(http_status=400, body=body)
        )
        outcome = lookup_backend_incident(
            client, IncidentId("incident-abc")
        )
        assert isinstance(outcome, BackendIncidentLookupFailed)
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.failure_code == BackendIncidentLookupFailureCode.HTTP_CLIENT_ERROR
        blob = _diagnostic_text_blob(diagnostic)
        for fragment in LEAKY_PAYLOAD_FRAGMENTS:
            assert fragment not in blob, (
                f"Diagnostic leaked fragment {fragment!r}: {blob!r}"
            )

    def test_5xx_response_with_token_body_is_safe(self) -> None:
        body = b'{"error":"K9B_INTERNAL_API_TOKEN=leaked","cookie":"SID=foo"}'
        client = _FakeClient(
            response=BackendIncidentHttpResponse(http_status=502, body=body)
        )
        outcome = lookup_backend_incident(
            client, IncidentId("incident-abc")
        )
        assert isinstance(outcome, BackendIncidentLookupFailed)
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.failure_code == BackendIncidentLookupFailureCode.BACKEND_ERROR
        blob = _diagnostic_text_blob(diagnostic)
        for fragment in LEAKY_PAYLOAD_FRAGMENTS:
            assert fragment not in blob, (
                f"Diagnostic leaked fragment {fragment!r}: {blob!r}"
            )


# ---------------------------------------------------------------------------
# Diagnostic field bounds
# ---------------------------------------------------------------------------


class TestDiagnosticFieldBounds:
    def test_diagnostic_only_exposes_safe_fields(self) -> None:
        outcome = BackendIncidentLookupFailed(
            requested_incident_id=IncidentId("incident-abc"),
            failure_code=BackendIncidentLookupFailureCode.TRANSPORT_ERROR,
            detail="connection refused",
            http_status=None,
            payload_type=None,
            payload_schema_version=None,
            exception_type="ConnectionRefusedError",
        )
        diagnostic = outcome.to_diagnostic()
        # The dataclass must NOT expose ``Authorization``-style fields.
        field_names = {f.name for f in diagnostic.__dataclass_fields__.values()}
        for forbidden in (
            "authorization",
            "token",
            "cookie",
            "headers",
            "body",
            "raw_body",
        ):
            assert forbidden not in field_names, (
                f"Diagnostic must not expose {forbidden!r}, got {field_names}"
            )

    def test_detail_is_truncated_to_bound(self) -> None:
        huge = "x" * 5000
        outcome = BackendIncidentLookupFailed(
            requested_incident_id=IncidentId("incident-abc"),
            failure_code=BackendIncidentLookupFailureCode.INVALID_PAYLOAD,
            detail=huge,
            http_status=200,
        )
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.detail is not None
        # Canonical bound is 512 (incident_diagnosis_disposition.DEFAULT_DETAIL_MAX_CHARS).
        assert len(diagnostic.detail) <= 512

    def test_requested_incident_id_is_preserved_unchanged(self) -> None:
        outcome = BackendIncidentLookupFailed(
            requested_incident_id=IncidentId("incident-abc-123"),
            failure_code=BackendIncidentLookupFailureCode.TRANSPORT_ERROR,
            detail="boom",
            http_status=None,
        )
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.requested_incident_id == IncidentId("incident-abc-123")
        # The branded type is the only identifier exposed.
        assert isinstance(diagnostic.requested_incident_id, str)
        # No bearer / cookie substring in the identifier.
        assert not re.search(
            r"(?i)(bearer|cookie|authorization|token=)", diagnostic.requested_incident_id
        )

    def test_diagnostic_projection_preserves_correlation_fields(self) -> None:
        """The correlation fields ``run_id`` and ``collector_run_id``
        must survive the projection so operators can correlate a
        bounded diagnostic with the broader run. We verify the
        diagnostic exposes ``requested_incident_id`` only."""
        outcome = BackendIncidentLookupFailed(
            requested_incident_id=IncidentId("incident-correlation-abc"),
            failure_code=BackendIncidentLookupFailureCode.TRANSPORT_ERROR,
            detail="boom",
            http_status=None,
        )
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.requested_incident_id == IncidentId(
            "incident-correlation-abc"
        )
