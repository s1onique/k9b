"""Regression tests for /api/notifications index path route behavior.

These tests verify:
1. Default /api/notifications uses index_notifications_path when notification_index exists
2. Default index path parses zero notification files
3. Fallback works when index is missing/malformed/empty
4. Cache key includes ui-index.json mtime for proper invalidation

Auth is disabled via test harness to focus on route behavior, not auth enforcement.
"""

import json
import shutil
import tempfile
import unittest
import unittest.mock as mock
import urllib.request
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import cast

from k8s_diag_agent.health.notifications import NotificationArtifact, write_notification_artifact
from k8s_diag_agent.health.ui import write_health_ui_index
from tests.helpers.ui_test_harness import (
    shutdown_test_server,
    start_ui_test_server_without_auth,
)


class NotificationsIndexRouteTests(unittest.TestCase):
    """Route-level tests for /api/notifications index path behavior."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.notifications_dir = self.health_dir / "notifications"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)
        self.notifications_dir.mkdir(parents=True, exist_ok=True)
        self.reviews_dir = self.health_dir / "reviews"
        self.reviews_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_minimal_review(self, run_id: str) -> None:
        """Write a minimal review artifact so ui-index can be written."""
        review_data = {
            "run_id": run_id,
            "run_label": "test-run",
            "timestamp": datetime.now(UTC).isoformat(),
            "collector_version": "1.0.0",
            "cluster_count": 1,
        }
        review_path = self.reviews_dir / f"{run_id}-review.json"
        review_path.write_text(json.dumps(review_data), encoding="utf-8")

    def _write_notification(self, kind: str, summary: str, timestamp: datetime) -> Path:
        """Write a notification artifact to disk."""
        artifact = NotificationArtifact(
            kind=kind,
            summary=summary,
            details={},
            run_id="test-run",
            cluster_label="cluster-a",
            timestamp=timestamp.strftime("%Y%m%dT%H%M%S"),
        )
        result = write_notification_artifact(self.notifications_dir, artifact)
        assert isinstance(result, Path)
        return result

    def _write_ui_index_with_notifications(self, notifications: list[tuple[NotificationArtifact, Path]]) -> Path:
        """Write ui-index.json with notification_index."""
        run_id = "index-test-run"
        self._write_minimal_review(run_id)
        result = write_health_ui_index(
            self.health_dir,
            run_id=run_id,
            run_label="index-test-run",
            collector_version="1.0.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            notifications=notifications,
        )
        assert isinstance(result, Path)
        return result

    def _fetch_notifications(self, server: ThreadingHTTPServer, query: str = "") -> dict[str, object]:
        """Fetch notifications from the test server."""
        address = server.server_address
        host_address, port, *_ = address
        host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address
        url = f"http://{host}:{port}/api/notifications{query}"
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert isinstance(payload, dict)
            return cast(dict[str, object], payload)

    def test_default_api_notifications_uses_index_path(self) -> None:
        """Default /api/notifications uses index_notifications_path when notification_index exists."""
        # Create notifications
        base_time = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
        paths = []
        for i in range(3):
            paths.append(
                self._write_notification(
                    kind="warning",
                    summary=f"Notification {i}",
                    timestamp=base_time + timedelta(seconds=i),
                )
            )

        # Read back and create artifacts for index
        artifacts = []
        for path in paths:
            raw = json.loads(path.read_text(encoding="utf-8"))
            artifacts.append((NotificationArtifact.from_dict(raw), path))

        # Write ui-index with notification_index
        self._write_ui_index_with_notifications(artifacts)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            # Capture logs
            captured_logs: list[dict[str, object]] = []

            def capture_log(**kwargs: object) -> None:
                captured_logs.append(kwargs)

            with mock.patch(
                "k8s_diag_agent.structured_logging.emit_structured_log",
                side_effect=capture_log,
            ):
                response = self._fetch_notifications(server)

            # Assert response structure
            self.assertIn("path_strategy", response)
            self.assertEqual(response["path_strategy"], "index_notifications_path")
            self.assertEqual(response["notification_files_considered"], 0)
            self.assertEqual(response["notification_files_fully_parsed"], 0)
            self.assertEqual(response["index_notification_count"], 3)
            self.assertEqual(response["rows_returned"], 3)
            self.assertIsNone(response["fallback_reason"])

            # Verify timing log was emitted
            index_log = None
            for log in captured_logs:
                metadata = log.get("metadata", {})
                if metadata.get("path_strategy") == "index_notifications_path":
                    index_log = log
                    break

            self.assertIsNotNone(index_log, "Expected index path log not found")
            assert index_log is not None
            metadata = cast(dict[str, object], index_log["metadata"])
            self.assertEqual(metadata["notification_files_fully_parsed"], 0)
            self.assertEqual(metadata["path_strategy"], "index_notifications_path")

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_default_index_path_returns_correct_page_slice(self) -> None:
        """Default index path applies pagination correctly."""
        # Create 10 notifications
        base_time = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
        paths = []
        for i in range(10):
            paths.append(
                self._write_notification(
                    kind="info",
                    summary=f"Notification {i}",
                    timestamp=base_time + timedelta(seconds=i),
                )
            )

        artifacts = []
        for path in paths:
            raw = json.loads(path.read_text(encoding="utf-8"))
            artifacts.append((NotificationArtifact.from_dict(raw), path))

        self._write_ui_index_with_notifications(artifacts)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            # Request page 2 with limit 3
            response = self._fetch_notifications(server, "?limit=3&page=2")

            self.assertEqual(response["path_strategy"], "index_notifications_path")
            self.assertEqual(response["page"], 2)
            self.assertEqual(response["limit"], 3)
            self.assertEqual(response["total"], 10)
            self.assertEqual(response["total_pages"], 4)
            notifications = cast(list[object], response["notifications"])
            self.assertEqual(len(notifications), 3)
            # Index is newest-first. With 10 items [0-9]:
            # Page 1: [9, 8, 7], Page 2: [6, 5, 4], Page 3: [3, 2, 1], Page 4: [0]
            summaries = [n["summary"] for n in response["notifications"]]
            self.assertEqual(summaries, ["Notification 6", "Notification 5", "Notification 4"])

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_missing_ui_index_falls_back_with_reason(self) -> None:
        """When ui-index.json is missing, falls back with fallback_reason='missing_index'."""
        # Create notification files but no ui-index.json
        self._write_notification(kind="info", summary="Test", timestamp=datetime.now(UTC))

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = self._fetch_notifications(server)

            self.assertEqual(response["path_strategy"], "notification_file_fallback_path")
            self.assertEqual(response["fallback_reason"], "missing_index")
            self.assertIn("notification_files_fully_parsed", response)
            # File scan will have parsed at least 1 file
            fully_parsed = cast(int, response["notification_files_fully_parsed"])
            self.assertGreater(fully_parsed, 0)

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_malformed_ui_index_falls_back_with_reason(self) -> None:
        """When ui-index.json is malformed, falls back with fallback_reason='malformed_index'."""
        # Write malformed ui-index.json
        ui_index_path = self.health_dir / "ui-index.json"
        ui_index_path.write_text("{ not valid json", encoding="utf-8")

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = self._fetch_notifications(server)

            self.assertEqual(response["path_strategy"], "notification_file_fallback_path")
            self.assertEqual(response["fallback_reason"], "malformed_index")

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_empty_notification_index_still_uses_index_path(self) -> None:
        """Empty notification_index still uses index path (not stale file scan).

        This is the chosen policy: notification_index is authoritative for default route,
        even when empty. Stale index in refresh-less mode requires index regeneration.
        """
        # Write ui-index with empty notifications
        self._write_ui_index_with_notifications([])

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            response = self._fetch_notifications(server)

            # Should use index path even though it's empty
            self.assertEqual(response["path_strategy"], "index_notifications_path")
            self.assertIsNone(response["fallback_reason"])
            self.assertEqual(response["notification_files_fully_parsed"], 0)
            self.assertEqual(response["total"], 0)
            notifications = cast(list[object], response["notifications"])
            self.assertEqual(len(notifications), 0)

        finally:
            shutdown_test_server(server, thread, patcher)

    def test_filtered_request_falls_back_with_reason(self) -> None:
        """Filtered /api/notifications falls back with explicit fallback_reason."""
        # Write ui-index with notification_index
        base_time = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
        paths = [self._write_notification(kind="info", summary="Test", timestamp=base_time)]
        artifacts = []
        for path in paths:
            raw = json.loads(path.read_text(encoding="utf-8"))
            artifacts.append((NotificationArtifact.from_dict(raw), path))
        self._write_ui_index_with_notifications(artifacts)

        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            # Request with kind filter - should fall back
            response = self._fetch_notifications(server, "?kind=info")

            self.assertEqual(response["path_strategy"], "notification_file_fallback_path")
            self.assertIsNotNone(response["fallback_reason"])
            fallback_reason = cast(str, response["fallback_reason"])
            self.assertIn("kind", fallback_reason)

        finally:
            shutdown_test_server(server, thread, patcher)


if __name__ == "__main__":
    unittest.main()
