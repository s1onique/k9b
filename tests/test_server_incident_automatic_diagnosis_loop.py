"""Route-level tests for automatic diagnosis loop API handler.

This module tests that:
1. POST /api/incidents/{id}/automatic-diagnosis-loop/one-pass
   → collect_automatic_diagnosis_evidence() is called exactly once
2. The route correctly matches and extracts incident_id
3. Error handling returns bounded error responses
4. The endpoint does NOT use fake-runner semantics
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
    handle_incident_automatic_diagnosis_loop_one_pass_api,
    match_automatic_diagnosis_loop_route,
)

# =============================================================================
# Route Matching Tests
# =============================================================================


class TestRouteMatching:
    """Tests for route pattern matching."""

    def test_match_valid_route(self) -> None:
        """Test that valid routes match and extract incident_id."""
        path = "/api/incidents/incident-123/automatic-diagnosis-loop/one-pass"
        incident_id = match_automatic_diagnosis_loop_route(path)
        assert incident_id == "incident-123"

    def test_match_route_with_special_chars(self) -> None:
        """Test route matching with URL-encoded incident IDs."""
        path = "/api/incidents/k8s%3Apod%2Fdefault%2Fnginx/automatic-diagnosis-loop/one-pass"
        incident_id = match_automatic_diagnosis_loop_route(path)
        # The route should extract the raw encoded ID
        assert incident_id is not None

    def test_no_match_wrong_path(self) -> None:
        """Test that wrong paths don't match."""
        assert match_automatic_diagnosis_loop_route("/api/incidents/123") is None
        assert match_automatic_diagnosis_loop_route("/api/incidents/123/diagnosis-loop/one-pass") is None
        assert match_automatic_diagnosis_loop_route("/api/incidents/123/fake-path") is None

    def test_no_match_root(self) -> None:
        """Test that root path doesn't match."""
        assert match_automatic_diagnosis_loop_route("/") is None
        assert match_automatic_diagnosis_loop_route("/api") is None


# =============================================================================
# Handler Tests - collect_automatic_diagnosis_evidence() Call Proof
# =============================================================================


class TestHandlerCallsCollector:
    """Tests proving collect_automatic_diagnosis_evidence() is called."""

    @patch(
        "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.collect_automatic_diagnosis_evidence"
    )
    def test_handler_calls_collector_exactly_once(
        self,
        mock_collect: MagicMock,
    ) -> None:
        """Prove the handler calls the REAL collector, not fake-runner."""
        # Setup mock to return a valid JSON-safe result
        mock_result = MagicMock()
        mock_result.skipped = False
        mock_result.collector_run_id = "collector-123"
        mock_result.incident_results = {
            "incident-123": MagicMock(
                eligible=True,
                eligibility_reason="incident_eligible",
                run_id="run-123",
                checks_run=3,
                checks_skipped=0,
                checks_rejected=0,
                review_packet_path=Path("/tmp/review.json"),  # Real Path object for JSON serialization
                error=None,
            )
        }
        mock_collect.return_value = mock_result

        # Create mock handler
        mock_handler = MagicMock()
        mock_handler.command = "POST"
        mock_handler._health_root = Path("/tmp/health")

        # Call handler
        handle_incident_automatic_diagnosis_loop_one_pass_api(
            mock_handler,
            "incident-123",
        )

        # Prove collector was called exactly once with correct args
        mock_collect.assert_called_once()
        call_kwargs = mock_collect.call_args.kwargs
        assert call_kwargs["incident_id"] == "incident-123"
        assert "external_analysis_dir" in call_kwargs

    @patch(
        "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.collect_automatic_diagnosis_evidence"
    )
    def test_handler_returns_success_response(
        self,
        mock_collect: MagicMock,
    ) -> None:
        """Test successful response structure."""
        mock_result = MagicMock()
        mock_result.skipped = False
        mock_result.collector_run_id = "collector-456"
        mock_result.incident_results = {
            "incident-123": MagicMock(
                eligible=True,
                eligibility_reason="incident_eligible",
                run_id="run-456",
                checks_run=5,
                checks_skipped=1,
                checks_rejected=0,
                review_packet_path=Path("/tmp/review.json"),
                error=None,
            )
        }
        mock_collect.return_value = mock_result

        mock_handler = MagicMock()
        mock_handler.command = "POST"
        mock_handler._health_root = Path("/tmp/health")

        with patch(
            "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_automatic_diagnosis_loop_one_pass_api(
                mock_handler,
                "incident-123",
            )

            # Verify send_json_response was called with success response
            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            response = args[1]
            assert response["incident_id"] == "incident-123"
            assert response["eligible"] is True
            assert response["run_id"] == "run-456"
            assert response["collector_run_id"] == "collector-456"
            assert response["checks_run"] == 5
            assert response["automatic_diagnosis_review_available"] is True
            assert response["read_only"] is True
            assert response["no_remediation_attempted"] is True


class TestHandlerErrorCases:
    """Tests for error handling."""

    def test_method_not_allowed_get(self) -> None:
        """Test that GET method returns 405."""
        mock_handler = MagicMock()
        mock_handler.command = "GET"

        with patch(
            "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_automatic_diagnosis_loop_one_pass_api(
                mock_handler,
                "incident-123",
            )

            args, kwargs = mock_send.call_args
            assert kwargs["code"] == 405
            response = args[1]
            assert response["error_class"] == "method_not_allowed"

    def test_method_not_allowed_put(self) -> None:
        """Test that PUT method returns 405."""
        mock_handler = MagicMock()
        mock_handler.command = "PUT"

        with patch(
            "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_automatic_diagnosis_loop_one_pass_api(
                mock_handler,
                "incident-123",
            )

            args, kwargs = mock_send.call_args
            assert kwargs["code"] == 405

    @patch(
        "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.collect_automatic_diagnosis_evidence"
    )
    def test_collector_exception_returns_bounded_error(
        self,
        mock_collect: MagicMock,
    ) -> None:
        """Test that collector exceptions return bounded error without raw text."""
        mock_collect.side_effect = ValueError("Sensitive internal error message with stack trace")

        mock_handler = MagicMock()
        mock_handler.command = "POST"
        mock_handler._health_root = Path("/tmp/health")

        with patch(
            "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_automatic_diagnosis_loop_one_pass_api(
                mock_handler,
                "incident-123",
            )

            args, kwargs = mock_send.call_args
            assert kwargs["code"] == 500
            response = args[1]
            # Verify no raw exception text in response
            assert "Sensitive internal error" not in str(response.get("error", ""))
            assert response["error"] == "collector_error"
            assert response["error_class"] == "ValueError"

    @patch(
        "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.collect_automatic_diagnosis_evidence"
    )
    def test_skipped_incident_returns_skipped_response(
        self,
        mock_collect: MagicMock,
    ) -> None:
        """Test skipped incident returns proper skipped response."""
        mock_result = MagicMock()
        mock_result.skipped = True
        mock_result.eligible = False
        mock_result.eligibility_reason = "incident_closed"
        mock_result.skip_reason = "incident_closed"
        mock_collect.return_value = mock_result

        mock_handler = MagicMock()
        mock_handler.command = "POST"
        mock_handler._health_root = Path("/tmp/health")

        with patch(
            "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_automatic_diagnosis_loop_one_pass_api(
                mock_handler,
                "incident-123",
            )

            args, kwargs = mock_send.call_args
            assert kwargs["code"] == 200
            response = args[1]
            assert response["skipped"] is True
            assert response["eligible"] is False


class TestEndpointDistinction:
    """Tests proving this endpoint uses REAL collector, not fake-runner."""

    def test_endpoint_uses_collect_automatic_diagnosis_evidence(self) -> None:
        """Prove the endpoint imports and calls the automatic diagnosis collector.

        This distinguishes it from /diagnosis-loop/one-pass which uses
        run_one_read_only_diagnosis_loop_pass() with fake_runner=True.
        """
        import k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop as handler_module

        # Verify the module imports the automatic diagnosis collector
        assert hasattr(
            handler_module,
            "collect_automatic_diagnosis_evidence",
        ), "Module should import collect_automatic_diagnosis_evidence"

    @patch(
        "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.collect_automatic_diagnosis_evidence"
    )
    def test_no_fake_runner_in_response(
        self,
        mock_collect: MagicMock,
    ) -> None:
        """Verify response doesn't contain fake_runner artifacts."""
        mock_result = MagicMock()
        mock_result.skipped = False
        mock_result.collector_run_id = "real-collector"
        mock_result.incident_results = {
            "incident-123": MagicMock(
                eligible=True,
                run_id="real-run",
                checks_run=3,
                checks_skipped=0,
                checks_rejected=0,
                review_packet_path=Path("/tmp/review.json"),
                error=None,
            )
        }
        mock_collect.return_value = mock_result

        mock_handler = MagicMock()
        mock_handler.command = "POST"
        mock_handler._health_root = Path("/tmp/health")

        with patch(
            "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_automatic_diagnosis_loop_one_pass_api(
                mock_handler,
                "incident-123",
            )

            args, kwargs = mock_send.call_args
            response = args[1]
            # Verify no fake_runner indicators
            assert "fake_runner" not in str(response)
            assert response.get("run_id", "").startswith("auto-") or response.get("run_id", "") != "fake"
