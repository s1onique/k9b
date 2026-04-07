import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from k8s_diag_agent.health.adaptation import HealthProposal
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.loop import (
    DrilldownArtifact,
    HealthAssessmentArtifact,
    HealthRating,
    HealthSnapshotRecord,
    HealthTarget,
)
from k8s_diag_agent.health.notifications import NotificationArtifact
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
        external_path = self.tmpdir / "runs" / "health" / "external-analysis" / "analysis.json"
        external_path.parent.mkdir(parents=True, exist_ok=True)
        external_artifact = ExternalAnalysisArtifact(
            tool_name="k8sgpt",
            run_id="health-run-1",
            cluster_label=target.label,
            source_artifact="assessments/cluster-alpha.json",
            summary="analysis complete",
            findings=("finding1",),
            suggested_next_checks=("check1",),
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=str(external_path),
            provider="k8sgpt",
            duration_ms=150,
        )
        notification = NotificationArtifact(
            kind="degraded-health",
            summary="threshold exceeded",
            details={"missing": ["event"]},
            run_id="health-run-1",
            cluster_label=target.label,
            context=target.context,
        )
        output_dir = self.tmpdir / "runs" / "health"
        notification_path = output_dir / "notifications" / "20260101-degraded-health.json"
        notification_path.parent.mkdir(parents=True, exist_ok=True)
        notification_record = (notification, notification_path)
        history_entries = [
            {
                "tool_name": "k8sgpt",
                "status": "success",
                "timestamp": "2025-12-31T23:58:00Z",
                "duration_ms": 150,
            },
            {
                "tool_name": "llm-autodrilldown",
                "status": "success",
                "timestamp": "2025-12-31T23:57:00Z",
                "duration_ms": 180,
            },
            {
                "tool_name": "k8sgpt",
                "status": "failed",
                "timestamp": "2025-12-31T23:56:00Z",
                "duration_ms": 220,
            },
        ]
        history_dir = output_dir / "external-analysis"
        history_dir.mkdir(parents=True, exist_ok=True)
        for idx, entry in enumerate(history_entries, start=1):
            path = history_dir / f"history-{idx}.json"
            path.write_text(json.dumps(entry), encoding="utf-8")
        result_path = write_health_ui_index(
            output_dir,
            run_id="health-run-1",
            run_label="health-run",
            collector_version="1.0",
            records=[record],
            assessments=[artifact],
            drilldowns=[drilldown],
            proposals=[proposal],
            external_analysis=[external_artifact],
            notifications=[notification_record],
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
        self.assertIn("artifact_paths", cluster_entry)
        self.assertIn("fleet_status", data)
        self.assertIn("proposal_status_summary", data)
        self.assertIn("artifact_path", data["latest_drilldown"])
        self.assertIn("artifact_path", data["proposals"][0])
        self.assertIn("drilldown_availability", data)
        self.assertEqual(data["drilldown_availability"]["available"], 1)
        self.assertIn("notification_history", data)
        self.assertEqual(data["notification_history"][0]["kind"], "degraded-health")
        self.assertIn("external_analysis", data)
        self.assertEqual(data["external_analysis"]["count"], 1)
        self.assertEqual(data["run"]["notification_count"], 1)
        self.assertIn("latest_assessment", data)
        self.assertEqual(data["latest_assessment"]["cluster_label"], "cluster-alpha")
        self.assertIn("artifact_path", data["latest_assessment"])
        llm_stats = data["run"].get("llm_stats")
        self.assertIsNotNone(llm_stats)
        self.assertEqual(llm_stats["totalCalls"], 1)
        self.assertEqual(llm_stats["successfulCalls"], 1)
        self.assertEqual(llm_stats["failedCalls"], 0)
        self.assertEqual(llm_stats["p50LatencyMs"], 150)
        self.assertEqual(llm_stats["providerBreakdown"][0]["provider"], "k8sgpt")
        self.assertEqual(llm_stats["scope"], "current_run")
        historical_stats = data["run"].get("historical_llm_stats")
        self.assertIsNotNone(historical_stats)
        self.assertEqual(historical_stats["totalCalls"], 3)
        self.assertEqual(historical_stats["successfulCalls"], 2)
        self.assertEqual(historical_stats["failedCalls"], 1)
        self.assertEqual(historical_stats["lastCallTimestamp"], "2025-12-31T23:58:00Z")
        self.assertEqual(historical_stats["p50LatencyMs"], 180)
        self.assertEqual(historical_stats["p95LatencyMs"], 220)
        self.assertEqual(historical_stats["p99LatencyMs"], 220)
        self.assertEqual(historical_stats["scope"], "retained_history")
        self.assertEqual(historical_stats["providerBreakdown"][0]["provider"], "k8sgpt")
        self.assertEqual(historical_stats["providerBreakdown"][1]["provider"], "llm-autodrilldown")

    def test_historical_llm_stats_handles_missing_durations(self) -> None:
        output_dir = self.tmpdir / "runs" / "health"
        history_dir = output_dir / "external-analysis"
        history_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "tool_name": "k8sgpt",
            "status": "success",
            "timestamp": "2025-12-31T23:50:00Z",
        }
        (history_dir / "missing-duration.json").write_text(json.dumps(entry), encoding="utf-8")
        result_path = write_health_ui_index(
            output_dir,
            run_id="health-run-missing",
            run_label="health-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[],
            notifications=[],
        )
        data = json.loads(result_path.read_text(encoding="utf-8"))
        historical_stats = data["run"].get("historical_llm_stats")
        self.assertIsNotNone(historical_stats)
        self.assertEqual(historical_stats["totalCalls"], 1)
        self.assertEqual(historical_stats["successfulCalls"], 1)
        self.assertEqual(historical_stats["failedCalls"], 0)
        self.assertEqual(historical_stats["lastCallTimestamp"], "2025-12-31T23:50:00Z")
        self.assertIsNone(historical_stats["p50LatencyMs"])
        self.assertIsNone(historical_stats["p95LatencyMs"])
        self.assertIsNone(historical_stats["p99LatencyMs"])
        self.assertEqual(historical_stats["scope"], "retained_history")

    def test_run_stats_include_durations_from_reviews(self) -> None:
        output_dir = self.tmpdir / "runs" / "health"
        reviews_dir = output_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        durations = [8, 11, 15, 18, 30]
        for idx, seconds in enumerate(durations, start=1):
            run_id = f"health-run-20260101T00000{idx}Z"
            start = datetime.strptime(run_id[-16:], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            finish = start + timedelta(seconds=seconds)
            review_path = reviews_dir / f"{run_id}-review.json"
            review_path.write_text(
                json.dumps({"run_id": run_id, "timestamp": finish.isoformat()}),
                encoding="utf-8",
            )
        target = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
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
            baseline_policy_path="baseline.json",
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
        result_path = write_health_ui_index(
            output_dir,
            run_id="health-run-1",
            run_label="health-run",
            collector_version="1.0",
            records=[record],
            assessments=[artifact],
            drilldowns=[],
            proposals=[],
            external_analysis=[],
            notifications=[],
        )
        data = json.loads(result_path.read_text(encoding="utf-8"))
        stats = data.get("run_stats")
        self.assertIsInstance(stats, dict)
        self.assertEqual(stats.get("total_runs"), len(durations))
        self.assertEqual(stats.get("last_run_duration_seconds"), durations[-1])
        self.assertEqual(stats.get("p50_run_duration_seconds"), 15)
        self.assertEqual(stats.get("p95_run_duration_seconds"), 30)
        self.assertEqual(stats.get("p99_run_duration_seconds"), 30)
