import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.feedback.runner import run_feedback_loop

FIXTURE_SNAPSHOT = Path(__file__).resolve().parents[1] / "fixtures" / "snapshots" / "sanitized-alpha.json"


def _load_fixture_snapshot() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURE_SNAPSHOT.read_text(encoding="utf-8")))


class FeedbackRunnerTest(unittest.TestCase):
    def _write_config(self, directory: Path, run_id: str, pairs: list[dict[str, Any]]) -> Path:
        config = {
            "run_id": run_id,
            "provider": "default",
            "collector_version": "0.1",
            "output_dir": str(directory / "runs"),
            "targets": [
                {"context": "alpha", "label": "alpha"},
                {"context": "beta", "label": "beta"},
            ],
            "pairs": pairs,
        }
        config_path = directory / "feedback.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return config_path

    def _snapshot_for(self, context: str) -> ClusterSnapshot:
        data = _load_fixture_snapshot()
        if context == "beta":
            metadata = cast(dict[str, Any], data["metadata"])
            metadata["node_count"] += 1
            status = cast(dict[str, Any], data["status"])
            missing = cast(list[str], status["missing_evidence"])
            missing.append("events")
        return ClusterSnapshot.from_dict(data)

    @patch("k8s_diag_agent.feedback.runner.list_kube_contexts", return_value=["alpha", "beta"])
    @patch("k8s_diag_agent.feedback.runner.collect_cluster_snapshot")
    def test_run_feedback_writes_artifact(
        self, collect_mock: Any, contexts_mock: Any
    ) -> None:
        collect_mock.side_effect = lambda ctx: self._snapshot_for(ctx)
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = self._write_config(base, "test-run", [
                {"primary": "alpha", "secondary": "beta", "label": "alpha-vs-beta", "assess": True}
            ])
            exit_code, artifacts = run_feedback_loop(config_path, quiet=True)
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(artifacts), 1)
            artifact = artifacts[0]
            self.assertEqual(artifact.context_name, "alpha-vs-beta")
            self.assertEqual(artifact.snapshot_pair.primary_snapshot_id, "sanitized-alpha")
            self.assertGreaterEqual(len(artifact.validation_results), 3)

    @patch("k8s_diag_agent.feedback.runner.list_kube_contexts", return_value=["alpha", "beta"])
    @patch("k8s_diag_agent.feedback.runner.collect_cluster_snapshot")
    def test_missing_evidence_triggers_validation(
        self, collect_mock: Any, contexts_mock: Any
    ) -> None:
        def collect(context: str) -> ClusterSnapshot:
            data = _load_fixture_snapshot()
            if context == "alpha":
                status = cast(dict[str, Any], data["status"])
                missing = cast(list[str], status["missing_evidence"])
                missing.append("logs")
            return ClusterSnapshot.from_dict(data)

        collect_mock.side_effect = collect
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = self._write_config(base, "test-missing", [
                {"primary": "alpha", "secondary": "beta", "label": "miss-evidence", "assess": True}
            ])
            exit_code, artifacts = run_feedback_loop(config_path, quiet=True)
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(artifacts), 1)
            artifact = artifacts[0]
            self.assertIn("logs", artifact.missing_evidence)
            missing_check = next(
                (result for result in artifact.validation_results if result.name == "missing-evidence-check"),
                None,
            )
            assert missing_check is not None
            self.assertFalse(missing_check.passed)

    @patch("k8s_diag_agent.feedback.runner.list_kube_contexts", return_value=["alpha", "beta"])
    @patch("k8s_diag_agent.feedback.runner.collect_cluster_snapshot")
    def test_llm_failure_is_recorded(
        self, collect_mock: Any, contexts_mock: Any
    ) -> None:
        collect_mock.side_effect = lambda ctx: self._snapshot_for(ctx)

        class BrokenProvider:
            def assess(self, prompt: str, payload: dict[str, object]) -> dict[str, object]:
                raise RuntimeError("provider down")

        with patch(
            "k8s_diag_agent.feedback.runner.get_provider", return_value=BrokenProvider()
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                base = Path(tmpdir)
                config_path = self._write_config(base, "test-broken", [
                    {"primary": "alpha", "secondary": "beta", "label": "broken", "assess": True}
                ])
                exit_code, artifacts = run_feedback_loop(config_path, quiet=True)
                self.assertEqual(exit_code, 0)
                artifact = artifacts[0]
                self.assertIsNone(artifact.assessment)
            llm_check = next(
                (result for result in artifact.validation_results if result.name == "llm-assessment"),
                None,
            )
            assert llm_check is not None
            self.assertFalse(llm_check.passed)

    @patch("k8s_diag_agent.feedback.runner.list_kube_contexts", return_value=["alpha", "beta"])
    @patch("k8s_diag_agent.feedback.runner.collect_cluster_snapshot")
    def test_optional_assessment_path(
        self, collect_mock: Any, contexts_mock: Any
    ) -> None:
        collect_mock.side_effect = lambda ctx: self._snapshot_for(ctx)
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = self._write_config(base, "test-no-assess", [
                {"primary": "alpha", "secondary": "beta", "label": "no-assess", "assess": False}
            ])
            exit_code, artifacts = run_feedback_loop(config_path, quiet=True)
            self.assertEqual(exit_code, 0)
            artifact = artifacts[0]
            self.assertIsNone(artifact.assessment)
            self.assertEqual(artifact.validation_results, [])

    @patch("k8s_diag_agent.feedback.runner.list_kube_contexts", return_value=["alpha", "beta"])
    @patch("k8s_diag_agent.feedback.runner.collect_cluster_snapshot")
    def test_pair_metadata_survives_artifact(self, collect_mock: Any, contexts_mock: Any) -> None:
        collect_mock.side_effect = lambda ctx: self._snapshot_for(ctx)
        pair_metadata = {
            "primary": "alpha",
            "secondary": "beta",
            "label": "intent-aware",
            "intent": "prod-vs-prod",
            "expected_drift_categories": ["helm_releases"],
            "unexpected_drift_categories": ["metadata"],
            "notes": "Both clusters share the same role.",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = self._write_config(base, "test-metadata", [pair_metadata])
            exit_code, artifacts = run_feedback_loop(config_path, quiet=True)
            self.assertEqual(exit_code, 0)
            artifact = artifacts[0]
            self.assertEqual(artifact.comparison_intent, "prod-vs-prod")
            self.assertEqual(artifact.comparison_notes, "Both clusters share the same role.")
            self.assertEqual(artifact.expected_drift_categories, ("helm_releases",))
            self.assertEqual(artifact.unexpected_drift_categories, ("metadata",))
