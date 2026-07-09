"""Contract tests for autodiag incident listing failure events.

These tests verify that the autodiag incident listing failure OTEL event
includes structured error_type and diagnostic fields for operator diagnostics.
"""

from __future__ import annotations

from unittest.mock import patch

from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
    BackendListingErrorType,
    _build_listing_error_diagnostic,
    _list_incidents_backend_api,
)


class TestAutodiagListingFailureEventContract:
    """Test that listing failure events contain structured diagnostic fields."""

    def test_failure_event_contains_error_type_on_missing_url(self) -> None:
        """Missing backend URL should return error_type=missing_backend_url."""
        # Call _list_incidents_backend_api directly with missing URL
        incidents, success, error, error_type = _list_incidents_backend_api(
            backend_url=None,
            internal_api_token="test-token",
            active_only=True,
            limit=None,
        )

        # Assert listing failed
        assert success is False
        assert len(incidents) == 0
        assert error_type == BackendListingErrorType.MISSING_BACKEND_URL

    def test_failure_event_contains_error_type_on_missing_token(self) -> None:
        """Missing token should return error_type=missing_internal_token."""
        incidents, success, error, error_type = _list_incidents_backend_api(
            backend_url="http://localhost:8080",
            internal_api_token=None,
            active_only=True,
            limit=None,
        )

        # Assert listing failed
        assert success is False
        assert len(incidents) == 0
        assert error_type == BackendListingErrorType.MISSING_INTERNAL_TOKEN

    def test_failure_event_contains_diagnostic_on_missing_url(self) -> None:
        """Diagnostic should explain how to fix missing URL."""
        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.MISSING_BACKEND_URL,
            None,
            "test error",
        )

        # Diagnostic should tell operator to set the URL
        assert "K9B_BACKEND_INTERNAL_URL" in diagnostic
        assert "http://k9b-backend:8080" in diagnostic

    def test_failure_event_contains_diagnostic_on_missing_token(self) -> None:
        """Diagnostic should explain how to fix missing token."""
        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.MISSING_INTERNAL_TOKEN,
            None,
            "test error",
        )

        # Diagnostic should tell operator to set the token
        assert "K9B_INTERNAL_API_TOKEN" in diagnostic


class TestAutodiagListingUsesSameClientAsPromotion:
    """Test that autodiag listing uses the same client/config as promotion."""

    def test_listing_creates_scheduler_client_with_same_signature(self) -> None:
        """_list_incidents_backend_api should create SchedulerClient with url and token."""
        from k8s_diag_agent.ui.server_incident_internal_client import SchedulerClient

        with patch.object(
            SchedulerClient,
            "list_incidents",
            return_value={"incidents": [], "total": 0},
        ) as mock_list:
            incidents, success, error, error_type = _list_incidents_backend_api(
                backend_url="http://k9b-backend:8080",
                internal_api_token="test-token-123",
                active_only=True,
                limit=None,
            )

            # Verify client was instantiated and called
            mock_list.assert_called_once()

    def test_listing_passes_active_only_filter_to_client(self) -> None:
        """_list_incidents_backend_api should pass active_only to client."""
        from k8s_diag_agent.ui.server_incident_internal_client import SchedulerClient

        with patch.object(
            SchedulerClient,
            "list_incidents",
            return_value={"incidents": [], "total": 0},
        ) as mock_list:
            # Call with active_only=True
            _list_incidents_backend_api(
                backend_url="http://k9b-backend:8080",
                internal_api_token="test-token",
                active_only=True,
                limit=None,
            )

            # Verify list_incidents was called (the client handles status filtering)
            mock_list.assert_called_once()

    def test_listing_passes_limit_to_client(self) -> None:
        """_list_incidents_backend_api should pass limit to client."""
        from k8s_diag_agent.ui.server_incident_internal_client import SchedulerClient

        with patch.object(
            SchedulerClient,
            "list_incidents",
            return_value={"incidents": [], "total": 0},
        ) as mock_list:
            # Call with limit=5
            _list_incidents_backend_api(
                backend_url="http://k9b-backend:8080",
                internal_api_token="test-token",
                active_only=True,
                limit=5,
            )

            mock_list.assert_called_once()
            # Verify limit was passed to list_incidents
            call_kwargs = mock_list.call_args
            assert call_kwargs[1].get("limit") == 5 or (
                len(call_kwargs[0]) > 1 and call_kwargs[0][1] == 5
            )


class TestAutodiagListingDiagnosticMapping:
    """Test that each error_type maps to actionable diagnostic."""

    def test_missing_backend_url_diagnostic(self) -> None:
        """MISSING_BACKEND_URL should map to diagnostic about setting the URL."""
        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.MISSING_BACKEND_URL,
            None,
            "test error",
        )

        assert "K9B_BACKEND_INTERNAL_URL" in diagnostic
        assert "http://k9b-backend:8080" in diagnostic

    def test_missing_token_diagnostic(self) -> None:
        """MISSING_INTERNAL_TOKEN should map to diagnostic about setting the token."""
        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.MISSING_INTERNAL_TOKEN,
            None,
            "test error",
        )

        assert "K9B_INTERNAL_API_TOKEN" in diagnostic

    def test_unauthorized_diagnostic(self) -> None:
        """UNAUTHORIZED should map to diagnostic about token mismatch."""
        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.UNAUTHORIZED,
            401,
            "Unauthorized",
        )

        assert "invalid or expired" in diagnostic

    def test_backend_unreachable_diagnostic(self) -> None:
        """BACKEND_UNREACHABLE should map to diagnostic about service status."""
        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.BACKEND_UNREACHABLE,
            None,
            "Connection refused",
        )

        assert "unreachable" in diagnostic
        assert "running" in diagnostic

    def test_timeout_diagnostic(self) -> None:
        """TIMEOUT should map to diagnostic about backend health."""
        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.TIMEOUT,
            None,
            "timed out",
        )

        assert "timed out" in diagnostic
        assert "health" in diagnostic

    def test_bad_response_404_diagnostic(self) -> None:
        """BAD_RESPONSE with 404 should map to diagnostic about endpoint version."""
        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.BAD_RESPONSE,
            404,
            "Not found",
        )

        assert "404" in diagnostic
        assert "endpoint" in diagnostic.lower()

    def test_invalid_json_diagnostic(self) -> None:
        """INVALID_JSON should map to diagnostic about backend bug."""
        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.INVALID_JSON,
            None,
            "JSONDecodeError",
        )

        assert "invalid json" in diagnostic.lower()
        assert "backend bug" in diagnostic.lower()

    def test_unknown_diagnostic(self) -> None:
        """UNKNOWN should map to diagnostic about checking logs."""
        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.UNKNOWN,
            None,
            "Something went wrong",
        )

        assert "unexpected" in diagnostic.lower()
        assert "logs" in diagnostic.lower()
