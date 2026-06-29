"""End-to-end tests for cross-run persistence of alertmanager source actions.

These tests verify the complete flow:
1. API promote/disable writes the registry entry
2. The registry entry uses canonical_identity for the key (matching health loop lookup)
3. The registry entry can be read back with correct key format

Bug fixed: The action handler was using `matching_key` for both the registry key
and the canonical_identity field, while the health loop uses `canonical_identity`
for the registry key. This caused a mismatch where operator actions weren't
applied in subsequent runs.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisStatus
from k8s_diag_agent.external_analysis.config import (
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from k8s_diag_agent.health.ui import write_health_ui_index
from tests.helpers.ui_test_harness import (
    shutdown_test_server,
    start_ui_test_server_without_auth,
)
from tests.unit.test_ui_server_api_alertmanager_sources_fixtures import (
    build_artifact,
    build_compact_artifact,
    build_health_dirs,
    build_review_artifact,
    build_sources_artifact,
    cleanup_test_dir,
    make_test_dirs,
    post_source_action,
    read_registry,
)


class AlertmanagerSourceRegistryPersistenceTests(unittest.TestCase):
    """End-to-end tests for cross-run persistence of alertmanager source actions."""

    def setUp(self) -> None:
        self.tmpdir, self.runs_dir, self.health_dir = make_test_dirs()
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        cleanup_test_dir(self.tmpdir)

    def _write_sources_with_canonical_identity(
        self,
        run_id: str,
        source_id: str,
        endpoint: str,
        canonical_identity: str,
        origin: str = "alertmanager-crd",
        state: str = "auto-tracked",
        cluster_context: str = "test-cluster",
    ) -> None:
        """Write a run-scoped alertmanager-sources artifact with explicit canonical_identity.

        This simulates what the health loop discovery produces, with explicit
        canonical_identity for cross-run matching.
        """
        import json

        build_health_dirs(self.health_dir, run_id)
        build_review_artifact(self.health_dir, run_id)

        # Parse namespace and name from canonical_identity for proper model behavior
        if "/" in canonical_identity:
            name_parts = canonical_identity.rsplit("/", 1)
            ns = name_parts[0]
            name = name_parts[1]
        else:
            ns = "monitoring"
            name = endpoint

        sources: list[dict[str, object]] = [
            {
                "source_id": source_id,
                "endpoint": endpoint,
                "namespace": ns,
                "name": name,
                "origin": origin,
                "state": state,
                # Explicit canonical_identity for cross-run matching
                # This must match what the health loop uses for registry lookups
                "canonical_identity": canonical_identity,
                # matching_key is UI-derived fallback
                "matching_key": endpoint,  # Also include matching_key for completeness
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["crd_discovery"],
            },
        ]
        sources_artifact = build_sources_artifact(sources, cluster_context)
        sources_path = self.health_dir / f"{run_id}-alertmanager-sources.json"
        sources_path.write_text(json.dumps(sources_artifact, indent=2), encoding="utf-8")

        compact_artifact = build_compact_artifact(cluster_context)
        compact_path = self.health_dir / f"{run_id}-alertmanager-compact.json"
        compact_path.write_text(json.dumps(compact_artifact, indent=2), encoding="utf-8")

        # Write ui-index.json with embedded sources
        artifact = build_artifact(
            run_id=run_id,
            status=ExternalAnalysisStatus.SUCCESS,
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
        index_path = self.health_dir / "ui-index.json"
        if index_path.exists():
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
            run_entry = index_data.get("run") or {}
            run_entry["alertmanager_sources"] = sources_artifact
            run_entry["alertmanager_compact"] = compact_artifact
            index_data["run"] = run_entry
            index_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")

    def test_promote_writes_registry_entry_with_canonical_identity(self) -> None:
        """Test that promote action writes registry entry using canonical_identity.

        The registry key must be: cluster_context:canonical_identity
        This matches what the health loop uses for lookups in subsequent runs.
        """
        run_id = "promote-registry-test"
        source_id = "crd:monitoring/test-alertmanager"
        endpoint = "http://alertmanager.monitoring.svc:9093"
        # canonical_identity is computed as namespace/name by the model
        canonical_identity = "monitoring/test-alertmanager"
        cluster_context = "test-cluster"

        self._write_sources_with_canonical_identity(
            run_id=run_id,
            source_id=source_id,
            endpoint=endpoint,
            canonical_identity=canonical_identity,
            origin="alertmanager-crd",
            state="auto-tracked",
        )

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = post_source_action(server, run_id, source_id, "promote")
            self.assertEqual(response.get("status"), "success", f"Promote should succeed: {response}")
        finally:
            shutdown_test_server(server, thread, patcher)

        # Verify registry entry was written
        registry = read_registry(self.health_dir)
        assert registry is not None, "Registry should be written"
        registry_entries = registry.entries
        self.assertIsNotNone(registry_entries, "Registry entries should exist")

        # The registry key must use canonical_identity (not matching_key)
        expected_registry_key = f"{cluster_context}:{canonical_identity}"
        self.assertIn(
            expected_registry_key,
            registry_entries,
            f"Registry key should be '{expected_registry_key}' using canonical_identity"
        )

        # Verify the registry entry has correct canonical_identity
        entry = registry_entries[expected_registry_key]
        self.assertEqual(
            entry.canonical_identity,
            canonical_identity,
            "Registry entry canonical_identity should match source canonical_identity"
        )
        self.assertEqual(
            entry.desired_state.value,
            "manual",
            "Promoted source should have desired_state=manual"
        )
        self.assertEqual(
            entry.cluster_context,
            cluster_context,
            "Registry entry cluster_context should match"
        )

    def test_disable_writes_registry_entry_with_canonical_identity(self) -> None:
        """Test that disable action writes registry entry using canonical_identity.

        The registry key must be: cluster_context:canonical_identity
        This matches what the health loop uses for lookups in subsequent runs.
        """
        run_id = "disable-registry-test"
        source_id = "service:monitoring/test-service"
        endpoint = "http://test-service.monitoring.svc:9093"
        # canonical_identity is computed as namespace/name by the model
        canonical_identity = "monitoring/test-service"
        cluster_context = "test-cluster"

        self._write_sources_with_canonical_identity(
            run_id=run_id,
            source_id=source_id,
            endpoint=endpoint,
            canonical_identity=canonical_identity,
            origin="service-heuristic",
            state="auto-tracked",
        )

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = post_source_action(server, run_id, source_id, "disable")
            self.assertEqual(response.get("status"), "success", f"Disable should succeed: {response}")
        finally:
            shutdown_test_server(server, thread, patcher)

        # Verify registry entry was written
        registry = read_registry(self.health_dir)
        assert registry is not None, "Registry should be written"
        registry_entries = registry.entries

        # The registry key must use canonical_identity (not matching_key)
        expected_registry_key = f"{cluster_context}:{canonical_identity}"
        self.assertIn(
            expected_registry_key,
            registry_entries,
            f"Registry key should be '{expected_registry_key}' using canonical_identity"
        )

        # Verify the registry entry has correct canonical_identity and state
        entry = registry_entries[expected_registry_key]
        self.assertEqual(
            entry.canonical_identity,
            canonical_identity,
            "Registry entry canonical_identity should match source canonical_identity"
        )
        self.assertEqual(
            entry.desired_state.value,
            "disabled",
            "Disabled source should have desired_state=disabled"
        )

    def test_registry_key_matches_health_loop_lookup(self) -> None:
        """Test that registry key format matches what health loop uses for lookups.

        This verifies end-to-end consistency:
        - UI server writes: {cluster_context}:{source.canonical_identity}
        - Health loop looks up: {cluster_context}:{source.canonical_identity}

        Both must use canonical_identity from the discovery layer.
        """
        run_id = "registry-key-match-test"
        source_id = "prometheus-config:default/k8s"
        endpoint = "http://prometheus.default:9090"
        # canonical_identity is computed as namespace/name format by the model
        # For "prometheus-config:default/k8s" with namespace="default" and name="k8s",
        # the computed canonical_identity would be "default/k8s"
        canonical_identity = "default/k8s"
        cluster_context = "test-cluster"

        self._write_sources_with_canonical_identity(
            run_id=run_id,
            source_id=source_id,
            endpoint=endpoint,
            canonical_identity=canonical_identity,
            origin="prometheus-crd-config",
            state="discovered",
        )

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = post_source_action(server, run_id, source_id, "promote")
            self.assertEqual(response.get("status"), "success")
        finally:
            shutdown_test_server(server, thread, patcher)

        # Simulate what the health loop does when looking up registry state
        # It reads from registry and looks up using: cluster_context:canonical_identity
        registry = read_registry(self.health_dir)
        assert registry is not None, "Registry should be written"
        registry_entries = registry.entries

        # This is the exact lookup pattern the health loop uses
        health_loop_lookup_key = f"{cluster_context}:{canonical_identity}"

        # Verify the lookup key exists (health loop can find it)
        self.assertIn(
            health_loop_lookup_key,
            registry_entries,
            f"Health loop lookup key '{health_loop_lookup_key}' should exist in registry"
        )

        # Verify the entry has the correct desired_state
        entry = registry_entries[health_loop_lookup_key]
        self.assertEqual(
            entry.desired_state.value,
            "manual",
            "Promoted source should be found by health loop with desired_state=manual"
        )
        self.assertEqual(
            entry.cluster_context,
            cluster_context,
            "Cluster context should match for proper lookup"
        )


if __name__ == "__main__":
    unittest.main()
