import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, cast
from unittest.mock import patch

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.feedback.runner import run_feedback_loop


SANITIZED_ASSESSMENT: Dict[str, Any] = {
    "observed_signals": [
        {
            "id": "signal-1",
            "description": "sanitized signal",
            "layer": "workload",
            "evidence_id": "sanitized.comparison",
            "severity": "info",
        }
    ],
    "findings": [
        {
            "description": "Sanitized finding",
            "supporting_signals": ["signal-1"],
            "layer": "workload",
        }
    ],
    "hypotheses": [
        {
            "description": "Sanitized hypothesis",
            "confidence": "medium",
            "probable_layer": "workload",
            "what_would_falsify": "Telemetry shows sanitized evidence",
        }
    ],
    "next_evidence_to_collect": [
        {
            "description": "Run sanitized next check",
            "owner": "platform-engineer",
            "method": "kubectl",
            "evidence_needed": ["sanitized evidence"],
        }
    ],
    "recommended_action": {
        "type": "observation",
        "description": "Observe sanitized diff",
        "references": ["signal-1"],
        "safety_level": "low-risk",
    },
    "safety_level": "low-risk",
    "probable_layer_of_origin": "workload",
    "overall_confidence": "medium",
}


class DummyProvider:
    def assess(self, prompt: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        del prompt, payload
        return cast(Dict[str, Any], SANITIZED_ASSESSMENT.copy())


class SanitizedReplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
        self.primary_path = self.fixture_dir / "snapshots" / "sanitized-alpha.json"
        self.diff_path = self.fixture_dir / "comparisons" / "sanitized-alpha-vs-beta.json"

    def _load_primary(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], json.loads(self.primary_path.read_text(encoding="utf-8")))

    def _load_secondary(self) -> Dict[str, Any]:
        data = self._load_primary()
        data["metadata"]["node_count"] = 4
        data["metadata"]["pod_count"] = 61
        release = data["helm_releases"][0]
        release["chart_version"] = "2.2.0"
        release["chart"] = "payments-2.2.0"
        release["app_version"] = "2.2.0"
        data["crds"] = [
            {
                "name": "widgets.example.com",
                "served_versions": ["v1"],
                "storage_version": "v1",
            }
        ]
        return data

    def _snapshot_for(self, context: str) -> ClusterSnapshot:
        if context == "alpha":
            return ClusterSnapshot.from_dict(self._load_primary())
        return ClusterSnapshot.from_dict(self._load_secondary())

    def _write_config(self, directory: Path) -> Path:
        config = {
            "run_id": "sanitized-run",
            "provider": "default",
            "collector_version": "0.1",
            "output_dir": str(directory / "runs"),
            "targets": [
                {"context": "alpha", "label": "alpha"},
                {"context": "beta", "label": "beta"},
            ],
            "pairs": [
                {"primary": "alpha", "secondary": "beta", "label": "alpha-vs-beta", "assess": True}
            ],
        }
        path = directory / "feedback.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    @patch("k8s_diag_agent.feedback.runner.get_provider", return_value=DummyProvider())
    @patch("k8s_diag_agent.feedback.runner.collect_cluster_snapshot")
    @patch("k8s_diag_agent.feedback.runner.list_kube_contexts", return_value=["alpha", "beta"])
    def test_sanitized_replay_writes_expected_artifacts(
        self, contexts_mock: Any, collect_mock: Any, provider_mock: Any
    ) -> None:
        collect_mock.side_effect = lambda ctx: self._snapshot_for(ctx)
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = self._write_config(base)
            exit_code, artifacts = run_feedback_loop(config_path, quiet=True)
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(artifacts), 1)
            output_dir = base / "runs"
            diff_file = output_dir / "comparisons" / "sanitized-run-alpha-vs-beta-diff.json"
            self.assertTrue(diff_file.exists())
            actual_diff = json.loads(diff_file.read_text(encoding="utf-8"))["differences"]
            expected_diff = json.loads(self.diff_path.read_text(encoding="utf-8"))["differences"]
            self.assertEqual(actual_diff, expected_diff)
            feedback_file = output_dir / "feedback" / "sanitized-run-alpha-vs-beta.json"
            self.assertTrue(feedback_file.exists())
            feedback = json.loads(feedback_file.read_text(encoding="utf-8"))
            self.assertEqual(feedback["run_id"], "sanitized-run")
            self.assertEqual(feedback["snapshot_pair"]["comparison_summary"], {"metadata": 2, "helm_releases": 1, "crds": 2})
            assessment_file = output_dir / "assessments" / "sanitized-run-alpha-vs-beta-assessment.json"
            self.assertTrue(assessment_file.exists())
            self.assertEqual(json.loads(assessment_file.read_text(encoding="utf-8")), SANITIZED_ASSESSMENT)
