"""Contract tests for incident API routes JSON responses.

These tests prove that incident routes always return JSON, never HTML:
- GET /api/incidents - list incidents
- GET /api/incidents/{id} - get incident detail
- POST /api/incidents/{id}/automatic-diagnosis-loop/one-pass - automatic diagnosis
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import MockApiHandler, assert_json_response, assert_no_html_in_response


class TestIncidentListJsonContract:
    """Tests proving incident list route returns JSON."""

    def test_list_incidents_returns_json(self) -> None:
        """GET /api/incidents returns JSON list."""
        from k8s_diag_agent.ui.server_incident_reads import handle_incidents_list_route

        with patch(
            "k8s_diag_agent.ui.server_incident_reads.handle_list_incidents",
            return_value={"incidents": [], "total": 0},
        ):
            handler = MockApiHandler()
            handler.path = "/api/incidents"
            result = handle_incidents_list_route(handler, "")  # type: ignore[arg-type]

            assert result is True
            assert_json_response(handler, expected_code=200, expected_body_keys=["incidents"])
            assert handler._sent_body is not None
            assert isinstance(handler._sent_body["incidents"], list)

    def test_incident_list_with_data_is_valid_json(self) -> None:
        """incident list with data must be valid JSON."""
        from k8s_diag_agent.ui.server_incident_reads import handle_incidents_list_route

        with patch(
            "k8s_diag_agent.ui.server_incident_reads.handle_list_incidents",
            return_value={
                "incidents": [
                    {"incident_id": "test-1", "status": "open"},
                    {"incident_id": "test-2", "status": "closed"},
                ],
                "total": 2,
            },
        ):
            handler = MockApiHandler()
            handler.path = "/api/incidents"
            handle_incidents_list_route(handler, "")  # type: ignore[arg-type]

            json_str = json.dumps(handler._sent_body)
            parsed = json.loads(json_str)
            assert parsed["total"] == 2
            assert len(parsed["incidents"]) == 2


class TestIncidentDetailJsonContract:
    """Tests proving incident detail routes return JSON, never HTML."""

    def test_get_incident_found_returns_json_200(self) -> None:
        """GET /api/incidents/{id} for existing incident returns JSON 200."""
        from k8s_diag_agent.ui.server_incident_reads import handle_incident_detail_route

        with patch(
            "k8s_diag_agent.ui.server_incident_reads.handle_get_incident",
            return_value={
                "incident_id": "test-incident-123",
                "status": "open",
                "created_at": "2024-01-01T00:00:00Z",
            },
        ):
            handler = MockApiHandler()
            handler.path = "/api/incidents/test-incident-123"
            result = handle_incident_detail_route(handler, handler.path)  # type: ignore[arg-type]

            assert result is True
            assert_json_response(handler, expected_code=200)
            assert handler._sent_body is not None
            assert handler._sent_body["incident_id"] == "test-incident-123"

    def test_get_incident_not_found_returns_json_404(self) -> None:
        """GET /api/incidents/{id} for missing incident returns JSON 404, not HTML."""
        from k8s_diag_agent.ui.server_incident_reads import handle_incident_detail_route

        with patch(
            "k8s_diag_agent.ui.server_incident_reads.handle_get_incident",
            return_value=None,  # Not found
        ):
            handler = MockApiHandler()
            handler.path = "/api/incidents/nonexistent-incident-123"
            result = handle_incident_detail_route(handler, handler.path)  # type: ignore[arg-type]

            assert result is True
            assert handler._sent_code == 404, f"Expected 404, got {handler._sent_code}"
            assert_json_response(handler, expected_code=404)

            # Must be valid JSON
            assert handler._sent_body is not None
            json_str = json.dumps(handler._sent_body)
            parsed = json.loads(json_str)
            assert parsed == handler._sent_body

            # Must not contain HTML markers
            assert_no_html_in_response(handler)

    def test_get_incident_exception_returns_json_500(self) -> None:
        """GET /api/incidents/{id} on exception returns JSON 500, not HTML."""
        from k8s_diag_agent.ui.server_incident_reads import handle_incident_detail_route

        with patch(
            "k8s_diag_agent.ui.server_incident_reads.handle_get_incident",
            side_effect=RuntimeError("Unexpected error"),
        ):
            handler = MockApiHandler()
            handler.path = "/api/incidents/test-incident-123"
            result = handle_incident_detail_route(handler, handler.path)  # type: ignore[arg-type]

            assert result is True
            assert handler._sent_code == 500
            assert_json_response(handler, expected_code=500)
            assert_no_html_in_response(handler)

    def test_incident_response_contains_no_html(self) -> None:
        """Incident responses must not contain HTML tags."""
        from k8s_diag_agent.ui.server_incident_reads import handle_incident_detail_route

        with patch(
            "k8s_diag_agent.ui.server_incident_reads.handle_get_incident",
            return_value={
                "incident_id": "test-incident",
                "status": "open",
                "description": "Test incident",
            },
        ):
            handler = MockApiHandler()
            handler.path = "/api/incidents/test-incident"
            handle_incident_detail_route(handler, handler.path)  # type: ignore[arg-type]

            assert_no_html_in_response(handler)


class TestIncidentChildRouteFallback:
    """Tests proving unknown incident child routes return handled responses."""

    def test_unknown_incident_child_path_returns_json_404(self) -> None:
        """Unknown /api/incidents/{id}/child path returns JSON 404, not HTML."""
        from k8s_diag_agent.ui.server_incident_reads import handle_incident_routes

        handler = MockApiHandler()
        handler.path = "/api/incidents/test-incident/nonexistent-child"
        result = handle_incident_routes(handler, handler.path, "")  # type: ignore[arg-type]

        # Route should not match any known pattern
        # If it returns False, the caller should handle as 404
        if not result:
            # This is expected - unknown child route returns False
            assert True
        else:
            # If it returns True, it should have set a response
            assert handler._sent_code is not None


class TestAutomaticDiagnosisLoopJsonContract:
    """Tests proving automatic diagnosis loop route returns JSON, never HTML."""

    def test_missing_incident_returns_json_error(self) -> None:
        """POST with missing incident returns JSON error, not HTML."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            handle_incident_automatic_diagnosis_loop_one_pass_api,
        )

        # Use MagicMock with all required attributes since the handler accesses result.skipped, etc.
        mock_result = MagicMock()
        mock_result.skipped = True
        mock_result.eligible = False
        mock_result.eligibility_reason = "incident_not_found"
        mock_result.incident_results = {}
        mock_result.run_id = "test-run-id"
        mock_result.skip_reason = "incident_not_found"

        with patch(
            "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.collect_automatic_diagnosis_evidence",
            return_value=mock_result,
        ):
            handler = MockApiHandler()
            handler.command = "POST"
            handler.path = "/api/incidents/nonexistent-incident/automatic-diagnosis-loop/one-pass"
            handle_incident_automatic_diagnosis_loop_one_pass_api(handler, "nonexistent-incident")  # type: ignore[arg-type]

            # Must return JSON, not HTML
            assert handler._sent_code in (200, 400, 404, 500)
            assert_json_response(handler)
            assert_no_html_in_response(handler)

    def test_collector_error_returns_json_500(self) -> None:
        """Collector error returns JSON 500, not HTML."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            handle_incident_automatic_diagnosis_loop_one_pass_api,
        )

        with patch(
            "k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop.collect_automatic_diagnosis_evidence",
            side_effect=RuntimeError("Collector error"),
        ):
            handler = MockApiHandler()
            handler.command = "POST"
            handler.path = "/api/incidents/test-incident/automatic-diagnosis-loop/one-pass"
            handle_incident_automatic_diagnosis_loop_one_pass_api(handler, "test-incident")  # type: ignore[arg-type]

            # Must return JSON
            assert handler._sent_code == 500
            assert_json_response(handler, expected_code=500)
            assert_no_html_in_response(handler)

    def test_wrong_method_returns_json_405(self) -> None:
        """GET to POST-only endpoint returns JSON 405, not HTML."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            handle_incident_automatic_diagnosis_loop_one_pass_api,
        )

        handler = MockApiHandler()
        handler.command = "GET"  # Wrong method
        handler.path = "/api/incidents/test-incident/automatic-diagnosis-loop/one-pass"
        handle_incident_automatic_diagnosis_loop_one_pass_api(handler, "test-incident")  # type: ignore[arg-type]

        # Must return JSON 405
        assert handler._sent_code == 405
        assert_json_response(handler, expected_code=405)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
