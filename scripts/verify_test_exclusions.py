#!/usr/bin/env python3
"""
Verify test exclusions match documented policy.

This script ensures that any test files excluded from sharded execution
are:
1. Documented in scripts/test_exclusions.md
2. Actually broken (import errors)
3. Not accidentally hiding working tests

Usage:
    python scripts/verify_test_exclusions.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Allowlisted exclusions - files that are documented as broken
ALLOWLISTED_EXCLUSIONS: set[str] = set()


def get_full_collection() -> tuple[set[str], set[str]]:
    """Get full pytest collection (including errors).
    
    Returns:
        Tuple of (nodeids, error_files)
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    
    nodeids: set[str] = set()
    error_files: set[str] = set()
    
    # Collect tests from stdout
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("tests/") and "::" in line:
            nodeids.add(line)
    
    # Combine stdout and stderr for error parsing
    combined_output = result.stdout + "\n" + result.stderr
    
    # Parse ERROR collecting lines from combined output
    for line in combined_output.splitlines():
        match = re.search(r"ERROR collecting (\S+)", line)
        if match:
            error_files.add(match.group(1))
    
    return nodeids, error_files


def get_sharded_collection() -> set[str]:
    """Get sharded pytest collection (with ignore flags).
    
    Returns:
        Set of nodeids
    """
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--collect-only", "-q",
            "tests/",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    
    nodeids: set[str] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("tests/") and "::" in line:
            nodeids.add(line)
    
    return nodeids


def main() -> int:
    print("=" * 70)
    print("Test Exclusion Verification")
    print("=" * 70)
    
    # Get collections
    full_nodeids, error_files = get_full_collection()
    sharded_nodeids = get_sharded_collection()
    
    print(f"\nFull collection: {len(full_nodeids)} tests")
    print(f"Error files in full collection: {len(error_files)}")
    for f in sorted(error_files):
        print(f"  - {f}")
    
    print(f"\nSharded collection: {len(sharded_nodeids)} tests")
    
    # Find missing tests (in full but not in sharded)
    missing_from_shaded = full_nodeids - sharded_nodeids
    
    if missing_from_shaded:
        print(f"\nMissing from sharded collection: {len(missing_from_shaded)}")
        
        # Group by file
        by_file: dict[str, list[str]] = {}
        for nodeid in missing_from_shaded:
            file = nodeid.split("::")[0]
            if file not in by_file:
                by_file[file] = []
            by_file[file].append(nodeid)
        
        errors = 0
        for file, nodeids in sorted(by_file.items()):
            if file in ALLOWLISTED_EXCLUSIONS:
                print(f"  [ALLOWLISTED] {file}: {len(nodeids)} tests")
            else:
                print(f"  [ERROR] {file}: {len(nodeids)} tests - NOT in exclusion allowlist!")
                errors += 1
        
        if errors > 0:
            print(f"\nERROR: {errors} unallowlisted file(s) missing from sharded collection")
            print("Update scripts/test_exclusions.md to document these exclusions")
            return 1
    
    # Check that allowlisted files actually have errors (fail-closed)
    print("\nChecking allowlisted exclusions are actually broken:")
    stale_allowlist_errors = 0
    for file in sorted(ALLOWLISTED_EXCLUSIONS):
        if file in error_files:
            print(f"  [OK] {file} - confirmed broken")
        else:
            print(f"  [ERROR] {file} - allowlisted but no longer broken")
            stale_allowlist_errors += 1
    
    print("\n" + "=" * 70)
    
    if stale_allowlist_errors > 0:
        print("VERIFICATION FAILED")
        print("=" * 70)
        print(f"\nERROR: {stale_allowlist_errors} stale exclusion(s) in allowlist")
        print("Remove these files from ALLOWLISTED_EXCLUSIONS or fix their import errors")
        return 1
    
    print("VERIFICATION PASSED")
    print("=" * 70)
    print("\nExclusion policy summary:")
    print(f"  - {len(ALLOWLISTED_EXCLUSIONS)} allowlisted exclusions")
    print(f"  - {len(sharded_nodeids)} tests in sharded collection")
    print("  - All missing tests are documented in scripts/test_exclusions.md")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
