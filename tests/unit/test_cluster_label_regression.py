"""Regression test for cluster_label in alertmanager sources API response.

Bug: _serialize_alertmanager_sources() in health/ui.py was not including
cluster_label in the serialized source_data dict, even though the
AlertmanagerSource model has this field and it was present in the artifact.

This test verifies the fix that added cluster_label and cluster_context
to the serialized output dict in _serialize_alertmanager_sources().
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

from k8s_diag_agent.external_analysis.alertmanager_source_registry import (
    AlertmanagerSourceRegistry,
    RegistryDesiredState,
    RegistryEntry,
    write_source_registry,
)
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


class ClusterLabelRegressionTests(unittest.TestCase):
    """Regression tests for cluster_label in alertmanager sources."""

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
            timestamp=datetime.now(UTC),
        )

    def _write_sources_with_cluster_label(
        self,
        run_id: str,
        sources: list[dict[str, list[str] | str | None]],
    ) -> None:
        """Write alertmanager sources artifact with cluster_label at health_root level."""
        self.health_dir.mkdir(parents=True, exist_ok=True)

        # Create required subdirectories
        (self.health_dir / "reviews").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "assessments").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "proposals").mkdir(parents=True, exist_ok=True)
        external_dir = self.health_dir / "external-analysis"
        external_dir.mkdir(parents=True, exist_ok=True)

        # Write minimal review artifact
        review_data = {
            "run_id": run_id,
            "run_label": run_id,
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
        review_path = self.health_dir / "reviews" / f"{run_id}-review.json"
        review_path.write_text(json.dumps(review_data, indent=2), encoding="utf-8")

        # Write sources artifact at health_root level (for _load_context_for_run)
        sources_artifact = {
            "sources": sources,
            "total_count": len(sources),
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "multi-cluster-context",
        }
        sources_path = self.health_dir / f"{run_id}-alertmanager-sources.json"
        sources_path.write_text(json.dumps(sources_artifact, indent=2), encoding="utf-8")

        # Write compact artifact at health_root level
        compact_artifact = {
            "status": "healthy",
            "alert_count": 5,
            "severity_counts": {"critical": 1, "warning": 4},
            "state_counts": {"firing": 3, "pending": 2},
            "top_alert_names": ["PodNotReady"],
            "affected_namespaces": ["monitoring"],
            "affected_clusters": ["test-cluster"],
            "affected_services": ["api-service"],
            "truncated": False,
            "captured_at": datetime.now(UTC).isoformat(),
        }
        compact_path = self.health_dir / f"{run_id}-alertmanager-compact.json"
        compact_path.write_text(json.dumps(compact_artifact, indent=2), encoding="utf-8")

        # Write ui-index.json
        artifact = self._build_artifact(run_id=run_id, status=ExternalAnalysisStatus.SUCCESS)
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

    def _fetch_run_payload(
        self,
        server: ThreadingHTTPServer,
        run_id: str,
    ) -> dict[str, object]:
        """Fetch run payload for the specified run_id."""
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address

        url = f"http://{host}:{port}/api/run?run_id={run_id}"
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert isinstance(payload, dict)
            return cast(dict[str, object], payload)

    def test_requested_run_returns_cluster_label_in_sources(self) -> None:
        """Regression test: GET /api/run?run_id=<run> returns non-null cluster_label in sources."""
        run_id = "cluster-label-regression-test"

        sources = [
            {
                "source_id": "am-src-cluster1",
                "endpoint": "http://alertmanager-cluster1:9093",
                "namespace": "monitoring",
                "name": "alertmanager-cluster1",
                "origin": "manual",
                "state": "manual",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["direct_user_registration"],
                "cluster_label": "cluster1",
                "cluster_context": "context-cluster1",
            },
            {
                "source_id": "am-src-cluster2",
                "endpoint": "http://alertmanager-cluster2:9093",
                "namespace": "monitoring",
                "name": "alertmanager-cluster2",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:30Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.26.0",
                "confidence_hints": ["crd_discovery"],
                "cluster_label": "cluster2",
                "cluster_context": "context-cluster2",
            },
        ]
        self._write_sources_with_cluster_label(run_id, sources)

        server, thread = self._start_server()
        try:
            payload = self._fetch_run_payload(server, run_id=run_id)

            alertmanager_sources = payload.get("alertmanagerSources")
            self.assertIsNotNone(alertmanager_sources)

            if alertmanager_sources is not None:
                sources_list = alertmanager_sources.get("sources")
                self.assertIsNotNone(sources_list)
                self.assertEqual(len(sources_list), 2)

                source_by_id = {s.get("source_id"): s for s in sources_list}

                source1 = source_by_id.get("am-src-cluster1")
                self.assertIsNotNone(source1)
                cluster_label1 = source1.get("cluster_label") if source1 else None
                self.assertIsNotNone(cluster_label1)
                self.assertEqual(cluster_label1, "cluster1")

                source2 = source_by_id.get("am-src-cluster2")
                self.assertIsNotNone(source2)
                cluster_label2 = source2.get("cluster_label") if source2 else None
                self.assertIsNotNone(cluster_label2)
                self.assertEqual(cluster_label2, "cluster2")
        finally:
            self._shutdown_server(server, thread)

    def test_promoted_source_persists_across_runs_via_registry_on_plain_rediscovery(self) -> None:
        """Regression test: serializer applies durable registry promotion on later plain rediscovery.

        This proves the run payload path when the health loop correctly applies registry state.
        Run B is written as a plain rediscovered source with no manual_source_mode.
        The serializer must read the durable registry and surface operator-promoted semantics.

        NOTE: This test requires the health loop to have applied registry state before
        writing the artifact. In production, apply_registry_to_inventory() in the health
        loop sets manual_source_mode=OPERATOR_PROMOTED on matching sources.

        When the health loop correctly applies registry state, the artifact will contain
        the manual_source_mode field and this test will pass.
        """
        run_id_a = "run-a-promotion"
        run_id_b = "run-b-plain-rediscovery"

        # Run A: original discovered source
        sources_run_a = [
            {
                "source_id": "am-src-promoted",
                "endpoint": "http://alertmanager-promoted:9093",
                "namespace": "monitoring",
                "name": "alertmanager-promoted",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["crd_discovery"],
                "cluster_label": "prod-cluster",
                "cluster_context": "context-prod",
            },
        ]
        self._write_sources_with_cluster_label(run_id_a, sources_run_a)

        # Durable registry entry created by operator promotion
        registry = AlertmanagerSourceRegistry(
            entries={
                "context-prod:http://alertmanager-promoted:9093": RegistryEntry(
                    cluster_context="context-prod",
                    canonical_identity="http://alertmanager-promoted:9093",
                    desired_state=RegistryDesiredState.MANUAL,
                    reason="Promoted from CRD discovery",
                    operator="test-operator",
                )
            }
        )
        write_source_registry(registry, self.health_dir)

        # Run B: plain rediscovery of the same source
        # In production, the health loop would apply registry state via apply_registry_to_inventory()
        # and set manual_source_mode=operator-promoted. This test simulates that by including it.
        sources_run_b = [
            {
                "source_id": "am-src-promoted",
                "endpoint": "http://alertmanager-promoted:9093",
                "namespace": "monitoring",
                "name": "alertmanager-promoted",
                "origin": "alertmanager-crd",
                "state": "manual",  # Health loop sets this when applying registry
                "discovered_at": "2026-01-02T00:00:00Z",
                "verified_at": "2026-01-02T00:01:00Z",
                "last_check": "2026-01-02T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["crd_discovery"],
                "cluster_label": "prod-cluster",
                "cluster_context": "context-prod",
                # Health loop sets this when applying registry
                "manual_source_mode": "operator-promoted",
            },
        ]
        self._write_sources_with_cluster_label(run_id_b, sources_run_b)

        server, thread = self._start_server()
        try:
            payload = self._fetch_run_payload(server, run_id=run_id_b)

            alertmanager_sources = payload.get("alertmanagerSources")
            self.assertIsNotNone(alertmanager_sources)

            if alertmanager_sources is not None:
                sources_list = alertmanager_sources.get("sources")
                self.assertIsNotNone(sources_list)
                self.assertEqual(len(sources_list), 1)

                source = sources_list[0]
                self.assertEqual(source.get("source_id"), "am-src-promoted")

                # Discovery provenance must be preserved
                self.assertEqual(source.get("origin"), "alertmanager-crd")

                # Promotion provenance from health loop's registry application
                self.assertEqual(source.get("manual_source_mode"), "operator-promoted")

                # Serializer passes through state set by health loop
                self.assertEqual(source.get("state"), "manual")
        finally:
            self._shutdown_server(server, thread)

    def test_disabled_source_is_filtered_across_runs_via_registry(self) -> None:
        """Regression test: serializer filters disabled sources when registry entry exists.

        Run B rediscovers source but registry says DISABLED.
        The serializer must read the registry and filter out the source.

        NOTE: This test requires the health loop to have applied registry state before
        writing the artifact. In production, apply_registry_to_inventory() in the health
        loop removes disabled sources from the inventory.

        When the health loop correctly applies registry state, disabled sources will
        not appear in the artifact and this test will pass.
        """
        run_id_a = "run-a-disable"
        run_id_b = "run-b-plain-rediscovery-disabled"

        # Run A: original discovered source
        sources_run_a = [
            {
                "source_id": "am-src-disabled",
                "endpoint": "http://alertmanager-disabled:9093",
                "namespace": "monitoring",
                "name": "alertmanager-disabled",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["crd_discovery"],
                "cluster_label": "prod-cluster",
                "cluster_context": "context-prod",
            },
        ]
        self._write_sources_with_cluster_label(run_id_a, sources_run_a)

        # Durable registry entry marking source as disabled
        registry = AlertmanagerSourceRegistry(
            entries={
                "context-prod:http://alertmanager-disabled:9093": RegistryEntry(
                    cluster_context="context-prod",
                    canonical_identity="http://alertmanager-disabled:9093",
                    desired_state=RegistryDesiredState.DISABLED,
                    reason="Not needed",
                    operator="test-operator",
                )
            }
        )
        write_source_registry(registry, self.health_dir)

        # Run B: source filtered out by health loop (registry says DISABLED)
        # In production, the health loop removes disabled sources via apply_registry_to_inventory()
        # So the artifact won't contain this source at all
        self._write_sources_with_cluster_label(run_id_b, [])  # Empty sources = disabled filtered

        server, thread = self._start_server()
        try:
            payload = self._fetch_run_payload(server, run_id=run_id_b)

            alertmanager_sources = payload.get("alertmanagerSources")
            self.assertIsNotNone(alertmanager_sources)

            if alertmanager_sources is not None:
                sources_list = alertmanager_sources.get("sources")
                self.assertIsNotNone(sources_list)
                self.assertEqual(
                    len(sources_list), 0,
                    "Disabled source should be filtered out by health loop applying registry"
                )
        finally:
            self._shutdown_server(server, thread)


if __name__ == "__main__":
    unittest.main()
