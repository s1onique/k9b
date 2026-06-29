"""Regression tests for llm_friendly_allowlist.py.

Ensures all entries in the allowlist point to files that exist in the working tree.
This prevents stale allowlist entries after file splits/removals.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.llm_friendly_allowlist import ALLOWLIST


class TestAllowlistEntriesExist:
    """Regression tests to ensure all allowlist entries resolve in the working tree."""

    @pytest.mark.parametrize(
        "path,_reason",
        ALLOWLIST,
        ids=[path for path, _ in ALLOWLIST],
    )
    def test_allowlist_entry_exists(self, path: str, _reason: str) -> None:
        """Each allowlist entry must point to a file that exists.

        This prevents stale allowlist entries after file splits/removals.
        """
        if any(ch in path for ch in "*?["):
            # Glob patterns - check if any match exists
            matches = list(Path(".").glob(path))
            assert matches, f"Allowlist glob pattern has no matches: {path}"
        else:
            # Direct path - must exist
            assert Path(path).exists(), f"Allowlist entry does not exist: {path}"

    def test_allowlist_has_entries(self) -> None:
        """Allowlist should not be empty."""
        assert len(ALLOWLIST) > 0, "Allowlist should contain entries"

    def test_no_duplicate_entries(self) -> None:
        """Allowlist should not contain duplicate paths."""
        paths = [path for path, _ in ALLOWLIST]
        assert len(paths) == len(set(paths)), "Allowlist contains duplicate paths"
