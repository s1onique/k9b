import functools
import json
import shutil
import tempfile
import threading
import urllib.request
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

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


class RunApiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs" / "health"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)

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
        host, port = server.server_address
        url = f"http://{host}:{port}/api/run"
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

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
