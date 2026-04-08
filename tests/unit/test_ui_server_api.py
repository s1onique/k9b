import functools
import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
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

    def _write_index(self, artifact: ExternalAnalysisArtifact) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(
                enabled=True,
                provider=artifact.provider or "reviewer",
            )
        )
        write_health_ui_index(
            self.runs_dir,
            run_id=artifact.run_id,
            run_label=artifact.run_label or artifact.run_id,
            collector_version="tests",
            records=(),
            assessments=(),
            drilldowns=(),
            proposals=(),
            external_analysis=(artifact,),
            notifications=(),
            external_analysis_settings=settings,
        )

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
            payload = self._fetch_notifications_payload(server, "?limit=10&page=2")
        finally:
            self._shutdown_server(server, thread)
        self.assertEqual(payload.get("total"), total_items)
        self.assertEqual(payload.get("limit"), 10)
        self.assertEqual(payload.get("page"), 2)
        self.assertEqual(payload.get("total_pages"), 3)
        notifications = payload.get("notifications")
        self.assertIsInstance(notifications, list)
        assert isinstance(notifications, list)
        notification_list = cast(list[dict[str, object]], notifications)
        self.assertEqual(len(notification_list), 10)
        self.assertEqual(notification_list[0].get("summary"), "Entry 14")
        self.assertEqual(notification_list[-1].get("summary"), "Entry 5")
