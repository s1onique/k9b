import functools
import json
import shutil
import tempfile
import threading
import unittest
import unittest.mock as mock
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import cast

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.config import (
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from k8s_diag_agent.external_analysis.manual_next_check import ManualNextCheckError
from k8s_diag_agent.health.notifications import (
    NotificationArtifact,
    write_notification_artifact,
)
from k8s_diag_agent.health.ui import write_health_ui_index
from k8s_diag_agent.ui.server import HealthUIRequestHandler


class RunApiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs" / "health"
        self.notifications_dir = self.runs_dir / "notifications"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)
        self.notifications_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_artifact(
        self,
        run_id: str,
        status: ExternalAnalysisStatus,
        payload: dict[str, object] | None = None,
        summary: str | None = None,
        skip_reason: str | None = None,
        error_summary: str | None = None,
    ) -> ExternalAnalysisArtifact:
        return ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=run_id,
            run_label=run_id,
            cluster_label="review",
            summary=summary,
            status=status,
            provider="reviewer",
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload=payload,
            skip_reason=skip_reason,
            error_summary=error_summary,
        )

    def _write_index(
        self,
        artifact: ExternalAnalysisArtifact,
        *,
        extra_external_analysis: tuple[ExternalAnalysisArtifact, ...] | None = None,
    ) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(
                enabled=True,
                provider=artifact.provider or "reviewer",
            )
        )
        external_analysis = (artifact, *(extra_external_analysis or ()))
        write_health_ui_index(
            self.runs_dir,
            run_id=artifact.run_id,
            run_label=artifact.run_label or artifact.run_id,
            collector_version="tests",
            records=(),
            assessments=(),
            drilldowns=(),
            proposals=(),
            external_analysis=external_analysis,
            notifications=(),
            external_analysis_settings=settings,
        )

    def _write_plan_artifact(self, payload: Mapping[str, object], name: str) -> Path:
        path = self.runs_dir / "external-analysis" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _ensure_cluster_entry(self, label: str, context: str) -> None:
        index_path = self.runs_dir / "ui-index.json"
        data = json.loads(index_path.read_text(encoding="utf-8"))
        data["clusters"] = [
            {
                "label": label,
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

    def _create_notification(
        self,
        *,
        kind: str,
        cluster_label: str,
        summary: str,
        run_id: str,
        timestamp: str,
        context: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        write_notification_artifact(
            self.notifications_dir,
            NotificationArtifact(
                kind=kind,
                summary=summary,
                details=details or {},
                run_id=run_id,
                cluster_label=cluster_label,
                context=context,
                timestamp=timestamp,
            ),
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

    def _fetch_run_payload(self, server: ThreadingHTTPServer) -> dict[str, object]:
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address
        url = f"http://{host}:{port}/api/run"
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert isinstance(payload, dict)
            return cast(dict[str, object], payload)

    def _fetch_notifications_payload(self, server: ThreadingHTTPServer, suffix: str = "") -> dict[str, object]:
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address
        url = f"http://{host}:{port}/api/notifications{suffix}"
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert isinstance(payload, dict)
            return cast(dict[str, object], payload)

    def _shutdown_server(self, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    def test_run_endpoint_exposes_successful_review_enrichment(self) -> None:
        artifact = self._build_artifact(
            run_id="run-success",
            status=ExternalAnalysisStatus.SUCCESS,
            payload={
                "triageOrder": [],
                "topConcerns": [],
                "evidenceGaps": [],
                "nextChecks": [],
                "focusNotes": [],
            },
            summary=None,
        )
        self._write_index(artifact)
        server, thread = self._start_server()
        try:
            payload = self._fetch_run_payload(server)
        finally:
            self._shutdown_server(server, thread)
        enrichment = payload.get("reviewEnrichment")
        self.assertIsNotNone(enrichment)
        assert isinstance(enrichment, dict)
        self.assertEqual(enrichment["status"], "success")
        self.assertEqual(enrichment["triageOrder"], [])
        self.assertEqual(enrichment["topConcerns"], [])
        self.assertIsNone(payload.get("reviewEnrichmentStatus"))

    def test_run_endpoint_reports_failed_review_enrichment(self) -> None:
        artifact = self._build_artifact(
            run_id="run-fail",
            status=ExternalAnalysisStatus.FAILED,
            payload={
                "topConcerns": ["latency"],
                "nextChecks": ["inspect logs"],
            },
            summary="Failed insight",
            error_summary="timeout",
        )
        self._write_index(artifact)
        server, thread = self._start_server()
        try:
            payload = self._fetch_run_payload(server)
        finally:
            self._shutdown_server(server, thread)
        enrichment = payload.get("reviewEnrichment")
        self.assertIsNotNone(enrichment)
        assert isinstance(enrichment, dict)
        self.assertEqual(enrichment["status"], "failed")
        self.assertEqual(enrichment.get("errorSummary"), "timeout")
        self.assertIsNone(payload.get("reviewEnrichmentStatus"))

    def test_run_endpoint_reports_skipped_review_enrichment(self) -> None:
        artifact = self._build_artifact(
            run_id="run-skip",
            status=ExternalAnalysisStatus.SKIPPED,
            payload={"focusNotes": ["provider missing"]},
            skip_reason="adapter unavailable",
        )
        self._write_index(artifact)
        server, thread = self._start_server()
        try:
            payload = self._fetch_run_payload(server)
        finally:
            self._shutdown_server(server, thread)
        enrichment = payload.get("reviewEnrichment")
        self.assertIsNotNone(enrichment)
        assert isinstance(enrichment, dict)
        self.assertEqual(enrichment["status"], "skipped")
        self.assertEqual(enrichment.get("skipReason"), "adapter unavailable")
        self.assertIsNone(payload.get("reviewEnrichmentStatus"))

    def test_run_endpoint_includes_execution_history(self) -> None:
        artifact = self._build_artifact(run_id="run-history", status=ExternalAnalysisStatus.SUCCESS)
        execution_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id="run-history",
            run_label="run-history",
            cluster_label="cluster-a",
            summary="Executed",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/run-history-next-check-execution-0.json",
            provider="runner",
            duration_ms=45,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={
                "candidateDescription": "Inspect control-plane logs",
                "commandFamily": "kubectl-logs",
            },
        )
        self._write_index(artifact, extra_external_analysis=(execution_artifact,))
        server, thread = self._start_server()
        try:
            payload = self._fetch_run_payload(server)
        finally:
            self._shutdown_server(server, thread)
        history = payload.get("nextCheckExecutionHistory")
        self.assertIsInstance(history, list)
        assert isinstance(history, list)
        self.assertTrue(history)
        entry = history[0]
        self.assertEqual(entry.get("candidateDescription"), "Inspect control-plane logs")
        self.assertEqual(entry.get("status"), "success")

    def test_run_endpoint_exposes_next_check_queue(self) -> None:
        run_id = "queue-run"
        plan_payload = {
            "status": "success",
            "summary": "Queue plan",
            "artifactPath": "external-analysis/queue-plan.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": "Requires approval",
                    "targetCluster": "cluster-a",
                    "requiresOperatorApproval": True,
                    "approvalState": "approval-required",
                    "executionState": "unexecuted",
                    "priorityLabel": "primary",
                }
            ],
        }
        plan_path = self._write_plan_artifact(plan_payload, "queue-plan.json")
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id=run_id,
            run_label=run_id,
            cluster_label="cluster-a",
            summary="Queue candidate",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=str(plan_path.relative_to(self.runs_dir)),
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        self._write_index(plan_artifact)
        server, thread = self._start_server()
        try:
            payload = self._fetch_run_payload(server)
        finally:
            self._shutdown_server(server, thread)
        queue = payload.get("nextCheckQueue")
        self.assertIsInstance(queue, list)
        self.assertTrue(queue)
        statuses = {entry.get("queueStatus") for entry in queue if isinstance(entry, Mapping)}
        self.assertIn("approval-needed", statuses)

    def test_notifications_endpoint_filters(self) -> None:
        artifact = self._build_artifact(run_id="filter-run", status=ExternalAnalysisStatus.SUCCESS)
        self._write_index(artifact)
        base_time = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
        self._create_notification(
            kind="warning",
            cluster_label="cluster-a",
            summary="CPU spike",
            run_id="run-alpha",
            timestamp=base_time.strftime("%Y%m%dT%H%M%S"),
            context="prod",
        )
        self._create_notification(
            kind="warning",
            cluster_label="cluster-beta",
            summary="Memory pressure",
            run_id="run-beta",
            timestamp=(base_time + timedelta(minutes=1)).strftime("%Y%m%dT%H%M%S"),
        )
        self._create_notification(
            kind="info",
            cluster_label="cluster-beta",
            summary="Health check",
            run_id="run-gamma",
            timestamp=(base_time + timedelta(minutes=2)).strftime("%Y%m%dT%H%M%S"),
        )
        server, thread = self._start_server()
        try:
            payload = self._fetch_notifications_payload(server, "?kind=warning&cluster_label=cluster-beta")
        finally:
            self._shutdown_server(server, thread)
        self.assertEqual(payload.get("total"), 1)
        notifications = payload.get("notifications")
        self.assertIsInstance(notifications, list)
        assert isinstance(notifications, list)
        notification_list = cast(list[dict[str, object]], notifications)
        self.assertEqual(len(notification_list), 1)
        entry = notification_list[0]
        self.assertEqual(entry.get("summary"), "Memory pressure")

    def test_notifications_endpoint_enforces_limit(self) -> None:
        artifact = self._build_artifact(run_id="limit-run", status=ExternalAnalysisStatus.SUCCESS)
        self._write_index(artifact)
        base_time = datetime(2026, 4, 7, 13, 0, 0, tzinfo=UTC)
        total_items = 55
        for idx in range(total_items):
            self._create_notification(
                kind="info",
                cluster_label="cluster-limit",
                summary=f"Entry {idx}",
                run_id=f"run-{idx}",
                timestamp=(base_time + timedelta(seconds=idx)).strftime("%Y%m%dT%H%M%S"),
            )
        server, thread = self._start_server()
        try:
            payload = self._fetch_notifications_payload(server)
        finally:
            self._shutdown_server(server, thread)
        notifications = payload.get("notifications")
        self.assertIsInstance(notifications, list)
        assert isinstance(notifications, list)
        notification_list = cast(list[dict[str, object]], notifications)
        self.assertEqual(len(notification_list), 50)
        self.assertEqual(payload.get("total"), total_items)

    def test_notifications_endpoint_supports_pagination_params(self) -> None:
        artifact = self._build_artifact(run_id="paging-run", status=ExternalAnalysisStatus.SUCCESS)
        self._write_index(artifact)
        base_time = datetime(2026, 4, 7, 14, 0, 0, tzinfo=UTC)
        total_items = 25
        for idx in range(total_items):
            self._create_notification(
                kind="info",
                cluster_label="cluster-page",
                summary=f"Entry {idx}",
                run_id=f"run-{idx}",
                timestamp=(base_time + timedelta(seconds=idx)).strftime("%Y%m%dT%H%M%S"),
            )
        server, thread = self._start_server()
        try:
            self._fetch_notifications_payload(server, "?limit=10&page=2")
        finally:
            self._shutdown_server(server, thread)

    def test_next_check_execution_endpoint_runs_candidate(self) -> None:
        plan_payload: dict[str, object] = {
            "status": "success",
            "summary": "Planned candidate",
            "artifactPath": "external-analysis/run-1-next-check-plan.json",
            "reviewPath": "reviews/run-1-review.json",
            "enrichmentArtifactPath": "external-analysis/review-enrichment.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": "kubectl logs deployment/alpha",
                    "targetCluster": "cluster-a",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                    "gatingReason": None,
                    "candidateId": "candidate-logs",
                    "candidateIndex": 0,
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                }
            ],
        }
        self._write_plan_artifact(plan_payload, "run-1-next-check-plan.json")
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id="run-plan",
            run_label="health-run",
            cluster_label="health-run",
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/run-1-next-check-plan.json",
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        self._write_index(plan_artifact)
        self._ensure_cluster_entry("cluster-a", "prod")
        manual_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id="run-plan",
            run_label="health-run",
            cluster_label="cluster-a",
            summary="Executed",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/run-1-next-check-execution-0.json",
            provider="runner",
            duration_ms=123,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={
                "command": ["kubectl", "logs"],
                "candidateIndex": 0,
            },
        )
        with mock.patch(
            "k8s_diag_agent.ui.server.execute_manual_next_check", return_value=manual_artifact
        ) as mock_execute:
            server, thread = self._start_server()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/api/next-check-execution",
                    data=json.dumps({"candidateIndex": 0, "clusterLabel": "cluster-a"}).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(payload.get("status"), "success")
                self.assertEqual(
                    payload.get("artifactPath"), "external-analysis/run-1-next-check-execution-0.json"
                )
                self.assertEqual(payload.get("command"), ["kubectl", "logs"])
                mock_execute.assert_called_once()
            finally:
                self._shutdown_server(server, thread)

    def test_next_check_approval_endpoint_records_approval(self) -> None:
        plan_payload: dict[str, object] = {
            "status": "success",
            "candidateCount": 1,
            "artifactPath": "external-analysis/approval-plan.json",
            "reviewPath": "reviews/approval-run-review.json",
            "enrichmentArtifactPath": "external-analysis/approval-review.json",
            "candidates": [
                {
                    "description": "Inspect the control plane",
                    "targetCluster": "cluster-a",
                    "requiresOperatorApproval": True,
                    "safeToAutomate": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "candidate-control-plane",
                    "candidateIndex": 0,
                    "normalizationReason": "selection_default",
                    "safetyReason": "unknown_command",
                    "approvalReason": "unknown_command",
                    "duplicateReason": None,
                    "blockingReason": "unknown_command",
                }
            ],
        }
        self._write_plan_artifact(plan_payload, "approval-plan.json")
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id="approval-run",
            run_label="health-run",
            cluster_label="health-run",
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/approval-plan.json",
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        self._write_index(plan_artifact)
        self._ensure_cluster_entry("cluster-a", "prod")
        server, thread = self._start_server()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/api/next-check-approval",
                data=json.dumps({"candidateIndex": 0, "clusterLabel": "cluster-a"}).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload.get("status"), "success")
            self.assertEqual(payload.get("candidateIndex"), 0)
            self.assertIsNotNone(payload.get("artifactPath"))
            self.assertIsNotNone(payload.get("approvalTimestamp"))
        finally:
            self._shutdown_server(server, thread)

    def test_next_check_approval_endpoint_rejects_nonapproval_candidate(self) -> None:
        plan_payload: dict[str, object] = {
            "candidates": [
                {
                    "description": "kubectl get pods",
                    "targetCluster": "cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "candidate-get",
                    "candidateIndex": 0,
                }
            ],
        }
        self._write_plan_artifact(plan_payload, "approval-plan.json")
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id="approval-run",
            run_label="health-run",
            cluster_label="health-run",
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/approval-plan.json",
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        self._write_index(plan_artifact)
        self._ensure_cluster_entry("cluster-a", "prod")
        server, thread = self._start_server()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/api/next-check-approval",
                data=json.dumps({"candidateIndex": 0, "clusterLabel": "cluster-a"}).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(cm.exception.code, 400)
            body = cm.exception.read().decode("utf-8")
            data = json.loads(body)
            self.assertIsNone(data.get("blockingReason"))
        finally:
            self._shutdown_server(server, thread)

    def test_next_check_execution_endpoint_rejects_approval_needed(self) -> None:
        plan_payload: dict[str, object] = {
            "status": "success",
            "candidates": [
                {
                    "description": "kubectl logs deployment/alpha",
                    "targetCluster": "cluster-a",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": True,
                    "duplicateOfExistingEvidence": False,
                    "gatingReason": None,
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": "known_command",
                    "duplicateReason": None,
                    "blockingReason": "requires_approval",
                }
            ],
        }
        self._write_plan_artifact(plan_payload, "run-approval-plan.json")
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id="run-plan",
            run_label="health-run",
            cluster_label="health-run",
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/run-approval-plan.json",
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload={
                "candidates": plan_payload["candidates"],
            },
        )
        self._write_index(plan_artifact)
        self._ensure_cluster_entry("cluster-a", "prod")
        with mock.patch(
            "k8s_diag_agent.ui.server.execute_manual_next_check",
            side_effect=ManualNextCheckError("approval required"),
        ):
            server, thread = self._start_server()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/api/next-check-execution",
                    data=json.dumps({"candidateIndex": 0, "clusterLabel": "cluster-a"}).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(req, timeout=5)
                self.assertEqual(cm.exception.code, 400)
            finally:
                self._shutdown_server(server, thread)

    def test_next_check_approval_endpoint_accepts_candidate_id(self) -> None:
        plan_payload: dict[str, object] = {
            "status": "success",
            "candidateCount": 1,
            "artifactPath": "external-analysis/approval-plan-id.json",
            "reviewPath": "reviews/approval-run-review.json",
            "enrichmentArtifactPath": "external-analysis/approval-review.json",
            "candidates": [
                {
                    "description": "Inspect kube-controller manager",
                    "targetCluster": "cluster-a",
                    "requiresOperatorApproval": True,
                    "safeToAutomate": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "candidate-approve",
                    "candidateIndex": 3,
                    "normalizationReason": "selection_default",
                    "safetyReason": "unknown_command",
                    "approvalReason": "unknown_command",
                    "duplicateReason": None,
                    "blockingReason": "unknown_command",
                }
            ],
        }
        self._write_plan_artifact(plan_payload, "approval-plan-id.json")
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id="approval-run",
            run_label="health-run",
            cluster_label="health-run",
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/approval-plan-id.json",
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        self._write_index(plan_artifact)
        self._ensure_cluster_entry("cluster-a", "prod")
        server, thread = self._start_server()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/api/next-check-approval",
                data=json.dumps({"candidateId": "candidate-approve", "clusterLabel": "cluster-a"}).encode(
                    "utf-8"
                ),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload.get("status"), "success")
            self.assertEqual(payload.get("candidateIndex"), 3)
            self.assertIsNotNone(payload.get("artifactPath"))
            self.assertIsNotNone(payload.get("approvalTimestamp"))
        finally:
            self._shutdown_server(server, thread)

    def test_next_check_execution_endpoint_accepts_candidate_id(self) -> None:
        plan_payload: dict[str, object] = {
            "status": "success",
            "summary": "Candidate with stable ID",
            "artifactPath": "external-analysis/run-plan-id.json",
            "reviewPath": "reviews/run-id-review.json",
            "enrichmentArtifactPath": "external-analysis/review-id.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": "kubectl logs deployment/beta",
                    "targetCluster": "cluster-a",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                    "gatingReason": None,
                    "candidateId": "candidate-id-5",
                    "candidateIndex": 5,
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                }
            ],
        }
        self._write_plan_artifact(plan_payload, "run-plan-id.json")
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id="run-plan",
            run_label="health-run",
            cluster_label="health-run",
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/run-plan-id.json",
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        self._write_index(plan_artifact)
        self._ensure_cluster_entry("cluster-a", "prod")
        manual_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id="run-plan",
            run_label="health-run",
            cluster_label="cluster-a",
            summary="Executed",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/run-plan-id-next-check-execution-5.json",
            provider="runner",
            duration_ms=123,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={
                "command": ["kubectl", "logs"],
                "candidateIndex": 5,
            },
        )
        with mock.patch(
            "k8s_diag_agent.ui.server.execute_manual_next_check",
            return_value=manual_artifact,
        ) as mock_execute:
            server, thread = self._start_server()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/api/next-check-execution",
                    data=json.dumps({"candidateId": "candidate-id-5", "clusterLabel": "cluster-a"}).encode(
                        "utf-8"
                    ),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(payload.get("status"), "success")
                self.assertEqual(
                    payload.get("artifactPath"), "external-analysis/run-plan-id-next-check-execution-5.json"
                )
                self.assertEqual(payload.get("command"), ["kubectl", "logs"])
                mock_execute.assert_called_once()
                kwargs = mock_execute.call_args[1]
                self.assertEqual(kwargs.get("candidate_index"), 5)
            finally:
                self._shutdown_server(server, thread)
