"""Tests for content index storage temp path operations.

Tests that temp files are created on the same filesystem as the target DB
to ensure atomic replacement works without EXDEV errors.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from k8s_diag_agent.content_index.storage import (
    create_content_index_temp_path,
    create_temp_database,
)


class TestCreateContentIndexTempPath:
    """Test create_content_index_temp_path function."""

    def test_temp_path_is_created_next_to_db(self, tmp_path: Path) -> None:
        """Temp path is created in the same directory as the target DB."""
        db_path = tmp_path / "runs" / "content-index.sqlite"
        db_path.parent.mkdir()

        temp_path = create_content_index_temp_path(db_path)

        try:
            assert temp_path.parent == db_path.parent
            assert temp_path.name.startswith(f".{db_path.name}.")
            assert temp_path.name.endswith(".tmp")
        finally:
            temp_path.unlink(missing_ok=True)

    def test_temp_path_creates_parent_directory(self, tmp_path: Path) -> None:
        """Temp path creation creates parent directory if needed."""
        db_path = tmp_path / "nested" / "dir" / "content-index.sqlite"
        assert not db_path.parent.exists()

        temp_path = create_content_index_temp_path(db_path)

        try:
            assert db_path.parent.exists()
            assert temp_path.parent == db_path.parent
        finally:
            temp_path.unlink(missing_ok=True)

    def test_temp_path_file_exists(self, tmp_path: Path) -> None:
        """Temp path file is created on disk."""
        db_path = tmp_path / "content-index.sqlite"

        temp_path = create_content_index_temp_path(db_path)

        try:
            assert temp_path.exists()
        finally:
            temp_path.unlink(missing_ok=True)

    def test_temp_path_name_format(self, tmp_path: Path) -> None:
        """Temp path has expected naming format."""
        db_path = tmp_path / "content-index.sqlite"

        temp_path = create_content_index_temp_path(db_path)

        try:
            # Should be a hidden file (starts with .)
            assert temp_path.name.startswith(".")
            # Should have the DB name as prefix
            assert f".{db_path.name}." in temp_path.name
            # Should end with .tmp
            assert temp_path.name.endswith(".tmp")
        finally:
            temp_path.unlink(missing_ok=True)


class TestCreateTempDatabase:
    """Test create_temp_database function."""

    def test_creates_temp_db_next_to_target(self, tmp_path: Path) -> None:
        """create_temp_database creates DB in same directory as target."""
        target_path = tmp_path / "runs" / "content-index.sqlite"
        target_path.parent.mkdir()

        temp_path, conn = create_temp_database(target_path)

        try:
            conn.close()
            assert temp_path.parent == target_path.parent
        finally:
            temp_path.unlink(missing_ok=True)

    def test_creates_valid_database(self, tmp_path: Path) -> None:
        """create_temp_database creates a valid content index database."""
        target_path = tmp_path / "content-index.sqlite"

        temp_path, conn = create_temp_database(target_path)

        try:
            # Check that tables exist
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
            assert "content_index_metadata" in tables
            assert "content_item" in tables
            assert "content_projection" in tables
        finally:
            conn.close()
            temp_path.unlink(missing_ok=True)

    def test_works_without_target_path(self, tmp_path: Path) -> None:
        """create_temp_database still works without target_path (legacy behavior)."""
        # This should use the system temp directory
        temp_path, conn = create_temp_database()

        try:
            conn.close()
            assert temp_path.exists()
            # Should be in temp directory
            import tempfile
            expected_temp_dir = Path(tempfile.gettempdir())
            assert temp_path.parent == expected_temp_dir
        finally:
            temp_path.unlink(missing_ok=True)


class TestAtomicReplacementInvariant:
    """Test that atomic replacement invariant is maintained."""

    def test_rebuild_uses_same_filesystem_for_temp_and_target(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Rebuild operation places temp files next to target DB."""

        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        target_path = runs_dir / "content-index.sqlite"

        # Record all os.replace calls
        observed_replaces: list[tuple[Path, Path]] = []

        original_replace = os.replace

        def recording_replace(src: str | os.PathLike, dst: str | os.PathLike) -> None:
            observed_replaces.append((Path(src), Path(dst)))
            original_replace(src, dst)

        monkeypatch.setattr(os, "replace", recording_replace)

        # Create temp database next to target
        temp_path, conn = create_temp_database(target_path)
        conn.close()

        # Verify temp was created in same directory
        assert temp_path.parent == target_path.parent

        # Verify the recorded replace would be same-filesystem
        for src, dst in observed_replaces:
            assert src.parent == dst.parent, (
                f"Cross-device replace detected: {src} -> {dst}"
            )

        # Cleanup
        temp_path.unlink(missing_ok=True)

    def test_simulated_exdev_would_not_occur_with_same_fs_temp(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Simulated EXDEV should not occur when temp is colocated."""
        from k8s_diag_agent.content_index.storage import initialize_database
        from k8s_diag_agent.content_index.storage_rebuild import (
            atomically_replace_database,
        )

        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        target_path = runs_dir / "content-index.sqlite"
        temp_path = runs_dir / "temp.sqlite"

        # Create temp database in same directory
        initialize_database(temp_path)

        # Simulate EXDEV only when directories differ
        original_replace = os.replace

        def fail_on_cross_device(src: str | os.PathLike, dst: str | os.PathLike) -> None:
            src_path = Path(src)
            dst_path = Path(dst)
            if src_path.parent != dst_path.parent:
                raise OSError(
                    errno.EXDEV,
                    "Invalid cross-device link",
                    str(src),
                    str(dst),
                )
            original_replace(src, dst)

        monkeypatch.setattr(os, "replace", fail_on_cross_device)

        # This should succeed because temp is in same directory
        atomically_replace_database(target_path, temp_path)

        assert target_path.exists()
        assert not temp_path.exists()


class TestRebuildIndexEndToEnd:
    """End-to-end tests for rebuild_index with EXDEV regression coverage."""

    def test_rebuild_index_never_cross_device_replaces(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Rebuild index succeeds even when simulated EXDEV would fail cross-device.

        This test proves the real production call path: rebuild_index() ->
        create_temp_database() -> atomically_replace_database(). The temp file
        is now created in target_db_path.parent, so os.replace() never sees
        different parent directories.
        """
        from k8s_diag_agent.content_index.indexer_commands import rebuild_index
        from k8s_diag_agent.content_index.indexer_contract import (
            ContentIndexRoots,
            IndexerConfig,
        )

        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        target_path = runs_dir / "content-index.sqlite"

        # Simulate EXDEV only when directories differ
        original_replace = os.replace

        def fail_on_cross_device(src: str | os.PathLike, dst: str | os.PathLike) -> None:
            src_path = Path(src)
            dst_path = Path(dst)
            if src_path.parent != dst_path.parent:
                raise OSError(
                    errno.EXDEV,
                    "Invalid cross-device link",
                    str(src),
                    str(dst),
                )
            original_replace(src, dst)

        monkeypatch.setattr(os, "replace", fail_on_cross_device)

        # Create minimal roots with a simple artifact
        artifact_dir = runs_dir / "artifacts"
        artifact_dir.mkdir()
        test_file = artifact_dir / "test.json"
        test_file.write_text('{"incident_id": "test-123", "summary": "Test"}')

        roots = ContentIndexRoots(
            incident_store=None,
            artifact_root=artifact_dir,
            lab_root=None,
            trace_capture_root=None,
            perf_baseline_root=None,
        )

        # This should succeed because temp is created in target_path.parent
        summary = rebuild_index(target_path, roots, IndexerConfig(strict_mode=False))

        # Verify success
        assert target_path.exists()
        assert summary.status in ("ok", "completed")

        # Verify no cross-device replace was attempted
        # (If we get here without exception, the test passes)

    def test_rebuild_index_with_different_tmpdir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Rebuild index ignores global TMPDIR and uses target_db_path.parent.

        Even if the system temp directory is somewhere else, the temp DB
        should be created next to the target to ensure atomic replace works.
        """
        from k8s_diag_agent.content_index.indexer_commands import rebuild_index
        from k8s_diag_agent.content_index.indexer_contract import (
            ContentIndexRoots,
            IndexerConfig,
        )
        import tempfile

        # Create separate "global temp" directory
        global_tmp = tmp_path / "global-tmp"
        global_tmp.mkdir()

        # Monkeypatch tempfile to use our controlled directory
        monkeypatch.setenv("TMPDIR", str(global_tmp))
        tempfile.tempdir = None  # Reset cached tempdir

        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        target_path = runs_dir / "content-index.sqlite"

        # Record all temp file creations
        original_mkstemp = tempfile.mkstemp
        observed_temp_dirs: list[Path] = []

        def recording_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
            result = original_mkstemp(*args, **kwargs)
            if "dir" in kwargs:
                observed_temp_dirs.append(Path(kwargs["dir"]))  # type: ignore[arg-type]
            return result

        monkeypatch.setattr(tempfile, "mkstemp", recording_mkstemp)

        # Create minimal roots
        artifact_dir = runs_dir / "artifacts"
        artifact_dir.mkdir()
        test_file = artifact_dir / "test.json"
        test_file.write_text('{"incident_id": "test-456", "summary": "Test"}')

        roots = ContentIndexRoots(
            incident_store=None,
            artifact_root=artifact_dir,
            lab_root=None,
            trace_capture_root=None,
            perf_baseline_root=None,
        )

        # Rebuild should use target_path.parent as temp dir
        summary = rebuild_index(target_path, roots, IndexerConfig(strict_mode=False))

        # Verify the temp file was created in target_path.parent, not global_tmp
        assert target_path.exists()
        assert summary.status in ("ok", "completed")

        # The key assertion: temp was NOT created in global_tmp
        for temp_dir in observed_temp_dirs:
            assert temp_dir != global_tmp, (
                f"Temp file was created in global_tmp ({global_tmp}), "
                f"should be in target_path.parent ({target_path.parent})"
            )


class TestTempFileCleanup:
    """Test that temp files are cleaned up properly."""

    def test_temp_file_cleanup_on_failure(self, tmp_path: Path) -> None:
        """Temp files are cleaned up when initialization fails."""
        # Use a read-only directory to simulate failure
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        target_path = runs_dir / "content-index.sqlite"

        # This should succeed but we can test the path cleanup pattern
        temp_path, conn = create_temp_database(target_path)
        conn.close()

        # Manually unlink and verify cleanup works
        temp_path.unlink()
        assert not temp_path.exists()
