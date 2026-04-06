import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from k8s_diag_agent.health.summary import format_health_summary, gather_health_summary
from k8s_diag_agent.health.adaptation import ProposalLifecycleStatus


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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
