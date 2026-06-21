#!/usr/bin/env python3
"""LLM Evidence Boundaries Verification Gate.

This script verifies that k9b properly handles prompt-injection attempts and
maintains evidence-boundary discipline around LLM calls.

Usage:
    python scripts/verify_llm_evidence_boundaries.py
    python scripts/verify_llm_evidence_boundaries.py --verbose

Exit codes:
    0 - All checks passed
    1 - One or more checks failed

No API keys or live LLM calls required. Deterministic tests only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _get_venv_python() -> Path:
    """Get the path to the .venv Python interpreter.

    Returns:
        Path to .venv/bin/python

    Raises:
        RuntimeError: If .venv Python is not available.
    """
    repo_root = Path(__file__).parent.parent
    venv_python = repo_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        raise RuntimeError(
            f"Virtual environment Python not found: {venv_python}. "
            "Run scripts/verify_all.sh from the repo root, which ensures .venv is used."
        )
    return venv_python


def run_tests(verbose: bool = False) -> tuple[int, str]:
    """Run the LLM evidence boundaries tests.

    Returns:
        Tuple of (exit_code, output)
    """
    repo_root = Path(__file__).parent.parent
    test_file = repo_root / "tests" / "test_llm_evidence_boundaries.py"

    if not test_file.exists():
        return 1, f"ERROR: Test file not found: {test_file}"

    venv_python = _get_venv_python()
    cmd = [
        str(venv_python),
        "-m",
        "pytest",
        str(test_file),
        "-v",
        "--tb=short",
    ]

    if verbose:
        cmd.append("-s")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    output = result.stdout
    if result.stderr:
        output += "\nSTDERR:\n" + result.stderr

    return result.returncode, output


def run_prompt_boundaries_tests(verbose: bool = False) -> tuple[int, str]:
    """Run the existing prompt boundaries tests.

    Returns:
        Tuple of (exit_code, output)
    """
    repo_root = Path(__file__).parent.parent
    test_file = repo_root / "tests" / "test_prompt_boundaries.py"

    if not test_file.exists():
        return 0, f"SKIP: Test file not found: {test_file}"

    venv_python = _get_venv_python()
    cmd = [
        str(venv_python),
        "-m",
        "pytest",
        str(test_file),
        "-v",
        "--tb=short",
    ]

    if verbose:
        cmd.append("-s")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    output = result.stdout
    if result.stderr:
        output += "\nSTDERR:\n" + result.stderr

    return result.returncode, output


def check_boundary_markers() -> tuple[int, str]:
    """Verify boundary marker constants are properly defined.

    Returns:
        Tuple of (exit_code, output)
    """
    repo_root = Path(__file__).parent.parent
    boundaries_file = repo_root / "src" / "k8s_diag_agent" / "llm" / "prompt_boundaries.py"

    if not boundaries_file.exists():
        return 1, f"ERROR: Boundary markers file not found: {boundaries_file}"

    content = boundaries_file.read_text()

    required_markers = [
        "BEGIN_UNTRUSTED_CLUSTER_DATA",
        "END_UNTRUSTED_CLUSTER_DATA",
        "BEGIN_OUTPUT_SCHEMA",
        "END_OUTPUT_SCHEMA",
    ]

    for marker in required_markers:
        # Check for variable assignment like: VARIABLE_NAME = "..." or VARIABLE_NAME = '...'
        if f"{marker} =" not in content:
            return 1, f"ERROR: Missing boundary marker: {marker}"

    return 0, f"OK: All {len(required_markers)} boundary markers defined"


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify LLM evidence boundaries regression tests"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose test output",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("LLM Evidence Boundaries Verification Gate")
    print("=" * 60)
    print()

    all_passed = True
    all_output: list[str] = []

    # Check 1: Boundary markers defined
    print("[1/3] Checking boundary marker constants...")
    code, output = check_boundary_markers()
    print(f"      {output}")
    if code != 0:
        all_passed = False
    print()

    # Check 2: Prompt boundaries tests
    print("[2/3] Running prompt boundaries tests (existing)...")
    code, output = run_prompt_boundaries_tests(args.verbose)
    all_output.append(output)
    if code == 0:
        print("      PASS: Existing prompt boundaries tests")
    else:
        print("      FAIL: Existing prompt boundaries tests")
        all_passed = False
    print()

    # Check 3: LLM evidence boundaries regression tests
    print("[3/3] Running LLM evidence boundaries regression tests...")
    code, output = run_tests(args.verbose)
    all_output.append(output)
    if code == 0:
        print("      PASS: LLM evidence boundaries tests")
    else:
        print("      FAIL: LLM evidence boundaries tests")
        all_passed = False
    print()

    # Summary
    print("=" * 60)
    if all_passed:
        print("VERIFICATION GATE: PASSED")
        print("=" * 60)
        print()
        print("LLM evidence boundaries regression tests:")
        print("  - Prompt injection patterns are contained in UNTRUSTED sections")
        print("  - External analysis artifacts preserve structured boundaries")
        print("  - LLM call labels properly identify evidence sources")
        print("  - Boundary markers are properly defined")
        return 0
    else:
        print("VERIFICATION GATE: FAILED")
        print("=" * 60)
        print()
        if args.verbose:
            print("\n--- Test Output ---\n")
            for output in all_output:
                print(output)
        return 1


if __name__ == "__main__":
    sys.exit(main())
