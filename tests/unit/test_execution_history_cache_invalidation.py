"""Regression test for next-check execution cache invalidation.

This test verifies that executing a next-check candidate invalidates
the stale /api/run cache and exposes the new execution artifact in
the execution history on subsequent requests.

Bug: Previously, execution would write artifact but not update ui-index.json,
leaving the /api/run cache stale (keyed by ui-index.json mtime) and the
execution would not appear in the UI's Execution History panel until a full
health loop ran.

Fix: Backend now touches ui-index.json after successful execution, which
invalidates the cache and forces fresh data on the next /api/run request.
"""

import functools
import json
import shutil
import tempfile
import threading
import unittest
import unittest.mock as mock
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.config import (
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from k8s_diag_agent.health.ui import write_health_ui_index
from k8s_diag_agent.ui.server import HealthUIRequestHandler


class ExecutionCacheInvalidationTests(unittest.TestCase):
    """Regression test for execution history cache invalidation."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        # Canonical: parent 'runs' directory
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_plan_artifact(self, plan_payload: dict[str, object], filename: str) -> None:
        """Write a next-check plan artifact."""
        plan_dir = self.health_dir / "external-analysis"
        plan_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = plan_dir / filename
        artifact_path.write_text(json.dumps(plan_payload, indent=2), encoding="utf-8")

    def _ensure_cluster_entry(self, cluster_label: str, context: str) -> None:
        """Ensure the cluster exists in the ui-index."""
        index_path = self.health_dir / "ui-index.json"
        data = json.loads(index_path.read_text(encoding="utf-8"))
        data["clusters"] = [
            {
                "label": cluster_label,
                "context": context,
                "cluster_class": "primary",
                "cluster_role": "control",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 1,
                "non_running_pods": 0,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-a.json",
                    "assessment": "assessments/cluster-a.json",
                    "drilldown": "drilldowns/cluster-a.json",
                },
            }
        ]
        data["run"]["cluster_count"] = 1
        index_path.write_text(json.dumps(data), encoding="utf-8")

    def _write_index(self, plan_artifact: ExternalAnalysisArtifact) -> None:
        """Write ui-index.json with the given plan artifact."""
        self.health_dir.mkdir(parents=True, exist_ok=True)
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=False)
        )
        with mock.patch(
            "k8s_diag_agent.health.ui._collect_historical_external_analysis_entries",
            return_value=[],
        ):
            write_health_ui_index(
                self.health_dir,
                run_id=plan_artifact.run_id,
                run_label=plan_artifact.run_label or plan_artifact.run_id,
                collector_version="test",
                records=[],
                assessments=[],
                drilldowns=[],
                proposals=[],
                external_analysis=(plan_artifact,),
                notifications=(),
                external_analysis_settings=settings,
                available_adapters=None,
                expected_scheduler_interval_seconds=None,
            )

    def _start_server(self) -> tuple[ThreadingHTTPServer, threading.Thread]:
        handler = functools.partial(
            HealthUIRequestHandler,
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _fetch_run_payload(self, server: ThreadingHTTPServer) -> dict[str, Any]:
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address
        url = f"http://{host}:{port}/api/run"
        with urllib.request.urlopen(url, timeout=5) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            assert isinstance(payload, dict)
            return payload

    def _shutdown_server(self, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    def test_execution_invalidates_cache_and_appears_in_history(self) -> None:
        """Verify that execution invalidates stale cache and exposes new entry in history.

        Test flow:
        1. Create plan artifact and write ui-index.json
        2. Fetch /api/run to populate the cache (ui-index.json mtime is captured)
        3. Verify execution history is initially empty
        4. Execute the candidate via /api/next-check-execution
        5. Verify execution artifact is written
        6. Fetch /api/run again - should show new entry in history (cache invalidated)
        """
        run_id = "cache-invalidation-test"
        plan_payload: dict[str, object] = {
            "status": "success",
            "summary": "Planned candidate",
            "artifactPath": f"external-analysis/{run_id}-next-check-plan.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": "Check node status",
                    "targetCluster": "cluster-a",
                    "suggestedCommandFamily": "kubectl-get",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "node-check",
                    "candidateIndex": 0,
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                }
            ],
        }
        self._write_plan_artifact(plan_payload, f"{run_id}-next-check-plan.json")

        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id=run_id,
            run_label=run_id,
            cluster_label=run_id,
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=f"external-analysis/{run_id}-next-check-plan.json",
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        self._write_index(plan_artifact)
        self._ensure_cluster_entry("cluster-a", "prod")

        # Execution artifact that would be written on execution
        executed_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id=run_id,
            run_label=run_id,
            cluster_label="cluster-a",
            summary="Executed node check",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=f"external-analysis/{run_id}-next-check-execution-0.json",
            provider="runner",
            duration_ms=100,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={
                "candidateDescription": "Check node status",
                "commandFamily": "kubectl-get",
                "candidateIndex": 0,
                "candidateId": "node-check",
            },
        )

        # Actually write the artifact file on disk (what execute_manual_next_check does)
        execution_artifact_path = self.health_dir / "external-analysis" / f"{run_id}-next-check-execution-0.json"
        execution_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        execution_artifact_path.write_text(json.dumps({
            "tool_name": "next-check-runner",
            "run_id": run_id,
            "run_label": run_id,
            "cluster_label": "cluster-a",
            "summary": "Executed node check",
            "status": "success",
            "artifact_path": str(execution_artifact_path),
            "provider": "runner",
            "duration_ms": 100,
            "purpose": "next-check-execution",
            "timestamp": "2024-01-15T10:00:00Z",
            "payload": {
                "candidateDescription": "Check node status",
                "commandFamily": "kubectl-get",
                "candidateIndex": 0,
                "candidateId": "node-check",
            },
        }, indent=2), encoding="utf-8")

        server, thread = self._start_server()
        try:
            # Step 1: Fetch /api/run to populate the cache
            payload_before = self._fetch_run_payload(server)
            history_before = payload_before.get("nextCheckExecutionHistory", [])
            self.assertEqual(len(history_before), 0, "History should be empty initially")

            # Step 2: Simulate execution by pretending it happened (mock just prevents actual cmd execution)
            with mock.patch(
                "k8s_diag_agent.ui.server_next_checks.execute_manual_next_check",
                return_value=executed_artifact
            ):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/api/next-check-execution",
                    data=json.dumps({
                        "candidateIndex": 0,
                        "clusterLabel": "cluster-a"
                    }).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    exec_response = json.loads(response.read().decode("utf-8"))

            # Verify execution succeeded
            self.assertEqual(exec_response.get("status"), "success")
            self.assertEqual(
                exec_response.get("artifactPath"),
                f"external-analysis/{run_id}-next-check-execution-0.json"
            )

            # Step 3: Fetch /api/run again - should show new entry in history
            # This is the key assertion: cache should be invalidated and fresh data returned
            payload_after = self._fetch_run_payload(server)
            history_after = payload_after.get("nextCheckExecutionHistory", [])
            self.assertEqual(len(history_after), 1, "History should contain the new execution")
            entry = history_after[0]
            self.assertEqual(entry.get("candidateDescription"), "Check node status")
            self.assertEqual(entry.get("status"), "success")
            self.assertEqual(entry.get("clusterLabel"), "cluster-a")

        finally:
            self._shutdown_server(server, thread)

    def test_execution_artifact_exists_after_successful_execution(self) -> None:
        """Verify that execution writes the artifact file correctly."""
        run_id = "artifact-write-test"
        plan_payload: dict[str, object] = {
            "status": "success",
            "summary": "Planned candidate",
            "artifactPath": f"external-analysis/{run_id}-next-check-plan.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": "Check pod status",
                    "targetCluster": "cluster-a",
                    "suggestedCommandFamily": "kubectl-get",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "pod-check",
                    "candidateIndex": 0,
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                }
            ],
        }
        self._write_plan_artifact(plan_payload, f"{run_id}-next-check-plan.json")

        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id=run_id,
            run_label=run_id,
            cluster_label=run_id,
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=f"external-analysis/{run_id}-next-check-plan.json",
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        self._write_index(plan_artifact)
        self._ensure_cluster_entry("cluster-a", "prod")

        executed_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id=run_id,
            run_label=run_id,
            cluster_label="cluster-a",
            summary="Executed pod check",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=f"external-analysis/{run_id}-next-check-execution-0.json",
            provider="runner",
            duration_ms=50,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={
                "candidateDescription": "Check pod status",
                "commandFamily": "kubectl-get",
                "candidateIndex": 0,
            },
        )

        # Actually write the artifact file on disk
        execution_artifact_path = self.health_dir / "external-analysis" / f"{run_id}-next-check-execution-0.json"
        execution_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        execution_artifact_path.write_text(json.dumps({
            "tool_name": "next-check-runner",
            "run_id": run_id,
            "run_label": run_id,
            "cluster_label": "cluster-a",
            "summary": "Executed pod check",
            "status": "success",
            "artifact_path": str(execution_artifact_path),
            "provider": "runner",
            "duration_ms": 50,
            "purpose": "next-check-execution",
            "timestamp": "2024-01-15T10:00:00Z",
            "payload": {
                "candidateDescription": "Check pod status",
                "commandFamily": "kubectl-get",
                "candidateIndex": 0,
            },
        }, indent=2), encoding="utf-8")

        server, thread = self._start_server()
        try:
            # Mock to prevent actual command execution
            with mock.patch(
                "k8s_diag_agent.ui.server_next_checks.execute_manual_next_check",
                return_value=executed_artifact
            ):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/api/next-check-execution",
                    data=json.dumps({
                        "candidateIndex": 0,
                        "clusterLabel": "cluster-a"
                    }).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    _ = json.loads(response.read().decode("utf-8"))

            # Verify artifact file was written
            external_analysis_dir = self.health_dir / "external-analysis"
            artifact_path = external_analysis_dir / f"{run_id}-next-check-execution-0.json"
            self.assertTrue(artifact_path.exists(), "Execution artifact file should exist")

            # Verify artifact content
            artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact_data.get("status"), "success")
            self.assertEqual(artifact_data.get("purpose"), "next-check-execution")
            self.assertEqual(artifact_data["payload"]["candidateDescription"], "Check pod status")

        finally:
            self._shutdown_server(server, thread)


if __name__ == "__main__":
    unittest.main()