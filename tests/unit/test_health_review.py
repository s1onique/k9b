import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Sequence
from unittest import mock

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.health.drilldown import DrilldownArtifact, DrilldownPod
from k8s_diag_agent.health.review import (
    assessment_path_for_drilldown,
    rank_drilldown_candidates,
    select_latest_run,
    DrilldownCandidate,
)
from k8s_diag_agent.llm.assessor_schema import AssessorAssessment


def _make_artifact(
    run_id: str,
    timestamp: datetime,
    label: str,
    trigger_reasons: Sequence[str] | None = None,
    pods: Sequence[DrilldownPod] | None = None,
) -> DrilldownArtifact:
    reasons = tuple(trigger_reasons or ())
    pod_tuple = tuple(pods or ())
    return DrilldownArtifact(
        run_label="health-run",
        run_id=run_id,
        timestamp=timestamp,
        snapshot_timestamp=timestamp,
        context="test",
        label=label,
        cluster_id="cluster",
        trigger_reasons=reasons,
        missing_evidence=(),
        evidence_summary={"warning_events": 0},
        affected_namespaces=(),
        affected_workloads=(),
        warning_events=(),
        non_running_pods=pod_tuple,
        pod_descriptions={},
        rollout_status=(),
        collection_timestamps={
            "warning_events": timestamp.isoformat(),
            "pods": timestamp.isoformat(),
            "rollouts": timestamp.isoformat(),
        },
    )


def _write_artifact(path: Path, artifact: DrilldownArtifact) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")


def _load_review_script_module() -> object:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "review_latest_health.py"
    module_name = "tests.review_latest_health"
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load review script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HealthReviewLogicTest(unittest.TestCase):
    def test_latest_run_discovery_prefers_newer_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            drilldowns = base / "drilldowns"
            now = datetime.now(timezone.utc)
            older = _make_artifact("run-alpha", now - timedelta(minutes=10), "alpha")
            newer = _make_artifact("run-beta", now, "beta")
            _write_artifact(drilldowns / "alpha.json", older)
            _write_artifact(drilldowns / "beta.json", newer)
            selection = select_latest_run(drilldowns)
            self.assertEqual(selection.run_id, "run-beta")
            self.assertGreater(selection.run_timestamp, older.timestamp)
            self.assertEqual(selection.candidates[0].artifact.label, "beta")

    def test_top_drilldown_ranking_prefers_severity(self) -> None:
        ts = datetime.now(timezone.utc)
        pods = lambda phase, reason: [DrilldownPod(namespace="ns", name="pod", phase=phase, reason=reason)]
        candidates = [
            DrilldownCandidate(Path("image.json"), _make_artifact("run", ts, "image", ("ImagePullBackOff",), pods("pending", "ImagePullBackOff"))),
            DrilldownCandidate(Path("crash.json"), _make_artifact("run", ts, "crash", ("CrashLoopBackOff",), pods("running", "CrashLoopBackOff"))),
            DrilldownCandidate(Path("job.json"), _make_artifact("run", ts, "job", ("job_failures",), pods("failed", "failed"))),
            DrilldownCandidate(Path("pending.json"), _make_artifact("run", ts, "pending", (), pods("pending", "pending"))),
            DrilldownCandidate(Path("warning.json"), _make_artifact("run", ts, "warning", ("warning_event_threshold",), ())),
        ]
        ranked = rank_drilldown_candidates(reversed(candidates))
        ordered = [candidate.artifact.label for candidate in ranked]
        self.assertEqual(ordered, ["image", "crash", "job", "pending", "warning"])


class HealthReviewScriptTest(unittest.TestCase):
    def test_operator_review_skips_llm_without_provider(self) -> None:
        module = _load_review_script_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            health_dir = Path(tmpdir) / "health"
            drilldown_dir = health_dir / "drilldowns"
            artifact = _make_artifact("run-1", datetime.now(timezone.utc), "ctx")
            _write_artifact(drilldown_dir / "run-1-ctx-drilldown.json", artifact)
            with mock.patch.object(module, "assess_drilldown_artifact") as assess_mock:
                with mock.patch("sys.stdout", new=io.StringIO()) as output:
                    exit_code = module.run_operator_review(
                        health_dir=health_dir,
                        run_health=False,
                        health_config=module.DEFAULT_HEALTH_CONFIG,
                        env={},
                    )
                    self.assertEqual(exit_code, 0)
            assess_mock.assert_not_called()
            text = output.getvalue()
            self.assertIn("Selected cluster: cluster", text)
            self.assertIn("LLAMA_CPP env vars not set; skipping automated assessment.", text)
            self.assertIn("Top findings: none", text)
            self.assertIn("Next low-risk checks: none", text)

    def test_operator_review_runs_llm_when_provider_configured(self) -> None:
        module = _load_review_script_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            health_dir = Path(tmpdir) / "health"
            drilldown_dir = health_dir / "drilldowns"
            artifact = _make_artifact("run-42", datetime.now(timezone.utc), "ctx")
            _write_artifact(drilldown_dir / "run-42-ctx-drilldown.json", artifact)
            assessment_data = {
                "observed_signals": [],
                "findings": [
                    {
                        "description": "node pressure",
                        "supporting_signals": [],
                        "layer": "node",
                    }
                ],
                "hypotheses": [
                    {
                        "description": "images failing to pull",
                        "confidence": "high",
                        "probable_layer": "node",
                        "what_would_falsify": "image pull succeeds",
                    }
                ],
                "next_evidence_to_collect": [
                    {
                        "description": "retry kubectl describe",
                        "owner": "ops",
                        "method": "kubectl",
                        "evidence_needed": ["kubectl describe pod foo"],
                    }
                ],
                "recommended_action": {
                    "type": "observation",
                    "description": "watch readiness",
                    "references": [],
                    "safety_level": "low-risk",
                },
                "safety_level": "low-risk",
            }
            assessment = AssessorAssessment.from_dict(assessment_data)
            env = {
                "LLAMA_CPP_BASE_URL": "https://example",
                "LLAMA_CPP_MODEL": "vicuna",
            }
            with mock.patch.object(module, "assess_drilldown_artifact", return_value=assessment) as assess_mock:
                with mock.patch("sys.stdout", new=io.StringIO()) as output:
                    exit_code = module.run_operator_review(
                        health_dir=health_dir,
                        run_health=False,
                        health_config=module.DEFAULT_HEALTH_CONFIG,
                        env=env,
                    )
                self.assertEqual(exit_code, 0)
            assess_mock.assert_called_once()
            latest = select_latest_run(drilldown_dir)
            assessment_path = module.assessment_path_for_drilldown(
                latest.candidates[0].path, health_dir / "assessments"
            )
            self.assertTrue(assessment_path.exists())
            stored = json.loads(assessment_path.read_text(encoding="utf-8"))
            self.assertEqual(stored, assessment.to_dict())
            text = output.getvalue()
            self.assertIn("LLAMA_CPP config detected", text)
            self.assertIn("Top findings:", text)
            self.assertIn("Top hypothesis:", text)
            self.assertIn("Next low-risk checks:", text)
