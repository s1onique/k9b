"""Regression test: ensure no stale 2-tuple collect_pods callers exist in production code.

Reference: ACT-K9B-HOLMESGPT-COLLECT-PODS-CALLER-COMPAT01

This test scans production source files to ensure that collect_pods() calls
correctly unpack all three return values. Stale 2-tuple unpacking like:

    pods, errors = collect_pods(namespace, context)

would cause runtime failures since collect_pods() now returns a 3-tuple.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Files to scan for stale collect_pods() callers
# Exclude test files (they may legitimately mock or test different arities)
SRC_ROOT = Path(__file__).parent.parent / "src"


def _find_stale_collect_pods_calls(root: Path) -> list[tuple[str, int, str]]:
    """Find stale 2-tuple unpacking of collect_pods() calls.

    Returns list of (file_path, line_number, code_snippet) tuples.
    """
    stale_calls = []

    # Regex to match 2-tuple unpacking patterns like:
    # pods, errors = collect_pods(
    # pods, err = collect_pods(
    # pods, some_errors = collect_pods(
    two_tuple_pattern = re.compile(
        r"^\s*(\w+)\s*,\s*(\w+)\s*=\s*collect_pods\s*\(",
        re.MULTILINE,
    )

    for py_file in root.rglob("*.py"):
        # Skip test files and __pycache__
        if "test" in py_file.name or "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Check for stale 2-tuple pattern
        for match in two_tuple_pattern.finditer(content):
            # Verify it's a 2-element tuple, not 3-element
            line_start = content.rfind("\n", 0, match.start()) + 1
            line_end = content.find("\n", match.end())
            if line_end == -1:
                line_end = len(content)
            line = content[line_start:line_end]

            # Skip if it's a comment or string
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                continue

            stale_calls.append((
                str(py_file.relative_to(root.parent)),
                content[:match.start()].count("\n") + 1,
                line.strip(),
            ))

    return stale_calls


class TestCollectPodsCallerCompatibility:
    """Regression tests for collect_pods() 3-tuple return shape."""

    def test_no_stale_two_tuple_unpacking_in_src(self) -> None:
        """Production source files must not use stale 2-tuple unpacking."""
        stale_calls = _find_stale_collect_pods_calls(SRC_ROOT)

        if stale_calls:
            details = "\n".join(
                f"  {path}:{line}: {snippet}"
                for path, line, snippet in stale_calls
            )
            pytest.fail(
                f"Found {len(stale_calls)} stale 2-tuple collect_pods() caller(s):\n"
                f"{details}\n\n"
                f"collect_pods() now returns 3 values: (pods, errors, projection_metadata)\n"
                f"Update callers to unpack all three values."
            )

    def test_collect_pods_3tuple_in_src_files(self) -> None:
        """Verify collect_pods is called with 3-value unpacking in production code."""
        # This is a positive test - check that the fixed pattern exists
        src_files = list(SRC_ROOT.rglob("*.py"))

        found_3tuple_call = False
        for py_file in src_files:
            if "test" in py_file.name or "__pycache__" in str(py_file):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            # Look for 3-tuple unpacking: pods, errors, metadata = collect_pods(
            if re.search(r"\w+\s*,\s*\w+\s*,\s*\w+\s*=\s*collect_pods\s*\(", content):
                found_3tuple_call = True
                break

        assert found_3tuple_call, (
            "No 3-tuple collect_pods() unpacking found in production source files. "
            "At least one caller should unpack all three return values."
        )


if __name__ == "__main__":
    # Allow running this test directly
    pytest.main([__file__, "-v"])
