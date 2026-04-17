"""Regression tests for past-run status hydration.

Verifies that browsing past runs (via run_id query parameter) correctly
hydrates the reviewEnrichmentStatus field from run-scoped config, matching
the behavior of the latest-run path.
"""

import json
import shutil
import tempfile
import threading
import unittest
import unittest.mock as mock
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import cast

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
    ExternalAnalysisPurpose,
)
from k8s_diag_agent.health.ui import write_health_ui_index
from k8s_diag_agent.ui.server import HealthUIRequestHandler


class PastRunStatusHydrationTests(unittest.TestCase):
    """Regression tests for past-run reviewEnrichmentStatus hydration."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _start_server(self) -> tuple[ThreadingHTTPServer, threading.Thread]:
        from functools import partial
        handler = partial(
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

    def _fetch_run_payload(self, server: ThreadingHTTPServer, run_id: str) -> dict:
        import urllib.request
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address
        url = f"http://{host}:{port}/api/run?run_id={run_id}"
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert isinstance(payload, dict)
            return cast(dict, payload)

    def test_past_run_without_enrichment_artifact_derives_status_from_config(self) -> None:
        """Verify past-run status is derived from review artifact config when no enrichment artifact exists.

        This is the core regression test for the bug where browse-older-runs would show
        reviewEnrichmentStatus: null even when the run had enrichment configured.
        """
        # Create a "current" (latest) run that will be the default
        latest_run_id = "latest-run"
        latest_artifact = ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=latest_run_id,
            run_label=latest_run_id,
            cluster_label="primary",
            summary="Latest run",
            status=ExternalAnalysisStatus.SUCCESS,
            provider="reviewer",
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={
                "triageOrder": [],
                "topConcerns": [],
                "evidenceGaps": [],
                "nextChecks": [],
                "focusNotes": [],
            },
        )
        # Mock adapters to skip LLM calls
        with mock.patch(
            "k8s_diag_agent.health.ui._collect_historical_external_analysis_entries",
            return_value=[],
        ):
            write_health_ui_index(
                self.health_dir,
                run_id=latest_run_id,
                run_label=latest_run_id,
                collector_version="tests",
                records=(),
                assessments=(),
                drilldowns=(),
                proposals=(),
                external_analysis=(latest_artifact,),
                notifications=(),
                available_adapters=(),
            )

        # Create a past run WITHOUT an enrichment artifact but WITH config
        past_run_id = "past-run-2024"
        past_run_timestamp = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Create the review artifact for the past run with external_analysis_settings
        reviews_dir = self.health_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_artifact_path = reviews_dir / f"{past_run_id}-review.json"
        review_artifact = {
            "run_id": past_run_id,
            "run_label": f"Run {past_run_id}",
            "timestamp": past_run_timestamp.isoformat(),
            "collector_version": "1.0.0",
            "selected_drilldowns": [
                {
                    "label": "cluster-a",
                    "context": "prod",
                    "node_count": 5,
                    "warning_event_count": 2,
                    "non_running_pod_count": 1,
                    "missing_evidence": [],
                    "reasons": ["MemoryPressure"],
                }
            ],
            "external_analysis_settings": {
                "review_enrichment": {
                    "enabled": True,
                    "provider": "test-provider",
                }
            },
            # No enrichment artifact - this is the key scenario being tested
        }
        review_artifact_path.write_text(json.dumps(review_artifact), encoding="utf-8")

        # Also create drilldown artifact for the past run
        drilldowns_dir = self.health_dir / "drilldowns"
        drilldowns_dir.mkdir(parents=True, exist_ok=True)
        drilldown_artifact = {
            "run_id": past_run_id,
            "cluster_label": "cluster-a",
            "timestamp": past_run_timestamp.isoformat(),
            "findings": [],
        }
        (drilldowns_dir / f"{past_run_id}-cluster-a-drilldown.json").write_text(
            json.dumps(drilldown_artifact), encoding="utf-8"
        )

        # Start server and fetch the past run
        server, thread = self._start_server()
        try:
            # Fetch the past run specifically (not the latest)
            past_run_payload = self._fetch_run_payload(server, past_run_id)
        finally:
            self._shutdown_server(server, thread)

        # The key assertion: reviewEnrichmentStatus should NOT be null
        # It should be derived from the config in the review artifact
        review_enrichment_status = past_run_payload.get("reviewEnrichmentStatus")
        self.assertIsNotNone(
            review_enrichment_status,
            "reviewEnrichmentStatus should not be null for past runs with config. "
            f"Got payload: {json.dumps(past_run_payload, indent=2)}",
        )

        # Verify it's a valid status dict with expected fields
        # The run is enabled but no artifact exists, so status should be "not-attempted"
        assert isinstance(review_enrichment_status, dict)
        self.assertEqual(review_enrichment_status["status"], "not-attempted")
        self.assertTrue(review_enrichment_status["policyEnabled"])
        self.assertTrue(review_enrichment_status["runEnabled"])
        self.assertEqual(review_enrichment_status["runProvider"], "test-provider")

        # Verify reviewEnrichment is still None (no artifact)
        review_enrichment = past_run_payload.get("reviewEnrichment")
        self.assertIsNone(review_enrichment)

    def test_past_run_with_disabled_enrichment_shows_not_configured(self) -> None:
        """Verify past-run status correctly shows 'not configured' when enrichment is disabled."""
        past_run_id = "past-run-disabled"

        # Create latest run first
        latest_run_id = "latest"
        with mock.patch(
            "k8s_diag_agent.health.ui._collect_historical_external_analysis_entries",
            return_value=[],
        ):
            write_health_ui_index(
                self.health_dir,
                run_id=latest_run_id,
                run_label=latest_run_id,
                collector_version="tests",
                records=(),
                assessments=(),
                drilldowns=(),
                proposals=(),
                external_analysis=(),
                notifications=(),
                available_adapters=(),
            )

        # Create past run with enrichment DISABLED
        reviews_dir = self.health_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_artifact = {
            "run_id": past_run_id,
            "run_label": f"Run {past_run_id}",
            "timestamp": datetime(2024, 2, 1, tzinfo=UTC).isoformat(),
            "collector_version": "1.0.0",
            "selected_drilldowns": [
                {"label": "cluster-a", "context": "prod"}
            ],
            "external_analysis_settings": {
                "review_enrichment": {
                    "enabled": False,
                }
            },
        }
        (reviews_dir / f"{past_run_id}-review.json").write_text(
            json.dumps(review_artifact), encoding="utf-8"
        )

        # Create drilldown artifact
        drilldowns_dir = self.health_dir / "drilldowns"
        drilldowns_dir.mkdir(parents=True, exist_ok=True)
        (drilldowns_dir / f"{past_run_id}-cluster-a-drilldown.json").write_text(
            json.dumps({"run_id": past_run_id}), encoding="utf-8"
        )

        server, thread = self._start_server()
        try:
            past_run_payload = self._fetch_run_payload(server, past_run_id)
        finally:
            self._shutdown_server(server, thread)

        # Status should show "disabled-for-run" since enrichment was disabled for this specific run
        review_enrichment_status = past_run_payload.get("reviewEnrichmentStatus")
        self.assertIsNotNone(review_enrichment_status)
        assert isinstance(review_enrichment_status, dict)
        # The status should indicate enrichment was disabled for this specific run
        self.assertEqual(review_enrichment_status["status"], "disabled-for-run")
        self.assertFalse(review_enrichment_status["runEnabled"])

    def test_latest_run_with_enrichment_artifact_has_null_status(self) -> None:
        """Verify latest run with enrichment artifact gets null status (artifact carries the info).

        For the latest run, when an enrichment artifact exists, the status field
        is intentionally None because the status is embedded in the artifact itself
        (e.g., artifact.status = "success").
        
        This is a sanity check to ensure the fix doesn't change existing behavior.
        """
        latest_run_id = "latest-test"
        latest_artifact = ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=latest_run_id,
            run_label=latest_run_id,
            cluster_label="primary",
            summary="Latest",
            status=ExternalAnalysisStatus.SUCCESS,
            provider="reviewer",
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={},
        )
        with mock.patch(
            "k8s_diag_agent.health.ui._collect_historical_external_analysis_entries",
            return_value=[],
        ):
            write_health_ui_index(
                self.health_dir,
                run_id=latest_run_id,
                run_label=latest_run_id,
                collector_version="tests",
                records=(),
                assessments=(),
                drilldowns=(),
                proposals=(),
                external_analysis=(latest_artifact,),
                notifications=(),
                available_adapters=(),
            )

        server, thread = self._start_server()
        try:
            # Fetch without run_id - should use the latest
            address = server.server_address
            host_address, port, *_ = address
            host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address
            url = f"http://{host}:{port}/api/run"
            import urllib.request
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            self._shutdown_server(server, thread)

        # Latest run should have the enrichment ARTIFACT (not just status)
        review_enrichment = payload.get("reviewEnrichment")
        self.assertIsNotNone(review_enrichment, "Latest run should have reviewEnrichment artifact")

        # reviewEnrichmentStatus is intentionally None when artifact exists
        # because the status is embedded in the artifact itself.
        # This is the existing behavior we must NOT break.
        review_enrichment_status = payload.get("reviewEnrichmentStatus")
        self.assertIsNone(
            review_enrichment_status,
            "reviewEnrichmentStatus should be None when artifact exists "
            "(status is in the artifact itself)",
        )

        # Verify the artifact has the status info
        assert isinstance(review_enrichment, dict)
        self.assertEqual(review_enrichment.get("status"), "success")

    def test_past_run_with_malformed_enrichment_config_survives(self) -> None:
        """Verify past-run API survives malformed external_analysis_settings.review_enrichment.

        Regression test for Gap 1: malformed nested config should not crash the API.
        This tests that when review_enrichment is a non-dict value (e.g., "bogus"),
        the status is treated as unknown rather than crashing.
        """
        past_run_id = "past-run-malformed"

        # Create latest run first
        latest_run_id = "latest"
        with mock.patch(
            "k8s_diag_agent.health.ui._collect_historical_external_analysis_entries",
            return_value=[],
        ):
            write_health_ui_index(
                self.health_dir,
                run_id=latest_run_id,
                run_label=latest_run_id,
                collector_version="tests",
                records=(),
                assessments=(),
                drilldowns=(),
                proposals=(),
                external_analysis=(),
                notifications=(),
                available_adapters=(),
            )

        # Create past run with MALFORMED enrichment config - "review_enrichment" is a string, not a dict
        reviews_dir = self.health_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_artifact = {
            "run_id": past_run_id,
            "run_label": f"Run {past_run_id}",
            "timestamp": datetime(2024, 3, 1, tzinfo=UTC).isoformat(),
            "collector_version": "1.0.0",
            "selected_drilldowns": [
                {"label": "cluster-a", "context": "prod"}
            ],
            # Malformed: "review_enrichment" is a string instead of a dict
            "external_analysis_settings": {
                "review_enrichment": "bogus"  # type: ignore[dict-item]
            },
        }
        (reviews_dir / f"{past_run_id}-review.json").write_text(
            json.dumps(review_artifact), encoding="utf-8"
        )

        # Create drilldown artifact
        drilldowns_dir = self.health_dir / "drilldowns"
        drilldowns_dir.mkdir(parents=True, exist_ok=True)
        (drilldowns_dir / f"{past_run_id}-cluster-a-drilldown.json").write_text(
            json.dumps({"run_id": past_run_id}), encoding="utf-8"
        )

        server, thread = self._start_server()
        try:
            past_run_payload = self._fetch_run_payload(server, past_run_id)
        finally:
            self._shutdown_server(server, thread)

        # The API should succeed without crashing
        self.assertIsNotNone(past_run_payload)

        # reviewEnrichmentStatus should be None (unknown) since malformed config
        # is treated as absent - this is safe behavior
        review_enrichment_status = past_run_payload.get("reviewEnrichmentStatus")
        self.assertIsNone(
            review_enrichment_status,
            "Malformed nested config should result in None status (treated as unknown)"
        )

        # reviewEnrichment should also be None (no artifact)
        review_enrichment = past_run_payload.get("reviewEnrichment")
        self.assertIsNone(review_enrichment)


if __name__ == "__main__":
    unittest.main()
