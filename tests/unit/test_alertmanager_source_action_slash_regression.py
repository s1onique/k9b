"""Regression test for alertmanager source action with slash-containing source_id.

Bug: source_id values like 'crd:monitoring/kube-prometheus-stack-alertmanager' contain
a slash that was being interpreted as a URL path separator, causing 404 errors.

Fix: source_id is now read from the request body instead of the URL path.

See: https://starlette.dev/routing/ - path params default to [^/]+ (no slashes)
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
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
from tests.helpers.ui_test_harness import (
    shutdown_test_server,
    start_ui_test_server_without_auth,
)


class AlertmanagerSourceSlashRegressionTest(unittest.TestCase):
    """Regression test: source_id with slash must work via body-based API."""

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
        sources: list[dict],
    ) -> None:
        """Write health UI index with alertmanager sources."""
        self.health_dir.mkdir(parents=True, exist_ok=True)

        (self.health_dir / "reviews").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "assessments").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "proposals").mkdir(parents=True, exist_ok=True)
        (self.health_dir / "external-analysis").mkdir(parents=True, exist_ok=True)

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
            "cluster_context": "k3s-infra-prod",
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
            "affected_clusters": ["k3s-infra-prod"],
            "affected_services": [],
            "truncated": False,
            "captured_at": datetime.now(UTC).isoformat(),
        }
        compact_path = self.health_dir / f"{run_id}-alertmanager-compact.json"
        compact_path.write_text(json.dumps(compact_artifact, indent=2), encoding="utf-8")

        artifact = ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=run_id,
            run_label=run_id,
            cluster_label="k3s-infra-prod",
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

    def test_promote_source_id_with_slash(self) -> None:
        """Test that source_id containing a slash can be promoted.

        This is the exact failing case from production:
        source_id = 'crd:monitoring/kube-prometheus-stack-alertmanager'

        The slash was being interpreted as a URL path separator, causing 404.
        Now source_id is in the request body, so slashes work fine.
        """
        run_id = "health-run-20260708T075740Z"
        source_id = "crd:monitoring/kube-prometheus-stack-alertmanager"
        sources = [
            {
                "source_id": source_id,
                "endpoint": "http://alertmanager-operated.monitoring:9093",
                "namespace": "monitoring",
                "name": "kube-prometheus-stack-alertmanager",
                "origin": "alertmanager-crd",
                "state": "discovered",
                "canonical_identity": "monitoring/kube-prometheus-stack-alertmanager",
                "matching_key": "http://alertmanager-operated.monitoring:9093",
                "discovered_at": "2026-07-08T07:57:40Z",
                "verified_at": "2026-07-08T07:58:00Z",
                "last_check": "2026-07-08T08:00:00Z",
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
            import urllib.error
            import urllib.request

            address = server.server_address
            host_address, port, *_ = address
            host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address

            # Use body-based API: source_id is now in the request body
            url = f"http://{host}:{port}/api/runs/{run_id}/alertmanager-sources/action"
            payload = json.dumps({
                "sourceId": source_id,
                "action": "promote",
                "clusterLabel": "k3s-infra-prod",
                "reason": "Test regression for slash-containing source_id",
            }).encode("utf-8")

            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
                self.assertEqual(result.get("status"), "success")
                self.assertEqual(result.get("sourceId"), source_id)
                self.assertEqual(result.get("action"), "promote")
        finally:
            shutdown_test_server(server, thread, patcher)

    def test_disable_source_id_with_slash(self) -> None:
        """Test that source_id containing a slash can be disabled."""
        run_id = "health-run-20260708T075740Z"
        source_id = "service:monitoring/kube-prometheus-stack"
        sources = [
            {
                "source_id": source_id,
                "endpoint": "http://alertmanager.monitoring:9093",
                "namespace": "monitoring",
                "name": "kube-prometheus-stack",
                "origin": "service-heuristic",
                "state": "auto-tracked",
                "canonical_identity": "monitoring/kube-prometheus-stack",
                "matching_key": "http://alertmanager.monitoring:9093",
                "discovered_at": "2026-07-08T07:57:40Z",
                "verified_at": "2026-07-08T07:58:00Z",
                "last_check": "2026-07-08T08:00:00Z",
                "last_error": None,
                "verified_version": "0.27.0",
                "confidence_hints": ["service_discovery"],
            },
        ]

        self._write_index_with_sources(run_id, sources)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            import urllib.error
            import urllib.request

            address = server.server_address
            host_address, port, *_ = address
            host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address

            url = f"http://{host}:{port}/api/runs/{run_id}/alertmanager-sources/action"
            payload = json.dumps({
                "sourceId": source_id,
                "action": "disable",
                "clusterLabel": "k3s-infra-prod",
                "reason": "Test regression for slash-containing source_id",
            }).encode("utf-8")

            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
                self.assertEqual(result.get("status"), "success")
                self.assertEqual(result.get("sourceId"), source_id)
                self.assertEqual(result.get("action"), "disable")
        finally:
            shutdown_test_server(server, thread, patcher)


if __name__ == "__main__":
    unittest.main()
