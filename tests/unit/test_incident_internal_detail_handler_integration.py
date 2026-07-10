"""Integration tests for internal incident detail handler.

These tests verify that the internal incident detail handler correctly
serializes incidents using the canonical wrapper format for scheduler compatibility.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentSignal,
    IncidentStatus,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import reset_incident_store, set_incident_store


class TestInternalDetailHandlerIntegration(unittest.TestCase):
    """Integration tests for internal incident detail handler."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_handle_get_incident_returns_wrapper_with_canonical_incident(self) -> None:
        """handle_get_incident must return wrapper with nested canonical incident.

        This is the regression test for the bug where the handler returned a
        projection payload with created_at/updated_at instead of the canonical
        incident.to_dict() shape required by the scheduler.
        """
        # Create and store an incident
        incident = Incident(
            incident_id="test-incident-456",
            source_candidate_id="test-candidate-789",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="PodCrashLoop",
            severity="high",
            status=IncidentStatus.OPEN,
            first_observed_at=datetime(2024, 2, 1, 10, 0, 0, tzinfo=UTC),
            last_observed_at=datetime(2024, 2, 1, 12, 0, 0, tzinfo=UTC),
            signals=[
                IncidentSignal(
                    source="detector",
                    reason="Crash",
                    message="Container crashed",
                    captured_at=datetime(2024, 2, 1, 10, 0, 0, tzinfo=UTC),
                ),
            ],
            signal_count=1,
        )
        self._test_store._incidents["test-incident-456"] = incident

        # Create a mock handler to capture the response
        mock_handler = MagicMock()

        # Call the handler
        from k8s_diag_agent.ui.server_incident_internal_read_handlers import (
            handle_get_incident,
        )

        # Mock the token validation to always pass
        with patch(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            return_value=True,
        ):
            handle_get_incident(mock_handler, "test-incident-456")

        # Verify the handler sent a successful response
        mock_handler._send_json.assert_called_once()
        call_args = mock_handler._send_json.call_args

        # Check status code is 200
        self.assertEqual(call_args[0][1], 200)

        # Check response body structure - must be wrapper format
        response_body = call_args[0][0]
        self.assertIn("schema_version", response_body)
        self.assertIn("payload_type", response_body)
        self.assertIn("incident", response_body)

        # Verify envelope
        self.assertEqual(response_body["schema_version"], "1")
        self.assertEqual(response_body["payload_type"], "incident-internal-detail")

        # Verify nested incident has canonical fields
        nested = response_body["incident"]
        self.assertIn("first_observed_at", nested)
        self.assertIn("last_observed_at", nested)
        self.assertIn("incident_id", nested)
        self.assertIn("source_candidate_id", nested)
        self.assertIn("namespace", nested)
        self.assertIn("object_kind", nested)
        self.assertIn("object_name", nested)
        self.assertIn("class", nested)  # Canonical serialization uses "class"
        self.assertIn("severity", nested)
        self.assertIn("status", nested)

        # Verify timestamps are in ISO format
        self.assertEqual(nested["first_observed_at"], "2024-02-01T10:00:00+00:00")
        self.assertEqual(nested["last_observed_at"], "2024-02-01T12:00:00+00:00")

    def test_handle_get_incident_wrapper_can_be_parsed_by_scheduler_contract(self) -> None:
        """Handler response can be parsed by parse_backend_incident_detail_payload.

        This verifies end-to-end compatibility between the handler and the
        scheduler's contract parser.
        """
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
            parse_backend_incident_detail_payload,
        )

        # Create and store an incident
        incident = Incident(
            incident_id="test-incident-abc",
            source_candidate_id="test-candidate-def",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="PodCrashLoop",
            severity="high",
            status=IncidentStatus.OPEN,
            first_observed_at=datetime(2024, 3, 1, 10, 0, 0, tzinfo=UTC),
            last_observed_at=datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC),
            signals=[],
            signal_count=0,
        )
        self._test_store._incidents["test-incident-abc"] = incident

        # Create a mock handler to capture the response
        mock_handler = MagicMock()

        # Call the handler
        from k8s_diag_agent.ui.server_incident_internal_read_handlers import (
            handle_get_incident,
        )

        with patch(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            return_value=True,
        ):
            handle_get_incident(mock_handler, "test-incident-abc")

        # Get the response
        call_args = mock_handler._send_json.call_args
        response_body = call_args[0][0]

        # The scheduler's parser must be able to parse this response
        parsed_incident = parse_backend_incident_detail_payload(response_body)

        # Verify the parsed incident matches the original
        self.assertEqual(parsed_incident.incident_id, incident.incident_id)
        self.assertEqual(parsed_incident.source_candidate_id, incident.source_candidate_id)
        self.assertEqual(parsed_incident.first_observed_at, incident.first_observed_at)
        self.assertEqual(parsed_incident.last_observed_at, incident.last_observed_at)
        self.assertEqual(parsed_incident.status, incident.status)

    def test_handle_get_incident_returns_404_for_missing_incident(self) -> None:
        """Handler returns 404 when incident is not found."""
        mock_handler = MagicMock()

        from k8s_diag_agent.ui.server_incident_internal_read_handlers import (
            handle_get_incident,
        )

        with patch(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            return_value=True,
        ):
            handle_get_incident(mock_handler, "nonexistent-incident")

        # Verify 404 response
        mock_handler._send_json.assert_called_once()
        call_args = mock_handler._send_json.call_args

        self.assertEqual(call_args[0][1], 404)
        response_body = call_args[0][0]
        self.assertIn("error", response_body)
        self.assertEqual(response_body["error"], "Not Found")


if __name__ == "__main__":
    unittest.main()
