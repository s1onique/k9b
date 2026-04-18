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
import urllib.request
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
        self.tmpdir = Path(tempfile.mkdtemp()).resolve()  # Resolve to canonical path
        self.runs_dir = (self.tmpdir / "runs").resolve()
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


class AlertmanagerSourceActionURLEncodingTests(unittest.TestCase):
    """Regression tests for URL-encoded source_id in promote/disable actions.

    Bug: When UI sends source_id with `:` and `/` characters (e.g., 
    `crd:monitoring/kube-prometheus-stack-alertmanager`), the path parameter
    is URL-encoded (e.g., `crd%3Amonitoring%2Fkube-prometheus-stack-alertmanager`).
    The backend was not decoding this before lookup, causing "Source not found" errors.

    Expected fix: decode the route path parameter with urllib.parse.unquote()
    before source lookup, validation, and persistence.
    """

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp()).resolve()
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

    def _write_index_with_sources(
        self,
        run_id: str,
        sources: list[dict[str, object]],
    ) -> None:
        """Write health UI index with alertmanager sources containing special chars."""
        self.health_dir.mkdir(parents=True, exist_ok=True)

        # Create all required subdirectories to avoid errors during context loading
        (self.health_dir / "reviews").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "assessments").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "proposals").mkdir(parents=True, exist_ok=True)
        external_dir = self.health_dir / "external-analysis"
        external_dir.mkdir(parents=True, exist_ok=True)

        # Write a minimal review artifact to satisfy _load_context_for_run
        review_data = {
            "run_id": run_id,
            "run_label": run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "collector_version": "tests",
            "selected_drilldowns": [],  # Empty to avoid needing drilldown artifacts
            "clusters": [],
            "assessments": [],
            "health_rating": "healthy",
            "warnings": 0,
            "external_analysis_settings": {
                "review_enrichment": {"enabled": True, "provider": "reviewer"}
            },
        }
        review_path = self.health_dir / "reviews" / f"{run_id}-review.json"
        review_path.write_text(json.dumps(review_data, indent=2), encoding="utf-8")

        # Write sources artifact - must be at health_root level for _load_context_for_run
        sources_artifact = {
            "sources": sources,
            "total_count": len(sources),
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "test-cluster",
        }
        # Handler looks for sources at self._health_root / f"{run_id}-alertmanager-sources.json"
        # which is self.runs_dir / "health" / f"{run_id}-alertmanager-sources.json"
        sources_path = self.health_dir / f"{run_id}-alertmanager-sources.json"
        sources_path.write_text(json.dumps(sources_artifact, indent=2), encoding="utf-8")

        # Also write compact artifact at health_root level
        compact_artifact = {
            "status": "healthy",
            "alert_count": 5,
            "severity_counts": {"critical": 1, "warning": 4},
            "state_counts": {"firing": 3, "pending": 2},
            "top_alert_names": ["PodNotReady", "HighCPUUsage"],
            "affected_namespaces": ["monitoring"],
            "affected_clusters": ["test-cluster"],
            "affected_services": ["api-service"],
            "truncated": False,
            "captured_at": datetime.now(UTC).isoformat(),
        }
        compact_path = self.health_dir / f"{run_id}-alertmanager-compact.json"
        compact_path.write_text(json.dumps(compact_artifact, indent=2), encoding="utf-8")

        # Create the run's review artifact (using same ExternalAnalysisArtifact for consistency)
        artifact = self._build_artifact(
            run_id=run_id,
            status=ExternalAnalysisStatus.SUCCESS,
            timestamp=datetime.now(UTC),
        )
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
        # Post-process: inject alertmanager data into ui-index.json
        index_path = self.health_dir / "ui-index.json"
        if index_path.exists():
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
            run_entry = index_data.get("run") or {}
            run_entry["alertmanager_sources"] = sources_artifact
            run_entry["alertmanager_compact"] = compact_artifact
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

    def _post_source_action(
        self,
        server: ThreadingHTTPServer,
        run_id: str,
        source_id: str,
        action: str,
    ) -> dict[str, object]:
        """POST to the source action endpoint and return parsed JSON response."""
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address

        # The source_id is URL-encoded when placed in the path
        from urllib.parse import quote
        encoded_source_id = quote(source_id, safe="")
        url = f"http://{host}:{port}/api/runs/{run_id}/alertmanager-sources/{encoded_source_id}/action"

        payload = json.dumps({
            "action": action,
            "clusterLabel": "test-cluster",
            "reason": "test-regression",
        }).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return cast(dict[str, object], json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            # Read error response body for debugging
            error_body = exc.read().decode("utf-8") if exc.fp else ""
            raise AssertionError(
                f"HTTP {exc.code}: {exc.reason}. Error body: {error_body}"
            ) from exc

    def test_promote_source_with_colon_and_slash_in_id_succeeds(self) -> None:
        """Regression test: promoting source with `:` and `/` in source_id succeeds.

        The source_id 'crd:monitoring/kube-prometheus-stack-alertmanager' is URL-encoded
        to 'crd%3Amonitoring%2Fkube-prometheus-stack-alertmanager' in the path.
        The backend must decode this before source lookup.
        """
        run_id = "url-encoding-test-promote"
        source_id = "crd:monitoring/kube-prometheus-stack-alertmanager"

        sources: list[dict[str, object]] = [
            {
                "source_id": source_id,
                "endpoint": "http://alertmanager.monitoring.svc:9093",
                "namespace": "monitoring",
                "name": "kube-prometheus-stack-alertmanager",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",  # Can be promoted
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["crd_discovery"],
            },
        ]
        self._write_index_with_sources(run_id, sources)

        server, thread = self._start_server()
        try:
            response = self._post_source_action(server, run_id, source_id, "promote")

            # Key assertion: success status, not "Source not found"
            self.assertEqual(response.get("status"), "success", f"Promote should succeed: {response}")
            self.assertNotIn("Source not found", str(response.get("error", "")), 
                             "Source should be found after URL-decoding")

            # Verify the override was written with the correct decoded source_id
            external_dir = self.health_dir / "external-analysis"
            overrides_path = external_dir / f"{run_id}-alertmanager-source-overrides.json"
            self.assertTrue(overrides_path.exists(), "Override artifact should be written")

            overrides_data = json.loads(overrides_path.read_text(encoding="utf-8"))
            self.assertIn("overrides", overrides_data, "Override file should have 'overrides' key")
            
            # Find our override by source_id
            our_override: dict[str, object] | None = None
            for override in overrides_data.get("overrides", []):
                if override is not None and (cast(dict[str, object], override).get("source_id") or "") == source_id:
                    our_override = override
                    break
            
            self.assertIsNotNone(our_override, f"Override with source_id '{source_id}' should exist")
            self.assertEqual(cast(dict[str, object], our_override).get("action"), "promote", "Action should be 'promote'")

        finally:
            self._shutdown_server(server, thread)

    def test_disable_source_with_colon_and_slash_in_id_succeeds(self) -> None:
        """Regression test: disabling source with `:` and `/` in source_id succeeds.

        The source_id 'crd:monitoring/kube-prometheus-stack-alertmanager' is URL-encoded
        to 'crd%3Amonitoring%2Fkube-prometheus-stack-alertmanager' in the path.
        The backend must decode this before source lookup.
        """
        run_id = "url-encoding-test-disable"
        source_id = "crd:monitoring/kube-prometheus-stack-alertmanager"

        sources: list[dict[str, object]] = [
            {
                "source_id": source_id,
                "endpoint": "http://alertmanager.monitoring.svc:9093",
                "namespace": "monitoring",
                "name": "kube-prometheus-stack-alertmanager",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",  # Can be disabled
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["crd_discovery"],
            },
        ]
        self._write_index_with_sources(run_id, sources)

        server, thread = self._start_server()
        try:
            response = self._post_source_action(server, run_id, source_id, "disable")

            # Key assertion: success status, not "Source not found"
            self.assertEqual(response.get("status"), "success", f"Disable should succeed: {response}")
            self.assertNotIn("Source not found", str(response.get("error", "")), 
                             "Source should be found after URL-decoding")

            # Verify the override was written with the correct decoded source_id
            external_dir = self.health_dir / "external-analysis"
            overrides_path = external_dir / f"{run_id}-alertmanager-source-overrides.json"
            self.assertTrue(overrides_path.exists(), "Override artifact should be written")

            overrides_data = json.loads(overrides_path.read_text(encoding="utf-8"))
            
            # Find our override by source_id
            our_override: dict[str, object] | None = None
            for override in overrides_data.get("overrides", []):
                if override is not None and (cast(dict[str, object], override).get("source_id") or "") == source_id:
                    our_override = override
                    break
            
            self.assertIsNotNone(our_override, f"Override with source_id '{source_id}' should exist")
            self.assertEqual(cast(dict[str, object], our_override).get("action"), "disable", "Action should be 'disable'")

        finally:
            self._shutdown_server(server, thread)

    def test_encoded_path_parameter_is_decoded_before_lookup(self) -> None:
        """Test that URL decoding works for encoded source_id and non-encoded source_id.

        Uses two separate run_ids to avoid state conflicts. Uses promote action
        since it works reliably with auto-tracked sources.
        """
        # Test 1: Source with special characters (URL-encoded)
        run_id_special = "url-encoding-test-special"
        source_id_special = "crd:monitoring/kube-prometheus-stack-alertmanager"
        sources_special: list[dict[str, object]] = [
            {
                "source_id": source_id_special,
                "endpoint": "http://alertmanager.monitoring.svc:9093",
                "namespace": "monitoring",
                "name": "kube-prometheus-stack-alertmanager",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["crd_discovery"],
            },
        ]
        self._write_index_with_sources(run_id_special, sources_special)

        # Test 2: Source with no special characters (baseline)
        run_id_simple = "url-encoding-test-simple"
        source_id_simple = "simple-source-id"
        sources_simple: list[dict[str, object]] = [
            {
                "source_id": source_id_simple,
                "endpoint": "http://simple-alertmanager:9093",
                "namespace": "default",
                "name": "simple-alertmanager",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["direct_user_registration"],
            },
        ]
        self._write_index_with_sources(run_id_simple, sources_simple)

        server1, thread1 = self._start_server()
        try:
            # Test 1: Source with special characters (promote)
            response_special = self._post_source_action(server1, run_id_special, source_id_special, "promote")
            self.assertEqual(response_special.get("status"), "success",
                            f"Source with special chars should be found: {response_special}")
        finally:
            self._shutdown_server(server1, thread1)

        server2, thread2 = self._start_server()
        try:
            # Test 2: Source with no special characters (promote)
            response_simple = self._post_source_action(server2, run_id_simple, source_id_simple, "promote")
            self.assertEqual(response_simple.get("status"), "success",
                            f"Source with no special chars should be found: {response_simple}")
        finally:
            self._shutdown_server(server2, thread2)


if __name__ == "__main__":
    unittest.main()
