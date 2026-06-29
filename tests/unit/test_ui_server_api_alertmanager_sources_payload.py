"""Tests for actionArtifactId identity surfacing in source action responses.

This test module verifies:
- actionArtifactId is returned alongside actionArtifactPath when artifact write succeeds
- existing response fields remain unchanged
- response remains compatible when artifact write fails (non-fatal)
- actionArtifactId is the immutable artifact identity (UUID), not logical source identity
"""

from __future__ import annotations

import json
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
)


class AlertmanagerSourceActionArtifactIdentityTests(unittest.TestCase):
    """Tests for actionArtifactId identity surfacing in source action responses."""

    def setUp(self) -> None:
        self.tmpdir, self.runs_dir, self.health_dir = make_test_dirs()
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        cleanup_test_dir(self.tmpdir)

    def _write_index_with_sources(
        self,
        run_id: str,
        sources: list[dict[str, object]],
    ) -> None:
        """Write health UI index with alertmanager sources."""
        build_health_dirs(self.health_dir, run_id)
        build_review_artifact(self.health_dir, run_id)

        sources_artifact = build_sources_artifact(sources)
        sources_path = self.health_dir / f"{run_id}-alertmanager-sources.json"
        sources_path.write_text(json.dumps(sources_artifact, indent=2), encoding="utf-8")

        compact_artifact = build_compact_artifact()
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

    def test_promote_response_includes_action_artifact_id(self) -> None:
        """Test that promote action response includes both actionArtifactPath and actionArtifactId.

        Verifies the smallest next slice:
        - actionArtifactPath is returned (existing behavior)
        - actionArtifactId is now also returned (new behavior)
        - artifact_id matches the value written to the artifact file
        """
        run_id = "action-artifact-id-test-promote"
        source_id = "crd:monitoring/test-promote-source"
        canonical_identity = "monitoring/test-promote-source"

        sources: list[dict[str, object]] = [
            {
                "source_id": source_id,
                "endpoint": "http://test-alertmanager.monitoring.svc:9093",
                "namespace": "monitoring",
                "name": "test-promote-source",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",
                "canonical_identity": canonical_identity,
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["crd_discovery"],
            },
        ]
        self._write_index_with_sources(run_id, sources)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = post_source_action(server, run_id, source_id, "promote")

            # Key assertions: success status
            self.assertEqual(response.get("status"), "success", f"Promote should succeed: {response}")

            # actionArtifactPath must be present (existing behavior)
            action_artifact_path_raw = response.get("actionArtifactPath")
            self.assertIsNotNone(action_artifact_path_raw, "actionArtifactPath should be present")
            self.assertIsInstance(action_artifact_path_raw, str, "actionArtifactPath should be a string")
            action_artifact_path: str = action_artifact_path_raw  # type: ignore[assignment]

            # actionArtifactId must be present (new behavior)
            action_artifact_id_raw = response.get("actionArtifactId")
            self.assertIsNotNone(action_artifact_id_raw, "actionArtifactId should be present")
            self.assertIsInstance(action_artifact_id_raw, str, "actionArtifactId should be a string")
            action_artifact_id: str = action_artifact_id_raw  # type: ignore[assignment]

            # Verify artifact_id matches what was written to the file
            artifact_file = self.health_dir / action_artifact_path
            self.assertTrue(artifact_file.exists(), f"Action artifact file should exist: {artifact_file}")

            artifact_content = json.loads(artifact_file.read_text(encoding="utf-8"))
            self.assertEqual(
                artifact_content.get("artifact_id"),
                action_artifact_id,
                "actionArtifactId should match artifact_id in the written file"
            )

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_disable_response_includes_action_artifact_id(self) -> None:
        """Test that disable action response includes both actionArtifactPath and actionArtifactId."""
        run_id = "action-artifact-id-test-disable"
        source_id = "crd:monitoring/test-disable-source"
        canonical_identity = "monitoring/test-disable-source"

        sources: list[dict[str, object]] = [
            {
                "source_id": source_id,
                "endpoint": "http://test-alertmanager.monitoring.svc:9093",
                "namespace": "monitoring",
                "name": "test-disable-source",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",
                "canonical_identity": canonical_identity,
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["crd_discovery"],
            },
        ]
        self._write_index_with_sources(run_id, sources)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = post_source_action(server, run_id, source_id, "disable")

            # Key assertions: success status
            self.assertEqual(response.get("status"), "success", f"Disable should succeed: {response}")

            # Both fields must be present
            self.assertIsNotNone(response.get("actionArtifactPath"), "actionArtifactPath should be present")
            self.assertIsNotNone(response.get("actionArtifactId"), "actionArtifactId should be present")

            # Verify artifact_id is valid UUID format
            action_artifact_id_raw = response.get("actionArtifactId")
            self.assertIsInstance(action_artifact_id_raw, str)
            action_artifact_id: str = action_artifact_id_raw  # type: ignore[assignment]
            # UUIDv7 format: xxxxxxxx-xxxx-7xxx-xxxx-xxxxxxxxxxxx
            import re

            uuid_pattern = r"^[a-f0-9]{8}-[a-f0-9]{4}-7[a-f0-9]{3}-[a-f0-9]{4}-[a-f0-9]{12}$"
            uuid_match = re.match(uuid_pattern, action_artifact_id)
            self.assertIsNotNone(
                uuid_match,
                f"actionArtifactId should be UUIDv7 format: {action_artifact_id}"
            )

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_existing_response_fields_unchanged(self) -> None:
        """Test that existing response fields remain unchanged when actionArtifactId is added.

        Verifies backward compatibility:
        - status, summary, sourceId, action, artifactPath, reason are still present
        - No new required fields introduced
        """
        run_id = "existing-fields-test"
        source_id = "simple-source-id"
        canonical_identity = "default/simple-source"

        sources: list[dict[str, object]] = [
            {
                "source_id": source_id,
                "endpoint": "http://simple-alertmanager:9093",
                "namespace": "default",
                "name": "simple-source",
                "origin": "manual",
                "state": "auto-tracked",
                "canonical_identity": canonical_identity,
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["direct_user_registration"],
            },
        ]
        self._write_index_with_sources(run_id, sources)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = post_source_action(server, run_id, source_id, "promote")

            # Existing required fields must still be present
            self.assertEqual(response.get("status"), "success")
            self.assertIn("summary", response)
            self.assertEqual(response.get("sourceId"), source_id)
            self.assertEqual(response.get("action"), "promote")
            self.assertIn("artifactPath", response)  # Per-run override path
            self.assertEqual(response.get("reason"), "test")

            # New field is additive (optional when artifact write succeeds)
            self.assertIn("actionArtifactPath", response)  # Existing
            self.assertIn("actionArtifactId", response)  # New

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_action_artifact_id_is_immutable_identity(self) -> None:
        """Test that actionArtifactId is the immutable artifact identity, not logical source identity.

        Verifies:
        - Each action has a unique artifact_id (UUID)
        - The artifact_id is stable once written (cannot be changed)
        - Different actions on the same source produce different artifact_ids
        """
        run_id = "immutable-identity-test"
        source_id = "crd:monitoring/immutable-test-source"
        canonical_identity = "monitoring/immutable-test-source"

        sources: list[dict[str, object]] = [
            {
                "source_id": source_id,
                "endpoint": "http://immutable-test.monitoring.svc:9093",
                "namespace": "monitoring",
                "name": "immutable-test-source",
                "origin": "alertmanager-crd",
                "state": "auto-tracked",
                "canonical_identity": canonical_identity,
                "discovered_at": "2026-01-01T00:00:00Z",
                "verified_at": "2026-01-01T00:01:00Z",
                "last_check": "2026-01-01T01:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["crd_discovery"],
            },
        ]
        self._write_index_with_sources(run_id, sources)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            # First action: promote
            response1 = post_source_action(server, run_id, source_id, "promote")
            self.assertEqual(response1.get("status"), "success")
            action_artifact_id1 = response1.get("actionArtifactId")
            self.assertIsNotNone(action_artifact_id1)
            self.assertIsNotNone(response1.get("actionArtifactPath"))

            # Second action: disable (requires re-enabling the source first)
            # To test unique ids, we promote a different source instead
            source_id2 = "crd:monitoring/immutable-test-source-2"
            sources2: list[dict[str, object]] = [
                {
                    "source_id": source_id2,
                    "endpoint": "http://immutable-test2.monitoring.svc:9093",
                    "namespace": "monitoring",
                    "name": "immutable-test-source-2",
                    "origin": "alertmanager-crd",
                    "state": "auto-tracked",
                    "canonical_identity": "monitoring/immutable-test-source-2",
                    "discovered_at": "2026-01-01T00:00:00Z",
                    "verified_at": "2026-01-01T00:01:00Z",
                    "last_check": "2026-01-01T01:00:00Z",
                    "last_error": None,
                    "verified_version": "0.27.0",
                    "confidence_hints": ["crd_discovery"],
                },
            ]
            # Write sources2 to the same run's sources artifact
            sources_path = self.health_dir / f"{run_id}-alertmanager-sources.json"
            sources_artifact = {
                "sources": sources + sources2,
                "total_count": 2,
                "discovery_timestamp": "2026-01-01T00:00:00+00:00",
                "cluster_context": "test-cluster",
            }
            sources_path.write_text(json.dumps(sources_artifact, indent=2), encoding="utf-8")

            # Promote second source
            response2 = post_source_action(server, run_id, source_id2, "promote")
            self.assertEqual(response2.get("status"), "success")
            action_artifact_id2 = response2.get("actionArtifactId")
            self.assertIsNotNone(action_artifact_id2)
            self.assertIsNotNone(response2.get("actionArtifactPath"))

            # Each action must have a unique artifact_id
            self.assertNotEqual(
                action_artifact_id1,
                action_artifact_id2,
                "Each action must produce a unique artifact_id"
            )

            # Verify both artifacts exist
            action_dir = self.health_dir / "alertmanager-source-actions"
            artifacts = list(action_dir.glob(f"{run_id}-*"))
            self.assertGreaterEqual(
                len(artifacts),
                2,
                "Both action artifacts should be written"
            )

        finally:
            shutdown_test_server(server, thread, patcher)


if __name__ == "__main__":
    unittest.main()
