"""Shared test collection utilities.

This module provides the single source of truth for pytest collection
used by both shard_tests.py and verify_test_exclusions.py.

Usage:
    from test_collection import collect_test_nodeids, build_collection_command

Collection Policy:
    - Tests are collected from the tests/ directory using pytest --collect-only -q
    - No --ignore flags are used when ALLOWED_COLLECTION_EXCLUSIONS is empty
    - Any file-specific exclusions are added via ALLOWED_COLLECTION_EXCLUSIONS
    - This module contains NO raw --ignore patterns for test files (enforced by AST-based regression tests)

Adding exclusions:
    1. If a test file has a genuine import error, add it to ALLOWED_COLLECTION_EXCLUSIONS
    2. The collection command builder will automatically add --ignore flags
    3. Document the exclusion in scripts/test_exclusions.md
    4. The exclusion will be verified by verify_test_exclusions.py

DO NOT add raw ignore flags to collection code.
DO NOT add skips/xfails/deselects for healthy tests.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).parent.parent.resolve()

# Single source of truth for test file exclusions.
# These files have import errors and cannot be collected.
# Add new exclusions ONLY here, then document in scripts/test_exclusions.md
ALLOWED_COLLECTION_EXCLUSIONS: set[str] = set()

# Pattern to detect --ignore=tests/... or --ignore tests/... strings
# This is used for AST-based detection in the regression guard
IGNORE_PATTERN = re.compile(r"--ignore[=\s]+tests/")


class CollectionResult(NamedTuple):
    """Result of a pytest collection run."""
    nodeids: list[str]
    returncode: int
    stdout: str
    stderr: str


class IgnoreStringVisitor(ast.NodeVisitor):
    """AST visitor to find string constants matching ignore patterns."""

    def __init__(self) -> None:
        self.violations: list[tuple[int, str]] = []

    def visit_Constant(self, node: ast.Constant) -> None:
        """Visit constant nodes (Python 3.8+)."""
        if isinstance(node.value, str) and IGNORE_PATTERN.search(node.value):
            self.violations.append((node.lineno, node.value))

    def visit_Str(self, node: ast.Str) -> None:  # pragma: no cover  # Python < 3.8
        """Visit string nodes (Python < 3.8 fallback)."""
        if isinstance(node.s, str) and IGNORE_PATTERN.search(node.s):
            self.violations.append((node.lineno, node.s))


def _parse_nodeids_from_output(output: str) -> list[str]:
    """Parse test nodeids from pytest --collect-only output.

    Args:
        output: stdout from pytest --collect-only -q

    Returns:
        List of nodeid strings (sorted for determinism)
    """
    nodeids: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        # Match lines like: tests/unit/test_foo.py::test_bar
        # or: test_foo.py::test_bar (root-level files)
        if ("tests/" in line or line.startswith("test_")) and "::" in line:
            nodeids.append(line)
    return sorted(nodeids)


def build_collection_command(
    extra_args: list[str] | None = None,
    include_allowed_ignores: bool = True,
) -> list[str]:
    """Build the pytest collection command.

    This is the canonical way to build pytest collection commands.
    It handles ALLOWED_COLLECTION_EXCLUSIONS automatically.

    Args:
        extra_args: Additional pytest arguments to include
        include_allowed_ignores: If True, add --ignore flags for each allowed exclusion

    Returns:
        Command list suitable for subprocess.run()
    """
    cmd: list[str] = [
        sys.executable, "-m", "pytest",
        "--collect-only", "-q",
    ]

    # Add --ignore flags for allowed exclusions
    if include_allowed_ignores:
        for exclusion in sorted(ALLOWED_COLLECTION_EXCLUSIONS):
            cmd.extend(["--ignore", exclusion])

    # Add extra arguments
    if extra_args:
        cmd.extend(extra_args)

    # Add the tests directory
    cmd.append("tests/")

    return cmd


def collect_test_nodeids(
    extra_args: list[str] | None = None,
) -> CollectionResult:
    """Collect all test nodeids deterministically using pytest --collect-only.

    This is the canonical collection method used by both:
    - scripts/shard_tests.py (for sharding)
    - scripts/verify_test_exclusions.py (for verification)

    Args:
        extra_args: Additional pytest arguments

    Returns:
        CollectionResult with nodeids, returncode, stdout, and stderr
    """
    cmd = build_collection_command(extra_args=extra_args)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    nodeids = _parse_nodeids_from_output(result.stdout)

    return CollectionResult(
        nodeids=nodeids,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def check_for_hard_coded_ignores(file_path: Path) -> list[str]:
    """Check a Python file for hard-coded ignore patterns using AST.

    This is the regression guard that prevents future drift.
    Uses AST parsing to find string constants matching the ignore pattern,
    which catches cases where the ignore flag is on its own line in a
    multiline list argument.

    Args:
        file_path: Path to Python file to check

    Returns:
        List of lines containing hard-coded ignore patterns with line numbers
    """
    violations: list[str] = []

    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=str(file_path))
        visitor = IgnoreStringVisitor()
        visitor.visit(tree)

        for lineno, value in visitor.violations:
            violations.append(f"  Line {lineno}: {value!r}")

    except (OSError, SyntaxError):
        pass

    return violations


def verify_no_hard_coded_ignores(
    files_to_check: list[Path] | None = None,
) -> tuple[bool, list[str]]:
    """Verify that collection-related files have no hard-coded ignore patterns.

    Args:
        files_to_check: List of files to check. Defaults to collection-related files.

    Returns:
        Tuple of (passed, list of violations with file:line context)
    """
    if files_to_check is None:
        scripts_dir = REPO_ROOT / "scripts"
        files_to_check = [
            scripts_dir / "shard_tests.py",
            scripts_dir / "verify_test_exclusions.py",
            scripts_dir / "test_collection.py",
        ]

    all_violations: list[str] = []

    for file_path in files_to_check:
        if not file_path.exists():
            continue
        violations = check_for_hard_coded_ignores(file_path)
        if violations:
            all_violations.append(f"\n{file_path.name}:")
            all_violations.extend(violations)

    passed = len(all_violations) == 0
    return passed, all_violations


if __name__ == "__main__":
    # Self-test: verify no hard-coded ignores in this module
    passed, violations = verify_no_hard_coded_ignores()

    if not passed:
        print("REGRESSION GUARD FAILED: Hard-coded --ignore found!")
        print("".join(violations))
        sys.exit(1)

    print("Test collection module self-check: PASS")
    print(f"  ALLOWED_COLLECTION_EXCLUSIONS: {len(ALLOWED_COLLECTION_EXCLUSIONS)} files")

    # Show collection count
    result = collect_test_nodeids()
    print(f"  Collected {len(result.nodeids)} tests")
