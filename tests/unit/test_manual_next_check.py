import json
import shutil
import subprocess
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisStatus
from k8s_diag_agent.external_analysis.manual_next_check import (
    _OUTPUT_LIMIT,
    ManualNextCheckError,
    execute_manual_next_check,
)


class ManualNextCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _base_candidate(self) -> dict[str, object]:
        return {
            "description": "kubectl get pods -n default",
            "targetCluster": "cluster-a",
            "suggestedCommandFamily": "kubectl-get",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "duplicateOfExistingEvidence": False,
            "gatingReason": None,
            "candidateId": "",
        }

    def _runner(self, returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["kubectl"], returncode, stdout=stdout, stderr=stderr)

    def test_executes_safe_candidate_and_persists_artifact(self) -> None:
        candidate = self._base_candidate()
        artifact = execute_manual_next_check(
            runs_dir=self.runs_dir,
            run_id="run-1",
            run_label="run-1",
            plan_artifact_path=Path("external-analysis/plan.json"),
            candidate_index=0,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda command: self._runner(0, stdout="ok"),
        )
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SUCCESS)
        artifact_path = self.runs_dir / "external-analysis" / "run-1-next-check-execution-0.json"
        self.assertTrue(artifact_path.exists())
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "success")
        payload = data["payload"]
        self.assertEqual(payload["candidateIndex"], 0)
        self.assertEqual(payload["targetContext"], "prod")
        self.assertEqual(payload["command"][-2:], ["--context", "prod"])

    def test_records_failed_execution_and_exposes_error_summary(self) -> None:
        candidate = self._base_candidate()
        artifact = execute_manual_next_check(
            runs_dir=self.runs_dir,
            run_id="run-2",
            run_label="run-2",
            plan_artifact_path=Path("external-analysis/plan.json"),
            candidate_index=1,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda command: self._runner(1, stderr="permission denied"),
        )
        self.assertEqual(artifact.status, ExternalAnalysisStatus.FAILED)
        data = json.loads(
            (self.runs_dir / "external-analysis" / "run-2-next-check-execution-1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["error_summary"], "permission denied")

    def test_rejects_candidate_requiring_approval(self) -> None:
        candidate = self._base_candidate()
        candidate["requiresOperatorApproval"] = True
        with self.assertRaises(ManualNextCheckError):
            execute_manual_next_check(
                runs_dir=self.runs_dir,
                run_id="run-3",
                run_label="run-3",
                plan_artifact_path=Path("external-analysis/plan.json"),
                candidate_index=2,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
                command_runner=lambda command: self._runner(0),
            )

    def test_allows_candidate_with_recorded_approval(self) -> None:
        candidate = self._base_candidate()
        candidate["requiresOperatorApproval"] = True
        candidate["approvalStatus"] = "approved"
        artifact = execute_manual_next_check(
            runs_dir=self.runs_dir,
            run_id="run-approval",
            run_label="run-approval",
            plan_artifact_path=Path("external-analysis/plan.json"),
            candidate_index=2,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda command: self._runner(0),
        )
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SUCCESS)

    def test_rejects_duplicate_candidate(self) -> None:
        candidate = self._base_candidate()
        candidate["duplicateOfExistingEvidence"] = True
        with self.assertRaises(ManualNextCheckError):
            execute_manual_next_check(
                runs_dir=self.runs_dir,
                run_id="run-4",
                run_label="run-4",
                plan_artifact_path=Path("external-analysis/plan.json"),
                candidate_index=3,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
                command_runner=lambda command: self._runner(0),
            )

    def test_rejects_unsupported_family(self) -> None:
        candidate = self._base_candidate()
        candidate["suggestedCommandFamily"] = "kubectl-apply"
        with self.assertRaises(ManualNextCheckError):
            execute_manual_next_check(
                runs_dir=self.runs_dir,
                run_id="run-5",
                run_label="run-5",
                plan_artifact_path=Path("external-analysis/plan.json"),
                candidate_index=4,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
                command_runner=lambda command: self._runner(0),
            )

    def test_timeout_records_timed_out_metadata(self) -> None:
        candidate = self._base_candidate()
        def timeout_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(
                cmd="kubectl",
                timeout=1,
                output="stdout",
                stderr="stderr",
            )

        artifact = execute_manual_next_check(
            runs_dir=self.runs_dir,
            run_id="run-timeout",
            run_label="run-timeout",
            plan_artifact_path=Path("external-analysis/plan.json"),
            candidate_index=5,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=timeout_runner,
        )
        self.assertEqual(artifact.status, ExternalAnalysisStatus.FAILED)
        self.assertTrue(artifact.timed_out)
        self.assertEqual(artifact.error_summary, "Command timed out.")
        self.assertFalse(artifact.stdout_truncated)
        self.assertFalse(artifact.stderr_truncated)

    def test_truncates_long_output(self) -> None:
        candidate = self._base_candidate()
        long_stdout = "x" * (_OUTPUT_LIMIT + 10)
        artifact = execute_manual_next_check(
            runs_dir=self.runs_dir,
            run_id="run-truncate",
            run_label="run-truncate",
            plan_artifact_path=Path("external-analysis/plan.json"),
            candidate_index=6,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda command: self._runner(0, stdout=long_stdout, stderr="ok"),
        )
        self.assertTrue(artifact.stdout_truncated)
        self.assertFalse(artifact.stderr_truncated)
        expected_stdout_bytes = (_OUTPUT_LIMIT - 1) + len("…".encode())
        self.assertEqual(artifact.output_bytes_captured, expected_stdout_bytes + len("ok"))
        self.assertIn("…", artifact.raw_output or "")
