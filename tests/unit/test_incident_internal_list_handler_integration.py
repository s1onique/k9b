"""Integration tests for internal incident list handler.

These tests verify that the internal incident list handler correctly
serializes promoted incidents using the domain model fields.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import reset_incident_store, set_incident_store


class TestInternalListIncidentsAfterPromotion(unittest.TestCase):
    """Integration test: list incidents must serialize timestamps correctly after promotion."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_list_incidents_after_promotion_serializes_timestamps(self) -> None:
        """handle_list_incidents must correctly serialize promoted incident timestamps.

        This is the regression test for the bug where listing incidents after
        promotion failed with AttributeError because the handler referenced
        non-existent Incident.created_at instead of Incident.first_observed_at.
        """
        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )

        # Create and promote a candidate (simulating what happens during collection)
        promotion_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        candidate = IncidentCandidate(
            candidate_id="test-candidate",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="test-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(
                CandidateSignal(
                    source="pod",
                    reason="CrashLoopBackOff",
                    message="Back-off restarting failed container",
                ),
            ),
            evidence_needed=("pod_logs",),
            raw_object_kind=None,
        )

        # Promote the candidate (creates the incident)
        self._test_store.promote_candidates([candidate], promotion_time)

        # Create a mock handler to capture the response
        mock_handler = MagicMock()
        mock_handler.path = "/api/internal/incidents?limit=10"

        # Call the handler
        from k8s_diag_agent.ui.server_incident_internal_read_handlers import (
            handle_list_incidents,
        )

        # Mock the token validation to always pass
        with patch(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            return_value=True,
        ):
            handle_list_incidents(mock_handler)

        # Verify the handler sent a successful response
        mock_handler._send_json.assert_called_once()
        call_args = mock_handler._send_json.call_args

        # Check status code is 200
        self.assertEqual(call_args[0][1], 200)

        # Check response body structure
        response_body = call_args[0][0]
        self.assertIn("incidents", response_body)
        self.assertIn("total", response_body)
        self.assertEqual(response_body["total"], 1)

        # Check the incident has correct timestamp serialization
        # R13: Pagination path returns first_observed_at (for cursor key) + status + incident_id
        # The first_observed_at value uses first_observed_at_key (exact DB text)
        incident = response_body["incidents"][0]
        self.assertIn("incident_id", incident)
        self.assertIn("status", incident)
        self.assertIn("first_observed_at", incident)

        # Timestamps must be ISO format strings from first_observed_at
        expected_timestamp = promotion_time.isoformat()
        self.assertEqual(incident["first_observed_at"], expected_timestamp)

    def test_list_incidents_does_not_return_200_on_projection_failure(self) -> None:
        """Projection failure must return 500, not 200 with empty data.

        This ensures that when serialization fails, the handler correctly
        reports an error instead of silently returning an empty result.
        """
        mock_handler = MagicMock()
        mock_handler.path = "/api/internal/incidents?limit=10"

        from k8s_diag_agent.ui.server_incident_internal_read_handlers import (
            handle_list_incidents,
        )

        # Mock the token validation to always pass
        with patch(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            return_value=True,
        ):
            # Mock the store to raise an exception
            # Patch where it's imported (inside the function), not where it's used
            with patch(
                "k8s_diag_agent.collect.incident_store_provider.get_incident_store"
            ) as mock_get_store:
                mock_store = MagicMock()
                mock_store.list_incidents.side_effect = RuntimeError("Store unavailable")
                mock_get_store.return_value = mock_store

                handle_list_incidents(mock_handler)

        # Verify the handler sent an error response
        mock_handler._send_json.assert_called_once()
        call_args = mock_handler._send_json.call_args

        # Status code must be 500 for internal errors
        self.assertEqual(call_args[0][1], 500)

        # Response must contain error information
        response_body = call_args[0][0]
        self.assertIn("error", response_body)
        self.assertIn("message", response_body)
        self.assertEqual(response_body["error"], "Internal Error")


if __name__ == "__main__":
    unittest.main()
