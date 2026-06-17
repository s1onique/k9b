"""Tests for incident snapshot API endpoint with incident promotion.

These tests verify:
- Backend route success with mock collector data
- Backend route failure with sanitized error
- Backend route redaction
- No sentinel patterns in API response
- Incident promotion during successful snapshot capture
- Promotion errors do not mask successful evidence capture
- No remediation/mutation/LLM/external-tool APIs
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from k8s_diag_agent.collect.api_incident import (
    IncidentSnapshotRequest,
    IncidentSnapshotResponse,
    handle_incident_snapshot,
)
from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus

# =============================================================================
# Helper fixtures
# =============================================================================


def make_test_candidate(
    name: str = "test-pod",
    namespace: str = "default",
    candidate_class: CandidateClass = CandidateClass.CRASH_LOOP,
) -> IncidentCandidate:
    """Create a test incident candidate."""
    return IncidentCandidate(
        candidate_id=f"{namespace}-pod-{name}-{candidate_class.value}",
        namespace=namespace,
        object_kind=ObjectKind.POD,
        object_name=name,
        candidate_class=candidate_class,
        severity=Severity.ERROR,
        signals=(
            CandidateSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="Back-off restarting container",
            ),
        ),
        evidence_needed=("pod_logs", "pod_describe"),
    )


def make_mock_bundle_with_candidates(candidates: list[IncidentCandidate]) -> MagicMock:
    """Create a mock bundle with the given candidates."""
    mock_bundle = MagicMock()
    mock_bundle.metadata.bundle_id = "test-bundle-001"
    mock_bundle.metadata.captured_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
    mock_bundle.metadata.namespace = "default"
    mock_bundle.metadata.since_hours = 2
    mock_bundle.metadata.total_pods = 5
    mock_bundle.metadata.total_events = 3
    mock_bundle.metadata.total_deployments = 2
    mock_bundle.metadata.failing_pods_count = 2
    mock_bundle.metadata.symptoms_count = 3
    mock_bundle.metadata.candidates_count = len(candidates)
    mock_bundle.candidates = tuple(candidates)
    mock_bundle.to_dict.return_value = {
        "metadata": {
            "bundle_id": "test-bundle-001",
            "captured_at": "2024-01-15T12:00:00+00:00",
            "namespace": "default",
            "since_hours": 2,
            "total_pods": 5,
            "total_events": 3,
            "total_deployments": 2,
            "failing_pods_count": 2,
            "symptoms_count": 3,
            "candidates_count": len(candidates),
        },
        "pods": [],
        "events": [],
        "deployments": [],
        "symptoms": [],
        "collection_errors": [],
        "candidates": [c.to_dict() for c in candidates],
    }
    return mock_bundle


# =============================================================================
# Test Cases
# =============================================================================


class TestHandleIncidentSnapshotWithPromotion(unittest.TestCase):
    """Test incident promotion during snapshot capture."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        # Create a fresh store for testing
        from k8s_diag_agent.collect.incident_store import IncidentStore
        from k8s_diag_agent.collect.incident_store_provider import (
            set_incident_store,
        )

        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        from k8s_diag_agent.collect.incident_store_provider import (
            reset_incident_store,
            set_incident_store,
        )

        set_incident_store(None)
        reset_incident_store()

    def test_snapshot_promotes_candidates_into_store(self) -> None:
        """Successful snapshot capture promotes candidates into the store."""
        candidate = make_test_candidate(name="crashloop-pod")
        mock_bundle = make_mock_bundle_with_candidates([candidate])

        with patch(
            "k8s_diag_agent.collect.api_incident.collect_incident_snapshot",
            return_value=mock_bundle,
        ):
            request = IncidentSnapshotRequest(namespace="default")
            response = handle_incident_snapshot(request)

        self.assertEqual(response.incidents_promoted_count, 1)
        self.assertEqual(len(response.promoted_incidents), 1)
        self.assertEqual(response.candidates_count, 1)

    def test_response_includes_incidents_promoted_count(self) -> None:
        """Response summary includes incidents_promoted_count."""
        candidate = make_test_candidate(name="crashloop-pod")
        mock_bundle = make_mock_bundle_with_candidates([candidate])

        with patch(
            "k8s_diag_agent.collect.api_incident.collect_incident_snapshot",
            return_value=mock_bundle,
        ):
            request = IncidentSnapshotRequest(namespace="default")
            response = handle_incident_snapshot(request)

        data = response.to_dict()
        self.assertEqual(data["summary"]["incidents_promoted_count"], 1)
        self.assertEqual(data["summary"]["candidates_count"], 1)

    def test_promoted_incident_has_snapshot_bundle_id(self) -> None:
        """Promoted incident has snapshot_bundle_id equal to bundle ID."""
        candidate = make_test_candidate(name="crashloop-pod")
        mock_bundle = make_mock_bundle_with_candidates([candidate])

        with patch(
            "k8s_diag_agent.collect.api_incident.collect_incident_snapshot",
            return_value=mock_bundle,
        ):
            request = IncidentSnapshotRequest(namespace="default")
            response = handle_incident_snapshot(request)

        self.assertEqual(len(response.promoted_incidents), 1)
        self.assertEqual(
            response.promoted_incidents[0]["snapshot_bundle_id"],
            "test-bundle-001",
        )

    def test_no_candidates_produces_zero_promoted_incidents(self) -> None:
        """Snapshot with no candidates produces zero promoted incidents."""
        mock_bundle = make_mock_bundle_with_candidates([])

        with patch(
            "k8s_diag_agent.collect.api_incident.collect_incident_snapshot",
            return_value=mock_bundle,
        ):
            request = IncidentSnapshotRequest(namespace="default")
            response = handle_incident_snapshot(request)

        self.assertEqual(response.incidents_promoted_count, 0)
        self.assertEqual(len(response.promoted_incidents), 0)
        self.assertEqual(response.candidates_count, 0)

    def test_repeated_snapshot_with_same_candidate_deduplicates(self) -> None:
        """Repeated snapshot with same candidate merges, not duplicates."""
        candidate = make_test_candidate(name="crashloop-pod")
        mock_bundle = make_mock_bundle_with_candidates([candidate])

        with patch(
            "k8s_diag_agent.collect.api_incident.collect_incident_snapshot",
            return_value=mock_bundle,
        ):
            # First capture
            request = IncidentSnapshotRequest(namespace="default")
            response1 = handle_incident_snapshot(request)

            # Second capture with same candidate
            response2 = handle_incident_snapshot(request)

        # First capture promotes 1
        self.assertEqual(response1.incidents_promoted_count, 1)

        # Second capture promotes 1 (the merged incident)
        self.assertEqual(response2.incidents_promoted_count, 1)

        # But store should have only 1 incident (deduplicated)
        from k8s_diag_agent.collect.incident_store_provider import get_incident_store

        store = get_incident_store()
        self.assertEqual(len(store.list_incidents()), 1)

    def test_suppressed_incident_not_reopened_by_repeated_snapshot(self) -> None:
        """SUPPRESSED incident is not reopened by repeated snapshot."""
        from k8s_diag_agent.collect.incident_store_provider import get_incident_store

        candidate = make_test_candidate(name="crashloop-pod")
        mock_bundle = make_mock_bundle_with_candidates([candidate])

        with patch(
            "k8s_diag_agent.collect.api_incident.collect_incident_snapshot",
            return_value=mock_bundle,
        ):
            # First capture
            request = IncidentSnapshotRequest(namespace="default")
            response1 = handle_incident_snapshot(request)
            incident_id = response1.promoted_incidents[0]["incident_id"]

            # Suppress the incident
            store = get_incident_store()
            store.suppress(incident_id, "known issue")

            # Verify suppressed
            suppressed = store.get_incident(incident_id)
            assert suppressed is not None
            self.assertEqual(suppressed.status, IncidentStatus.SUPPRESSED)

            # Second capture - should NOT reopen
            _response2 = handle_incident_snapshot(request)

        # Store should still have 1 incident, still suppressed
        store = get_incident_store()
        self.assertEqual(len(store.list_incidents()), 1)
        after = store.get_incident(incident_id)
        assert after is not None
        self.assertEqual(after.status, IncidentStatus.SUPPRESSED)

    def test_promotion_error_does_not_mask_successful_capture(self) -> None:
        """Errors in promotion must not mask successful evidence capture."""
        candidate = make_test_candidate(name="crashloop-pod")
        mock_bundle = make_mock_bundle_with_candidates([candidate])

        # Make promotion raise an exception
        with patch(
            "k8s_diag_agent.collect.api_incident.collect_incident_snapshot",
            return_value=mock_bundle,
        ), patch.object(
            self._test_store,
            "promote_candidates_from_bundle",
            side_effect=RuntimeError("Store error"),
        ):
            request = IncidentSnapshotRequest(namespace="default")
            response = handle_incident_snapshot(request)

        # Response should still be successful
        self.assertEqual(response.bundle_id, "test-bundle-001")
        self.assertEqual(response.error, None)
        self.assertIsNotNone(response.bundle)
        # Promotion count should be 0 due to error
        self.assertEqual(response.incidents_promoted_count, 0)


class TestIncidentSnapshotResponseWithPromotion(unittest.TestCase):
    """Test the response shape with incident promotion fields."""

    def test_to_dict_includes_promotion_fields_in_summary(self) -> None:
        """to_dict() includes promotion fields in summary."""
        response = IncidentSnapshotResponse(
            bundle_id="test-001",
            captured_at="2024-01-15T12:00:00Z",
            namespace="default",
            summary={"total_pods": 5},
            bundle={"metadata": {}},
            candidates_count=2,
            incidents_promoted_count=1,
            promoted_incidents=[{"incident_id": "inc-1"}],
        )

        data = response.to_dict()

        self.assertEqual(data["summary"]["candidates_count"], 2)
        self.assertEqual(data["summary"]["incidents_promoted_count"], 1)
        self.assertIn("promoted_incidents", data)
        self.assertEqual(len(data["promoted_incidents"]), 1)

    def test_to_dict_without_promoted_incidents(self) -> None:
        """to_dict() works when no incidents promoted."""
        response = IncidentSnapshotResponse(
            bundle_id="test-001",
            captured_at="2024-01-15T12:00:00Z",
            namespace="default",
            summary={"total_pods": 5},
            bundle={"metadata": {}},
            candidates_count=0,
            incidents_promoted_count=0,
            promoted_incidents=[],
        )

        data = response.to_dict()

        self.assertEqual(data["summary"]["candidates_count"], 0)
        self.assertEqual(data["summary"]["incidents_promoted_count"], 0)
        self.assertNotIn("promoted_incidents", data)

    def test_promoted_incident_fields(self) -> None:
        """Promoted incident dict contains expected fields."""
        response = IncidentSnapshotResponse(
            bundle_id="test-001",
            captured_at="2024-01-15T12:00:00Z",
            namespace="default",
            summary={},
            bundle={"metadata": {}},
            candidates_count=1,
            incidents_promoted_count=1,
            promoted_incidents=[
                {
                    "incident_id": "default-pod-crashloop-pod-crash_loop",
                    "source_candidate_id": "cand-1",
                    "namespace": "default",
                    "object_kind": "Pod",
                    "object_name": "crashloop-pod",
                    "raw_object_kind": None,
                    "class": "crash_loop",
                    "severity": "error",
                    "status": "collecting_evidence",
                    "first_observed_at": "2024-01-15T12:00:00+00:00",
                    "last_observed_at": "2024-01-15T12:00:00+00:00",
                    "signals": [],
                    "evidence_needed": ["pod_logs", "pod_describe"],
                    "snapshot_bundle_id": "test-bundle-001",
                    "review_packet_available": False,
                    "review_packet_id": None,
                    "suppressed_reason": None,
                    "duplicate_of": None,
                    "resolved_at": None,
                    "resolution_notes": None,
                }
            ],
        )

        data = response.to_dict()
        incident = data["promoted_incidents"][0]

        self.assertEqual(incident["incident_id"], "default-pod-crashloop-pod-crash_loop")
        self.assertEqual(incident["snapshot_bundle_id"], "test-bundle-001")
        self.assertEqual(incident["status"], "collecting_evidence")


class TestNoForbiddenAPIs(unittest.TestCase):
    """Verify no persistence, remediation, mutation, LLM, or external tool APIs."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        from k8s_diag_agent.collect.incident_store import IncidentStore
        from k8s_diag_agent.collect.incident_store_provider import (
            set_incident_store,
        )

        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        from k8s_diag_agent.collect.incident_store_provider import (
            reset_incident_store,
            set_incident_store,
        )

        set_incident_store(None)
        reset_incident_store()

    def test_handle_incident_snapshot_has_no_forbidden_parameters(self) -> None:
        """handle_incident_snapshot must not have forbidden parameters."""
        import inspect

        sig = inspect.signature(handle_incident_snapshot)
        params = [p.name for p in sig.parameters.values()]

        forbidden = ["kubectl", "remediation", "mutation", "llm", "external", "persist", "database"]
        for param in params:
            for forb in forbidden:
                self.assertNotIn(forb, param.lower(), f"Found forbidden parameter: {param}")

    def test_response_has_no_remediation_fields(self) -> None:
        """IncidentSnapshotResponse must not have remediation-related fields."""
        import inspect

        sig = inspect.signature(IncidentSnapshotResponse)
        fields = [p.name for p in sig.parameters.values()]

        forbidden = ["remediate", "fix", "apply", "execute"]
        for field_name in fields:
            for forb in forbidden:
                self.assertNotIn(
                    forb,
                    field_name.lower(),
                    f"Found forbidden field: {field_name}",
                )


if __name__ == "__main__":
    unittest.main()
