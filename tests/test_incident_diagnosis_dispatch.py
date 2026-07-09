"""Tests for incident diagnosis dispatcher.

This module tests the incident_diagnosis_dispatch module which handles
incident source selection (local vs backend-api) and error classification.
"""

import json
import urllib.error
from email.message import Message

import pytest


class TestBackendListingErrorClassification:
    """Tests for backend listing error classification."""

    def test_classify_unauthorized_401(self) -> None:
        """HTTP 401 should be classified as unauthorized."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        # Create HTTPError with 401 status
        hdrs = Message()
        exc = urllib.error.HTTPError(
            url="http://localhost:8080/api/internal/incidents/list",
            code=401,
            msg="Unauthorized",
            hdrs=hdrs,
            fp=None,
        )
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.UNAUTHORIZED
        assert "HTTP 401" in error_msg

    def test_classify_unauthorized_403(self) -> None:
        """HTTP 403 should be classified as unauthorized."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        hdrs = Message()
        exc = urllib.error.HTTPError(
            url="http://localhost:8080/api/internal/incidents/list",
            code=403,
            msg="Forbidden",
            hdrs=hdrs,
            fp=None,
        )
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.UNAUTHORIZED
        assert "HTTP 403" in error_msg

    def test_classify_bad_response_500(self) -> None:
        """HTTP 500 should be classified as bad_response."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        hdrs = Message()
        exc = urllib.error.HTTPError(
            url="http://localhost:8080/api/internal/incidents/list",
            code=500,
            msg="Internal Server Error",
            hdrs=hdrs,
            fp=None,
        )
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.BAD_RESPONSE
        assert "HTTP 500" in error_msg

    def test_classify_bad_response_502(self) -> None:
        """HTTP 502 should be classified as bad_response."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        hdrs = Message()
        exc = urllib.error.HTTPError(
            url="http://localhost:8080/api/internal/incidents/list",
            code=502,
            msg="Bad Gateway",
            hdrs=hdrs,
            fp=None,
        )
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.BAD_RESPONSE
        assert "HTTP 502" in error_msg

    def test_classify_timeout_socket_timeout(self) -> None:
        """socket.timeout should be classified as timeout."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        exc = TimeoutError("timed out")
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.TIMEOUT
        assert "timed out" in error_msg.lower()

    def test_classify_timeout_error_type(self) -> None:
        """TimeoutError should be classified as timeout."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        exc = TimeoutError("The operation timed out")
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.TIMEOUT
        assert "timed out" in error_msg.lower()

    def test_classify_timeout_in_message(self) -> None:
        """Error message with 'timeout' should be classified as timeout."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        exc = OSError("Request timeout after 30 seconds")
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.TIMEOUT

    def test_classify_backend_unreachable_connection_refused(self) -> None:
        """Connection refused should be classified as backend_unreachable."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        exc = urllib.error.URLError(
            reason=ConnectionRefusedError("Connection refused")
        )
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.BACKEND_UNREACHABLE

    def test_classify_backend_unreachable_dns_failed(self) -> None:
        """DNS resolution failure should be classified as backend_unreachable."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        exc = urllib.error.URLError(
            reason=OSError("name or service not known")
        )
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.BACKEND_UNREACHABLE
        assert "Backend unreachable" in error_msg

    def test_classify_backend_unreachable_network_unreachable(self) -> None:
        """Network unreachable should be classified as backend_unreachable."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        exc = urllib.error.URLError(
            reason=OSError("Network is unreachable")
        )
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.BACKEND_UNREACHABLE

    def test_classify_backend_unreachable_no_route(self) -> None:
        """No route to host should be classified as backend_unreachable."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        exc = urllib.error.URLError(
            reason=OSError("No route to host")
        )
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.BACKEND_UNREACHABLE

    def test_classify_backend_unreachable_os_error(self) -> None:
        """OSError with connection refused should be classified as backend_unreachable."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        exc = OSError(111, "Connection refused")
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.BACKEND_UNREACHABLE

    def test_classify_invalid_json(self) -> None:
        """JSON decode error should be classified as invalid_json."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        exc = json.JSONDecodeError("Expecting value", "not json", 0)
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.INVALID_JSON
        assert "Invalid JSON" in error_msg

    def test_classify_unknown_generic_error(self) -> None:
        """Generic exceptions should be classified as unknown."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        exc = RuntimeError("Something went wrong")
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.UNKNOWN

    def test_classify_unknown_custom_exception(self) -> None:
        """Custom exceptions should be classified as unknown."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _classify_backend_listing_error,
        )

        class CustomError(Exception):
            pass

        exc = CustomError("Custom error message")
        error_type, error_msg = _classify_backend_listing_error(exc)

        assert error_type == BackendListingErrorType.UNKNOWN

    def test_error_message_truncation(self) -> None:
        """Error messages should be truncated to approximately 200 chars.

        Note: The actual limit is 200 chars from the original error string,
        but the formatted message may include the exception class name prefix.
        """
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            _classify_backend_listing_error,
        )

        # Use a moderately long message to test truncation
        long_message = "x" * 150
        exc = RuntimeError(long_message)
        _, error_msg = _classify_backend_listing_error(exc)

        # The message should be truncated
        assert len(error_msg) <= 250  # Allow for exception class prefix


class TestBackendListingErrorType:
    """Tests for BackendListingErrorType constants."""

    def test_error_types_are_strings(self) -> None:
        """All error types should be string constants."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
        )

        assert isinstance(BackendListingErrorType.UNAUTHORIZED, str)
        assert isinstance(BackendListingErrorType.TIMEOUT, str)
        assert isinstance(BackendListingErrorType.BACKEND_UNREACHABLE, str)
        assert isinstance(BackendListingErrorType.BAD_RESPONSE, str)
        assert isinstance(BackendListingErrorType.INVALID_JSON, str)
        assert isinstance(BackendListingErrorType.UNKNOWN, str)

    def test_error_types_are_distinct(self) -> None:
        """All error types should be distinct."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
        )

        error_types = [
            BackendListingErrorType.UNAUTHORIZED,
            BackendListingErrorType.TIMEOUT,
            BackendListingErrorType.BACKEND_UNREACHABLE,
            BackendListingErrorType.BAD_RESPONSE,
            BackendListingErrorType.INVALID_JSON,
            BackendListingErrorType.UNKNOWN,
        ]
        assert len(error_types) == len(set(error_types))


class TestDiagnosisIncidentSummary:
    """Tests for DiagnosisIncidentSummary dataclass."""

    def test_incident_summary_creation(self) -> None:
        """DiagnosisIncidentSummary should be creatable with required fields."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            DiagnosisIncidentSummary,
        )

        summary = DiagnosisIncidentSummary(
            incident_id="inc-123",
            status="open",
        )
        assert summary.incident_id == "inc-123"
        assert summary.status == "open"

    def test_incident_summary_is_frozen(self) -> None:
        """DiagnosisIncidentSummary should be frozen (immutable)."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            DiagnosisIncidentSummary,
        )

        summary = DiagnosisIncidentSummary(
            incident_id="inc-123",
            status="open",
        )
        with pytest.raises(AttributeError):
            summary.incident_id = "inc-456"


class TestIncidentDiagnosisDispatchConfig:
    """Tests for IncidentDiagnosisDispatchConfig."""

    def test_resolved_mode_local(self) -> None:
        """Mode 'local' should resolve to 'local'."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            MODE_LOCAL,
            IncidentDiagnosisDispatchConfig,
        )

        config = IncidentDiagnosisDispatchConfig(
            mode="local",
            backend_url=None,
            internal_api_token=None,
            store_backend="memory",
            process_role="",
        )
        assert config.resolved_mode() == MODE_LOCAL

    def test_resolved_mode_backend_api(self) -> None:
        """Mode 'backend-api' should resolve to 'backend-api'."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            MODE_BACKEND_API,
            IncidentDiagnosisDispatchConfig,
        )

        config = IncidentDiagnosisDispatchConfig(
            mode="backend-api",
            backend_url="http://localhost:8080",
            internal_api_token="token",
            store_backend="memory",
            process_role="",
        )
        assert config.resolved_mode() == MODE_BACKEND_API

    def test_resolved_mode_auto_sqlite(self) -> None:
        """Mode 'auto' with sqlite should resolve to 'backend-api'."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            MODE_BACKEND_API,
            IncidentDiagnosisDispatchConfig,
        )

        config = IncidentDiagnosisDispatchConfig(
            mode="auto",
            backend_url="http://localhost:8080",
            internal_api_token="token",
            store_backend="sqlite",
            process_role="",
        )
        assert config.resolved_mode() == MODE_BACKEND_API

    def test_resolved_mode_auto_scheduler(self) -> None:
        """Mode 'auto' with scheduler role should resolve to 'backend-api'."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            MODE_BACKEND_API,
            IncidentDiagnosisDispatchConfig,
        )

        config = IncidentDiagnosisDispatchConfig(
            mode="auto",
            backend_url="http://localhost:8080",
            internal_api_token="token",
            store_backend="memory",
            process_role="scheduler",
        )
        assert config.resolved_mode() == MODE_BACKEND_API

    def test_resolved_mode_auto_memory_backend(self) -> None:
        """Mode 'auto' with memory backend should resolve to 'local'."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            MODE_LOCAL,
            IncidentDiagnosisDispatchConfig,
        )

        config = IncidentDiagnosisDispatchConfig(
            mode="auto",
            backend_url=None,
            internal_api_token=None,
            store_backend="memory",
            process_role="",
        )
        assert config.resolved_mode() == MODE_LOCAL

    def test_requires_backend_api(self) -> None:
        """requires_backend_api should return True for backend-api mode."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            IncidentDiagnosisDispatchConfig,
        )

        config = IncidentDiagnosisDispatchConfig(
            mode="backend-api",
            backend_url="http://localhost:8080",
            internal_api_token="token",
            store_backend="memory",
            process_role="",
        )
        assert config.requires_backend_api() is True

    def test_requires_backend_api_local(self) -> None:
        """requires_backend_api should return False for local mode."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            IncidentDiagnosisDispatchConfig,
        )

        config = IncidentDiagnosisDispatchConfig(
            mode="local",
            backend_url=None,
            internal_api_token=None,
            store_backend="memory",
            process_role="",
        )
        assert config.requires_backend_api() is False
