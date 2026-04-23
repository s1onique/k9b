"""Tests for notification artifact identity (artifact_id field) and immutability."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from k8s_diag_agent.health.notifications import (
    NotificationArtifact,
    make_notification_artifact,
    write_notification_artifact,
)
from k8s_diag_agent.identity.artifact import new_artifact_id


def _make_artifact_with_timestamp(
    timestamp: str,
    kind: str = "test-kind",
    summary: str = "Test summary",
    details: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> NotificationArtifact:
    """Create a notification artifact with a controlled timestamp for testing immutability."""
    return NotificationArtifact(
        kind=kind,
        summary=summary,
        details=details or {"test": "data"},
        timestamp=timestamp,
        artifact_id=new_artifact_id(),
        run_id=run_id,
    )


class TestNotificationArtifactId(unittest.TestCase):
    """Tests for artifact_id field on NotificationArtifact."""

    def test_new_artifact_includes_artifact_id(self) -> None:
        """New notification artifact created via factory includes artifact_id."""
        artifact = make_notification_artifact(
            kind="test-kind",
            summary="Test summary",
            details={"key": "value"},
        )
        self.assertIsNotNone(artifact.artifact_id)
        self.assertIsInstance(artifact.artifact_id, str)
        assert artifact.artifact_id is not None
        self.assertGreater(len(artifact.artifact_id), 0)

    def test_artifact_id_format_is_uuid_like(self) -> None:
        """artifact_id should be UUID-like format (8-4-4-4-12)."""
        artifact = make_notification_artifact(
            kind="test-kind",
            summary="Test",
            details={},
        )
        assert artifact.artifact_id is not None
        parts = artifact.artifact_id.split("-")
        self.assertEqual(len(parts), 5)
        self.assertEqual(len(parts[0]), 8)
        self.assertEqual(len(parts[1]), 4)
        self.assertEqual(len(parts[2]), 4)
        self.assertEqual(len(parts[3]), 4)
        self.assertEqual(len(parts[4]), 12)

    def test_artifact_id_unique(self) -> None:
        """Multiple artifacts should have unique artifact_ids."""
        ids = {make_notification_artifact(kind="k", summary="s", details={}).artifact_id for _ in range(50)}
        self.assertEqual(len(ids), 50)

    def test_serialization_includes_artifact_id(self) -> None:
        """Serialized dict should include artifact_id when present."""
        artifact = make_notification_artifact(
            kind="degraded-health",
            summary="Cluster foo degraded",
            details={"warning": "memory pressure"},
        )
        data = artifact.to_dict()
        self.assertIn("artifact_id", data)
        self.assertEqual(data["artifact_id"], artifact.artifact_id)

    def test_roundtrip_preserves_artifact_id(self) -> None:
        """Serialization followed by deserialization preserves artifact_id."""
        original = make_notification_artifact(
            kind="proposal-created",
            summary="Proposal abc123 created",
            details={"target": "cluster-x"},
            run_id="run-456",
        )
        assert original.artifact_id is not None
        data = original.to_dict()
        restored = NotificationArtifact.from_dict(data)
        self.assertEqual(restored.artifact_id, original.artifact_id)
        self.assertEqual(restored.kind, original.kind)
        self.assertEqual(restored.summary, original.summary)
        self.assertEqual(restored.run_id, original.run_id)

    def test_backward_compat_deserializes_legacy_artifact_without_artifact_id(self) -> None:
        """Legacy notification artifact without artifact_id still deserializes successfully."""
        legacy_data = {
            "kind": "degraded-health",
            "summary": "Cluster bar degraded",
            "details": {"warnings": ["CPU spike"]},
            "run_id": "run-789",
            "cluster_label": "cluster-bar",
            "context": "us-east-1",
            "timestamp": "20260407T120000",
            # No artifact_id field - legacy artifact
        }
        artifact = NotificationArtifact.from_dict(legacy_data)
        self.assertIsNone(artifact.artifact_id)
        self.assertEqual(artifact.kind, "degraded-health")
        self.assertEqual(artifact.summary, "Cluster bar degraded")
        self.assertEqual(artifact.run_id, "run-789")

    def test_backward_compat_deserializes_artifact_with_null_artifact_id(self) -> None:
        """Notification artifact with null artifact_id deserializes as None."""
        data: dict[str, object] = {
            "kind": "info",
            "summary": "Health check complete",
            "details": {},
            "timestamp": "20260407T130000",
            "artifact_id": None,  # Explicit null
        }
        artifact = NotificationArtifact.from_dict(data)
        self.assertIsNone(artifact.artifact_id)

    def test_backward_compat_deserializes_artifact_with_empty_artifact_id(self) -> None:
        """Notification artifact with empty string artifact_id deserializes as None."""
        data = {
            "kind": "info",
            "summary": "Health check",
            "details": {},
            "timestamp": "20260407T140000",
            "artifact_id": "",  # Empty string
        }
        artifact = NotificationArtifact.from_dict(data)
        self.assertIsNone(artifact.artifact_id)

    def test_artifact_id_distinct_from_run_id(self) -> None:
        """artifact_id should be distinct from run_id."""
        artifact = make_notification_artifact(
            kind="suspicious-comparison",
            summary="Suspicious comparison",
            details={},
            run_id="run-abc-123",
        )
        assert artifact.artifact_id is not None
        self.assertNotEqual(artifact.artifact_id, artifact.run_id)
        # UUID format vs run_id format (they differ)
        self.assertNotRegex(artifact.run_id or "", r"^[0-9a-f]{8}-[0-9a-f]{4}")

    def test_artifact_id_distinct_from_timestamp(self) -> None:
        """artifact_id should be distinct from timestamp."""
        artifact = make_notification_artifact(
            kind="proposal-checked",
            summary="Proposal replayed",
            details={},
        )
        assert artifact.artifact_id is not None
        self.assertNotEqual(artifact.artifact_id, artifact.timestamp)
        # UUID format vs timestamp format (YYYYMMDDTHHMMSS)
        self.assertNotRegex(artifact.timestamp, r"^[0-9a-f]{8}-")

    def test_direct_instantiation_without_artifact_id(self) -> None:
        """Direct instantiation with explicit artifact_id=None sets it to None."""
        artifact = NotificationArtifact(
            kind="test",
            summary="Direct instantiation test",
            details={},
            timestamp="20260407T150000",
            artifact_id=None,
        )
        self.assertIsNone(artifact.artifact_id)
        data = artifact.to_dict()
        self.assertNotIn("artifact_id", data)

    def test_direct_instantiation_with_artifact_id(self) -> None:
        """Direct instantiation with explicit artifact_id sets it correctly."""
        explicit_id = new_artifact_id()
        artifact = NotificationArtifact(
            kind="test",
            summary="Direct instantiation with ID",
            details={},
            timestamp="20260407T160000",
            artifact_id=explicit_id,
        )
        self.assertEqual(artifact.artifact_id, explicit_id)
        data = artifact.to_dict()
        self.assertIn("artifact_id", data)
        self.assertEqual(data["artifact_id"], explicit_id)

    def test_factory_returns_distinct_ids_for_each_call(self) -> None:
        """Each call to make_notification_artifact returns a unique artifact_id."""
        ids = set()
        for _ in range(100):
            artifact = make_notification_artifact(
                kind="test",
                summary="Test",
                details={},
            )
            assert artifact.artifact_id is not None
            ids.add(artifact.artifact_id)
        self.assertEqual(len(ids), 100)

    def test_write_notification_artifact_persists_artifact_id(self) -> None:
        """write_notification_artifact writes artifact with artifact_id to disk."""
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "runs" / "health" / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            artifact = make_notification_artifact(
                kind="external-analysis",
                summary="Analysis complete",
                details={"tool": "kubectl"},
                run_id="run-write-test",
            )
            assert artifact.artifact_id is not None
            original_id = artifact.artifact_id

            path = write_notification_artifact(notifications_dir, artifact)
            self.assertTrue(path.is_file())

            # Read back and verify artifact_id is preserved
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("artifact_id", raw)
            self.assertEqual(raw["artifact_id"], original_id)

            restored = NotificationArtifact.from_dict(raw)
            self.assertEqual(restored.artifact_id, original_id)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestNotificationArtifactImmutability(unittest.TestCase):
    """Tests for notification artifact immutability guardrail.

    Notification artifacts are immutable: once written, they must not be overwritten.
    This class tests the immutability contract enforced by write_notification_artifact().
    """

    def test_write_notification_artifact_succeeds_normally(self) -> None:
        """Writing a notification artifact to a new path succeeds."""
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            artifact = _make_artifact_with_timestamp(
                timestamp="20260423T120000",
                kind="degraded-health",
                summary="Cluster degraded",
                details={"warnings": ["CPU spike"]},
                run_id="run-immutability-001",
            )

            path = write_notification_artifact(notifications_dir, artifact)

            self.assertTrue(path.exists())
            # Filename includes artifact_id since artifact has one
            self.assertTrue(path.name.startswith("20260423T120000-degraded-health-"))
            self.assertTrue(path.name.endswith(".json"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_immutability_rejects_overwrite_same_path(self) -> None:
        """Attempting to write an artifact with the same artifact_id again raises FileExistsError.

        This test verifies that immutability is enforced via artifact_id uniqueness.
        With the fix, same-second same-kind with distinct artifact_ids succeeds,
        but same artifact_id still raises FileExistsError.
        """
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            # Create two artifacts with the SAME artifact_id (identical identity)
            shared_artifact_id = new_artifact_id()

            artifact1 = NotificationArtifact(
                timestamp="20260423T120000",
                kind="proposal-created",
                summary="First proposal",
                details={"target": "cluster-a"},
                run_id="run-immutability-002",
                artifact_id=shared_artifact_id,
            )

            artifact2 = NotificationArtifact(
                timestamp="20260423T120000",
                kind="proposal-created",
                summary="Second proposal (should fail)",
                details={"target": "cluster-b"},
                run_id="run-immutability-002",
                artifact_id=shared_artifact_id,  # Same artifact_id = same artifact
            )

            # First write succeeds
            path1 = write_notification_artifact(notifications_dir, artifact1)
            self.assertTrue(path1.exists())

            # Second write with same artifact_id raises FileExistsError
            with self.assertRaises(FileExistsError) as context:
                write_notification_artifact(notifications_dir, artifact2)

            self.assertIn("already exists", str(context.exception))
            self.assertIn("immutability contract violated", str(context.exception))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_immutability_distinct_path_succeeds(self) -> None:
        """A distinct notification artifact with different timestamp writes successfully.

        This verifies that immutability doesn't block normal operation - different
        artifacts with different paths should write without conflict.
        """
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            # First artifact
            artifact1 = _make_artifact_with_timestamp(
                timestamp="20260423T120000",
                kind="degraded-health",
                summary="First notification",
                run_id="run-immutability-003",
            )

            # Second artifact with different timestamp (different path)
            artifact2 = _make_artifact_with_timestamp(
                timestamp="20260423T120001",
                kind="degraded-health",
                summary="Second notification",
                run_id="run-immutability-003",
            )

            path1 = write_notification_artifact(notifications_dir, artifact1)
            path2 = write_notification_artifact(notifications_dir, artifact2)

            self.assertTrue(path1.exists())
            self.assertTrue(path2.exists())
            self.assertNotEqual(path1, path2)

            # Verify both files contain correct content
            content1 = json.loads(path1.read_text(encoding="utf-8"))
            content2 = json.loads(path2.read_text(encoding="utf-8"))

            self.assertEqual(content1["summary"], "First notification")
            self.assertEqual(content2["summary"], "Second notification")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_immutability_distinct_kind_succeeds(self) -> None:
        """Artifacts with same timestamp but different kinds write successfully.

        Different kinds produce different filenames, so they don't conflict.
        """
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            artifact1 = _make_artifact_with_timestamp(
                timestamp="20260423T120000",
                kind="degraded-health",
                summary="Health issue",
                run_id="run-immutability-004",
            )

            artifact2 = _make_artifact_with_timestamp(
                timestamp="20260423T120000",
                kind="suspicious-comparison",
                summary="Comparison issue",
                run_id="run-immutability-004",
            )

            path1 = write_notification_artifact(notifications_dir, artifact1)
            path2 = write_notification_artifact(notifications_dir, artifact2)

            self.assertTrue(path1.exists())
            self.assertTrue(path2.exists())
            self.assertNotEqual(path1, path2)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_immutability_error_message_includes_path_context(self) -> None:
        """FileExistsError message includes timestamp, kind, and artifact_id for debugging."""
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            # Create artifact with controlled timestamp
            artifact1 = _make_artifact_with_timestamp(
                timestamp="20260423T120000",
                kind="external-analysis",
                summary="First analysis",
                run_id="run-immutability-005",
            )

            # Create second artifact with SAME artifact_id to trigger collision
            artifact2 = NotificationArtifact(
                timestamp="20260423T120000",
                kind="external-analysis",
                summary="Duplicate analysis",
                details={},
                run_id="run-immutability-005",
                artifact_id=artifact1.artifact_id,  # Same artifact_id = same path
            )

            write_notification_artifact(notifications_dir, artifact1)

            with self.assertRaises(FileExistsError) as context:
                write_notification_artifact(notifications_dir, artifact2)

            error_msg = str(context.exception)
            # Error should mention immutability
            self.assertIn("immutability contract violated", error_msg)
            # Error should include the artifact_id in context
            self.assertIn(artifact1.artifact_id, error_msg)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_backward_compat_normal_flow_unchanged(self) -> None:
        """Normal notification flows remain backward compatible.

        This test verifies that the immutability guard doesn't break
        the standard notification writing pattern where each notification
        gets a unique timestamp.
        """
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            # Simulate a normal notification flow with multiple notifications
            # each having a different timestamp
            timestamps = [
                ("20260423T120000", "degraded-health", "Cluster A degraded"),
                ("20260423T120001", "degraded-health", "Cluster B degraded"),
                ("20260423T120002", "proposal-created", "Proposal X created"),
                ("20260423T120003", "external-analysis", "Analysis complete"),
            ]

            written_paths = []
            for timestamp, kind, summary in timestamps:
                artifact = _make_artifact_with_timestamp(
                    timestamp=timestamp,
                    kind=kind,
                    summary=summary,
                    run_id="run-backward-compat",
                )
                path = write_notification_artifact(notifications_dir, artifact)
                written_paths.append(path)

            # All paths should exist
            for path in written_paths:
                self.assertTrue(path.exists())

            # Should have 4 distinct files
            self.assertEqual(len(written_paths), 4)
            self.assertEqual(len(set(written_paths)), 4)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestHealthLoopRunnerNotificationPath(unittest.TestCase):
    """Regression tests for the real notification recording path in HealthLoopRunner.

    This tests the actual call path from health/loop.py that was failing:
    _record_notification(directory, artifact) -> write_notification_artifact(directory, artifact)

    These tests exercise the fix through the real implementation, not just the artifact layer.
    """

    def test_record_notification_handles_same_second_same_kind(self) -> None:
        """HealthLoopRunner._record_notification handles same-second same-kind notifications.

        This is the real call-path regression test for the scheduler crash:
        - The health loop creates degraded-health notifications for multiple clusters
        - When two clusters degrade in the same second, they have the same timestamp
        - The fix ensures they have distinct artifact_ids, so they don't collide
        """
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            # Import the actual _record_notification method from HealthLoopRunner
            from k8s_diag_agent.health.loop import HealthLoopRunner
            from k8s_diag_agent.health.notifications import (
                NotificationArtifact,
                make_notification_artifact,
            )

            # Create two degraded-health notifications with same timestamp (simulating
            # two clusters becoming degraded in the same second during health loop)
            artifact1 = make_notification_artifact(
                kind="degraded-health",
                summary="cluster-a degraded (warning)",
                details={"warnings": ["CPU pressure"], "cluster": "cluster-a"},
                run_id="run-call-path-001",
                cluster_label="cluster-a",
            )
            artifact2 = make_notification_artifact(
                kind="degraded-health",
                summary="cluster-b degraded (warning)",
                details={"warnings": ["memory pressure"], "cluster": "cluster-b"},
                run_id="run-call-path-001",
                cluster_label="cluster-b",
            )

            # Force same timestamp to simulate same-second event
            artifact1 = NotificationArtifact(
                kind=artifact1.kind,
                summary=artifact1.summary,
                details=artifact1.details,
                run_id=artifact1.run_id,
                cluster_label=artifact1.cluster_label,
                context=artifact1.context,
                timestamp="20260423T081258",  # Same timestamp as artifact2
                artifact_id=artifact1.artifact_id,  # Distinct ID
            )
            artifact2 = NotificationArtifact(
                kind=artifact2.kind,
                summary=artifact2.summary,
                details=artifact2.details,
                run_id=artifact2.run_id,
                cluster_label=artifact2.cluster_label,
                context=artifact2.context,
                timestamp="20260423T081258",  # Same timestamp as artifact1
                artifact_id=artifact2.artifact_id,  # Distinct ID
            )

            # Use HealthLoopRunner._record_notification (the real failing path)
            # Initialize required attributes that __init__ would set
            runner = HealthLoopRunner.__new__(HealthLoopRunner)
            runner._notification_records = []  # Required by _record_notification

            path1 = runner._record_notification(notifications_dir, artifact1)
            path2 = runner._record_notification(notifications_dir, artifact2)

            # Both files should exist and be distinct
            self.assertTrue(path1.exists())
            self.assertTrue(path2.exists())
            self.assertNotEqual(path1, path2)

            # Content should be correct
            content1 = json.loads(path1.read_text(encoding="utf-8"))
            content2 = json.loads(path2.read_text(encoding="utf-8"))
            self.assertEqual(content1["summary"], "cluster-a degraded (warning)")
            self.assertEqual(content2["summary"], "cluster-b degraded (warning)")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_record_notification_rejects_true_duplicate(self) -> None:
        """HealthLoopRunner._record_notification rejects writes with same artifact_id.

        Even through the real call path, true duplicates (same artifact_id)
        should still raise FileExistsError to preserve immutability.
        """
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            from k8s_diag_agent.health.loop import HealthLoopRunner
            from k8s_diag_agent.health.notifications import NotificationArtifact

            # Create artifact with explicit artifact_id
            shared_id = "shared-artifact-id-999"
            artifact1 = NotificationArtifact(
                kind="degraded-health",
                summary="First notification",
                details={"cluster": "cluster-x"},
                run_id="run-call-path-002",
                cluster_label="cluster-x",
                timestamp="20260423T120000",
                artifact_id=shared_id,
            )
            artifact2 = NotificationArtifact(
                kind="degraded-health",
                summary="Duplicate notification",
                details={"cluster": "cluster-y"},
                run_id="run-call-path-002",
                cluster_label="cluster-y",
                timestamp="20260423T120000",
                artifact_id=shared_id,  # Same artifact_id = same identity
            )

            runner = HealthLoopRunner.__new__(HealthLoopRunner)
            runner._notification_records = []  # Required by _record_notification
            path1 = runner._record_notification(notifications_dir, artifact1)
            self.assertTrue(path1.exists())

            # Second write should raise FileExistsError
            with self.assertRaises(FileExistsError):
                runner._record_notification(notifications_dir, artifact2)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestNotificationArtifactIdempotencyFix(unittest.TestCase):
    """Regression tests for the same-second same-kind notification collision fix.

    These tests verify that notification artifacts with the same timestamp and kind
    can coexist when they have unique artifact_ids, preventing scheduler crashes
    in multi-cluster scenarios where multiple clusters become degraded in the same second.
    """

    def test_same_second_same_kind_with_artifact_ids_succeeds(self) -> None:
        """Two same-second same-kind notifications with distinct artifact_ids write successfully.

        This is the core regression test for the collision fix. When two clusters
        become degraded in the same second, they should produce distinct filenames
        based on their unique artifact_ids.
        """
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            # Create two artifacts with same timestamp and kind (simulating two clusters
            # becoming degraded in the same second)
            artifact1 = make_notification_artifact(
                kind="degraded-health",
                summary="Cluster A degraded",
                details={"cluster": "cluster-a"},
                run_id="run-regression-001",
            )
            artifact2 = make_notification_artifact(
                kind="degraded-health",
                summary="Cluster B degraded",
                details={"cluster": "cluster-b"},
                run_id="run-regression-001",
            )

            # Ensure they have the same timestamp (simulating same-second event)
            # by setting timestamps directly (bypass the factory's auto-timestamp)
            artifact1 = NotificationArtifact(
                kind=artifact1.kind,
                summary=artifact1.summary,
                details=artifact1.details,
                run_id=artifact1.run_id,
                cluster_label=artifact1.cluster_label,
                context=artifact1.context,
                timestamp="20260423T081258",  # Same timestamp
                artifact_id=artifact1.artifact_id,  # Distinct IDs
            )
            artifact2 = NotificationArtifact(
                kind=artifact2.kind,
                summary=artifact2.summary,
                details=artifact2.details,
                run_id=artifact2.run_id,
                cluster_label=artifact2.cluster_label,
                context=artifact2.context,
                timestamp="20260423T081258",  # Same timestamp
                artifact_id=artifact2.artifact_id,  # Distinct IDs
            )

            # Both writes should succeed
            path1 = write_notification_artifact(notifications_dir, artifact1)
            path2 = write_notification_artifact(notifications_dir, artifact2)

            # Both files should exist
            self.assertTrue(path1.exists())
            self.assertTrue(path2.exists())

            # Filenames should be different
            self.assertNotEqual(path1, path2)

            # Both should contain correct content
            content1 = json.loads(path1.read_text(encoding="utf-8"))
            content2 = json.loads(path2.read_text(encoding="utf-8"))
            self.assertEqual(content1["summary"], "Cluster A degraded")
            self.assertEqual(content2["summary"], "Cluster B degraded")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_filename_includes_artifact_id_when_available(self) -> None:
        """Notification artifact filenames include artifact_id suffix when present."""
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            artifact = make_notification_artifact(
                kind="degraded-health",
                summary="Test notification",
                details={},
                run_id="run-filename-test",
            )

            path = write_notification_artifact(notifications_dir, artifact)

            # Filename should include artifact_id
            self.assertIn(artifact.artifact_id, path.name)
            self.assertIn(artifact.timestamp, path.name)
            self.assertIn(artifact.kind, path.name)
            self.assertTrue(path.name.endswith(".json"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_legacy_artifact_without_artifact_id_uses_original_filename(self) -> None:
        """Legacy artifacts without artifact_id use the original {timestamp}-{kind}.json format."""
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            # Create artifact without artifact_id (legacy style)
            artifact = NotificationArtifact(
                kind="degraded-health",
                summary="Legacy notification",
                details={},
                run_id="run-legacy",
                timestamp="20260423T081258",
                artifact_id=None,  # Legacy artifact
            )

            path = write_notification_artifact(notifications_dir, artifact)

            # Filename should NOT include artifact_id
            self.assertEqual(path.name, "20260423T081258-degraded-health.json")
            self.assertNotIn("-", path.name.split(".")[0].split("-")[-1])  # Last segment shouldn't be UUID
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_immutability_error_message_includes_artifact_id(self) -> None:
        """FileExistsError includes artifact_id in context when artifact_id is present."""
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            # Create artifact with controlled timestamp and explicit artifact_id
            artifact1 = NotificationArtifact(
                timestamp="20260423T120000",
                kind="degraded-health",
                summary="First notification",
                details={},
                run_id="run-error-msg",
                artifact_id="test-artifact-id-12345",
            )

            # Write first artifact
            write_notification_artifact(notifications_dir, artifact1)

            # Try to write again with same artifact_id (should fail)
            artifact2 = NotificationArtifact(
                timestamp="20260423T120000",
                kind="degraded-health",
                summary="Duplicate notification",
                details={},
                run_id="run-error-msg",
                artifact_id="test-artifact-id-12345",  # Same artifact_id
            )

            with self.assertRaises(FileExistsError) as context:
                write_notification_artifact(notifications_dir, artifact2)

            error_msg = str(context.exception)
            # Should include immutability contract violation
            self.assertIn("immutability contract violated", error_msg)
            # Should include artifact_id in context for debugging
            self.assertIn("test-artifact-id-12345", error_msg)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_multiple_same_second_degraded_health_notifications(self) -> None:
        """Simulate multiple clusters becoming degraded in the same second (scheduler scenario)."""
        tmpdir = Path(tempfile.mkdtemp())
        try:
            notifications_dir = tmpdir / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            clusters = ["cluster-a", "cluster-b", "cluster-c"]
            written_paths = []

            # Simulate scheduler health loop: three clusters become degraded in same second
            for cluster in clusters:
                artifact = make_notification_artifact(
                    kind="degraded-health",
                    summary=f"{cluster} degraded (warning)",
                    details={"warnings": ["CPU pressure"], "cluster": cluster},
                    run_id="run-scheduler-001",
                    cluster_label=cluster,
                )
                # Force same timestamp to simulate same-second event
                artifact = NotificationArtifact(
                    kind=artifact.kind,
                    summary=artifact.summary,
                    details=artifact.details,
                    run_id=artifact.run_id,
                    cluster_label=artifact.cluster_label,
                    context=artifact.context,
                    timestamp="20260423T081258",  # Same timestamp
                    artifact_id=artifact.artifact_id,  # Unique IDs
                )
                path = write_notification_artifact(notifications_dir, artifact)
                written_paths.append(path)

            # All three files should exist
            for path in written_paths:
                self.assertTrue(path.exists())

            # Should have 3 distinct files
            self.assertEqual(len(written_paths), 3)
            self.assertEqual(len(set(written_paths)), 3)

            # Verify content
            for i, cluster in enumerate(clusters):
                content = json.loads(written_paths[i].read_text(encoding="utf-8"))
                self.assertEqual(content["summary"], f"{cluster} degraded (warning)")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
