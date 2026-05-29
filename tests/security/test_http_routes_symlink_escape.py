"""HTTP-level symlink escape tests for server routes.

This module exercises the HTTP routes with symlink-based escape attempts,
proving that symlink traversal is also blocked at the HTTP layer.

Invariant: Symlinks pointing outside the allowed root must not enable
unauthorized file access.

HTTP test harness is provided by server_http_test_support.py (via pytest_plugins).
"""

from __future__ import annotations

import pytest

pytest_plugins = ("tests.security.server_http_test_support",)

# =============================================================================
# TESTS: SYMLINK ESCAPE VIA HTTP
# =============================================================================


class TestSymlinkEscapeViaHTTP:
    """HTTP-level symlink escape tests.

    Tests that symlink-based escapes are also blocked at the HTTP layer.
    These are lighter-weight than full symlink tests since we verify the
    HTTP behavior (response status/body) rather than the full escape.
    """

    def test_symlink_final_target_not_accessible_via_http(self, http_harness: list) -> None:
        """Symlink pointing to canary must not be accessible via HTTP."""
        import os

        harness, port, canary = http_harness
        runs_dir = canary.allowed_root

        # Create a symlink inside runs_dir pointing to a canary file
        ea_dir = runs_dir / "external-analysis"
        symlink_dir = ea_dir / "subdir"
        symlink_dir.mkdir(parents=True, exist_ok=True)

        canary_file = canary.get_all_canary_paths()[0]
        symlink_path = symlink_dir / "escape-link"

        try:
            os.symlink(canary_file, symlink_path)
        except OSError:
            pytest.skip("Platform does not support symlinks")

        # Try to access via HTTP
        status, body, _ = harness.request("GET", "/artifact?path=external-analysis/subdir/escape-link")

        # Must not serve canary content
        assert canary.get_canary_content().encode() not in body, (
            "Symlink escape via HTTP: canary content was served"
        )

    def test_intermediate_symlink_not_followed_via_http(self, http_harness: list) -> None:
        """Symlink directory in intermediate path must not enable escape via HTTP."""
        import os

        harness, port, canary = http_harness
        runs_dir = canary.allowed_root

        # Create a symlink directory pointing to canary parent
        canary_parent = canary.get_all_canary_paths()[0].parent
        ea_dir = runs_dir / "external-analysis"
        symlink_dir_path = ea_dir / "linkdir"

        try:
            os.symlink(canary_parent, symlink_dir_path, target_is_directory=True)
        except OSError:
            pytest.skip("Platform does not support symlinks")

        canary_file = canary.get_all_canary_paths()[0]

        # Try to access canary file through intermediate symlink
        status, body, _ = harness.request(
            "GET",
            f"/artifact?path=external-analysis/linkdir/{canary_file.name}"
        )

        # Must not serve canary content
        assert canary.get_canary_content().encode() not in body, (
            "Intermediate symlink escape via HTTP: canary content was served"
        )
