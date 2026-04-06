import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.health.loop import (
    HealthLoopRunner,
    HealthRunConfig,
    HealthTarget,
    TriggerPolicy,
)
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.collect.cluster_snapshot import (
    ClusterSnapshot,
    ClusterSnapshotMetadata,
    CollectionStatus,
    ClusterHealthSignals,
    NodeConditionCounts,
    PodHealthCounts,
)
from k8s_diag_agent.security import sanitize_log_entry, sanitize_payload, sanitize_prompt
from scripts import run_health_scheduler
from k8s_diag_agent.compare.two_cluster import compare_snapshots
from k8s_diag_agent.llm.provider import build_assessment_input


class LoggingWorkflowTest(unittest.TestCase):
    def test_health_loop_writes_structured_events(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp())
        baseline = BaselinePolicy.load_from_file(Path("runs/health-baseline.example.json"))
        target = HealthTarget(
            context="test-context",
            label="test-context",
            monitor_health=False,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        config = HealthRunConfig(
            run_label="test-run",
            output_dir=tmp_dir,
            collector_version="test",
            targets=(target,),
            peers=(),
            trigger_policy=TriggerPolicy(False, False, False, False, False, False, 0),
            manual_pairs=(),
            baseline_policy=baseline,
        )
        def collector(context: str) -> ClusterSnapshot:
            metadata = ClusterSnapshotMetadata(
                cluster_id=context,
                captured_at=datetime.now(timezone.utc),
                control_plane_version="v1.26.0",
                node_count=1,
            )
            return ClusterSnapshot(
                metadata=metadata,
                collection_status=CollectionStatus(),
                health_signals=ClusterHealthSignals(
                    NodeConditionCounts.empty(),
                    PodHealthCounts.empty(),
                    0,
                    (),
                ),
            )
        runner = HealthLoopRunner(
            config,
            ("test-context",),
            manual_overrides=(),
            manual_drilldown_contexts=(),
            snapshot_collector=collector,
            quiet=True,
        )
        runner.execute()
        log_path = tmp_dir / "health" / "health.log"
        self.assertTrue(log_path.exists(), "Expected health log to be created")
        entries = [json.loads(line) for line in log_path.read_text().splitlines()]
        components = {entry["component"] for entry in entries}
        self.assertIn("health-loop", components)


class SchedulerLoggingTest(unittest.TestCase):
    def test_scheduler_uses_structured_schema(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp())
        log_path = tmp_dir / "scheduler.log"
        with patch.object(run_health_scheduler, "DEFAULT_LOG", log_path):
            run_health_scheduler._append_log(
                "Scheduler test",
                severity="WARNING",
                metadata={
                    "run_label": "scheduler-run",
                    "run_id": "run-123",
                    "authorization": "Bearer secret",
                },
            )
        self.assertTrue(log_path.exists())
        entry = json.loads(log_path.read_text())
        self.assertEqual(entry["component"], "health-scheduler")
        self.assertEqual(entry["severity"], "WARNING")
        self.assertEqual(entry["run_label"], "scheduler-run")
        self.assertEqual(entry["run_id"], "run-123")
        self.assertEqual(entry.get("authorization"), "<scrubbed>")


class SanitizerTest(unittest.TestCase):
    def test_prompt_redacts_sensitive_lines(self) -> None:
        prompt = "Authorization: Bearer secret-token\nkind: Secret\napi_key=secret"
        sanitized = sanitize_prompt(prompt)
        self.assertNotIn("Bearer secret-token", sanitized)
        self.assertNotIn("Authorization", sanitized)
        self.assertIn("<scrubbed secret manifest>", sanitized)

    def test_payload_redacts_secret_manifest(self) -> None:
        payload = {
            "kind": "Secret",
            "metadata": {"name": "foo"},
            "data": {"token": "abc"},
        }
        sanitized = sanitize_payload(payload)
        self.assertEqual(sanitized["kind"], "Secret")
        self.assertEqual(sanitized["redacted"], "secret manifest")
        self.assertEqual(sanitized["metadata"]["name"], "foo")

    def test_log_entry_scrubs_sensitive_keys(self) -> None:
        entry = sanitize_log_entry({"message": "ok", "authorization": "Bearer xyz"})
        self.assertEqual(entry["authorization"], "<scrubbed>")

    def test_token_like_log_lines_are_sanitized(self) -> None:
        log_line = "Received token=abc123 from webhook"
        sanitized = sanitize_payload(log_line)
        self.assertNotIn("abc123", sanitized)
        self.assertIn("<scrubbed>", sanitized)


class ProviderPayloadSanitizationTest(unittest.TestCase):
    def test_build_assessment_input_redacts_sensitive_labels(self) -> None:
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "snapshots" / "sanitized-alpha.json"
        raw_snapshot = json.loads(fixture_path.read_text(encoding="utf-8"))
        labels = raw_snapshot.setdefault("metadata", {}).setdefault("labels", {})
        labels["api_token"] = "Bearer secret-value"
        primary = ClusterSnapshot.from_dict(raw_snapshot)
        secondary = ClusterSnapshot.from_dict(raw_snapshot)
        comparison = compare_snapshots(primary, secondary)
        payload = build_assessment_input(primary, secondary, comparison)
        self.assertEqual(payload.primary_snapshot["metadata"]["labels"]["api_token"], "<scrubbed>")
        self.assertEqual(payload.secondary_snapshot["metadata"]["labels"]["api_token"], "<scrubbed>")
