"""Regression tests for vmalert_sources in historical run context loading.

This test verifies that GET /api/run?run_id=<run> returns non-null
vmalertSources when the vmalert-sources artifact exists for the requested run.

Bug: _load_context_for_run() was not loading vmalert_sources artifacts,
causing vmalertSources: null for historical runs loaded via ?run_id= query parameter.
"""

from __future__ import annotations

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


class VmalertSourcesHistoricalRunTests(unittest.TestCase):
    """Regression tests for vmalert_sources in requested-run context loading."""

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

    def _write_vmalert_sources_artifact(
        self,
        run_id: str,
        sources: list[dict[str, object]],
    ) -> Path:
        """Write a run-scoped vmalert-sources artifact in VmalertSourceInventory format."""
        from datetime import datetime

        from k8s_diag_agent.external_analysis.vmalert_discovery import (
            VmalertSource,
            VmalertSourceInventory,
            VmalertSourceMode,
            VmalertSourceOrigin,
            VmalertSourceState,
        )
        
        self.health_dir.mkdir(parents=True, exist_ok=True)

        # Convert raw dicts to VmalertSource objects
        vmalert_sources: list[VmalertSource] = []
        for src in sources:
            # Parse datetime fields if provided as ISO strings
            discovered_at = src.get("discovered_at")
            if isinstance(discovered_at, str):
                from k8s_diag_agent.datetime_utils import parse_iso_to_utc
                discovered_at = parse_iso_to_utc(discovered_at)
            
            verified_at = src.get("verified_at")
            if isinstance(verified_at, str):
                from k8s_diag_agent.datetime_utils import parse_iso_to_utc
                verified_at = parse_iso_to_utc(verified_at)
            
            last_check = src.get("last_check")
            if isinstance(last_check, str):
                from k8s_diag_agent.datetime_utils import parse_iso_to_utc
                last_check = parse_iso_to_utc(last_check)
            
            vmalert_sources.append(VmalertSource(
                source_id=str(src.get("source_id", "")),
                endpoint=str(src.get("endpoint", "")),
                namespace=src.get("namespace"),
                name=src.get("name"),
                origin=VmalertSourceOrigin(src.get("origin", "service-heuristic")),
                state=VmalertSourceState(src.get("state", "discovered")),
                discovered_at=discovered_at or datetime.now(UTC),
                verified_at=verified_at,
                last_check=last_check,
                last_error=src.get("last_error"),
                verified_version=src.get("verified_version"),
                confidence_hints=tuple(src.get("confidence_hints", [])),
                cluster_label=src.get("cluster_label"),
                cluster_context="test-cluster",
                manual_source_mode=VmalertSourceMode.NOT_MANUAL,
            ))

        # Build inventory with proper format
        inventory = VmalertSourceInventory(
            sources={s.source_id: s for s in vmalert_sources},
            discovered_at=datetime.now(UTC),
            cluster_context="test-cluster",
        )

        path = self.health_dir / f"{run_id}-vmalert-sources.json"
        path.write_text(json.dumps(inventory.to_dict(), indent=2), encoding="utf-8")
        return path

    def _write_index(
        self,
        artifact: ExternalAnalysisArtifact,
        *,
        vmalert_sources: dict[str, object] | None = None,
    ) -> None:
        """Write health UI index, optionally with vmalert data.
        
        Note: vmalert_sources are read from the artifact file (vmalert-sources.json)
        by _load_context_for_run, not from ui-index.json directly. This parameter
        is kept for API compatibility but is not injected into the index.
        
        IMPORTANT: This also writes the review artifact to health/reviews/ because
        _load_context_for_run() looks for the review artifact to determine if a
        historical run exists.
        """
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
        
        # Write review artifact to health/reviews/ so _load_context_for_run() can find it
        # _load_context_for_run() checks for this file to determine if a historical run exists
        reviews_dir = self.health_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_data = {
            "run_id": artifact.run_id,
            "run_label": artifact.run_label or artifact.run_id,
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
        review_path = reviews_dir / f"{artifact.run_id}-review.json"
        review_path.write_text(json.dumps(review_data, indent=2), encoding="utf-8")

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

    def test_requested_run_includes_vmalert_sources_from_artifact(self) -> None:
        """Regression test: GET /api/run?run_id=<run> returns non-null vmalertSources.

        This verifies that _load_context_for_run() loads vmalert_sources artifacts,
        causing vmalertSources to be populated in the API response for historical
        runs requested via ?run_id= query.
        """
        run_id = "historical-vmalert-test"

        # Prepare vmalert sources data for injection
        sources = [
            {
                "source_id": "vmalert-src-historical-1",
                "endpoint": "http://vmalert-historical:8880",
                "namespace": "victoria-metrics",
                "name": "vmalert-main",
                "origin": "vmalert-crd",
                "state": "auto-tracked",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "1.100.0",
                "confidence_hints": ["crd_discovery"],
                "cluster_label": "test-cluster",
            },
            {
                "source_id": "vmalert-src-historical-2",
                "endpoint": "http://vmalert-service:8880",
                "namespace": "monitoring",
                "name": "vmalert-secondary",
                "origin": "service-heuristic",
                "state": "discovered",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": None,
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": None,
                "confidence_hints": ["service_match"],
                "cluster_label": "test-cluster",
            },
        ]
        vmalert_sources_entry = {
            "sources": sources,
            "total_count": len(sources),
            "source_count": len(sources),
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "test-cluster",
        }

        # Create the run's review artifact and write index with vmalert data
        artifact = self._build_artifact(
            run_id=run_id,
            status=ExternalAnalysisStatus.SUCCESS,
            timestamp=datetime.now(UTC),
        )
        self._write_index(artifact, vmalert_sources=vmalert_sources_entry)

        # Also write run-scoped artifact files (for _load_context_for_run to find)
        self._write_vmalert_sources_artifact(run_id, sources)

        # Start the server
        server, thread = self._start_server()
        try:
            # Request the specific run via query parameter
            payload = self._fetch_run_payload(server, run_id=run_id)

            # Key assertion: vmalertSources must NOT be null
            vmalert_sources = payload.get("vmalertSources")
            self.assertIsNotNone(
                vmalert_sources,
                "vmalertSources should not be null when artifact exists"
            )

            # Verify the sources data is populated
            if vmalert_sources is not None:
                self.assertIsInstance(vmalert_sources, dict)
                sources_list = vmalert_sources.get("sources")
                self.assertIsNotNone(sources_list, "sources should not be null")
                self.assertEqual(len(sources_list), 2, "Should have 2 sources")

                # Verify source IDs match what we wrote
                source_ids = {s.get("source_id") for s in sources_list}
                self.assertIn("vmalert-src-historical-1", source_ids)
                self.assertIn("vmalert-src-historical-2", source_ids)

        finally:
            self._shutdown_server(server, thread)

    def test_latest_run_includes_vmalert_sources(self) -> None:
        """Baseline test: GET /api/run (no run_id) includes vmalertSources.

        This ensures the vmalert integration works for latest run as well.
        """
        run_id = "latest-vmalert-test"

        # Prepare vmalert data
        sources = [
            {
                "source_id": "vmalert-src-latest-1",
                "endpoint": "http://vmalert-latest:8880",
                "namespace": "victoria-metrics",
                "name": "vmalert-main",
                "origin": "manual",
                "state": "manual",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "1.100.0",
                "confidence_hints": ["direct_user_registration"],
                "cluster_label": "test-cluster",
            },
        ]
        vmalert_sources_entry = {
            "sources": sources,
            "total_count": len(sources),
            "source_count": len(sources),
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "test-cluster",
        }

        # Write vmalert artifact BEFORE write_health_ui_index
        # write_health_ui_index reads the artifact when building the index
        self._write_vmalert_sources_artifact(run_id, sources)

        # Create the run's review artifact and write index with vmalert data
        artifact = self._build_artifact(
            run_id=run_id,
            status=ExternalAnalysisStatus.SUCCESS,
            timestamp=datetime.now(UTC),
        )
        self._write_index(artifact, vmalert_sources=vmalert_sources_entry)

        # Start the server
        server, thread = self._start_server()
        try:
            # Request latest run (no run_id parameter)
            payload = self._fetch_run_payload(server)

            # Key assertion: vmalertSources should not be null
            vmalert_sources = payload.get("vmalertSources")
            self.assertIsNotNone(
                vmalert_sources,
                "Latest run should include vmalertSources"
            )

        finally:
            self._shutdown_server(server, thread)

    def test_requested_run_without_vmalert_sources_returns_null(self) -> None:
        """Test that requested run without vmalert sources artifact returns null.

        This verifies graceful handling when the artifact doesn't exist.
        """
        run_id = "no-vmalert-artifact-run"

        # Create the run's review artifact
        artifact = self._build_artifact(
            run_id=run_id,
            status=ExternalAnalysisStatus.SUCCESS,
            timestamp=datetime.now(UTC),
        )
        self._write_index(artifact)

        # DO NOT write vmalert_sources artifact - simulating a run without it

        # Start the server
        server, thread = self._start_server()
        try:
            # Request the specific run via query parameter
            payload = self._fetch_run_payload(server, run_id=run_id)

            # vmalertSources should be null when artifact doesn't exist
            vmalert_sources = payload.get("vmalertSources")
            # This is acceptable behavior - null when no artifact
            self.assertIn(
                vmalert_sources,
                (None, {}),  # Either None or empty dict is acceptable
                "vmalertSources should be null or empty when artifact doesn't exist"
            )

        finally:
            self._shutdown_server(server, thread)

    def test_vmalert_sources_counts_in_response(self) -> None:
        """Test that vmalert sources counts are correctly populated in the response."""
        run_id = "vmalert-counts-test"

        # Prepare vmalert sources with different states
        sources = [
            {
                "source_id": "vmalert-manual-1",
                "endpoint": "http://vmalert-manual:8880",
                "namespace": "victoria-metrics",
                "name": "manual-vmalert",
                "origin": "manual",
                "state": "manual",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "confidence_hints": ["direct_user_registration"],
                "cluster_label": "test-cluster",
            },
            {
                "source_id": "vmalert-auto-1",
                "endpoint": "http://vmalert-auto:8880",
                "namespace": "victoria-metrics",
                "name": "auto-vmalert",
                "origin": "vmalert-crd",
                "state": "auto-tracked",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "confidence_hints": ["crd_discovery"],
                "cluster_label": "test-cluster",
            },
            {
                "source_id": "vmalert-discovered-1",
                "endpoint": "http://vmalert-discovered:8880",
                "namespace": "monitoring",
                "name": "discovered-vmalert",
                "origin": "service-heuristic",
                "state": "discovered",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": None,
                "confidence_hints": ["service_match"],
                "cluster_label": "test-cluster",
            },
        ]
        vmalert_sources_entry = {
            "sources": sources,
            "total_count": len(sources),
            "source_count": len(sources),
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "test-cluster",
        }

        # Create the run's review artifact and write index with vmalert data
        artifact = self._build_artifact(
            run_id=run_id,
            status=ExternalAnalysisStatus.SUCCESS,
            timestamp=datetime.now(UTC),
        )
        self._write_index(artifact, vmalert_sources=vmalert_sources_entry)
        self._write_vmalert_sources_artifact(run_id, sources)

        # Start the server
        server, thread = self._start_server()
        try:
            payload = self._fetch_run_payload(server, run_id=run_id)

            vmalert_sources = payload.get("vmalertSources")
            self.assertIsNotNone(vmalert_sources, "vmalertSources should not be null")

            if vmalert_sources is not None:
                # Verify counts are present
                self.assertEqual(vmalert_sources.get("total_count"), 3)
                self.assertEqual(vmalert_sources.get("source_count"), 3)

                # Verify sources list
                sources_list = vmalert_sources.get("sources")
                self.assertEqual(len(sources_list), 3)

                # Verify individual source fields
                for src in sources_list:
                    self.assertIn("source_id", src)
                    self.assertIn("endpoint", src)
                    self.assertIn("origin", src)
                    self.assertIn("state", src)
                    # UI-computed fields should be present
                    self.assertIn("is_manual", src)
                    self.assertIn("display_origin", src)
                    self.assertIn("display_state", src)

        finally:
            self._shutdown_server(server, thread)


class VmalertSourcesAPIPayloadTests(unittest.TestCase):
    """Tests for vmalertSources in RunPayload API response structure."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp()).resolve()
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
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            timestamp=datetime.now(UTC) if timestamp is None else timestamp,
        )

    def _write_index(
        self,
        artifact: ExternalAnalysisArtifact,
        vmalert_sources: dict[str, object] | None = None,
    ) -> None:
        """Write health UI index with vmalert data."""
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
        
        # Write review artifact to health/reviews/ so _load_context_for_run() can find it
        # _load_context_for_run() checks for this file to determine if a historical run exists
        reviews_dir = self.health_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_data = {
            "run_id": artifact.run_id,
            "run_label": artifact.run_label or artifact.run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "collector_version": "tests",
            "selected_drilldowns": [],
            "clusters": [],
            "assessments": [],
            "health_rating": "healthy",
            "warnings": 0,
            "external_analysis_settings": {
                "review_enrichment": {"enabled": True, "provider": "reviewer"}
            },
        }
        review_path = reviews_dir / f"{artifact.run_id}-review.json"
        review_path.write_text(json.dumps(review_data, indent=2), encoding="utf-8")
        
        if vmalert_sources is not None:
            index_path = self.health_dir / "ui-index.json"
            if index_path.exists():
                index_data = json.loads(index_path.read_text(encoding="utf-8"))
                run_entry = index_data.get("run") or {}
                run_entry["vmalert_sources"] = vmalert_sources
                index_data["run"] = run_entry
                index_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")

    def _write_vmalert_sources_artifact(
        self,
        run_id: str,
        sources: list[dict[str, object]],
    ) -> Path:
        """Write a run-scoped vmalert-sources artifact in VmalertSourceInventory format."""
        from k8s_diag_agent.external_analysis.vmalert_discovery import (
            VmalertSource,
            VmalertSourceInventory,
            VmalertSourceMode,
            VmalertSourceOrigin,
            VmalertSourceState,
        )
        
        self.health_dir.mkdir(parents=True, exist_ok=True)

        # Convert raw dicts to VmalertSource objects
        vmalert_sources: list[VmalertSource] = []
        for src in sources:
            # Parse datetime fields if provided as ISO strings
            discovered_at = src.get("discovered_at")
            if isinstance(discovered_at, str):
                from k8s_diag_agent.datetime_utils import parse_iso_to_utc
                discovered_at = parse_iso_to_utc(discovered_at)
            
            verified_at = src.get("verified_at")
            if isinstance(verified_at, str):
                from k8s_diag_agent.datetime_utils import parse_iso_to_utc
                verified_at = parse_iso_to_utc(verified_at)
            
            last_check = src.get("last_check")
            if isinstance(last_check, str):
                from k8s_diag_agent.datetime_utils import parse_iso_to_utc
                last_check = parse_iso_to_utc(last_check)
            
            vmalert_sources.append(VmalertSource(
                source_id=str(src.get("source_id", "")),
                endpoint=str(src.get("endpoint", "")),
                namespace=src.get("namespace"),
                name=src.get("name"),
                origin=VmalertSourceOrigin(src.get("origin", "service-heuristic")),
                state=VmalertSourceState(src.get("state", "discovered")),
                discovered_at=discovered_at or datetime.now(UTC),
                verified_at=verified_at,
                last_check=last_check,
                last_error=src.get("last_error"),
                verified_version=src.get("verified_version"),
                confidence_hints=tuple(src.get("confidence_hints", [])),
                cluster_label=src.get("cluster_label"),
                cluster_context="test-cluster",
                manual_source_mode=VmalertSourceMode.NOT_MANUAL,
            ))

        # Build inventory with proper format
        inventory = VmalertSourceInventory(
            sources={s.source_id: s for s in vmalert_sources},
            discovered_at=datetime.now(UTC),
            cluster_context="test-cluster",
        )

        path = self.health_dir / f"{run_id}-vmalert-sources.json"
        path.write_text(json.dumps(inventory.to_dict(), indent=2), encoding="utf-8")
        return path

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

    def test_run_payload_has_vmalert_sources_field(self) -> None:
        """Verify RunPayload includes vmalertSources field."""
        run_id = "payload-field-test"

        sources = [
            {
                "source_id": "vmalert-test-1",
                "endpoint": "http://vmalert:8880",
                "namespace": "victoria-metrics",
                "name": "test-vmalert",
                "origin": "vmalert-crd",
                "state": "auto-tracked",
                "confidence_hints": ["crd_discovery"],
                "cluster_label": "test-cluster",
            },
        ]
        vmalert_sources_entry = {
            "sources": sources,
            "total_count": 1,
            "source_count": 1,
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "test-cluster",
        }

        artifact = self._build_artifact(
            run_id=run_id,
            status=ExternalAnalysisStatus.SUCCESS,
        )
        self._write_index(artifact, vmalert_sources=vmalert_sources_entry)
        self._write_vmalert_sources_artifact(run_id, sources)

        server, thread = self._start_server()
        try:
            payload = self._fetch_run_payload(server, run_id=run_id)

            # Key assertion: vmalertSources field exists in payload
            self.assertIn("vmalertSources", payload,
                         "RunPayload should include vmalertSources field")

            vmalert_sources = payload.get("vmalertSources")
            self.assertIsNotNone(vmalert_sources,
                                "vmalertSources should not be null when artifact exists")

        finally:
            self._shutdown_server(server, thread)
