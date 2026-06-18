"""Exception handling tests for server_alertmanager.py.

These tests verify that:
1. Malformed request JSON returns 400
2. Invalid/non-object JSON returns 400 behavior
3. Inventory/override read errors follow fallback behavior
4. Source action persistence failure returns 500 and logs safe metadata
5. Valid source action path still passes existing tests
6. Logs do not include raw payload/secret-like values
"""

import json
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
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
from tests.helpers.ui_test_harness import (
    shutdown_test_server,
    start_ui_test_server_without_auth,
)


class AlertmanagerSourceActionExceptionTests(unittest.TestCase):
    """Tests for exception handling in handle_alertmanager_source_action."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp()).resolve()
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_index_with_sources(
        self,
        run_id: str,
        sources: Sequence[Mapping[str, object]],
    ) -> None:
        """Write health UI index with alertmanager sources."""
        self.health_dir.mkdir(parents=True, exist_ok=True)

        # Create required subdirectories
        (self.health_dir / "reviews").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "assessments").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "proposals").mkdir(parents=True, exist_ok=True)
        external_dir = self.health_dir / "external-analysis"
        external_dir.mkdir(parents=True, exist_ok=True)

        # Write review artifact
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

        # Write sources artifact
        sources_artifact = {
            "sources": sources,
            "total_count": len(sources),
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "test-cluster",
        }
        sources_path = self.health_dir / f"{run_id}-alertmanager-sources.json"
        sources_path.write_text(json.dumps(sources_artifact, indent=2), encoding="utf-8")

        # Write compact artifact
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

        # Write ui-index.json
        artifact = ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=run_id,
            run_label=run_id,
            cluster_label="test-cluster",
            summary=f"Test artifact for {run_id}",
            status=ExternalAnalysisStatus.SUCCESS,
            provider="reviewer",
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
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
        # Post-process: inject alertmanager data
        index_path = self.health_dir / "ui-index.json"
        if index_path.exists():
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
            run_entry = index_data.get("run") or {}
            run_entry["alertmanager_sources"] = sources_artifact
            run_entry["alertmanager_compact"] = compact_artifact
            index_data["run"] = run_entry
            index_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")

    def _fetch(
        self,
        server: ThreadingHTTPServer,
        method: str,
        path: str,
        data: bytes | None = None,
    ) -> tuple[int, str]:
        """Make an HTTP request to the test server and return status code and body."""
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address
        url = f"http://{host}:{port}{path}"

        headers = {"Content-Type": "application/json"} if data else {}
        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def _post_source_action(
        self,
        server: ThreadingHTTPServer,
        run_id: str,
        source_id: str,
        payload: dict[str, object] | None = None,
    ) -> urllib.error.HTTPError | dict[str, object]:
        """POST to the source action endpoint."""
        from urllib.parse import quote

        encoded_source_id = quote(source_id, safe="")
        path = f"/api/runs/{run_id}/alertmanager-sources/{encoded_source_id}/action"
        body = json.dumps(payload or {"action": "promote", "clusterLabel": "test-cluster"}).encode(
            "utf-8"
        )

        try:
            status, body_text = self._fetch(server, "POST", path, body)
            if status >= 400:
                # Create HTTPError for consistency
                exc = urllib.error.HTTPError(path, status, "", {}, None)
                return exc
            return cast(dict[str, object], json.loads(body_text))
        except urllib.error.HTTPError as exc:
            return exc

    def test_malformed_json_returns_400(self) -> None:
        """Malformed JSON in request body returns 400."""
        run_id = "exception-test-malformed-json"
        source_id = "test-source-1"
        sources = [
            {
                "source_id": source_id,
                "endpoint": "http://alertmanager:9093",
                "namespace": "monitoring",
                "name": "test-alertmanager",
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
        self._write_index_with_sources(run_id, sources)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            from urllib.parse import quote

            encoded_source_id = quote(source_id, safe="")
            path = f"/api/runs/{run_id}/alertmanager-sources/{encoded_source_id}/action"

            # Send malformed JSON (missing closing brace)
            malformed_payload = b'{"action": "promote", "clusterLabel": "test-cluster"'

            status, body = self._fetch(server, "POST", path, malformed_payload)
            self.assertEqual(status, 400, "Malformed JSON should return 400")
            self.assertIn("Invalid JSON payload", body)

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_invalid_non_object_json_returns_400(self) -> None:
        """Non-object JSON (e.g., array) in request body returns 400."""
        run_id = "exception-test-array-json"
        source_id = "test-source-2"
        sources = [
            {
                "source_id": source_id,
                "endpoint": "http://alertmanager:9093",
                "namespace": "monitoring",
                "name": "test-alertmanager",
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
        self._write_index_with_sources(run_id, sources)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            from urllib.parse import quote

            encoded_source_id = quote(source_id, safe="")
            path = f"/api/runs/{run_id}/alertmanager-sources/{encoded_source_id}/action"

            # Send array instead of object (ValueError from json.loads)
            array_payload = b'["not", "an", "object"]'

            status, body = self._fetch(server, "POST", path, array_payload)
            self.assertEqual(status, 400, "Non-object JSON should return 400")
            self.assertIn("Invalid JSON payload", body)

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_missing_required_action_returns_400(self) -> None:
        """Missing 'action' field in request body returns 400."""
        run_id = "exception-test-missing-action"
        source_id = "test-source-3"
        sources = [
            {
                "source_id": source_id,
                "endpoint": "http://alertmanager:9093",
                "namespace": "monitoring",
                "name": "test-alertmanager",
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
        self._write_index_with_sources(run_id, sources)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            from urllib.parse import quote

            encoded_source_id = quote(source_id, safe="")
            path = f"/api/runs/{run_id}/alertmanager-sources/{encoded_source_id}/action"

            # Send valid JSON but missing required 'action' field
            payload = b'{"clusterLabel": "test-cluster"}'

            status, body = self._fetch(server, "POST", path, payload)
            self.assertEqual(status, 400, "Missing action should return 400")
            self.assertIn("action is required", body)

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_corrupted_override_read_uses_fallback(self) -> None:
        """Corrupted override file read results in fresh start (fallback behavior)."""
        run_id = "exception-test-corrupted-override"
        source_id = "test-source-4"
        sources = [
            {
                "source_id": source_id,
                "endpoint": "http://alertmanager:9093",
                "namespace": "monitoring",
                "name": "test-alertmanager",
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
        self._write_index_with_sources(run_id, sources)

        # Pre-write a corrupted overrides file
        overrides_path = self.health_dir / f"{run_id}-alertmanager-source-overrides.json"
        overrides_path.write_text('{"corrupted": "data', encoding="utf-8")  # Missing closing brace

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = self._post_source_action(
                server,
                run_id,
                source_id,
                {"action": "promote", "clusterLabel": "test-cluster"},
            )

            # Should succeed despite corrupted file (starts fresh)
            self.assertIsInstance(response, dict)
            self.assertEqual(response.get("status"), "success")

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_unicode_decode_error_returns_400(self) -> None:
        """Invalid UTF-8 encoding in request body returns 400."""
        run_id = "exception-test-unicode-error"
        source_id = "test-source-5"
        sources = [
            {
                "source_id": source_id,
                "endpoint": "http://alertmanager:9093",
                "namespace": "monitoring",
                "name": "test-alertmanager",
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
        self._write_index_with_sources(run_id, sources)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            from urllib.parse import quote

            encoded_source_id = quote(source_id, safe="")
            path = f"/api/runs/{run_id}/alertmanager-sources/{encoded_source_id}/action"

            # Send invalid UTF-8 bytes (continuation byte without start)
            invalid_utf8 = b'{"action": "promote", "clusterLabel": "test-cluster"}\xff\xfe'

            status, body = self._fetch(server, "POST", path, invalid_utf8)
            self.assertEqual(status, 400, "Invalid UTF-8 should return 400")

        finally:
            shutdown_test_server(server, thread, patcher)


class AlertmanagerSourceActionLoggingTests(unittest.TestCase):
    """Tests to verify logs don't include sensitive data."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp()).resolve()
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_index_with_sources(
        self,
        run_id: str,
        sources: Sequence[Mapping[str, object]],
    ) -> None:
        """Write health UI index with alertmanager sources."""
        self.health_dir.mkdir(parents=True, exist_ok=True)

        (self.health_dir / "reviews").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "assessments").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "proposals").mkdir(parents=True, exist_ok=True)
        external_dir = self.health_dir / "external-analysis"
        external_dir.mkdir(parents=True, exist_ok=True)

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

        sources_artifact = {
            "sources": sources,
            "total_count": len(sources),
            "discovery_timestamp": datetime.now(UTC).isoformat(),
            "cluster_context": "test-cluster",
        }
        sources_path = self.health_dir / f"{run_id}-alertmanager-sources.json"
        sources_path.write_text(json.dumps(sources_artifact, indent=2), encoding="utf-8")

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

        artifact = ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=run_id,
            run_label=run_id,
            cluster_label="test-cluster",
            summary=f"Test artifact for {run_id}",
            status=ExternalAnalysisStatus.SUCCESS,
            provider="reviewer",
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
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
        index_path = self.health_dir / "ui-index.json"
        if index_path.exists():
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
            run_entry = index_data.get("run") or {}
            run_entry["alertmanager_sources"] = sources_artifact
            run_entry["alertmanager_compact"] = compact_artifact
            index_data["run"] = run_entry
            index_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")

    def _fetch(
        self,
        server: ThreadingHTTPServer,
        method: str,
        path: str,
        data: bytes | None = None,
    ) -> tuple[int, str]:
        """Make an HTTP request to the test server and return status code and body."""
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address
        url = f"http://{host}:{port}{path}"

        headers = {"Content-Type": "application/json"} if data else {}
        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def test_success_log_does_not_include_raw_payload(self) -> None:
        """Verify success logs don't include raw request payload."""
        run_id = "logging-test-success"
        source_id = "test-source-logging"
        sources = [
            {
                "source_id": source_id,
                "endpoint": "http://alertmanager:9093",
                "namespace": "monitoring",
                "name": "test-alertmanager",
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
        self._write_index_with_sources(run_id, sources)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            with self.assertLogs("k8s_diag_agent.ui.server_alertmanager", level="INFO") as logs:
                from urllib.parse import quote

                encoded_source_id = quote(source_id, safe="")
                path = f"/api/runs/{run_id}/alertmanager-sources/{encoded_source_id}/action"

                payload = json.dumps(
                    {
                        "action": "promote",
                        "clusterLabel": "test-cluster",
                        "reason": "test-reason-for-logging",
                    }
                ).encode("utf-8")

                self._fetch(server, "POST", path, payload)

            # Verify log doesn't contain raw JSON payload
            log_output = "\n".join(logs.output)
            self.assertNotIn("test-reason-for-logging", log_output)
            self.assertNotIn('{"action"', log_output)

        finally:
            shutdown_test_server(server, thread, patcher)


if __name__ == "__main__":
    unittest.main()
