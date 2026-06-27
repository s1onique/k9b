"""Shared test collection utilities.

This module provides the single source of truth for pytest collection
used by both shard_tests.py and verify_test_exclusions.py.

Usage:
    from test_collection import collect_test_nodeids, get_collection_command

Collection Policy:
    - Tests are collected from the tests/ directory using pytest --collect-only -q
    - No --ignore flags are used in normal collection (all healthy tests are included)
    - Any file-specific exclusions must be added to ALLOWED_COLLECTION_EXCLUSIONS below
    - This module contains NO raw --ignore=tests/... literals (enforced by regression tests)

Adding exclusions:
    1. If a test file has a genuine import error, add it to ALLOWED_COLLECTION_EXCLUSIONS
    2. Document the exclusion in scripts/test_exclusions.md
    3. The exclusion will be verified by verify_test_exclusions.py

DO NOT add raw --ignore=tests/... to collection code.
DO NOT add skips/xfails/deselects for healthy tests.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).parent.parent.resolve()

# Single source of truth for test file exclusions.
# These files have import errors and cannot be collected.
# Add new exclusions ONLY here, then document in scripts/test_exclusions.md
ALLOWED_COLLECTION_EXCLUSIONS: set[str] = set()

# Regex pattern to catch raw --ignore=tests/... literals (regression guard)
# Only matches actual command-line usage inside subprocess calls.
# Matches: subprocess.run([..., "--ignore=tests/foo.py", ...])
# Does NOT match: docstrings, comments, print statements, variable assignments
HARD_CODED_IGNORE_PATTERN = r'\["\']--ignore[=\s]+tests/'


class CollectionResult(NamedTuple):
    """Result of a pytest collection run."""
    nodeids: list[str]
    returncode: int
    stdout: str
    stderr: str


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


def collect_test_nodeids(
    include_errors: bool = False,
) -> CollectionResult:
    """Collect all test nodeids deterministically using pytest --collect-only.
    
    This is the canonical collection method used by both:
    - scripts/shard_tests.py (for sharding)
    - scripts/verify_test_exclusions.py (for verification)
    
    Args:
        include_errors: If True, collection includes files with import errors.
                       If False (default), collection is used for execution.
                       
    Returns:
        CollectionResult with nodeids, returncode, stdout, and stderr
    """
    cmd = [
        sys.executable, "-m", "pytest",
        "--collect-only", "-q",
        "tests/",
    ]
    
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
    """Check a Python file for hard-coded --ignore=tests/... literals.
    
    This is the regression guard that prevents future drift.
    
    Args:
        file_path: Path to Python file to check
        
    Returns:
        List of lines containing hard-coded ignore patterns
    """
    violations: list[str] = []
    import re
    pattern = re.compile(HARD_CODED_IGNORE_PATTERN)
    
    try:
        with open(file_path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if pattern.search(line):
                    violations.append(f"  Line {line_no}: {line.strip()}")
    except OSError:
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
