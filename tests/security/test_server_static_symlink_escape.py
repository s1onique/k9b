"""Symlink escape regression tests for server_static.py.

This module tests the security regression corpus for symlink-based path
escape attacks on the artifact and static file serving endpoints.

Invariant: No request can cause the server to follow a symlink outside the
explicitly allowed root and allowlist.

Test corpus covers:
- Symlink files pointing to files outside root
- Symlink directories pointing to directories outside root
- Intermediate symlink components in the path
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.security.server_static_test_support import (
    MockHandler,
    SecurityCanaryFiles,
)

# =============================================================================
# TESTS: Symlink escape prevention
# =============================================================================


class TestSymlinkEscapePrevention:
    """Tests for serve_artifact() rejecting symlink-based escape attempts.

    The serve_artifact function must:
    1. Reject any path that escapes the runs_dir root via symlinks
    2. Never follow symlinks that lead outside the allowed root
    3. Check containment before following symlinks
    """

    @pytest.fixture(autouse=True)
    def setup_test_env(self, tmp_path: Path) -> None:
        """Set up test environment with runs_dir and canary files."""
        self.runs_dir = tmp_path / "runs"
        self.runs_dir.mkdir(parents=True)
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True)
        self.ea_dir = self.runs_dir / "external-analysis"
        self.ea_dir.mkdir(parents=True)

        # Create a valid artifact inside the root
        self.valid_artifact = self.ea_dir / "run-test-assessment-001.json"
        self.valid_artifact.write_text(
            '{"findings": [], "summary": "valid artifact"}',
            encoding="utf-8",
        )

        # Set up canary files outside the root
        self.canary = SecurityCanaryFiles(self.runs_dir)

        yield

        self.canary.cleanup()

    def _call_serve_artifact(self, path: str) -> MockHandler:
        """Call serve_artifact with the given path."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        serve_artifact(handler, f"path={path}")
        return handler

    def test_symlink_outside_root_not_followed(self) -> None:
        """Symlink pointing outside allowed root must not be followed.

        This is a permanent regression test for the symlink escape bug class.
        A symlink inside the artifact directory must not allow access to files
        outside the runs_dir root.
        """
        import os

        from k8s_diag_agent.ui.server_static import serve_artifact

        # Create a symlink inside the runs_dir pointing to a canary file
        symlink_dir = self.ea_dir / "subdir"
        symlink_dir.mkdir(parents=True)
        canary_file = self.canary.get_all_canary_paths()[0]

        symlink_path = symlink_dir / "escape-link"
        try:
            os.symlink(canary_file, symlink_path)
        except OSError:
            pytest.skip("Platform does not support symlinks")

        # Try to access the symlink path
        handler = MockHandler(self.runs_dir, self.canary)
        query = "path=external-analysis/subdir/escape-link"
        serve_artifact(handler, query)

        # Regression assertion: canary content must never be served through a symlink.
        assert self.canary.get_canary_content().encode() not in handler._response_body, (
            "Symlink escape: canary content was served via symlink. "
            "serve_artifact() must check containment BEFORE following symlinks."
        )

    def test_symlink_in_intermediate_directory_not_followed(self) -> None:
        """Symlink in an intermediate path component must not be followed.

        This tests the case where a symlink directory (not the final file)
        inside runs_dir points outside runs_dir. The path might look like:
        runs/external-analysis/linkdir/canary.json
        where linkdir -> /outside/canary_dir

        The initial is_symlink() check only catches the final path component.
        The relative_to() check after resolution catches the escaped target.
        """
        import os

        from k8s_diag_agent.ui.server_static import serve_artifact

        # Create a symlink directory pointing to a canary parent directory
        # Note: Do NOT create linkdir as a real directory - we want to create a symlink there
        canary_parent = self.canary.get_all_canary_paths()[0].parent

        symlink_dir_path = self.ea_dir / "linkdir"
        try:
            os.symlink(canary_parent, symlink_dir_path, target_is_directory=True)
        except OSError:
            pytest.skip("Platform does not support symlinks")

        # Create a file inside the symlink target to attempt to access
        canary_file = self.canary.get_all_canary_paths()[0]

        # Try to access the canary file through the intermediate symlink
        # Request: external-analysis/linkdir/<canary_filename>
        handler = MockHandler(self.runs_dir, self.canary)
        query = f"path=external-analysis/linkdir/{canary_file.name}"
        serve_artifact(handler, query)

        # Should not serve canary content - the relative_to() check after
        # resolution should catch that the resolved path is outside root
        assert self.canary.get_canary_content().encode() not in handler._response_body, (
            "Intermediate symlink escape: canary content was served via symlink dir. "
            "The relative_to() containment check after resolution must reject this."
        )
