"""Regression tests for alertmanager_sources in historical run context loading.

This test verifies that GET /api/run?run_id=<run> returns non-null
alertmanagerSources when ui-index.json contains alertmanager_sources for
the requested run.

Bug: _load_context_for_run() was not loading alertmanager_sources artifacts,
causing build_run_payload() to serialize alertmanagerSources: null for
historical runs loaded via ?run_id= query parameter.
"""

import functools
import json
import shutil
import tempfile
import threading
import unittest
from datetime import UTC, datetime
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


class AlertmanagerSourcesHistoricalRunTests(unittest.TestCase):
    """Regression tests for alertmanager_sources in requested-run context loading."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_artifact(
        self,
        run_id: str,
        status: ExternalAnalysisStatus,
        purpose: ExternalAnalysisPurpose = ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
        timestamp: datetime | None = None,
    ) -> ExternalAnalysisArtifact:
        return ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=run_id,
            run_label=run_id,
            cluster_label="review",
            summary=f"Test artifact for {run_id}",
            status=status,
            provider="reviewer",
            purpose=purpose,
            timestamp=datetime.now(UTC) if timestamp is None else timestamp,
        )

    def _write_alertmanager_sources_artifact(
        self,
        run_id: str,
        sources: list[dict[str, list[str] | str | None]],
    ) -> Path:
        """Write a run-scoped alertmanager-sources artifact."""
        external_dir = self.health_dir / "external-analysis"
        external_dir.mkdir(parents=True, exist_ok=True)

        artifact = {
            "sources": sources,
            "total_count": len(sources),
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "test-cluster",
        }
        path = external_dir / f"{run_id}-alertmanager-sources.json"
        path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        return path

    def _write_alertmanager_compact_artifact(
        self,
        run_id: str,
    ) -> Path:
        """Write a run-scoped alertmanager-compact artifact."""
        external_dir = self.health_dir / "external-analysis"
        external_dir.mkdir(parents=True, exist_ok=True)

        artifact = {
            "status": "healthy",
            "alert_count": 5,
            "severity_counts": {"critical": 1, "warning": 4},
            "state_counts": {"firing": 3, "pending": 2},
            "top_alert_names": ["PodNotReady", "HighCPUUsage"],
            "affected_namespaces": ["monitoring", "default"],
            "affected_clusters": ["test-cluster"],
            "affected_services": ["api-service"],
            "truncated": False,
            "captured_at": datetime.now(UTC).isoformat(),
        }
        path = external_dir / f"{run_id}-alertmanager-compact.json"
        path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        return path

    def _write_index(
        self,
        artifact: ExternalAnalysisArtifact,
        *,
        alertmanager_sources: dict[str, object] | None = None,
        alertmanager_compact: dict[str, object] | None = None,
    ) -> None:
        """Write health UI index, optionally with alertmanager data."""
        self.health_dir.mkdir(parents=True, exist_ok=True)
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(
                enabled=True,
                provider=artifact.provider or "reviewer",
            )
        )
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
        )
        # Post-process: inject alertmanager data into ui-index.json if provided
        if alertmanager_sources is not None or alertmanager_compact is not None:
            index_path = self.health_dir / "ui-index.json"
            if index_path.exists():
                index_data = json.loads(index_path.read_text(encoding="utf-8"))
                run_entry = index_data.get("run") or {}
                if alertmanager_compact is not None:
                    run_entry["alertmanager_compact"] = alertmanager_compact
                if alertmanager_sources is not None:
                    run_entry["alertmanager_sources"] = alertmanager_sources
                index_data["run"] = run_entry
                index_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")

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

    def _fetch_run_payload(
        self,
        server: ThreadingHTTPServer,
        run_id: str | None = None,
    ) -> dict[str, object]:
        """Fetch run payload, optionally with run_id query parameter."""
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address

        if run_id:
            url = f"http://{host}:{port}/api/run?run_id={run_id}"
        else:
            url = f"http://{host}:{port}/api/run"

        import urllib.request
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert isinstance(payload, dict)
            return cast(dict[str, object], payload)

    def test_requested_run_includes_alertmanager_sources_from_artifact(self) -> None:
        """Regression test: GET /api/run?run_id=<run> returns non-null alertmanagerSources.

        This verifies the fix for the bug where _load_context_for_run() did not
        load alertmanager_sources artifacts, causing alertmanagerSources: null
        in the API response for historical runs requested via ?run_id= query.
        """
        run_id = "historical-am-test"

        # Prepare alertmanager sources data for injection
        sources = [
            {
                "source_id": "am-src-historical-1",
                "endpoint": "http://alertmanager-historical:9093",
                "namespace": "monitoring",
                "name": "historical-alertmanager",
                "origin": "manual",
                "state": "manual",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["direct_user_registration"],
            },
            {
                "source_id": "am-src-historical-2",
                "endpoint": "http://alertmanager-crd:9093",
                "namespace": "monitoring",
                "name": "crd-alertmanager",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:30Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.26.0",
                "confidence_hints": ["crd_discovery", "namespace_match"],
            },
        ]
        alertmanager_sources_entry = {
            "sources": sources,
            "total_count": len(sources),
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "test-cluster",
        }
        alertmanager_compact_entry = {
            "status": "healthy",
            "alert_count": 5,
            "severity_counts": {"critical": 1, "warning": 4},
            "state_counts": {"firing": 3, "pending": 2},
            "top_alert_names": ["PodNotReady", "HighCPUUsage"],
            "affected_namespaces": ["monitoring", "default"],
            "affected_clusters": ["test-cluster"],
            "affected_services": ["api-service"],
            "truncated": False,
            "captured_at": datetime.now(UTC).isoformat(),
        }

        # Create the run's review artifact and write index with alertmanager data
        artifact = self._build_artifact(
            run_id=run_id,
            status=ExternalAnalysisStatus.SUCCESS,
            timestamp=datetime.now(UTC),
        )
        self._write_index(
            artifact,
            alertmanager_sources=alertmanager_sources_entry,
            alertmanager_compact=alertmanager_compact_entry,
        )

        # Also write run-scoped artifact files (for _load_context_for_run to find)
        self._write_alertmanager_sources_artifact(run_id, sources)
        self._write_alertmanager_compact_artifact(run_id)

        # Start the server
        server, thread = self._start_server()
        try:
            # Request the specific run via query parameter
            payload = self._fetch_run_payload(server, run_id=run_id)

            # Key assertion: alertmanagerSources must NOT be null
            alertmanager_sources = payload.get("alertmanagerSources")
            self.assertIsNotNone(
                alertmanager_sources,
                "alertmanagerSources should not be null when artifact exists"
            )

            # Verify the sources data is populated
            if alertmanager_sources is not None:
                self.assertIsInstance(alertmanager_sources, dict)
                sources_list = alertmanager_sources.get("sources")
                self.assertIsNotNone(sources_list, "sources should not be null")
                self.assertEqual(len(sources_list), 2, "Should have 2 sources")

                # Verify source IDs match what we wrote
                source_ids = {s.get("source_id") for s in sources_list}
                self.assertIn("am-src-historical-1", source_ids)
                self.assertIn("am-src-historical-2", source_ids)

        finally:
            self._shutdown_server(server, thread)

    def test_latest_run_includes_alertmanager_sources(self) -> None:
        """Baseline test: GET /api/run (no run_id) still includes alertmanagerSources.

        This ensures the fix doesn't break the existing behavior for latest run.
        """
        run_id = "latest-am-test"

        # Prepare alertmanager data
        sources = [
            {
                "source_id": "am-src-latest-1",
                "endpoint": "http://alertmanager-latest:9093",
                "namespace": "monitoring",
                "name": "latest-alertmanager",
                "origin": "manual",
                "state": "manual",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["direct_user_registration"],
            },
        ]
        alertmanager_sources_entry = {
            "sources": sources,
            "total_count": len(sources),
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "test-cluster",
        }
        alertmanager_compact_entry = {
            "status": "healthy",
            "alert_count": 5,
            "severity_counts": {"critical": 1, "warning": 4},
            "state_counts": {"firing": 3, "pending": 2},
            "top_alert_names": ["PodNotReady", "HighCPUUsage"],
            "affected_namespaces": ["monitoring", "default"],
            "affected_clusters": ["test-cluster"],
            "affected_services": ["api-service"],
            "truncated": False,
            "captured_at": datetime.now(UTC).isoformat(),
        }

        # Create the run's review artifact and write index with alertmanager data
        artifact = self._build_artifact(
            run_id=run_id,
            status=ExternalAnalysisStatus.SUCCESS,
            timestamp=datetime.now(UTC),
        )
        self._write_index(
            artifact,
            alertmanager_sources=alertmanager_sources_entry,
            alertmanager_compact=alertmanager_compact_entry,
        )

        # Also write run-scoped artifact files (for consistency)
        self._write_alertmanager_sources_artifact(run_id, sources)
        self._write_alertmanager_compact_artifact(run_id)

        # Start the server
        server, thread = self._start_server()
        try:
            # Request latest run (no run_id parameter)
            payload = self._fetch_run_payload(server)

            # Key assertion: alertmanagerSources should not be null
            alertmanager_sources = payload.get("alertmanagerSources")
            self.assertIsNotNone(
                alertmanager_sources,
                "Latest run should include alertmanagerSources"
            )

        finally:
            self._shutdown_server(server, thread)

    def test_requested_run_without_alertmanager_sources_returns_null(self) -> None:
        """Test that requested run without alertmanager sources artifact returns null.

        This verifies graceful handling when the artifact doesn't exist.
        """
        run_id = "no-am-artifact-run"

        # Create the run's review artifact
        artifact = self._build_artifact(
            run_id=run_id,
            status=ExternalAnalysisStatus.SUCCESS,
            timestamp=datetime.now(UTC),
        )
        self._write_index(artifact)

        # DO NOT write alertmanager_sources artifact - simulating a run without it

        # Start the server
        server, thread = self._start_server()
        try:
            # Request the specific run via query parameter
            payload = self._fetch_run_payload(server, run_id=run_id)

            # alertmanagerSources should be null when artifact doesn't exist
            alertmanager_sources = payload.get("alertmanagerSources")
            # This is acceptable behavior - null when no artifact
            self.assertIn(
                alertmanager_sources,
                (None, {}),  # Either None or empty dict is acceptable
                "alertmanagerSources should be null or empty when artifact doesn't exist"
            )

        finally:
            self._shutdown_server(server, thread)


if __name__ == "__main__":
    unittest.main()