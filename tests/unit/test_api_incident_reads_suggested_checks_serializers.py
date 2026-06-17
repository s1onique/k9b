"""Tests for serializer behavior with optional suggested_checks field.

These tests verify:
1. Serializer behavior for optional `next_check_plan_payload`
2. `suggested_checks` population from pre-loaded linked artifacts
3. Empty/omitted suggested-check behavior
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.api_incident_reads import build_incident_detail_payload

from .incident_lifecycle_fixtures import make_full_incident


class TestBuildIncidentDetailPayloadSuggestedChecks(unittest.TestCase):
    """Test suggested_checks field in detail payload."""

    def test_detail_suggested_checks_field_present(self) -> None:
        """Detail payload must include suggested_checks field."""
        incident = make_full_incident()
        result = build_incident_detail_payload(incident)

        self.assertIn("suggested_checks", result)
        self.assertIsInstance(result["suggested_checks"], list)

    def test_detail_suggested_checks_empty_by_default(self) -> None:
        """Detail payload suggested_checks must be empty when no mapping exists."""
        incident = make_full_incident()
        result = build_incident_detail_payload(incident)

        self.assertEqual(result["suggested_checks"], [])

    def test_detail_includes_suggested_checks_from_linked_artifact(self) -> None:
        """Detail payload must include suggested_checks from linked next-check plan."""
        incident = make_full_incident()
        # Simulate a next-check plan with a linked candidate for this incident
        plan_payload = {
            "run_id": "run-123",
            "linkage_schema_version": 1,
            "candidates": [
                {
                    "linkage_status": "linked",
                    "incident_id": incident.incident_id,
                    "candidateId": "check-001",
                    "title": "Pod Log Inspection",
                    "rationale": "Investigate crash loop",
                    "description": "Check pod logs for crash loop errors",
                    "riskLevel": "LOW",
                },
            ],
        }

        result = build_incident_detail_payload(incident, next_check_plan_payload=plan_payload)

        self.assertIn("suggested_checks", result)
        self.assertEqual(len(result["suggested_checks"]), 1)
        self.assertEqual(result["suggested_checks"][0]["check_id"], "check-001")
        self.assertEqual(result["suggested_checks"][0]["title"], "Pod Log Inspection")
        self.assertEqual(result["suggested_checks"][0]["source"], "next-check-plan")
        self.assertEqual(result["suggested_checks"][0]["status"], "suggested")
        self.assertEqual(result["suggested_checks"][0]["risk_level"], "LOW")

    def test_detail_remains_empty_when_no_plan_payload(self) -> None:
        """Detail payload must remain empty when next_check_plan_payload is None."""
        incident = make_full_incident()

        result = build_incident_detail_payload(incident)

        self.assertEqual(result["suggested_checks"], [])

    def test_detail_ignores_partial_candidates(self) -> None:
        """Detail payload must ignore candidates with partial linkage_status."""
        incident = make_full_incident()
        plan_payload = {
            "run_id": "run-123",
            "candidates": [
                {
                    "linkage_status": "partial",
                    "candidateId": "check-001",
                    "description": "Check pod logs",
                    "namespace": "default",
                    "objectKind": "Pod",
                },
            ],
        }

        result = build_incident_detail_payload(incident, next_check_plan_payload=plan_payload)

        self.assertEqual(result["suggested_checks"], [])

    def test_detail_ignores_unlinked_candidates(self) -> None:
        """Detail payload must ignore candidates with unlinked linkage_status."""
        incident = make_full_incident()
        plan_payload = {
            "run_id": "run-123",
            "candidates": [
                {
                    "linkage_status": "unlinked",
                    "candidateId": "check-001",
                    "description": "Check pod logs",
                },
            ],
        }

        result = build_incident_detail_payload(incident, next_check_plan_payload=plan_payload)

        self.assertEqual(result["suggested_checks"], [])

    def test_detail_ignores_non_matching_incident_id(self) -> None:
        """Detail payload must ignore candidates with non-matching incident_id."""
        incident = make_full_incident()
        plan_payload = {
            "run_id": "run-123",
            "candidates": [
                {
                    "linkage_status": "linked",
                    "incident_id": "different-incident-123",
                    "candidateId": "check-001",
                    "description": "Check pod logs",
                },
            ],
        }

        result = build_incident_detail_payload(incident, next_check_plan_payload=plan_payload)

        self.assertEqual(result["suggested_checks"], [])

    def test_detail_ignores_old_artifacts_without_linkage(self) -> None:
        """Detail payload must ignore old artifacts without linkage fields."""
        incident = make_full_incident()
        plan_payload = {
            "run_id": "run-123",
            "candidates": [
                {
                    "candidateId": "check-001",
                    "description": "Check pod logs",
                    "suggestedCommandFamily": "kubectl-logs",
                },
            ],
        }

        result = build_incident_detail_payload(incident, next_check_plan_payload=plan_payload)

        self.assertEqual(result["suggested_checks"], [])

    def test_detail_mixed_candidates_only_linked_extracted(self) -> None:
        """Detail payload must only extract safely linked candidates from mixed plan."""
        incident = make_full_incident()
        plan_payload = {
            "run_id": "run-123",
            "candidates": [
                {
                    "linkage_status": "linked",
                    "incident_id": incident.incident_id,
                    "candidateId": "check-001",
                    "title": "Check pod logs",
                },
                {"linkage_status": "unlinked", "candidateId": "check-002", "description": "Check events"},
                {"linkage_status": "partial", "candidateId": "check-003", "description": "Check describe"},
            ],
        }

        result = build_incident_detail_payload(incident, next_check_plan_payload=plan_payload)

        self.assertEqual(len(result["suggested_checks"]), 1)
        self.assertEqual(result["suggested_checks"][0]["check_id"], "check-001")


if __name__ == "__main__":
    unittest.main()
