import json
import shutil
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.health.adaptation import HealthProposal
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.loop import (
    DrilldownArtifact,
    HealthAssessmentArtifact,
    HealthRating,
    HealthSnapshotRecord,
    HealthTarget,
)
from k8s_diag_agent.health.ui import write_health_ui_index
from k8s_diag_agent.models import ConfidenceLevel


class HealthUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ui_index_contains_expected_keys(self) -> None:
        target = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="prod",
            cluster_role="primary",
            baseline_cohort="fleet",
        )
        snapshot = ClusterSnapshot.from_dict(
            {
                "metadata": {
                    "cluster_id": "cluster-alpha",
                    "captured_at": "2026-01-01T00:00:00Z",
                    "control_plane_version": "v1.26.0",
                    "node_count": 2,
                },
                "health_signals": {
                    "node_conditions": {"ready": 2},
                    "pod_counts": {"non_running": 0},
                    "warning_events": (),
                    "job_failures": 0,
                },
            }
        )
        record = HealthSnapshotRecord(
            target=target,
            snapshot=snapshot,
            path=self.tmpdir / "snapshot.json",
            baseline_policy=BaselinePolicy.empty(),
            baseline_policy_path="health-baseline.json",
        )
        artifact = HealthAssessmentArtifact(
            run_label="health-run",
            run_id="health-run-1",
            timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id="cluster-alpha",
            snapshot_path=str(record.path),
            assessment={"observed_signals": [], "findings": []},
            missing_evidence=(),
            health_rating=HealthRating.HEALTHY,
        )
        drilldown = DrilldownArtifact(
            run_label="health-run",
            run_id="health-run-1",
            timestamp=snapshot.metadata.captured_at,
            snapshot_timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id="cluster-alpha",
            trigger_reasons=("warning_event_threshold",),
            missing_evidence=(),
            evidence_summary={"foo": "bar"},
            affected_namespaces=("default",),
            affected_workloads=(),
            warning_events=(),
            non_running_pods=(),
            pod_descriptions={},
            rollout_status=(),
            collection_timestamps={"warning_events": "2026-01-01T00:00:00Z"},
        )
        proposal = HealthProposal(
            proposal_id="p1",
            source_run_id="health-run-1",
            source_artifact_path="runs/health/review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold",
            rationale="test",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="test",
            rollback_note="test",
        )
        output_dir = self.tmpdir / "runs" / "health"
        result_path = write_health_ui_index(
            output_dir,
            run_id="health-run-1",
            run_label="health-run",
            collector_version="1.0",
            records=[record],
            assessments=[artifact],
            drilldowns=[drilldown],
            proposals=[proposal],
        )
        self.assertTrue(result_path.exists())
        data = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertIn("run", data)
        self.assertIn("clusters", data)
        self.assertIn("drilldowns", data)
        self.assertIn("latest_drilldown", data)
        self.assertIn("proposals", data)
        self.assertEqual(len(data["clusters"]), 1)
        self.assertEqual(len(data["drilldowns"]), 1)
        self.assertEqual(len(data["proposals"]), 1)
        cluster_entry = data["clusters"][0]
        self.assertIn("cluster_class", cluster_entry)
        self.assertIn("cluster_role", cluster_entry)
