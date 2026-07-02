"""Tests for review_artifact_paths propagation in compute_p4c_outcome()."""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    compute_p4c_outcome,
)


class TestReviewArtifactPathPropagation:
    """Tests for review_artifact_paths propagation in failure cases."""

    def test_review_artifact_paths_from_evidence(self) -> None:
        """Review artifact paths are preserved from evidence."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "The shipping pod is Unschedulable because FailedScheduling",
            "review_packet_path": "/artifacts/review/test.json",
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        assert outcome.review_artifact_paths == ("/artifacts/review/test.json",)

    def test_review_artifact_paths_from_backend_incident_detail(self) -> None:
        """Review artifact paths are extracted from backend_incident_detail."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "The shipping pod is Unschedulable",
            # No review_packet_path, but backend_incident_detail has it
            "backend_incident_detail": {
                "automatic_diagnosis_review": {
                    "artifact_name": "auto-test-incident-diagnosis-review-packet.json"
                }
            },
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        assert len(outcome.review_artifact_paths) > 0
        assert "auto-test-incident" in outcome.review_artifact_paths[0]

    def test_pass_run_ids_preserved_in_premature_failure(self) -> None:
        """Pass run IDs are preserved even in premature_terminal_no_checks failures."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["pass-001", "pass-002"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        assert outcome.pass_run_ids == ("pass-001", "pass-002")
        assert outcome.success is False
        assert outcome.mode == "premature_terminal_no_checks"
