import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.health.adaptation import ProposalLifecycleStatus
from k8s_diag_agent.health.summary import format_health_summary, gather_health_summary


class HealthSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_dir = self.tmpdir / "runs" / "health"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, relative: str, content: object) -> None:
        path = self.health_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")

    def _write_review(self, run_id: str, warnings: int, non_running: int, score: int) -> None:
        review = {
            "run_id": run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "selected_drilldowns": [
                {
                    "context": "cluster-alpha",
                    "label": "cluster-alpha",
                    "warning_event_count": warnings,
                    "non_running_pod_count": non_running,
                }
            ],
            "quality_summary": [
                {"dimension": "signal_quality", "level": "medium", "score": score, "detail": ""}
            ],
            "failure_modes": [],
            "proposed_improvements": [],
        }
        self._write(f"reviews/{run_id}-review.json", review)

    def _write_proposal(self, run_id: str, proposal_id: str, promoted: bool) -> None:
        history = [
            {"status": ProposalLifecycleStatus.PROPOSED.value, "timestamp": "2026-01-01T00:00:00Z"}
        ]
        if promoted:
            history.append({"status": ProposalLifecycleStatus.PROMOTED.value, "timestamp": "2026-01-01T00:05:00Z"})
        self._write(
            f"proposals/{proposal_id}.json",
            {
                "proposal_id": proposal_id,
                "source_run_id": run_id,
                "source_artifact_path": f"runs/health/reviews/{run_id}-review.json",
                "target": "health.trigger_policy.warning_event_threshold",
                "proposed_change": "Raise threshold",
                "rationale": "Noise reduction",
                "confidence": "medium",
                "expected_benefit": "Fewer alerts",
                "rollback_note": "Revert if needed",
                "promotion_payload": {"threshold": 5},
                "lifecycle_history": history,
            },
        )

    def test_health_summary_reports_noise_and_triggers(self) -> None:
        # create two runs so the second is considered latest
        base_run = "health-run-20260101T000000Z"
        latest_run = "health-run-20260102T000000Z"
        self._write(
            f"assessments/{base_run}-cluster-alpha-assessment.json",
            {"findings": [{"description": "base finding"}]},
        )
        self._write(
            f"assessments/{latest_run}-cluster-alpha-assessment.json",
            {"findings": [{"description": "latest finding"}]},
        )
        self._write(
            "history.json",
            {
                "cluster-alpha": {
                    "health_rating": "degraded",
                    "warning_event_count": 3,
                    "pod_counts": {"non_running": 2},
                    "missing_evidence": ["events"],
                    "cluster_class": "prod",
                    "cluster_role": "primary",
                }
            },
        )
        self._write_review(base_run, warnings=6, non_running=4, score=40)
        self._write_review(latest_run, warnings=3, non_running=2, score=60)
        self._write_proposal(base_run, "p-noise", promoted=True)
        self._write_proposal(latest_run, "p-latest", promoted=False)
        self._write(
            f"triggers/{latest_run}-a-vs-b-trigger.json",
            {
                "primary": "cluster-alpha",
                "secondary": "cluster-beta",
                "primary_label": "cluster-alpha",
                "secondary_label": "cluster-beta",
                "trigger_reasons": ["manual"],
                "notes": "Manual run",
            },
        )
        self._write(
            f"{latest_run}-comparison-decisions.json",
            [
                {
                    "primary_label": "cluster-alpha",
                    "secondary_label": "cluster-beta",
                    "policy_eligible": True,
                    "triggered": True,
                    "comparison_intent": "suspicious drift",
                    "reason": "manual comparison",
                    "primary_class": "prod",
                    "secondary_class": "prod",
                    "primary_role": "primary",
                    "secondary_role": "primary",
                }
            ],
        )

        summary = gather_health_summary(self.health_dir)
        formatted = format_health_summary(summary)

        self.assertIn(latest_run, formatted)
        self.assertIn("cluster-alpha", formatted)
        self.assertIn("latest finding", formatted)
        self.assertIn("noise 6->3", formatted)
        self.assertIn("signal loss risk", formatted)
        self.assertIn("manual", formatted)
        self.assertIn("prod/primary", formatted)
        self.assertIn("Comparison policy decisions", formatted)
        self.assertIn("classification suspicious drift", formatted)

    def test_all_assessments_are_reported(self) -> None:
        run_id = "multicluster-20260102T000000Z"
        self._write(
            f"assessments/{run_id}-cluster-alpha-assessment.json",
            {"findings": [{"description": "alpha"}]},
        )
        self._write(
            f"assessments/{run_id}-cluster-beta-assessment.json",
            {"findings": [{"description": "beta"}]},
        )
        summary = gather_health_summary(self.health_dir, run_id=run_id)
        labels = [entry.label for entry in summary.clusters]
        self.assertCountEqual(labels, ["cluster-alpha", "cluster-beta"])

    def test_cluster_summary_records_baseline_cohort(self) -> None:
        run_id = "baseline-cohort-20260102T000000Z"
        self._write(
            f"assessments/{run_id}-cluster-alpha-assessment.json",
            {"findings": [{"description": "baseline"}]},
        )
        self._write(
            "history.json",
            {
                "cluster-alpha": {
                    "health_rating": "healthy",
                    "warning_event_count": 0,
                    "pod_counts": {"non_running": 0},
                    "missing_evidence": [],
                    "cluster_class": "prod",
                    "cluster_role": "primary",
                    "baseline_cohort": "fleet-production",
                }
            },
        )
        summary = gather_health_summary(self.health_dir, run_id=run_id)
        self.assertEqual(len(summary.clusters), 1)
        entry = summary.clusters[0]
        self.assertEqual(entry.baseline_cohort, "fleet-production")
        formatted = format_health_summary(summary)
        self.assertIn("cohort fleet-production", formatted)


class HealthSummaryEventAwareStatusTests(unittest.TestCase):
    """Tests verifying health-summary uses event-aware proposal status derivation."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_dir = self.tmpdir / "runs" / "health"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, relative: str, content: object) -> None:
        path = self.health_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")

    def _write_assessment(self, run_id: str) -> None:
        self._write(
            f"assessments/{run_id}-cluster-alpha-assessment.json",
            {"findings": [{"description": "test finding"}]},
        )

    def _write_review(self, run_id: str, warnings: int = 3, non_running: int = 1, score: int = 50) -> None:
        review = {
            "run_id": run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "selected_drilldowns": [
                {
                    "context": "cluster-alpha",
                    "label": "cluster-alpha",
                    "warning_event_count": warnings,
                    "non_running_pod_count": non_running,
                }
            ],
            "quality_summary": [
                {"dimension": "signal_quality", "level": "medium", "score": score, "detail": ""}
            ],
            "failure_modes": [],
            "proposed_improvements": [],
        }
        self._write(f"reviews/{run_id}-review.json", review)

    def _write_proposal(self, proposal_id: str, run_id: str, embedded_status: str) -> None:
        self._write(
            f"proposals/{proposal_id}.json",
            {
                "proposal_id": proposal_id,
                "source_run_id": run_id,
                "source_artifact_path": f"reviews/{run_id}-review.json",
                "target": "health.trigger_policy.warning_event_threshold",
                "proposed_change": "Raise threshold",
                "rationale": "Test proposal",
                "confidence": "medium",
                "expected_benefit": "Test",
                "rollback_note": "Revert if needed",
                "promotion_payload": {"threshold": 5},
                "lifecycle_history": [
                    {"status": embedded_status, "timestamp": "2026-01-01T00:00:00Z"}
                ],
            },
        )

    def _write_transition_event(
        self, proposal_id: str, status: str, transition: str, timestamp: str, artifact_id: str
    ) -> None:
        """Write a transition event artifact."""
        transitions_dir = self.health_dir / "proposals" / "transitions"
        transitions_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "artifact_id": artifact_id,
            "proposal_id": proposal_id,
            "status": status,
            "transition": transition,
            "created_at": timestamp,
        }
        filename = f"{proposal_id}-{transition}-{artifact_id}.json"
        (transitions_dir / filename).write_text(json.dumps(data), encoding="utf-8")

    def test_proposal_status_derived_from_transition_events(self) -> None:
        """Verify health-summary uses transition event status over embedded history."""
        run_id = "event-test-20260102T000000Z"
        self._write_assessment(run_id)
        self._write_review(run_id, warnings=5, non_running=1, score=50)

        # Create proposal with embedded 'pending' status
        proposal_id = "p-event-test"
        self._write_proposal(proposal_id, run_id, "pending")

        # Write a 'check' transition event showing 'checked' status (later timestamp)
        self._write_transition_event(
            proposal_id,
            "checked",
            "check",
            "2026-04-07T12:00:00+00:00",
            "event-uuid-001",
        )

        summary = gather_health_summary(self.health_dir, run_id=run_id)

        # Verify the proposal summary reflects the event-derived 'checked' status
        self.assertEqual(len(summary.proposals), 1)
        self.assertEqual(summary.proposals[0].proposal_id, proposal_id)
        self.assertEqual(summary.proposals[0].lifecycle_status, "checked")

    def test_proposal_status_falls_back_to_embedded_history_when_no_events(self) -> None:
        """Verify legacy proposals without events use embedded history."""
        run_id = "legacy-test-20260102T000000Z"
        self._write_assessment(run_id)
        self._write_review(run_id, warnings=3, non_running=1, score=50)

        # Create proposal with embedded 'proposed' status (no transition events)
        proposal_id = "p-legacy"
        self._write_proposal(proposal_id, run_id, "proposed")

        summary = gather_health_summary(self.health_dir, run_id=run_id)

        # Verify the proposal summary reflects embedded 'proposed' status
        self.assertEqual(len(summary.proposals), 1)
        self.assertEqual(summary.proposals[0].proposal_id, proposal_id)
        self.assertEqual(summary.proposals[0].lifecycle_status, "proposed")

    def test_promoted_reports_use_event_derived_status(self) -> None:
        """Verify promoted summary uses event-derived status, not embedded history."""
        base_run = "promoted-base-20260101T000000Z"
        after_run = "promoted-after-20260102T000000Z"

        # Setup base run assessment and review
        self._write_assessment(base_run)
        self._write_review(base_run, warnings=8, non_running=5, score=30)

        # Setup after run assessment and review
        self._write_assessment(after_run)
        self._write_review(after_run, warnings=3, non_running=1, score=70)

        # Create proposal with embedded 'proposed' status
        proposal_id = "p-promoted"
        self._write_proposal(proposal_id, base_run, "proposed")

        # Write a 'promote' transition event showing 'accepted' status
        self._write_transition_event(
            proposal_id,
            "accepted",
            "promote",
            "2026-04-07T12:00:00+00:00",
            "promote-event-001",
        )

        summary = gather_health_summary(self.health_dir, run_id=after_run)

        # Verify the proposal is included in promoted reports
        self.assertEqual(len(summary.promoted), 1)
        self.assertEqual(summary.promoted[0].proposal_id, proposal_id)
        # Verify signal improvement was captured
        self.assertIn("signal", summary.promoted[0].signal_note)

    def test_accepted_status_derives_from_latest_transition_event(self) -> None:
        """Verify that when multiple events exist, latest status wins."""
        run_id = "multi-event-20260102T000000Z"
        self._write_assessment(run_id)
        self._write_review(run_id, warnings=5, non_running=1, score=50)

        proposal_id = "p-multi-event"
        self._write_proposal(proposal_id, run_id, "pending")

        # Write earlier 'check' event showing 'checked'
        self._write_transition_event(
            proposal_id,
            "checked",
            "check",
            "2026-04-07T10:00:00+00:00",
            "check-event-001",
        )

        # Write later 'promote' event showing 'accepted'
        self._write_transition_event(
            proposal_id,
            "accepted",
            "promote",
            "2026-04-07T14:00:00+00:00",
            "promote-event-002",
        )

        summary = gather_health_summary(self.health_dir, run_id=run_id)

        # Verify latest event status ('accepted') is used
        self.assertEqual(len(summary.proposals), 1)
        self.assertEqual(summary.proposals[0].lifecycle_status, "accepted")
