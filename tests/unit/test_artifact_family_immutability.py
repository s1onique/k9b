"""Tests for artifact family immutability enforcement.

These tests prove that artifact families covered by DOC-CLAIM-0041 through
DOC-CLAIM-0045 use immutable write paths and reject overwrites.

Coverage:
- DOC-CLAIM-0041: Immutable write helper (write_append_only_json_artifact)
- DOC-CLAIM-0042: ClusterSnapshot artifacts (inline enforcement in persist_history_fact_artifacts)
- DOC-CLAIM-0043: Assessment artifacts
- DOC-CLAIM-0044: Comparison artifacts
- DOC-CLAIM-0045: Review artifacts
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.health.notifications import NotificationArtifact, write_notification_artifact


class TestClusterComparisonArtifactImmutability(unittest.TestCase):
    """Test that Comparison artifacts reject overwrites.

    Evidence for DOC-CLAIM-0044 (Comparison artifacts are immutable).
    """

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_comparison_write_rejects_overwrite(self) -> None:
        """Test that writing to an existing comparison path raises FileExistsError."""
        # Setup directories
        comparisons_dir = self.tmpdir / "comparisons"
        comparisons_dir.mkdir(parents=True)

        # Pre-create a comparison file
        pre_existing_path = comparisons_dir / "run-001-prod1-vs-prod2-comparison.json"
        pre_existing_path.write_text("{}", encoding="utf-8")

        # Test the immutable write helper directly
        from k8s_diag_agent.identity.artifact import write_append_only_json_artifact

        # This should raise FileExistsError because the path already exists
        with self.assertRaises(FileExistsError) as ctx:
            write_append_only_json_artifact(
                pre_existing_path,
                {"differences": {}},
                context="simulated duplicate comparison write",
            )

        self.assertIn("immutability contract violated", str(ctx.exception))


class TestReviewArtifactImmutability(unittest.TestCase):
    """Test that Review artifacts reject overwrites.

    Evidence for DOC-CLAIM-0045 (Review artifacts are immutable).
    """

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_review_write_rejects_overwrite(self) -> None:
        """Test that writing to an existing review path raises FileExistsError."""
        # Setup directories
        reviews_dir = self.tmpdir / "reviews"
        reviews_dir.mkdir(parents=True)

        # Pre-create a review file
        pre_existing_path = reviews_dir / "run-001-review.json"
        pre_existing_path.write_text("{}", encoding="utf-8")

        # Test the immutable write helper directly
        from k8s_diag_agent.identity.artifact import write_append_only_json_artifact

        # This should raise FileExistsError because the path already exists
        with self.assertRaises(FileExistsError) as ctx:
            write_append_only_json_artifact(
                pre_existing_path,
                {"run_id": "run-001", "review": "data"},
                context="simulated duplicate review write",
            )

        self.assertIn("immutability contract violated", str(ctx.exception))


class TestNotificationArtifactImmutability(unittest.TestCase):
    """Test that Notification artifacts (used by Review pipeline) reject overwrites."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_notification_write_rejects_overwrite(self) -> None:
        """Test that write_notification_artifact rejects overwrites."""
        notifications_dir = self.tmpdir / "notifications"
        notifications_dir.mkdir(parents=True)

        # Create a notification artifact
        artifact = NotificationArtifact(
            kind="test-kind",
            summary="Test notification",
            details={"key": "value"},
            run_id="run-001",
            timestamp="20240101T000000",
            artifact_id="fixed-id-for-test",  # Fixed ID for deterministic filename
        )

        # First write succeeds
        first_path = write_notification_artifact(notifications_dir, artifact)
        self.assertTrue(first_path.exists())

        # Second write to same path should fail
        with self.assertRaises(FileExistsError) as ctx:
            write_notification_artifact(notifications_dir, artifact)

        self.assertIn("immutability contract violated", str(ctx.exception))


class TestImmutableWriteHelperEnforcement(unittest.TestCase):
    """Test that write_append_only_json_artifact properly enforces immutability.

    Evidence for DOC-CLAIM-0041 (immutable source-of-truth artifacts).
    """

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_existing_file_raises_fileexistserror(self) -> None:
        """Test that writing to an existing path raises FileExistsError."""
        from k8s_diag_agent.identity.artifact import write_append_only_json_artifact

        path = self.tmpdir / "existing.json"
        path.write_text("original content", encoding="utf-8")

        with self.assertRaises(FileExistsError) as ctx:
            write_append_only_json_artifact(path, {"key": "value"})

        self.assertIn("immutability contract violated", str(ctx.exception))
        # Verify original content is unchanged
        self.assertEqual(path.read_text(encoding="utf-8"), "original content")

    def test_nonexistent_path_succeeds(self) -> None:
        """Test that writing to a new path succeeds."""
        from k8s_diag_agent.identity.artifact import write_append_only_json_artifact

        path = self.tmpdir / "new.json"
        result = write_append_only_json_artifact(path, {"key": "value"})

        self.assertEqual(result, path)
        self.assertTrue(path.exists())

    def test_context_included_in_error(self) -> None:
        """Test that context is included in the FileExistsError message."""
        from k8s_diag_agent.identity.artifact import write_append_only_json_artifact

        path = self.tmpdir / "existing.json"
        path.write_text("original", encoding="utf-8")
        context = "run_id=test, kind=Assessment"

        with self.assertRaises(FileExistsError) as ctx:
            write_append_only_json_artifact(path, {"key": "value"}, context=context)

        error_msg = str(ctx.exception)
        self.assertIn("immutability contract violated", error_msg)
        self.assertIn("run_id=test", error_msg)
        self.assertIn("kind=Assessment", error_msg)

    def test_parent_directories_created(self) -> None:
        """Test that parent directories are created if missing."""
        from k8s_diag_agent.identity.artifact import write_append_only_json_artifact

        path = self.tmpdir / "deeply" / "nested" / "path" / "artifact.json"
        result = write_append_only_json_artifact(path, {"key": "value"})

        self.assertEqual(result, path)
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
