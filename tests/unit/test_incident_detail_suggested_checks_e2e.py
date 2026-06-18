"""End-to-end regression tests for IncidentDetail.suggested_checks.

Tests the full read-only production path:
1. Incident creation with signal.run_id
2. Real {run_id}-next-check-plan.json artifact placement
3. Incident detail API fetch
4. Frontend payload rendering assertions
5. Negative cases: missing, wrong run_id, partial, unsafe artifacts

Constraints enforced:
- Read-only only
- No backend model changes
- No execution, promotion, or remediation paths
- No action/control buttons in output

This is a regression test for the incidents meta-epic ACT:
"Add incident detail end-to-end regression for runtime suggested checks"
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from k8s_diag_agent.collect.api_incident_reads import handle_get_incident
from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import reset_incident_store, set_incident_store

from .incident_lifecycle_fixtures import TEST_TIME_1, TEST_TIME_2, make_candidate

# =============================================================================
# Realistic artifact fixtures
# =============================================================================


def make_valid_next_check_plan_artifact(
    run_id: str,
    incident_id: str,
    *,
    candidate_id: str = "check-001",
    title: str = "Pod Log Inspection",
    description: str = "Check pod logs for crash loop errors",
    rationale: str = "CrashLoopBackOff typically leaves informative logs",
    risk_level: str = "LOW",
) -> dict:
    """Create a realistic valid next-check-plan.json artifact.

    This fixture represents a real artifact produced by the next-check planner
    with proper linkage fields for SAFE incident association.
    """
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": [
            {
                "linkage_status": "linked",
                "incident_id": incident_id,
                "candidateId": candidate_id,
                "title": title,
                "description": description,
                "rationale": rationale,
                "riskLevel": risk_level,
                "sourceReason": "CrashLoopBackOff",
                "suggestedCommandFamily": "kubectl-logs",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "confidence": "high",
                "estimatedCost": "low",
            },
        ],
    }


def make_partial_next_check_plan_artifact(run_id: str) -> dict:
    """Create an artifact with partial candidates (no usable linked check).

    Partial candidates have entity fields but no incident_id linkage.
    These should NOT appear in incident detail suggested_checks.
    """
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": [
            {
                "linkage_status": "partial",
                "candidateId": "check-001",
                "title": "Check pod logs",
                "description": "Check pod logs for crash loop",
                "namespace": "default",
                "objectKind": "Pod",
                "objectName": "test-pod",
            },
            {
                "linkage_status": "unlinked",
                "candidateId": "check-002",
                "title": "Describe pod",
                "description": "Describe the pod",
            },
        ],
    }


def make_wrong_incident_next_check_plan_artifact(run_id: str, wrong_incident_id: str) -> dict:
    """Create an artifact where linked candidates reference a different incident.

    These should NOT appear in incident detail suggested_checks for our incident.
    """
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": [
            {
                "linkage_status": "linked",
                "incident_id": wrong_incident_id,
                "candidateId": "check-001",
                "title": "Check logs",
                "description": "Check logs for other incident",
                "riskLevel": "LOW",
            },
        ],
    }


def make_legacy_next_check_plan_artifact(run_id: str) -> dict:
    """Create an artifact without linkage fields (legacy format).

    Legacy artifacts without linkage_status and incident_id should
    NOT produce suggested checks.
    """
    return {
        "run_id": run_id,
        "candidates": [
            {
                "candidateId": "check-001",
                "title": "Check logs",
                "description": "Check pod logs",
                "suggestedCommandFamily": "kubectl-logs",
            },
        ],
    }


def make_malformed_next_check_plan_artifact() -> str:
    """Return malformed JSON that should be gracefully skipped."""
    return "{ invalid json }"


def make_empty_candidates_next_check_plan_artifact(run_id: str) -> dict:
    """Create an artifact with empty candidates list.

    An artifact with linkage fields but no candidates should
    produce empty suggested_checks, not fail.
    """
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": [],
    }


def make_no_candidates_key_next_check_plan_artifact(run_id: str) -> dict:
    """Create an artifact without a candidates key.

    Should be gracefully handled (empty suggested_checks).
    """
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
    }


# =============================================================================
# Regression tests
# =============================================================================


class TestIncidentDetailSuggestedChecksE2E(unittest.TestCase):
    """End-to-end regression tests for incident detail suggested_checks path.

    Tests the full production path:
    - incident store -> signal extraction -> artifact loading -> API handler
    - -> serializer -> payload -> frontend rendering assertions
    """

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)
        self._tmpdir = tempfile.mkdtemp()
        self._external_dir = Path(self._tmpdir) / "external-analysis"
        self._external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up after each test."""
        set_incident_store(None)
        reset_incident_store()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_plan_artifact(self, run_id: str, payload: dict) -> None:
        """Write a plan artifact to the external_analysis directory."""
        path = self._external_dir / f"{run_id}-next-check-plan.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _write_malformed_artifact(self, run_id: str, content: str) -> None:
        """Write a malformed artifact to the external_analysis directory."""
        path = self._external_dir / f"{run_id}-next-check-plan.json"
        path.write_text(content, encoding="utf-8")

    def _create_incident_with_signal(
        self,
        run_id: str,
        *,
        signal_reason: str = "CrashLoopBackOff",
        signal_message: str = "restarting",
        captured_at: datetime = TEST_TIME_1,
    ) -> str:
        """Create an incident with a signal in the store."""
        # Create incident via candidate promotion
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Add signal to the stored incident (required for artifact lookup)
        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason=signal_reason,
            message=signal_message,
            captured_at=captured_at,
            run_id=run_id,
        )
        stored_incident.signals.append(signal)

        return incident_id

    # =========================================================================
    # Positive case: Valid linked artifact produces suggested checks
    # =========================================================================

    def test_valid_linked_artifact_produces_suggested_check(self) -> None:
        """Valid linked next-check-plan artifact produces suggested_checks in incident detail."""
        # Create incident with signal
        incident_id = self._create_incident_with_signal("run-valid-001")
        run_id = "run-valid-001"

        # Write valid artifact with linked candidate for this incident
        artifact = make_valid_next_check_plan_artifact(
            run_id=run_id,
            incident_id=incident_id,
            candidate_id="check-pod-logs",
            title="Inspect pod logs for test-pod",
            rationale="CrashLoopBackOff typically leaves informative logs",
            risk_level="LOW",
        )
        self._write_plan_artifact(run_id, artifact)

        # Fetch incident detail through production API path
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Assert suggested_checks is populated
        self.assertIsNotNone(result)
        assert result is not None  # for mypy
        self.assertIn("suggested_checks", result)
        self.assertEqual(len(result["suggested_checks"]), 1)

        # Assert check content
        check = result["suggested_checks"][0]
        self.assertEqual(check["check_id"], "check-pod-logs")
        self.assertEqual(check["title"], "Inspect pod logs for test-pod")
        self.assertEqual(check["rationale"], "CrashLoopBackOff typically leaves informative logs")
        self.assertEqual(check["source"], "next-check-plan")
        self.assertEqual(check["risk_level"], "LOW")
        self.assertEqual(check["status"], "suggested")

    def test_multiple_linked_candidates_from_same_artifact(self) -> None:
        """Artifact with multiple linked candidates produces multiple suggested_checks."""
        incident_id = self._create_incident_with_signal("run-multi-001")

        # Write artifact with multiple linked candidates
        artifact = {
            "run_id": "run-multi-001",
            "linkage_schema_version": 1,
            "candidates": [
                {
                    "linkage_status": "linked",
                    "incident_id": incident_id,
                    "candidateId": "check-001",
                    "title": "Check pod logs",
                    "rationale": "First diagnostic step",
                    "riskLevel": "LOW",
                },
                {
                    "linkage_status": "linked",
                    "incident_id": incident_id,
                    "candidateId": "check-002",
                    "title": "Describe deployment",
                    "rationale": "Check replica status",
                    "riskLevel": "MEDIUM",
                },
            ],
        }
        self._write_plan_artifact("run-multi-001", artifact)

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)
        assert result is not None
        self.assertEqual(len(result["suggested_checks"]), 2)
        check_ids = [c["check_id"] for c in result["suggested_checks"]]
        self.assertIn("check-001", check_ids)
        self.assertIn("check-002", check_ids)

    def test_multiple_runs_produce_multiple_suggested_checks(self) -> None:
        """Incident with signals from multiple runs produces checks from all linked artifacts."""
        # Create incident with signals from two runs
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        stored_incident.signals.extend([
            IncidentSignal(
                source="pod", reason="CrashLoopBackOff", message="restarting",
                captured_at=TEST_TIME_1, run_id="run-1",
            ),
            IncidentSignal(
                source="pod", reason="CrashLoopBackOff", message="restarting again",
                captured_at=TEST_TIME_2, run_id="run-2",
            ),
        ])

        # Write artifacts for both runs
        self._write_plan_artifact("run-1", make_valid_next_check_plan_artifact(
            run_id="run-1", incident_id=incident_id, candidate_id="check-001",
        ))
        self._write_plan_artifact("run-2", make_valid_next_check_plan_artifact(
            run_id="run-2", incident_id=incident_id, candidate_id="check-002",
        ))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Should have checks from both artifacts
        self.assertEqual(len(result["suggested_checks"]), 2)
        check_ids = [c["check_id"] for c in result["suggested_checks"]]
        self.assertIn("check-001", check_ids)
        self.assertIn("check-002", check_ids)

    # =========================================================================
    # Negative cases: Unlinked, partial, wrong incident, missing artifacts
    # =========================================================================

    def test_missing_artifact_produces_empty_suggested_checks(self) -> None:
        """Missing next-check-plan artifact produces empty suggested_checks."""
        incident_id = self._create_incident_with_signal("run-missing")

        # Don't write any artifact
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertEqual(result["suggested_checks"], [])

    def test_partial_candidates_are_ignored(self) -> None:
        """Partial/unlinked candidates do NOT produce suggested_checks."""
        incident_id = self._create_incident_with_signal("run-partial")

        # Write artifact with partial candidates (no incident_id linkage)
        self._write_plan_artifact("run-partial", make_partial_next_check_plan_artifact("run-partial"))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Partial candidates should be filtered out
        self.assertEqual(result["suggested_checks"], [])

    def test_wrong_incident_candidates_are_ignored(self) -> None:
        """Candidates linked to a different incident do NOT appear in this incident."""
        incident_id = self._create_incident_with_signal("run-wrong")

        # Write artifact where candidate is linked to a DIFFERENT incident
        self._write_plan_artifact("run-wrong", make_wrong_incident_next_check_plan_artifact(
            run_id="run-wrong",
            wrong_incident_id="different-incident-id-12345",
        ))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Should be empty because incident_id doesn't match
        self.assertEqual(result["suggested_checks"], [])

    def test_legacy_artifact_without_linkage_fields_is_ignored(self) -> None:
        """Legacy artifacts without linkage_status and incident_id are ignored."""
        incident_id = self._create_incident_with_signal("run-legacy")

        # Write legacy artifact (no linkage fields)
        self._write_plan_artifact("run-legacy", make_legacy_next_check_plan_artifact("run-legacy"))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Legacy artifacts without linkage fields should produce empty
        self.assertEqual(result["suggested_checks"], [])

    def test_malformed_json_artifact_is_skipped(self) -> None:
        """Malformed JSON in plan artifact is gracefully skipped."""
        incident_id = self._create_incident_with_signal("run-malformed")

        # Write malformed artifact
        self._write_malformed_artifact("run-malformed", make_malformed_next_check_plan_artifact())

        # Should not raise - should gracefully handle
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertEqual(result["suggested_checks"], [])

    def test_empty_candidates_list_produces_empty_suggested_checks(self) -> None:
        """Artifact with empty candidates list produces empty suggested_checks (not an error)."""
        incident_id = self._create_incident_with_signal("run-empty")

        self._write_plan_artifact("run-empty", make_empty_candidates_next_check_plan_artifact("run-empty"))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertEqual(result["suggested_checks"], [])

    def test_no_candidates_key_produces_empty_suggested_checks(self) -> None:
        """Artifact without candidates key produces empty suggested_checks (not an error)."""
        incident_id = self._create_incident_with_signal("run-no-candidates")

        self._write_plan_artifact("run-no-candidates",
                                  make_no_candidates_key_next_check_plan_artifact("run-no-candidates"))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertEqual(result["suggested_checks"], [])

    def test_wrong_run_id_artifact_is_not_loaded(self) -> None:
        """Artifact with wrong run_id in filename is not associated with incident."""
        incident_id = self._create_incident_with_signal("run-correct")

        # Write artifact with WRONG run_id in filename (but correct content)
        correct_artifact = make_valid_next_check_plan_artifact(
            run_id="run-wrong-filename",
            incident_id=incident_id,
        )
        # Write to file with wrong run_id
        wrong_path = self._external_dir / "run-wrong-filename-next-check-plan.json"
        wrong_path.write_text(json.dumps(correct_artifact), encoding="utf-8")

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Should be empty because filename doesn't match signal's run_id
        self.assertEqual(result["suggested_checks"], [])

    # =========================================================================
    # Safety assertions: No action controls in output
    # =========================================================================

    def test_no_execution_controls_in_suggested_checks(self) -> None:
        """Suggested checks do not include execution controls (Run, Execute, Promote, etc.)."""
        incident_id = self._create_incident_with_signal("run-controls")
        self._write_plan_artifact("run-controls", make_valid_next_check_plan_artifact(
            run_id="run-controls",
            incident_id=incident_id,
        ))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Check that the payload structure doesn't include action fields
        check = result["suggested_checks"][0]

        # These fields should NOT exist in suggested_check payload
        self.assertNotIn("run", check)
        self.assertNotIn("execute", check)
        self.assertNotIn("promote", check)
        self.assertNotIn("apply", check)
        self.assertNotIn("remediate", check)
        self.assertNotIn("action", check)

        # Status should be "suggested" (read-only state)
        self.assertEqual(check["status"], "suggested")

    # =========================================================================
    # Read-only path verification
    # =========================================================================

    def test_incident_detail_does_not_mutate_store(self) -> None:
        """handle_get_incident does not mutate the incident store."""
        incident_id = self._create_incident_with_signal("run-mutation")

        # Get initial state
        initial_signal_count = len(self._test_store.get_incident(incident_id).signals)

        # Fetch incident detail
        self._write_plan_artifact("run-mutation", make_valid_next_check_plan_artifact(
            run_id="run-mutation",
            incident_id=incident_id,
        ))
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # State should be unchanged
        final_signal_count = len(self._test_store.get_incident(incident_id).signals)
        self.assertEqual(initial_signal_count, final_signal_count)

        # Result should still have suggested_checks from artifact
        self.assertEqual(len(result["suggested_checks"]), 1)

    def test_external_analysis_dir_not_required(self) -> None:
        """handle_get_incident works without external_analysis_dir (returns empty suggested_checks)."""
        incident_id = self._create_incident_with_signal("run-no-dir")

        # No external_analysis_dir provided
        result = handle_get_incident(incident_id, external_analysis_dir=None)

        self.assertEqual(result["suggested_checks"], [])


class TestIncidentDetailSuggestedChecksSafety(unittest.TestCase):
    """Safety-specific tests for suggested_checks extraction.

    Ensures that unsafe run_ids and malicious paths cannot leak into
    incident detail suggested_checks.
    """

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)
        self._tmpdir = tempfile.mkdtemp()
        self._external_dir = Path(self._tmpdir) / "external-analysis"
        self._external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up after each test."""
        set_incident_store(None)
        reset_incident_store()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _create_incident_with_signal(self, run_id: str) -> str:
        """Create an incident with a signal in the store."""
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=TEST_TIME_1,
            run_id=run_id,
        )
        stored_incident.signals.append(signal)

        return incident_id

    def test_unsafe_run_id_with_path_traversal_is_rejected(self) -> None:
        """run_id with path traversal (../) is rejected and doesn't leak artifacts."""
        incident_id = self._create_incident_with_signal("../etc/passwd")

        # Create a file that should NOT be accessible
        etc_dir = Path(self._tmpdir).parent / "etc"
        etc_dir.mkdir(parents=True, exist_ok=True)
        (etc_dir / "passwd").write_text("malicious content", encoding="utf-8")

        # Try to access via path traversal run_id
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Should be empty (unsafe run_id was rejected)
        self.assertEqual(result["suggested_checks"], [])

    def test_unsafe_run_id_with_absolute_path_is_rejected(self) -> None:
        """run_id that is an absolute path is rejected."""
        incident_id = self._create_incident_with_signal("/tmp/malicious")

        # Create artifact in /tmp
        malicious_dir = Path("/tmp")
        malicious_path = malicious_dir / "malicious-next-check-plan.json"
        malicious_path.write_text(json.dumps({
            "run_id": "/tmp/malicious",
            "linkage_schema_version": 1,
            "candidates": [{
                "linkage_status": "linked",
                "incident_id": incident_id,
                "candidateId": "malicious-check",
                "title": "Malicious check",
            }],
        }), encoding="utf-8")

        try:
            # Try to access via absolute path run_id
            result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

            # Should be empty (unsafe run_id was rejected)
            self.assertEqual(result["suggested_checks"], [])
        finally:
            # Cleanup
            malicious_path.unlink(missing_ok=True)

    def test_unsafe_run_id_with_glob_metacharacter_is_rejected(self) -> None:
        """run_id with glob metacharacters is rejected."""
        incident_id = self._create_incident_with_signal("run-*")

        # Create artifact in external-analysis (should NOT be accessed)
        self._external_dir.mkdir(parents=True, exist_ok=True)
        (self._external_dir / "run-run-*-next-check-plan.json").write_text(json.dumps({
            "run_id": "run-*",
            "linkage_schema_version": 1,
            "candidates": [{
                "linkage_status": "linked",
                "incident_id": incident_id,
                "candidateId": "glob-check",
                "title": "Glob check",
            }],
        }), encoding="utf-8")

        # Try to access via glob run_id
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Should be empty (unsafe run_id was rejected)
        self.assertEqual(result["suggested_checks"], [])


if __name__ == "__main__":
    unittest.main()