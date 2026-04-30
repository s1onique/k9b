"""Regression tests for /api/run performance and instrumentation.

These tests verify:
1. /api/run default path does not scan all notification files
2. /api/run timing log includes request lifecycle fields
3. Cached /api/run request path is observable and fast
4. Existing /api/runs index fast-path tests still pass
"""

import functools
import json
import shutil
import tempfile
import threading
import unittest
import unittest.mock as mock
import urllib.request
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
from k8s_diag_agent.health.ui import write_health_ui_index
from k8s_diag_agent.ui.server import HealthUIRequestHandler


class RunPayloadPerformanceTests(unittest.TestCase):
    """Tests for /api/run performance characteristics."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.notifications_dir = self.health_dir / "notifications"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)
        self.notifications_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_artifact(self, run_id: str) -> ExternalAnalysisArtifact:
        return ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=run_id,
            run_label=run_id,
            cluster_label="review",
            summary="Test review",
            status=ExternalAnalysisStatus.SUCCESS,
            provider="reviewer",
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={},
        )

    def _write_index(self, artifact: ExternalAnalysisArtifact) -> None:
        self.health_dir.mkdir(parents=True, exist_ok=True)
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="reviewer")
        )
        with mock.patch(
            "k8s_diag_agent.health.ui._collect_historical_external_analysis_entries",
            return_value=[],
        ):
            write_health_ui_index(
                self.health_dir,
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
                available_adapters=(),
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

    def _shutdown_server(self, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    def _fetch_run_payload(self, server: ThreadingHTTPServer) -> dict[str, object]:
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address
        url = f"http://{host}:{port}/api/run"
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert isinstance(payload, dict)
            return cast(dict[str, object], payload)

    def test_default_run_payload_does_not_scan_all_notification_files(self) -> None:
        """Regression test: /api/run default path should NOT scan all notification files.

        Previously, /api/run was globbing all 20141 notification files just to count them
        for telemetry observability. This was wasteful for initial selected-run detail
        which loads notifications from ui-index.json instead.
        """
        run_id = "perf-test-run"
        artifact = self._build_artifact(run_id)
        self._write_index(artifact)

        # Create some notification files
        # In the old buggy code, even these few files would be scanned
        for i in range(5):
            notification_path = self.notifications_dir / f"notification-{i}.json"
            notification_path.write_text(
                json.dumps({"kind": "info", "summary": f"Notification {i}"}),
                encoding="utf-8",
            )

        server, thread = self._start_server()
        try:
            # Patch the structured logging to capture timing fields
            captured_logs: list[dict[str, object]] = []

            def capture_log(**kwargs: object) -> None:
                captured_logs.append(kwargs)

            with mock.patch(
                "k8s_diag_agent.structured_logging.emit_structured_log",
                side_effect=capture_log,
            ):
                self._fetch_run_payload(server)

            # Find the timing log entry
            timing_log = None
            for log in captured_logs:
                if cast(str, log.get("message", "")).startswith("/api/run payload built"):
                    timing_log = log
                    break

            self.assertIsNotNone(timing_log, "Should have a timing log entry")
            metadata = cast(dict[str, object], timing_log.get("metadata", {}))

            # Key assertion: notification scan strategy should be "skipped_default"
            self.assertEqual(
                metadata.get("notification_scan_strategy"),
                "skipped_default",
                "Default /api/run should skip notification file scanning",
            )

            # Key assertion: notification_files_scanned should be exactly 0
            self.assertEqual(
                metadata.get("notification_files_scanned"),
                0,
                "Default /api/run should not scan notification files",
            )

        finally:
            self._shutdown_server(server, thread)

    def test_run_payload_timing_log_includes_lifecycle_fields(self) -> None:
        """Regression test: /api/run timing log should include request lifecycle fields."""
        run_id = "timing-test-run"
        artifact = self._build_artifact(run_id)
        self._write_index(artifact)

        server, thread = self._start_server()
        try:
            captured_logs: list[dict[str, object]] = []

            def capture_log(**kwargs: object) -> None:
                captured_logs.append(kwargs)

            with mock.patch(
                "k8s_diag_agent.structured_logging.emit_structured_log",
                side_effect=capture_log,
            ):
                self._fetch_run_payload(server)

            # Find the timing log entry
            timing_log = None
            for log in captured_logs:
                if cast(str, log.get("message", "")).startswith("/api/run payload built"):
                    timing_log = log
                    break

            self.assertIsNotNone(timing_log, "Should have a timing log entry")
            metadata = cast(dict[str, object], timing_log.get("metadata", {}))

            # Required timing fields per spec
            required_fields = [
                "request_id",
                "total_duration_ms",
                "single_flight_acquire_ms",
                "ui_index_read_ms",
                "cache_lookup_ms",
                "payload_build_ms",
                "serialize_ms",
                "payload_bytes",
                "notification_scan_strategy",
                "notification_files_scanned",
                "notification_scan_ms",
                "notification_records_used",
            ]

            for field in required_fields:
                self.assertIn(
                    field,
                    metadata,
                    f"Timing log should include '{field}' field",
                )

        finally:
            self._shutdown_server(server, thread)

    def test_cached_run_payload_is_fast(self) -> None:
        """Regression test: Cached /api/run should be fast and observable."""
        run_id = "cache-perf-test"
        artifact = self._build_artifact(run_id)
        self._write_index(artifact)

        server, thread = self._start_server()
        try:
            captured_logs: list[dict[str, object]] = []

            def capture_log(**kwargs: object) -> None:
                captured_logs.append(kwargs)

            with mock.patch(
                "k8s_diag_agent.structured_logging.emit_structured_log",
                side_effect=capture_log,
            ):
                # First request - builds the payload
                self._fetch_run_payload(server)

                # Clear logs between requests
                captured_logs.clear()

                # Second request - should be cached
                self._fetch_run_payload(server)

            # Find the cache hit log entry
            cache_hit_log = None
            for log in captured_logs:
                msg = cast(str, log.get("message", ""))
                if "served from cache" in msg or "served from single-flight" in msg:
                    cache_hit_log = log
                    break

            self.assertIsNotNone(cache_hit_log, "Should have a cache hit log entry")
            metadata = cast(dict[str, object], cache_hit_log.get("metadata", {}))

            # Cache hit should be true
            self.assertTrue(
                metadata.get("cache_hit"),
                "Second request should be a cache hit",
            )

            # Total duration should be very low for cached request
            total_duration = cast(float, metadata.get("total_duration_ms", 999999))
            self.assertLess(
                total_duration,
                100,  # Cached request should complete in under 100ms
                f"Cached /api/run should be fast, got {total_duration}ms",
            )

            # Should include payload_bytes for cached response
            self.assertIn(
                "payload_bytes",
                metadata,
                "Cache hit log should include payload_bytes",
            )

        finally:
            self._shutdown_server(server, thread)


# Note: /api/runs index fast-path is comprehensively tested in test_index_super_fast_path.py


if __name__ == "__main__":
    unittest.main()
