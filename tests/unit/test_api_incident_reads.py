"""Tests for read-only incident API handlers.

Tests:
- list incidents returns promoted incidents
- list incidents returns deterministic order
- list incidents empty store returns []
- get incident returns matching record
- get unknown incident returns None
- status filter works
- response contains no remediation/action fields
- tests can inject/reset store deterministically
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.api_incident_reads import (
    handle_get_incident,
    handle_list_incidents,
)
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)

from .incident_store_fixtures import TEST_TIME_1, make_candidate


class TestHandleListIncidents(unittest.TestCase):
    """Test list incidents API handler."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        from k8s_diag_agent.collect.incident_store import IncidentStore

        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_list_incidents_returns_promoted_incidents(self) -> None:
        """List incidents returns incidents promoted into the store."""
        # Add incidents
        candidate = make_candidate(name="crashloop-pod", namespace="default")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)

        result = handle_list_incidents()

        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["incidents"]), 1)
        self.assertEqual(result["incidents"][0]["object_name"], "crashloop-pod")

    def test_list_incidents_returns_deterministic_order(self) -> None:
        """List incidents returns incidents sorted by incident_id."""
        # Add incidents in non-sorted order
        cand_z = make_candidate(name="z-pod", namespace="default")
        cand_a = make_candidate(name="a-pod", namespace="default")
        cand_m = make_candidate(name="m-pod", namespace="default")

        self._test_store.promote_candidates([cand_z, cand_a, cand_m], TEST_TIME_1)

        result = handle_list_incidents()

        incident_ids = [inc["incident_id"] for inc in result["incidents"]]
        self.assertEqual(incident_ids, sorted(incident_ids))

    def test_list_incidents_empty_store_returns_empty(self) -> None:
        """List incidents returns empty list when store has no incidents."""
        result = handle_list_incidents()

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["incidents"], [])

    def test_list_incidents_with_status_filter(self) -> None:
        """List incidents filters by status correctly."""
        # Add two incidents
        candidate1 = make_candidate(name="crashloop-pod-1")
        candidate2 = make_candidate(name="crashloop-pod-2")

        self._test_store.promote_candidates([candidate1, candidate2], TEST_TIME_1)

        # Mark one as suppressed
        incidents = self._test_store.list_incidents()
        self._test_store.suppress(incidents[0].incident_id, "known issue")

        # Filter by OPEN status
        result_open = handle_list_incidents(status="open")
        self.assertEqual(result_open["total"], 1)

        # Filter by SUPPRESSED status
        result_suppressed = handle_list_incidents(status="suppressed")
        self.assertEqual(result_suppressed["total"], 1)

        # Filter by non-matching status
        result_investigating = handle_list_incidents(status="investigating")
        self.assertEqual(result_investigating["total"], 0)

    def test_list_incidents_invalid_status_returns_empty(self) -> None:
        """List incidents with invalid status returns empty list."""
        # Add an incident
        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)

        result = handle_list_incidents(status="invalid_status")

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["incidents"], [])


class TestHandleGetIncident(unittest.TestCase):
    """Test get incident API handler."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        from k8s_diag_agent.collect.incident_store import IncidentStore

        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_get_incident_returns_matching_record(self) -> None:
        """Get incident returns the correct incident."""
        # Add incident
        candidate = make_candidate(name="crashloop-pod", namespace="default")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident_id = incidents[0].incident_id

        result = handle_get_incident(incident_id)

        self.assertIsNotNone(result)
        self.assertEqual(result["incident_id"], incident_id)
        self.assertEqual(result["namespace"], "default")
        self.assertEqual(result["object_name"], "crashloop-pod")

    def test_get_incident_unknown_returns_none(self) -> None:
        """Get incident returns None for unknown ID."""
        result = handle_get_incident("unknown-incident-id")

        self.assertIsNone(result)


class TestNoForbiddenFields(unittest.TestCase):
    """Verify no remediation, mutation, or action fields in responses."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        from k8s_diag_agent.collect.incident_store import IncidentStore

        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_list_response_has_no_remediation_fields(self) -> None:
        """List incidents response must not have remediation-related fields."""
        # Add an incident
        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)

        result = handle_list_incidents()

        # Check each incident for forbidden fields
        forbidden = ["remediate", "fix", "apply", "execute", "action", "mutate"]
        for incident in result["incidents"]:
            for field in incident.keys():
                for forb in forbidden:
                    self.assertNotIn(
                        forb.lower(),
                        field.lower(),
                        f"Found forbidden field: {field}",
                    )

    def test_detail_response_has_no_remediation_fields(self) -> None:
        """Get incident response must not have remediation-related fields."""
        # Add an incident
        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident_id = incidents[0].incident_id

        result = handle_get_incident(incident_id)

        self.assertIsNotNone(result)
        forbidden = ["remediate", "fix", "apply", "execute", "action", "mutate"]
        for field in result.keys():
            for forb in forbidden:
                self.assertNotIn(
                    forb.lower(),
                    field.lower(),
                    f"Found forbidden field: {field}",
                )

    def test_handler_has_no_forbidden_parameters(self) -> None:
        """API handlers must not have forbidden parameters."""
        import inspect

        for func in [handle_list_incidents, handle_get_incident]:
            sig = inspect.signature(func)
            params = [p.name for p in sig.parameters.values()]
            forbidden = ["kubectl", "remediation", "mutation", "llm", "persist", "database"]
            # Allow external_analysis_dir - it's the explicit artifact loading seam
            allowed = {"external_analysis_dir"}
            for param in params:
                if param in allowed:
                    continue
                for forb in forbidden:
                    self.assertNotIn(
                        forb.lower(),
                        param.lower(),
                        f"Found forbidden parameter: {param} in {func.__name__}",
                    )


if __name__ == "__main__":
    unittest.main()
