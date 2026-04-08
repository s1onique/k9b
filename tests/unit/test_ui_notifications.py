import shutil
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from k8s_diag_agent.health.notifications import NotificationArtifact, write_notification_artifact
from k8s_diag_agent.ui.notifications import DEFAULT_NOTIFICATION_LIMIT, query_notifications


class UINotificationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs" / "health"
        self.notifications_dir = self.runs_dir / "notifications"
        self.notifications_dir.mkdir(parents=True, exist_ok=True)

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
    ) -> None:
        artifact = NotificationArtifact(
            kind=kind,
            summary=summary,
            details=details or {},
            run_id=run_id,
            cluster_label=cluster_label,
            context=context,
            timestamp=timestamp.strftime("%Y%m%dT%H%M%S"),
        )
        write_notification_artifact(self.notifications_dir, artifact)

    def test_filters_by_kind_and_cluster_label(self) -> None:
        base_time = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
        self._write_notification(
            kind="warning",
            cluster_label="cluster-a",
            summary="CPU spike",
            timestamp=base_time,
            run_id="run-a",
        )
        self._write_notification(
            kind="warning",
            cluster_label="cluster-b",
            summary="Memory pressure",
            timestamp=base_time + timedelta(minutes=1),
            run_id="run-b",
        )
        self._write_notification(
            kind="info",
            cluster_label="cluster-b",
            summary="Health check",
            timestamp=base_time + timedelta(minutes=2),
            run_id="run-c",
        )
        payload = query_notifications(self.runs_dir, kind="warning", cluster_label="cluster-b")
        notifications = payload["notifications"]
        self.assertEqual(payload["total"], 1)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["summary"], "Memory pressure")

    def test_search_matches_summary_and_details(self) -> None:
        base_time = datetime(2026, 4, 7, 13, 0, 0, tzinfo=UTC)
        self._write_notification(
            kind="warning",
            cluster_label="cluster-z",
            summary="Database latency",
            timestamp=base_time,
            run_id="run-z",
            details={"target": "db"},
        )
        payload = query_notifications(self.runs_dir, search="DB")
        self.assertEqual(payload["total"], 1)
        notifications = payload["notifications"]
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["summary"], "Database latency")

    def test_limits_results_and_reports_total(self) -> None:
        base_time = datetime(2026, 4, 7, 14, 0, 0, tzinfo=UTC)
        for idx in range(55):
            self._write_notification(
                kind="info",
                cluster_label="cluster-x",
                summary=f"Entry {idx}",
                timestamp=base_time + timedelta(seconds=idx),
                run_id=f"run-{idx}",
            )
        payload = query_notifications(self.runs_dir)
        self.assertEqual(payload["total"], 55)
        self.assertEqual(len(payload["notifications"]), 50)
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["limit"], DEFAULT_NOTIFICATION_LIMIT)
        self.assertEqual(payload["total_pages"], 2)

    def test_pagination_returns_expected_slice(self) -> None:
        base_time = datetime(2026, 4, 7, 15, 0, 0, tzinfo=UTC)
        total_items = 60
        for idx in range(total_items):
            self._write_notification(
                kind="info",
                cluster_label="cluster-y",
                summary=f"Entry {idx}",
                timestamp=base_time + timedelta(seconds=idx),
                run_id=f"run-{idx}",
            )
        payload = query_notifications(self.runs_dir, limit=20, page=2)
        self.assertEqual(payload["total"], total_items)
        self.assertEqual(payload["page"], 2)
        self.assertEqual(payload["limit"], 20)
        self.assertEqual(payload["total_pages"], 3)
        self.assertEqual(len(payload["notifications"]), 20)
        self.assertEqual(payload["notifications"][0]["summary"], "Entry 39")
        self.assertEqual(payload["notifications"][-1]["summary"], "Entry 20")
