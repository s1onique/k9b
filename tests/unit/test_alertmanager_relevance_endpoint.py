"""Tests for the POST /api/alertmanager-relevance-feedback endpoint handler.

These tests exercise the actual HTTP endpoint using a test server, covering:
1. Valid request → review artifact created
2. Invalid request → 400 response
3. Source execution artifact unchanged (immutability)
4. Persisted review visible after re-read through normal server path
"""

import functools
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisPurpose,
)
from k8s_diag_agent.ui.server import HealthUIRequestHandler


class TestAlertmanagerRelevanceFeedbackEndpoint(unittest.TestCase):
    """Real HTTP endpoint tests for POST /api/alertmanager-relevance-feedback."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True, exist_ok=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)

        # Write minimal ui-index.json for server to initialize
        ui_index = {
            "run": {
                "run_id": "test-run",
                "run_label": "Test Run",
            }
        }
        (self.health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

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

    def _create_execution_artifact(
        self,
        run_id: str,
        index: int,
        alertmanager_provenance: dict[str, Any] | None = None,
    ) -> tuple[Path, str]:
        """Create a mock execution artifact.

        Returns tuple of (artifact_path, relative_path) where relative_path is
        relative to runs_dir (for use in API calls).
        """
        artifact_data: dict[str, object] = {
            "purpose": "next-check-execution",
            "run_id": run_id,
            "cluster_label": "cluster-a",
            "status": "success",
            "tool_name": "kubectl",
            "summary": "Test execution",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if alertmanager_provenance:
            artifact_data["alertmanager_provenance"] = alertmanager_provenance

        artifact_path = self.external_dir / f"{run_id}-next-check-execution-{index}.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")
        # Relative path from runs_dir (what the API expects)
        relative_path = str(artifact_path.relative_to(self.runs_dir))
        return artifact_path, relative_path

    def _post_alertmanager_feedback(
        self,
        server: ThreadingHTTPServer,
        payload: dict,
    ) -> tuple[int, dict]:
        """Send POST request to alertmanager-relevance-feedback endpoint."""
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/alertmanager-relevance-feedback"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.getcode(), json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_valid_request_creates_review_artifact(self) -> None:
        """Test that a valid request creates an immutable review artifact."""
        run_id = "test-valid"
        artifact_path, relative_path = self._create_execution_artifact(run_id, 0)

        server, thread = self._start_server()
        try:
            code, response = self._post_alertmanager_feedback(
                server,
                {
                    "artifactPath": relative_path,
                    "alertmanagerRelevance": "relevant",
                    "alertmanagerRelevanceSummary": "Alertmanager was helpful",
                },
            )

            self.assertEqual(code, 200)
            self.assertEqual(response["status"], "success")
            self.assertIn("reviewArtifactPath", response)

            # Verify review artifact was created (review path is relative to health_dir)
            review_path = self.health_dir / response["reviewArtifactPath"]
            self.assertTrue(review_path.exists(), f"Review path {review_path} does not exist")

            # Verify review artifact content
            review_data = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual(review_data["purpose"], ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value)
            self.assertEqual(review_data["alertmanager_relevance"], "relevant")
            self.assertEqual(review_data["alertmanager_relevance_summary"], "Alertmanager was helpful")
            self.assertIn("reviewed_at", review_data)
        finally:
            self._shutdown_server(server, thread)

    def test_source_execution_artifact_unchanged(self) -> None:
        """Test that source execution artifact is NOT modified when review is created."""
        run_id = "test-immutability"
        artifact_path, relative_path = self._create_execution_artifact(run_id, 0)
        original_content = artifact_path.read_text(encoding="utf-8")

        server, thread = self._start_server()
        try:
            code, response = self._post_alertmanager_feedback(
                server,
                {
                    "artifactPath": relative_path,
                    "alertmanagerRelevance": "not_relevant",
                },
            )

            self.assertEqual(code, 200)

            # Source artifact should be unchanged
            current_content = artifact_path.read_text(encoding="utf-8")
            self.assertEqual(current_content, original_content)

            # Review artifact should be separate (review path is relative to health_dir)
            review_path = self.health_dir / response["reviewArtifactPath"]
            self.assertTrue(review_path.exists(), f"Review path {review_path} does not exist")
            self.assertNotEqual(review_path, artifact_path)
        finally:
            self._shutdown_server(server, thread)

    def test_invalid_relevance_class_returns_400(self) -> None:
        """Test that invalid alertmanagerRelevance returns 400."""
        run_id = "test-invalid-class"
        _, relative_path = self._create_execution_artifact(run_id, 0)

        server, thread = self._start_server()
        try:
            code, response = self._post_alertmanager_feedback(
                server,
                {
                    "artifactPath": relative_path,
                    "alertmanagerRelevance": "invalid_class",
                },
            )

            self.assertEqual(code, 400)
            self.assertIn("error", response)
            self.assertIn("Invalid alertmanagerRelevance", response["error"])
        finally:
            self._shutdown_server(server, thread)

    def test_missing_artifact_path_returns_400(self) -> None:
        """Test that missing artifactPath returns 400."""
        server, thread = self._start_server()
        try:
            code, response = self._post_alertmanager_feedback(
                server,
                {
                    "alertmanagerRelevance": "relevant",
                },
            )

            self.assertEqual(code, 400)
            self.assertIn("error", response)
            self.assertIn("artifactPath is required", response["error"])
        finally:
            self._shutdown_server(server, thread)

    def test_missing_relevance_returns_400(self) -> None:
        """Test that missing alertmanagerRelevance returns 400."""
        run_id = "test-missing-relevance"
        _, relative_path = self._create_execution_artifact(run_id, 0)

        server, thread = self._start_server()
        try:
            code, response = self._post_alertmanager_feedback(
                server,
                {
                    "artifactPath": relative_path,
                },
            )

            self.assertEqual(code, 400)
            self.assertIn("error", response)
            self.assertIn("alertmanagerRelevance is required", response["error"])
        finally:
            self._shutdown_server(server, thread)

    def test_nonexistent_artifact_returns_404(self) -> None:
        """Test that non-existent artifact path returns 404."""
        server, thread = self._start_server()
        try:
            code, response = self._post_alertmanager_feedback(
                server,
                {
                    "artifactPath": "external-analysis/nonexistent.json",
                    "alertmanagerRelevance": "relevant",
                },
            )

            self.assertEqual(code, 404)
            self.assertIn("error", response)
            self.assertIn("not found", response["error"].lower())
        finally:
            self._shutdown_server(server, thread)

    def test_invalid_json_returns_400(self) -> None:
        """Test that invalid JSON returns 400."""
        server, thread = self._start_server()
        try:
            port = server.server_address[1]
            url = f"http://127.0.0.1:{port}/api/alertmanager-relevance-feedback"
            data = b"not valid json"
            req = urllib.request.Request(
                url,
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, 400)
        finally:
            self._shutdown_server(server, thread)

    def test_empty_body_returns_400(self) -> None:
        """Test that empty body returns 400."""
        server, thread = self._start_server()
        try:
            port = server.server_address[1]
            url = f"http://127.0.0.1:{port}/api/alertmanager-relevance-feedback"
            req = urllib.request.Request(
                url,
                data=b"",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, 400)
        finally:
            self._shutdown_server(server, thread)

    def test_preserves_server_owned_provenance(self) -> None:
        """Test that review artifact preserves server-owned provenance from execution."""
        run_id = "test-provenance"
        provenance = {
            "matchedDimensions": ["namespace"],
            "matchedValues": {"namespace": ["monitoring"]},
            "alertmanagerSource": "prometheus",
        }
        artifact_path, relative_path = self._create_execution_artifact(run_id, 0, alertmanager_provenance=provenance)

        server, thread = self._start_server()
        try:
            code, response = self._post_alertmanager_feedback(
                server,
                {
                    "artifactPath": relative_path,
                    "alertmanagerRelevance": "noisy",
                    "alertmanagerRelevanceSummary": "Too much noise",
                },
            )

            self.assertEqual(code, 200)

            # Verify provenance is preserved in review artifact (review path is relative to health_dir)
            review_path = self.health_dir / response["reviewArtifactPath"]
            self.assertTrue(review_path.exists(), f"Review path {review_path} does not exist")
            review_data = json.loads(review_path.read_text(encoding="utf-8"))

            self.assertIn("alertmanager_provenance", review_data)
            self.assertEqual(review_data["alertmanager_provenance"], provenance)
        finally:
            self._shutdown_server(server, thread)

    def test_review_visible_after_reload_through_discovery(self) -> None:
        """Test that persisted review is discoverable after reload."""
        from k8s_diag_agent.ui.server_read_support import _load_alertmanager_review_artifacts

        run_id = "test-reload"
        provenance = {"matchedDimensions": ["namespace"]}
        artifact_path, relative_path = self._create_execution_artifact(run_id, 0, alertmanager_provenance=provenance)

        server, thread = self._start_server()
        try:
            # Create review through endpoint
            code, response = self._post_alertmanager_feedback(
                server,
                {
                    "artifactPath": relative_path,
                    "alertmanagerRelevance": "not_relevant",
                    "alertmanagerRelevanceSummary": "Not helpful for this namespace",
                },
            )
            self.assertEqual(code, 200)

            # Discover the review (as UI projection would)
            reviews = _load_alertmanager_review_artifacts(self.external_dir, run_id)

            # The source_artifact in the review is relative to health_root (external-analysis/...)
            # But the key in reviews_by_source is also external-analysis/...
            source_artifact = str(artifact_path.relative_to(self.health_dir))

            # Verify review is discoverable
            self.assertIn(source_artifact, reviews, f"Expected {source_artifact} in {reviews.keys()}")
            discovered = reviews[source_artifact]
            self.assertEqual(discovered["alertmanager_relevance"], "not_relevant")
            self.assertEqual(discovered["alertmanager_relevance_summary"], "Not helpful for this namespace")
        finally:
            self._shutdown_server(server, thread)

    def test_review_visible_in_merged_history_after_reload(self) -> None:
        """Test that review is visible in merged execution history after reload."""
        from k8s_diag_agent.ui.server_read_support import (
            _load_alertmanager_review_artifacts,
            _merge_alertmanager_review_into_history_entry,
        )

        run_id = "test-merged-reload"
        provenance = {"matchedDimensions": ["cluster"]}
        artifact_path, relative_path = self._create_execution_artifact(run_id, 0, alertmanager_provenance=provenance)

        server, thread = self._start_server()
        try:
            # Create review through endpoint
            code, response = self._post_alertmanager_feedback(
                server,
                {
                    "artifactPath": relative_path,
                    "alertmanagerRelevance": "noisy",
                    "alertmanagerRelevanceSummary": "Too many false positives",
                },
            )
            self.assertEqual(code, 200)

            # Discover and merge (as UI projection would)
            reviews = _load_alertmanager_review_artifacts(self.external_dir, run_id)

            # The source_artifact key is relative to health_dir
            source_artifact = str(artifact_path.relative_to(self.health_dir))
            review = reviews.get(source_artifact)

            # Create entry with source_artifact as the key (what execution history uses)
            execution_entry: dict[str, Any] = {
                "artifactPath": source_artifact,  # Use source_artifact as key
                "timestamp": "2026-04-26T14:00:00Z",
                "status": "success",
            }

            merged = _merge_alertmanager_review_into_history_entry(execution_entry, review)

            # Verify all expected fields in merged entry
            self.assertEqual(merged["alertmanagerRelevance"], "noisy")
            self.assertEqual(merged["alertmanagerRelevanceSummary"], "Too many false positives")
            self.assertIn("alertmanagerReviewedAt", merged)
            self.assertIn("alertmanagerReviewArtifactPath", merged)
        finally:
            self._shutdown_server(server, thread)

    def test_all_valid_relevance_classes_accepted(self) -> None:
        """Test that all 4 valid relevance classes are accepted."""
        valid_classes = ["relevant", "not_relevant", "noisy", "unsure"]

        for relevance_class in valid_classes:
            # Clean up from previous iteration
            for f in self.external_dir.glob("*-alertmanager-review-*.json"):
                f.unlink()

            run_id = f"test-{relevance_class}"
            _, relative_path = self._create_execution_artifact(run_id, 0)

            server, thread = self._start_server()
            try:
                code, response = self._post_alertmanager_feedback(
                    server,
                    {
                        "artifactPath": relative_path,
                        "alertmanagerRelevance": relevance_class,
                    },
                )

                self.assertEqual(code, 200, f"Failed for class: {relevance_class}")
                self.assertEqual(response["alertmanagerRelevance"], relevance_class)

                # Verify review artifact was created (review path is relative to health_dir)
                review_path = self.health_dir / response["reviewArtifactPath"]
                self.assertTrue(review_path.exists(), f"Review path {review_path} does not exist")
            finally:
                self._shutdown_server(server, thread)

    def test_review_does_not_require_summary(self) -> None:
        """Test that review creation works without optional summary."""
        run_id = "test-no-summary"
        _, relative_path = self._create_execution_artifact(run_id, 0)

        server, thread = self._start_server()
        try:
            code, response = self._post_alertmanager_feedback(
                server,
                {
                    "artifactPath": relative_path,
                    "alertmanagerRelevance": "relevant",
                    # No alertmanagerRelevanceSummary
                },
            )

            self.assertEqual(code, 200)
            self.assertIsNone(response.get("alertmanagerRelevanceSummary"))

            # Verify review artifact was created without summary (review path is relative to health_dir)
            review_path = self.health_dir / response["reviewArtifactPath"]
            self.assertTrue(review_path.exists(), f"Review path {review_path} does not exist")
            review_data = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertIsNone(review_data.get("alertmanager_relevance_summary"))
        finally:
            self._shutdown_server(server, thread)


if __name__ == "__main__":
    unittest.main()
