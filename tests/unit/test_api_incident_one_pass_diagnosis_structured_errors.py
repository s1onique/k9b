"""Tests for structured error responses in incident one-pass diagnosis service API.

Tests that structured errors (LLMProviderNotConfiguredError, LLMProviderError,
IncidentNotFoundError) return proper HTTP status codes (503, 502, 404).

This file was split from test_api_incident_one_pass_diagnosis_service.py to
keep individual test files under the 500-line LLM-friendly threshold.
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from k8s_diag_agent.collect.api_incident_one_pass_diagnosis_provider import (
    reset_providers,
)
from k8s_diag_agent.collect.diagnosis_service_errors import (
    LLMProviderError,
    LLMProviderNotConfiguredError,
)
from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)
from k8s_diag_agent.ui.server_incident_one_pass_diagnosis_service import (
    handle_incident_one_pass_diagnosis_service_api,
)


class _WFile:
    """Mock write file for testing."""

    def __init__(self) -> None:
        self._buf = BytesIO()

    def write(self, data: bytes) -> int:
        return self._buf.write(data)

    def flush(self) -> None:
        pass

    def getvalue(self) -> bytes:
        return self._buf.getvalue()


class MockHandler:
    """Mock HTTP handler for testing."""

    def __init__(
        self,
        path: str,
        health_root: Path,
        body: bytes,
    ) -> None:
        self.path = path
        self._health_root = health_root
        self._body = body

        class _Headers:
            def get(self, key: str, default: str = "") -> str:
                if key == "Content-Length":
                    return str(len(body))
                return default

        self.headers = _Headers()
        self.rfile = BytesIO(body)
        self._response_status = 200
        self._response_headers: dict[str, str] = {}
        self.wfile = _WFile()

    def send_response(self, code: int) -> None:
        self._response_status = code

    def send_header(self, key: str, value: str) -> None:
        self._response_headers[key] = value

    def end_headers(self) -> None:
        pass


def _create_test_incident() -> Incident:
    """Create a test incident for testing."""
    return Incident(
        incident_id="test-incident",
        source_candidate_id="candidate-001",
        namespace="default",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind=None,
        candidate_class="readiness_failure",
        severity="warning",
        status=IncidentStatus.OPEN,
        first_observed_at=datetime.now(UTC),
        last_observed_at=datetime.now(UTC),
    )


class TestStructuredErrorResponses(unittest.TestCase):
    """Test that structured errors return proper HTTP status codes."""

    def test_llm_provider_not_configured_returns_503(self) -> None:
        """LLM provider not configured should return 503 with structured error."""
        from k8s_diag_agent.collect.api_incident_one_pass_diagnosis_provider import (
            set_diagnosis_provider,
        )

        try:
            # Set up incident store with a test incident
            incident = _create_test_incident()
            store = IncidentStore()
            store._incidents["test-incident"] = incident
            set_incident_store(store)

            with TemporaryDirectory() as tmpdir:
                health_root = Path(tmpdir)
                body = json.dumps({}).encode("utf-8")
                handler = MockHandler(
                    path="/api/incidents/test-incident/one-pass-diagnosis",
                    health_root=health_root,
                    body=body,
                )

                # Inject a provider that raises LLMProviderNotConfiguredError
                class RaisingProvider:
                    """Provider that raises LLMProviderNotConfiguredError on complete."""

                    def complete(self, prompt: str) -> str:
                        raise LLMProviderNotConfiguredError(
                            "LLM provider not configured. "
                            "Set K9B_DIAGNOSIS_PROVIDER_NAME, "
                            "K9B_DIAGNOSIS_MODEL, and K9B_DIAGNOSIS_BASE_URL."
                        )

                set_diagnosis_provider(RaisingProvider())

                handle_incident_one_pass_diagnosis_service_api(
                    handler=handler,  # type: ignore[arg-type]
                    incident_id="test-incident",
                )

                self.assertEqual(handler._response_status, 503)
                response_body = handler.wfile.getvalue().decode("utf-8")
                response_data = json.loads(response_body)
                self.assertEqual(response_data["error"], "llm_provider_not_configured")
                self.assertIn("message", response_data)
                self.assertIn("retryable", response_data)
                self.assertFalse(response_data["retryable"])
        finally:
            reset_providers()
            reset_incident_store()

    def test_llm_provider_error_returns_502(self) -> None:
        """LLM provider failure should return 502 with structured error."""
        from k8s_diag_agent.collect.api_incident_one_pass_diagnosis_provider import (
            set_diagnosis_provider,
        )

        try:
            # Set up incident store with a test incident
            incident = _create_test_incident()
            store = IncidentStore()
            store._incidents["test-incident"] = incident
            set_incident_store(store)

            with TemporaryDirectory() as tmpdir:
                health_root = Path(tmpdir)
                body = json.dumps({}).encode("utf-8")
                handler = MockHandler(
                    path="/api/incidents/test-incident/one-pass-diagnosis",
                    health_root=health_root,
                    body=body,
                )

                # Inject a provider that raises LLMProviderError
                class RaisingProvider:
                    """Provider that raises LLMProviderError on complete."""

                    def complete(self, prompt: str) -> str:
                        raise LLMProviderError("Provider timeout after 120s")

                set_diagnosis_provider(RaisingProvider())

                handle_incident_one_pass_diagnosis_service_api(
                    handler=handler,  # type: ignore[arg-type]
                    incident_id="test-incident",
                )

                self.assertEqual(handler._response_status, 502)
                response_body = handler.wfile.getvalue().decode("utf-8")
                response_data = json.loads(response_body)
                self.assertEqual(response_data["error"], "llm_provider_failed")
                self.assertIn("message", response_data)
                self.assertIn("retryable", response_data)
                self.assertTrue(response_data["retryable"])
        finally:
            reset_providers()
            reset_incident_store()

    def test_incident_not_found_returns_404(self) -> None:
        """Incident not found should return 404 with structured error."""
        try:
            with TemporaryDirectory() as tmpdir:
                health_root = Path(tmpdir)
                body = json.dumps({}).encode("utf-8")
                handler = MockHandler(
                    path="/api/incidents/nonexistent-incident/one-pass-diagnosis",
                    health_root=health_root,
                    body=body,
                )

                handle_incident_one_pass_diagnosis_service_api(
                    handler=handler,  # type: ignore[arg-type]
                    incident_id="nonexistent-incident",
                )

                self.assertEqual(handler._response_status, 404)
                response_body = handler.wfile.getvalue().decode("utf-8")
                response_data = json.loads(response_body)
                self.assertEqual(response_data["error"], "incident_not_found")
                self.assertIn("message", response_data)
                self.assertIn("incident_id", response_data)
        finally:
            reset_providers()


if __name__ == "__main__":
    unittest.main()
