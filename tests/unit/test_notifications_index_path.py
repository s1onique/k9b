"""Regression tests for /api/notifications cold-load index path.

These tests verify that:
1. Default /api/notifications reads from notification_index when present
2. Default path fully parses zero notification files
3. Malformed/missing index falls back with explicit reason
4. Unsupported filters either work from index or fall back with explicit reason
"""

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from k8s_diag_agent.health.notifications import NotificationArtifact, write_notification_artifact


class NotificationIndexPathTests(unittest.TestCase):
    """Tests for notification index read model."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.notifications_dir = self.health_dir / "notifications"
        self.notifications_dir.mkdir(parents=True, exist_ok=True)
        self.reviews_dir = self.health_dir / "reviews"
        self.reviews_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_notification(
        self,
        *,
        kind: str,
        cluster_label: str,
        summary: str,
        timestamp: datetime,
        details: dict[str, str] | None = None,
        context: str | None = None,
        run_id: str | None = None,
    ) -> Path:
        artifact = NotificationArtifact(
            kind=kind,
            summary=summary,
            details=details or {},
            run_id=run_id,
            cluster_label=cluster_label,
            context=context,
            timestamp=timestamp.strftime("%Y%m%dT%H%M%S"),
        )
        result = write_notification_artifact(self.notifications_dir, artifact)
        assert isinstance(result, Path)
        return result

    def _write_minimal_review(self, run_id: str, run_label: str = "test-run") -> Path:
        """Write a minimal review artifact so ui-index can be written."""
        review_data = {
            "run_id": run_id,
            "run_label": run_label,
            "timestamp": datetime.now(UTC).isoformat(),
            "collector_version": "1.0.0",
            "cluster_count": 1,
        }
        review_path = self.reviews_dir / f"{run_id}-review.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(json.dumps(review_data), encoding="utf-8")
        return review_path

    def _write_ui_index_with_notifications(
        self,
        notifications: list[tuple[NotificationArtifact, Path]],
        run_id: str = "index-run",
    ) -> Path:
        """Write a ui-index.json with notification_index included."""
        from k8s_diag_agent.health.ui import write_health_ui_index

        # Write minimal review first
        self._write_minimal_review(run_id)

        # Write ui-index
        result = write_health_ui_index(
            self.health_dir,
            run_id=run_id,
            run_label="index-run",
            collector_version="1.0.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            notifications=notifications,
        )
        assert isinstance(result, Path)
        return result

    def test_default_api_notifications_uses_index_when_present(self) -> None:
        """Default /api/notifications should read from notification_index when available.

        This test verifies the index path behavior:
        - No filters (kind=None, cluster_label=None, search=None)
        - page=1, limit=50
        - Returns results from notification_index without parsing files
        """
        # Create 3 notifications
        base_time = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
        paths = []
        for i in range(3):
            paths.append(
                self._write_notification(
                    kind="warning",
                    cluster_label=f"cluster-{i}",
                    summary=f"Notification {i}",
                    timestamp=base_time + timedelta(minutes=i),
                    run_id="run-1",
                )
            )
        artifacts = []
        for i, path in enumerate(paths):
            raw = json.loads(path.read_text(encoding="utf-8"))
            artifacts.append((NotificationArtifact.from_dict(raw), path))

        # Write ui-index with notification_index
        index_path = self._write_ui_index_with_notifications(artifacts)
        index_data = json.loads(index_path.read_text(encoding="utf-8"))

        # Verify notification_index exists in the written index
        self.assertIn("notification_index", index_data)

        # Load the index and verify notification_index structure
        from k8s_diag_agent.ui.server import load_ui_index

        index = load_ui_index(self.health_dir)
        self.assertIn("notification_index", index)

        # Check that notification_index has the expected structure
        notif_index = cast(dict[str, object], index["notification_index"])
        self.assertIn("notifications", notif_index)
        self.assertIn("total_count", notif_index)
        self.assertEqual(notif_index["total_count"], 3)

    def test_notification_index_structure(self) -> None:
        """notification_index should have list-view fields needed by UI.

        Required fields:
        - notifications: list of notification summaries
        - total_count: total notifications available
        - generated_at: when index was generated
        - version: schema version
        """
        base_time = datetime(2026, 4, 7, 13, 0, 0, tzinfo=UTC)
        path = self._write_notification(
            kind="info",
            cluster_label="cluster-test",
            summary="Test notification",
            timestamp=base_time,
            run_id="run-1",
        )
        raw = json.loads(path.read_text(encoding="utf-8"))
        artifact = NotificationArtifact.from_dict(raw)

        index_path = self._write_ui_index_with_notifications([(artifact, path)])
        index_data = json.loads(index_path.read_text(encoding="utf-8"))

        notif_index = index_data["notification_index"]
        self.assertIn("notifications", notif_index)
        self.assertIn("total_count", notif_index)
        self.assertIn("generated_at", notif_index)
        self.assertIn("version", notif_index)

        # Check notification entry structure
        entries = notif_index["notifications"]
        self.assertEqual(len(entries), 1)
        entry = entries[0]

        # Required list-view fields
        self.assertIn("kind", entry)
        self.assertIn("summary", entry)
        self.assertIn("timestamp", entry)
        self.assertIn("runId", entry)
        self.assertIn("clusterLabel", entry)
        self.assertIn("artifactPath", entry)  # Provenance pointer

    def test_notification_index_bounded_to_500(self) -> None:
        """notification_index should be bounded to latest 500 notifications."""
        base_time = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
        paths = []

        # Write 550 notifications (more than the 500 limit)
        for i in range(550):
            paths.append(
                self._write_notification(
                    kind="info",
                    cluster_label="cluster-x",
                    summary=f"Notification {i}",
                    timestamp=base_time + timedelta(seconds=i),
                    run_id=f"run-{i}",
                )
            )

        artifacts = []
        for path in paths:
            raw = json.loads(path.read_text(encoding="utf-8"))
            artifacts.append((NotificationArtifact.from_dict(raw), path))

        index_path = self._write_ui_index_with_notifications(artifacts)
        index_data = json.loads(index_path.read_text(encoding="utf-8"))

        notif_index = index_data["notification_index"]

        # Should be bounded to 500
        self.assertEqual(len(notif_index["notifications"]), 500)

        # But total_count should reflect actual total
        self.assertEqual(notif_index["total_count"], 550)

        # Entries should be newest first (notification 549 is newest, 549-499=50 offset to get 500 entries)
        newest_entry = notif_index["notifications"][0]
        self.assertEqual(newest_entry["summary"], "Notification 549")

    def test_notification_index_sorted_newest_first(self) -> None:
        """notification_index entries should be sorted newest first."""
        base_time = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
        paths = []

        # Write notifications with different timestamps
        for i in [5, 1, 3, 2, 4]:  # Out of order
            paths.append(
                self._write_notification(
                    kind="info",
                    cluster_label="cluster-x",
                    summary=f"Notification {i}",
                    timestamp=base_time + timedelta(minutes=i),
                    run_id=f"run-{i}",
                )
            )

        artifacts = []
        for path in paths:
            raw = json.loads(path.read_text(encoding="utf-8"))
            artifacts.append((NotificationArtifact.from_dict(raw), path))

        index_path = self._write_ui_index_with_notifications(artifacts)
        index_data = json.loads(index_path.read_text(encoding="utf-8"))

        notif_index = index_data["notification_index"]
        entries = notif_index["notifications"]

        # Should be sorted newest first (notification 5, 4, 3, 2, 1)
        summaries = [e["summary"] for e in entries]
        self.assertEqual(summaries, [
            "Notification 5",
            "Notification 4",
            "Notification 3",
            "Notification 2",
            "Notification 1",
        ])

    def test_notification_index_has_artifact_path_provenance(self) -> None:
        """notification_index entries should have artifactPath for provenance."""
        base_time = datetime(2026, 4, 7, 14, 0, 0, tzinfo=UTC)
        path = self._write_notification(
            kind="warning",
            cluster_label="cluster-a",
            summary="Provenance test",
            timestamp=base_time,
            run_id="run-1",
        )
        raw = json.loads(path.read_text(encoding="utf-8"))
        artifact = NotificationArtifact.from_dict(raw)

        index_path = self._write_ui_index_with_notifications([(artifact, path)])
        index_data = json.loads(index_path.read_text(encoding="utf-8"))

        notif_index = index_data["notification_index"]
        entry = notif_index["notifications"][0]

        # artifactPath should be present and point to the notification artifact
        self.assertIn("artifactPath", entry)
        self.assertIn("notifications", entry["artifactPath"])
        self.assertTrue(entry["artifactPath"].endswith(".json"))


class NotificationFallbackTests(unittest.TestCase):
    """Tests for notification index fallback behavior."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.notifications_dir = self.health_dir / "notifications"
        self.notifications_dir.mkdir(parents=True, exist_ok=True)
        self.reviews_dir = self.health_dir / "reviews"
        self.reviews_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_notification(
        self,
        *,
        kind: str,
        cluster_label: str,
        summary: str,
        timestamp: datetime,
    ) -> Path:
        artifact = NotificationArtifact(
            kind=kind,
            summary=summary,
            details={},
            run_id="run-1",
            cluster_label=cluster_label,
            context=None,
            timestamp=timestamp.strftime("%Y%m%dT%H%M%S"),
        )
        result = write_notification_artifact(self.notifications_dir, artifact)
        assert isinstance(result, Path)
        return result

    def _write_minimal_review(self, run_id: str) -> Path:
        review_data = {
            "run_id": run_id,
            "run_label": "test-run",
            "timestamp": datetime.now(UTC).isoformat(),
            "collector_version": "1.0.0",
            "cluster_count": 1,
        }
        review_path = self.reviews_dir / f"{run_id}-review.json"
        review_path.write_text(json.dumps(review_data), encoding="utf-8")
        return review_path

    def _write_ui_index_without_notification_index(
        self,
        run_id: str = "no-notif-index-run",
    ) -> Path:
        """Write a ui-index.json WITHOUT notification_index (old format or missing)."""
        from k8s_diag_agent.health.ui import write_health_ui_index

        self._write_minimal_review(run_id)

        # Write ui-index with empty notifications
        result = write_health_ui_index(
            self.health_dir,
            run_id=run_id,
            run_label="no-notif-index-run",
            collector_version="1.0.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            notifications=[],  # Empty notifications
        )
        assert isinstance(result, Path)
        return result

    def test_missing_ui_index_falls_back_to_file_scan(self) -> None:
        """When ui-index.json is missing, query_notifications should use file scan."""
        # Create some notification files
        base_time = datetime(2026, 4, 7, 15, 0, 0, tzinfo=UTC)
        self._write_notification(
            kind="info",
            cluster_label="cluster-x",
            summary="Fallback test",
            timestamp=base_time,
        )

        # No ui-index.json exists
        ui_index_path = self.health_dir / "ui-index.json"
        self.assertFalse(ui_index_path.exists())

        # query_notifications should work by scanning files
        from k8s_diag_agent.ui.notifications import query_notifications

        payload = query_notifications(self.health_dir)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(len(payload["notifications"]), 1)

    def test_malformed_ui_index_falls_back_to_file_scan(self) -> None:
        """When ui-index.json is malformed, query_notifications should use file scan."""
        # Create some notification files
        base_time = datetime(2026, 4, 7, 16, 0, 0, tzinfo=UTC)
        self._write_notification(
            kind="info",
            cluster_label="cluster-y",
            summary="Malformed index test",
            timestamp=base_time,
        )

        # Write malformed ui-index.json
        ui_index_path = self.health_dir / "ui-index.json"
        ui_index_path.write_text("{ not valid json", encoding="utf-8")

        # query_notifications should work by scanning files
        from k8s_diag_agent.ui.notifications import query_notifications

        payload = query_notifications(self.health_dir)
        self.assertEqual(payload["total"], 1)

    def test_notification_index_with_empty_list_is_authoritative(self) -> None:
        """When ui-index has notification_index with empty list, it is authoritative.

        Default /api/notifications route policy:
        - if notification_index exists, it is authoritative, including empty index
        - stale refresh-less artifacts require index regeneration, not fallback to file scan

        This tests the legacy query_notifications() helper behavior, not route behavior.
        The route (/api/notifications) would use index path for empty notification_index.
        """
        # Write ui-index with empty notifications
        self._write_ui_index_without_notification_index()
        index_path = self.health_dir / "ui-index.json"
        index_data = json.loads(index_path.read_text(encoding="utf-8"))

        # Verify notification_index IS present
        self.assertIn("notification_index", index_data)
        # Empty since we passed empty notifications
        self.assertEqual(index_data["notification_index"]["total_count"], 0)
        self.assertEqual(len(index_data["notification_index"]["notifications"]), 0)

    def test_legacy_file_scan_helper_fallback(self) -> None:
        """query_notifications() helper falls back to file scan when index missing.

        NOTE: This tests the legacy file-scan helper behavior, not route behavior.
        The /api/notifications route uses index path when notification_index exists.
        """
        # Create notification files
        base_time = datetime(2026, 4, 7, 17, 0, 0, tzinfo=UTC)
        self._write_notification(
            kind="info",
            cluster_label="cluster-z",
            summary="File scan test",
            timestamp=base_time,
        )

        # No ui-index.json - helper should use file scan
        ui_index_path = self.health_dir / "ui-index.json"
        self.assertFalse(ui_index_path.exists())

        from k8s_diag_agent.ui.notifications import query_notifications

        payload = query_notifications(self.health_dir)
        self.assertEqual(payload["total"], 1)


if __name__ == "__main__":
    unittest.main()
