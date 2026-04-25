import io
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.collect.cluster_snapshot import (
    ClusterHealthSignals,
    ClusterSnapshot,
    ClusterSnapshotMetadata,
    CollectionStatus,
    NodeConditionCounts,
    PodHealthCounts,
)
from k8s_diag_agent.compare.two_cluster import compare_snapshots
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.loop import (
    HealthLoopRunner,
    HealthRunConfig,
    HealthTarget,
    TriggerPolicy,
)
from k8s_diag_agent.llm.provider import build_assessment_input
from k8s_diag_agent.security import sanitize_log_entry, sanitize_payload, sanitize_prompt
from k8s_diag_agent.structured_logging import emit_structured_log
from scripts import run_health_scheduler


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
                captured_at=datetime.now(UTC),
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

    def test_emit_structured_log_streams_to_stdout(self) -> None:
        stream = io.StringIO()
        with patch("k8s_diag_agent.structured_logging.DEFAULT_LOG_STREAM", stream):
            emit_structured_log(
                component="stream-test",
                message="stdout check",
                run_label="test-run",
            )
        lines = [line for line in stream.getvalue().splitlines() if line]
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["component"], "stream-test")
        self.assertEqual(entry["message"], "stdout check")


class SchedulerLoggingTest(unittest.TestCase):
    def test_scheduler_logs_stream_by_default(self) -> None:
        stream = io.StringIO()
        env_key = run_health_scheduler.SCHEDULER_LOG_ENV
        with patch("k8s_diag_agent.structured_logging.DEFAULT_LOG_STREAM", stream), patch.dict(
            os.environ, {env_key: ""}
        ):
            run_health_scheduler._append_log(
                "Scheduler test",
                severity="WARNING",
                metadata={
                    "run_label": "scheduler-run",
                    "run_id": "run-123",
                    "authorization": "Bearer secret",
                },
            )
        lines = [line for line in stream.getvalue().splitlines() if line]
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["component"], "health-scheduler")
        self.assertEqual(entry["severity"], "WARNING")
        self.assertEqual(entry["run_label"], "scheduler-run")
        self.assertEqual(entry["run_id"], "run-123")
        self.assertEqual(entry.get("authorization"), "<scrubbed>")

    def test_scheduler_can_mirror_to_file_when_env_set(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp())
        log_path = tmp_dir / "scheduler.log"
        env_key = run_health_scheduler.SCHEDULER_LOG_ENV
        with patch.dict(os.environ, {env_key: str(log_path)}):
            run_health_scheduler._append_log(
                "Scheduler test",
                severity="INFO",
                metadata={
                    "run_label": "scheduler-run-2",
                    "run_id": "run-456",
                    "authorization": "Bearer secret",
                },
            )
        self.assertTrue(log_path.exists())
        entry = json.loads(log_path.read_text())
        self.assertEqual(entry["component"], "health-scheduler")
        self.assertEqual(entry["severity"], "INFO")
        self.assertEqual(entry["run_label"], "scheduler-run-2")
        self.assertEqual(entry["run_id"], "run-456")
        self.assertEqual(entry.get("authorization"), "<scrubbed>")


class SchedulerLlamaCppConfigLoggingTest(unittest.TestCase):
    """Tests that llamacpp max_tokens fields appear as ints in scheduler config logs."""

    def test_llamacpp_max_tokens_fields_not_scrubbed(self) -> None:
        stream = io.StringIO()
        env_key = run_health_scheduler.SCHEDULER_LOG_ENV
        # Set up llamacpp env vars
        test_env = {
            "LLAMA_CPP_BASE_URL": "http://localhost:8080",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TIMEOUT_SECONDS": "60",
            "LLAMA_CPP_MAX_TOKENS_AUTO_DRILLDOWN": "2048",
            "LLAMA_CPP_MAX_TOKENS_REVIEW_ENRICHMENT": "4096",
            "LLAMA_CPP_RESPONSE_FORMAT_JSON": "true",
        }
        with patch("k8s_diag_agent.structured_logging.DEFAULT_LOG_STREAM", stream), \
             patch.dict(os.environ, {**test_env, env_key: ""}):
            run_health_scheduler._append_log(
                "Scheduler llama.cpp config test",
                severity="INFO",
                metadata={
                    "run_label": "scheduler-run",
                    "run_id": "run-789",
                    "llamacpp_max_tokens_auto_drilldown": 2048,
                    "llamacpp_max_tokens_review_enrichment": 4096,
                },
            )
        lines = [line for line in stream.getvalue().splitlines() if line]
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        # Verify token-count fields are present and not scrubbed
        self.assertEqual(entry["llamacpp_max_tokens_auto_drilldown"], 2048)
        self.assertEqual(entry["llamacpp_max_tokens_review_enrichment"], 4096)
        self.assertIsInstance(entry["llamacpp_max_tokens_auto_drilldown"], int)
        self.assertIsInstance(entry["llamacpp_max_tokens_review_enrichment"], int)
        self.assertNotEqual(entry["llamacpp_max_tokens_auto_drilldown"], "<scrubbed>")
        self.assertNotEqual(entry["llamacpp_max_tokens_review_enrichment"], "<scrubbed>")

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


class TokenCountFieldSanitizationTest(unittest.TestCase):
    """Tests that safe token-count fields are not scrubbed."""

    def test_max_tokens_not_scrubbed(self) -> None:
        entry = sanitize_log_entry({"message": "ok", "max_tokens": 1024})
        self.assertEqual(entry["max_tokens"], 1024)

    def test_llamacpp_max_tokens_auto_drilldown_not_scrubbed(self) -> None:
        entry = sanitize_log_entry({"llamacpp_max_tokens_auto_drilldown": 2048})
        self.assertEqual(entry["llamacpp_max_tokens_auto_drilldown"], 2048)

    def test_llamacpp_max_tokens_review_enrichment_not_scrubbed(self) -> None:
        entry = sanitize_log_entry({"llamacpp_max_tokens_review_enrichment": 4096})
        self.assertEqual(entry["llamacpp_max_tokens_review_enrichment"], 4096)

    def test_prompt_tokens_estimate_not_scrubbed(self) -> None:
        entry = sanitize_log_entry({"prompt_tokens_estimate": 500})
        self.assertEqual(entry["prompt_tokens_estimate"], 500)

    def test_actual_prompt_tokens_estimate_not_scrubbed(self) -> None:
        entry = sanitize_log_entry({"actual_prompt_tokens_estimate": 450})
        self.assertEqual(entry["actual_prompt_tokens_estimate"], 450)

    def test_completion_tokens_not_scrubbed(self) -> None:
        entry = sanitize_log_entry({"completion_tokens": 200})
        self.assertEqual(entry["completion_tokens"], 200)

    def test_total_tokens_not_scrubbed(self) -> None:
        entry = sanitize_log_entry({"total_tokens": 700})
        self.assertEqual(entry["total_tokens"], 700)

    def test_bearer_token_is_scrubbed(self) -> None:
        entry = sanitize_log_entry({"bearer_token": "secret-value"})
        self.assertEqual(entry["bearer_token"], "<scrubbed>")

    def test_access_token_is_scrubbed(self) -> None:
        entry = sanitize_log_entry({"access_token": "secret-value"})
        self.assertEqual(entry["access_token"], "<scrubbed>")

    def test_refresh_token_is_scrubbed(self) -> None:
        entry = sanitize_log_entry({"refresh_token": "secret-value"})
        self.assertEqual(entry["refresh_token"], "<scrubbed>")

    def test_authorization_is_scrubbed(self) -> None:
        entry = sanitize_log_entry({"authorization": "Bearer secret"})
        self.assertEqual(entry["authorization"], "<scrubbed>")

    def test_api_key_is_scrubbed(self) -> None:
        entry = sanitize_log_entry({"api_key": "secret-value"})
        self.assertEqual(entry["api_key"], "<scrubbed>")

    def test_nested_dict_with_safe_token_fields_not_scrubbed(self) -> None:
        entry = sanitize_log_entry({"config": {"max_tokens": 1024, "timeout_seconds": 30}})
        self.assertEqual(entry["config"]["max_tokens"], 1024)
        self.assertEqual(entry["config"]["timeout_seconds"], 30)

    def test_nested_dict_with_credential_token_is_scrubbed(self) -> None:
        entry = sanitize_log_entry({"config": {"bearer_token": "secret", "max_tokens": 1024}})
        self.assertEqual(entry["config"]["bearer_token"], "<scrubbed>")
        self.assertEqual(entry["config"]["max_tokens"], 1024)

    def test_nested_list_with_token_fields_not_scrubbed(self) -> None:
        entry = sanitize_log_entry({"llm_stats": [{"prompt_tokens": 100}, {"completion_tokens": 50}]})
        self.assertEqual(entry["llm_stats"][0]["prompt_tokens"], 100)
        self.assertEqual(entry["llm_stats"][1]["completion_tokens"], 50)

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
