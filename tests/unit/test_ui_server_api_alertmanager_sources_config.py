"""Regression tests for URL-encoded source_id in promote/disable actions.

Bug: When UI sends source_id with `:` and `/` characters (e.g.,
`crd:monitoring/kube-prometheus-stack-alertmanager`), the path parameter
is URL-encoded (e.g., `crd%3Amonitoring%2Fkube-prometheus-stack-alertmanager`).
The backend was not decoding this before lookup, causing "Source not found" errors.

Expected fix: decode the route path parameter with urllib.parse.unquote()
before source lookup, validation, and persistence.
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
)


class AlertmanagerSourceActionURLEncodingTests(unittest.TestCase):
    """Regression tests for URL-encoded source_id in promote/disable actions."""

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
        """Write health UI index with alertmanager sources containing special chars."""
        build_health_dirs(self.health_dir, run_id)
        build_review_artifact(self.health_dir, run_id)

        sources_artifact = build_sources_artifact(sources)
        sources_path = self.health_dir / f"{run_id}-alertmanager-sources.json"
        sources_path.write_text(__import__("json").dumps(sources_artifact, indent=2), encoding="utf-8")

        compact_artifact = build_compact_artifact()
        compact_path = self.health_dir / f"{run_id}-alertmanager-compact.json"
        compact_path.write_text(__import__("json").dumps(compact_artifact, indent=2), encoding="utf-8")

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
        import json

        index_path = self.health_dir / "ui-index.json"
        if index_path.exists():
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
            run_entry = index_data.get("run") or {}
            run_entry["alertmanager_sources"] = sources_artifact
            run_entry["alertmanager_compact"] = compact_artifact
            index_data["run"] = run_entry
            index_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")

    def test_promote_source_with_colon_and_slash_in_id_succeeds(self) -> None:
        """Regression test: promoting source with `:` and `/` in source_id succeeds.

        The source_id 'crd:monitoring/kube-prometheus-stack-alertmanager' is URL-encoded
        to 'crd%3Amonitoring%2Fkube-prometheus-stack-alertmanager' in the path.
        The backend must decode this before source lookup.
        """
        import json

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

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = post_source_action(server, run_id, source_id, "promote")

            # Key assertion: success status, not "Source not found"
            self.assertEqual(response.get("status"), "success", f"Promote should succeed: {response}")
            self.assertNotIn("Source not found", str(response.get("error", "")),
                             "Source should be found after URL-decoding")

            # Verify the override was written with the correct decoded source_id
            overrides_path = self.health_dir / f"{run_id}-alertmanager-source-overrides.json"
            self.assertTrue(overrides_path.exists(), "Override artifact should be written")

            overrides_data = json.loads(overrides_path.read_text(encoding="utf-8"))
            self.assertIn("overrides", overrides_data, "Override file should have 'overrides' key")

            # Find our override by source_id
            from typing import cast

            our_override: dict[str, object] | None = None
            for override in overrides_data.get("overrides", []):
                if override is not None and (cast(dict[str, object], override).get("source_id") or "") == source_id:
                    our_override = override
                    break

            self.assertIsNotNone(our_override, f"Override with source_id '{source_id}' should exist")
            self.assertEqual(cast(dict[str, object], our_override).get("action"), "promote", "Action should be 'promote'")

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_disable_source_with_colon_and_slash_in_id_succeeds(self) -> None:
        """Regression test: disabling source with `:` and `/` in source_id succeeds.

        The source_id 'crd:monitoring/kube-prometheus-stack-alertmanager' is URL-encoded
        to 'crd%3Amonitoring%2Fkube-prometheus-stack-alertmanager' in the path.
        The backend must decode this before source lookup.
        """
        import json

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

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = post_source_action(server, run_id, source_id, "disable")

            # Key assertion: success status, not "Source not found"
            self.assertEqual(response.get("status"), "success", f"Disable should succeed: {response}")
            self.assertNotIn("Source not found", str(response.get("error", "")),
                             "Source should be found after URL-decoding")

            # Verify the override was written with the correct decoded source_id
            overrides_path = self.health_dir / f"{run_id}-alertmanager-source-overrides.json"
            self.assertTrue(overrides_path.exists(), "Override artifact should be written")

            overrides_data = json.loads(overrides_path.read_text(encoding="utf-8"))

            from typing import cast

            # Find our override by source_id
            our_override: dict[str, object] | None = None
            for override in overrides_data.get("overrides", []):
                if override is not None and (cast(dict[str, object], override).get("source_id") or "") == source_id:
                    our_override = override
                    break

            self.assertIsNotNone(our_override, f"Override with source_id '{source_id}' should exist")
            self.assertEqual(cast(dict[str, object], our_override).get("action"), "disable", "Action should be 'disable'")

        finally:
            shutdown_test_server(server, thread, patcher)

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

        server1, thread1, patcher1 = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            # Test 1: Source with special characters (promote)
            response_special = post_source_action(server1, run_id_special, source_id_special, "promote")
            self.assertEqual(response_special.get("status"), "success",
                            f"Source with special chars should be found: {response_special}")
        finally:
            shutdown_test_server(server1, thread1, patcher1)

        server2, thread2, patcher2 = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            # Test 2: Source with no special characters (promote)
            response_simple = post_source_action(server2, run_id_simple, source_id_simple, "promote")
            self.assertEqual(response_simple.get("status"), "success",
                            f"Source with no special chars should be found: {response_simple}")
        finally:
            shutdown_test_server(server2, thread2, patcher2)


if __name__ == "__main__":
    unittest.main()
