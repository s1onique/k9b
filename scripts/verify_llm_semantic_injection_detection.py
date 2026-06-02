#!/usr/bin/env python3
"""Semantic Injection Detection Verification Gate.

This script verifies that k9b's deterministic local semantic injection detector
is properly integrated into the prompt construction path.

Usage:
    python scripts/verify_llm_semantic_injection_detection.py
    python scripts/verify_llm_semantic_injection_detection.py --verbose

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


def run_unit_tests(verbose: bool = False) -> tuple[int, str]:
    """Run the semantic injection detector unit tests.

    Returns:
        Tuple of (exit_code, output)
    """
    repo_root = Path(__file__).parent.parent
    test_file = repo_root / "tests" / "test_semantic_injection_detector.py"

    if not test_file.exists():
        return 1, f"ERROR: Test file not found: {test_file}"

    cmd = [
        sys.executable,
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


def run_prompt_integration_tests(verbose: bool = False) -> tuple[int, str]:
    """Run the prompt integration tests.

    Returns:
        Tuple of (exit_code, output)
    """
    repo_root = Path(__file__).parent.parent
    test_file = repo_root / "tests" / "test_semantic_injection_prompt_integration.py"

    if not test_file.exists():
        return 1, f"ERROR: Test file not found: {test_file}"

    cmd = [
        sys.executable,
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


def check_detector_module() -> tuple[int, str]:
    """Verify the semantic injection detector module is properly defined.

    Returns:
        Tuple of (exit_code, output)
    """
    repo_root = Path(__file__).parent.parent
    detector_file = repo_root / "src" / "k8s_diag_agent" / "llm" / "semantic_injection_detector.py"

    if not detector_file.exists():
        return 1, f"ERROR: Detector module not found: {detector_file}"

    content = detector_file.read_text()

    # Check for required functions
    required_items = [
        "def detect_semantic_injection",
        "def build_security_note",
        "class SemanticInjectionFinding",
        "instruction_override",
        "role_reassignment",
        "secret_exfiltration",
        "output_suppression",
        "answer_poisoning",
        "tool_abuse",
    ]

    for item in required_items:
        if item not in content:
            return 1, f"ERROR: Missing required item in detector module: {item}"

    return 0, f"OK: Detector module contains all required items ({len(required_items)})"


def check_integration_in_prompt_builder() -> tuple[int, str]:
    """Verify the detector is integrated into the prompt builder.

    Returns:
        Tuple of (exit_code, output)
    """
    repo_root = Path(__file__).parent.parent
    prompt_file = repo_root / "src" / "k8s_diag_agent" / "llm" / "drilldown_prompts.py"

    if not prompt_file.exists():
        return 1, f"ERROR: Prompt builder not found: {prompt_file}"

    content = prompt_file.read_text()

    # Check for integration
    required_items = [
        "from .semantic_injection_detector import",
        "detect_semantic_injection",
        "build_security_note",
        "injection_findings",
        "security_note",
        "[UNTRUSTED_EVIDENCE_SECURITY_NOTE]",
    ]

    for item in required_items:
        if item not in content:
            return 1, f"ERROR: Missing required integration item in prompt builder: {item}"

    return 0, f"OK: Prompt builder integrates detector ({len(required_items)} items)"


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify semantic injection detection integration"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose test output",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Semantic Injection Detection Verification Gate")
    print("=" * 60)
    print()

    all_passed = True
    all_output: list[str] = []

    # Check 1: Detector module exists and has required items
    print("[1/5] Checking detector module...")
    code, output = check_detector_module()
    print(f"      {output}")
    if code != 0:
        all_passed = False
    print()

    # Check 2: Detector integrated into prompt builder
    print("[2/5] Checking prompt builder integration...")
    code, output = check_integration_in_prompt_builder()
    print(f"      {output}")
    if code != 0:
        all_passed = False
    print()

    # Check 3: Unit tests
    print("[3/5] Running semantic injection detector unit tests...")
    code, output = run_unit_tests(args.verbose)
    all_output.append(output)
    if code == 0:
        print("      PASS: Detector unit tests")
    else:
        print("      FAIL: Detector unit tests")
        all_passed = False
    print()

    # Check 4: Prompt integration tests
    print("[4/5] Running prompt integration tests...")
    code, output = run_prompt_integration_tests(args.verbose)
    all_output.append(output)
    if code == 0:
        print("      PASS: Prompt integration tests")
    else:
        print("      FAIL: Prompt integration tests")
        all_passed = False
    print()

    # Check 5: Run existing evidence boundary tests (regression)
    print("[5/5] Running existing LLM evidence boundary tests (regression)...")
    test_file = Path(__file__).parent.parent / "tests" / "test_llm_evidence_boundaries.py"
    if test_file.exists():
        cmd = [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        all_output.append(result.stdout)
        if result.returncode == 0:
            print("      PASS: Existing evidence boundary tests")
        else:
            print("      FAIL: Existing evidence boundary tests")
            all_passed = False
    else:
        print("      SKIP: Test file not found")
    print()

    # Summary
    print("=" * 60)
    if all_passed:
        print("VERIFICATION GATE: PASSED")
        print("=" * 60)
        print()
        print("Semantic injection detection regression tests:")
        print("  - Detector module exists and is properly defined")
        print("  - Detector integrated into prompt builder")
        print("  - Detector unit tests pass")
        print("  - Prompt integration tests pass")
        print("  - Existing evidence boundary tests still pass")
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