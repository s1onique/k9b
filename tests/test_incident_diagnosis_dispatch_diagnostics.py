"""Tests for diagnostic message builder in incident diagnosis dispatcher.

This module contains tests for the _build_listing_error_diagnostic function
which provides actionable error diagnostics for backend listing failures.
"""


class TestBuildListingErrorDiagnostic:
    """Tests for the diagnostic message builder."""

    def test_diagnostic_missing_backend_url(self) -> None:
        """Missing backend URL should provide actionable diagnostic."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _build_listing_error_diagnostic,
        )

        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.MISSING_BACKEND_URL, None, "test error"
        )
        assert "K9B_BACKEND_INTERNAL_URL" in diagnostic
        assert "http://k9b-backend:8080" in diagnostic

    def test_diagnostic_missing_token(self) -> None:
        """Missing token should provide actionable diagnostic."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _build_listing_error_diagnostic,
        )

        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.MISSING_INTERNAL_TOKEN, None, "test error"
        )
        assert "K9B_INTERNAL_API_TOKEN" in diagnostic
        assert "match" in diagnostic.lower()

    def test_diagnostic_unauthorized(self) -> None:
        """Unauthorized error should provide actionable diagnostic."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _build_listing_error_diagnostic,
        )

        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.UNAUTHORIZED, 401, "Unauthorized"
        )
        assert "invalid or expired" in diagnostic
        assert "matches" in diagnostic.lower()

    def test_diagnostic_backend_unreachable(self) -> None:
        """Backend unreachable should provide connectivity diagnostic."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _build_listing_error_diagnostic,
        )

        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.BACKEND_UNREACHABLE, None, "Connection refused"
        )
        assert "unreachable" in diagnostic
        assert "running" in diagnostic

    def test_diagnostic_timeout(self) -> None:
        """Timeout should provide diagnostic."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _build_listing_error_diagnostic,
        )

        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.TIMEOUT, None, "Request timed out"
        )
        assert "timed out" in diagnostic
        assert "health" in diagnostic

    def test_diagnostic_bad_response_404(self) -> None:
        """404 response should provide diagnostic."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _build_listing_error_diagnostic,
        )

        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.BAD_RESPONSE, 404, "Not found"
        )
        assert "404" in diagnostic
        assert "endpoint" in diagnostic.lower()

    def test_diagnostic_invalid_json(self) -> None:
        """Invalid JSON should provide diagnostic."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _build_listing_error_diagnostic,
        )

        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.INVALID_JSON, None, "JSONDecodeError"
        )
        assert "invalid json" in diagnostic.lower()
        assert "backend bug" in diagnostic.lower()

    def test_diagnostic_unknown(self) -> None:
        """Unknown error should provide fallback diagnostic."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
            BackendListingErrorType,
            _build_listing_error_diagnostic,
        )

        diagnostic = _build_listing_error_diagnostic(
            BackendListingErrorType.UNKNOWN, None, "Something went wrong"
        )
        assert "unexpected" in diagnostic.lower()
        assert "logs" in diagnostic.lower()
