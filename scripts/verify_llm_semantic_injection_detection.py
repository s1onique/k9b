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


def _get_venv_python() -> Path:
    """Get the path to the virtual environment Python interpreter.

    Returns:
        Path to .venv/bin/python

    Raises:
        FileNotFoundError: If the virtual environment Python does not exist
    """
    repo_root = Path(__file__).parent.parent
    venv_python = repo_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        raise FileNotFoundError(
            f"Virtual environment Python not found: {venv_python}. "
            "Please ensure the virtual environment is set up."
        )
    return venv_python


def run_unit_tests(verbose: bool = False) -> tuple[int, str]:
    """Run the semantic injection detector unit tests.

    Returns:
        Tuple of (exit_code, output)
    """
    repo_root = Path(__file__).parent.parent
    test_file = repo_root / "tests" / "test_semantic_injection_detector.py"

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


def run_prompt_integration_tests(verbose: bool = False) -> tuple[int, str]:
    """Run the prompt integration tests.

    Returns:
        Tuple of (exit_code, output)
    """
    repo_root = Path(__file__).parent.parent
    test_file = repo_root / "tests" / "test_semantic_injection_prompt_integration.py"

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


def check_integration_in_prompt_builder(
    prompt_file: Path,
    builder_name: str,
) -> tuple[int, str]:
    """Verify the detector is integrated into a prompt builder.

    Args:
        prompt_file: Path to the prompt builder file
        builder_name: Human-readable name for the builder

    Returns:
        Tuple of (exit_code, output)
    """
    if not prompt_file.exists():
        return 1, f"ERROR: Prompt builder not found: {prompt_file}"

    content = prompt_file.read_text()

    # Check for integration - allow both single and double dot imports
    # (single dot for llm/ subdirectory, double dot for external_analysis/)
    required_items = [
        ("import marker", lambda c: "semantic_injection_detector import" in c),
        "detect_semantic_injection",
        "build_security_note",
        "injection_findings",
        "security_note",
        "[UNTRUSTED_EVIDENCE_SECURITY_NOTE]",
    ]

    for item in required_items:
        if isinstance(item, tuple):
            check_name, check_fn = item
            if not check_fn(content):
                return 1, f"ERROR: Missing required integration item in {builder_name}: {check_name}"
        elif item not in content:  # type: ignore[operator]  # pre-existing: list contains mixed str/tuple types
            return 1, f"ERROR: Missing required integration item in {builder_name}: {item}"

    return 0, f"OK: {builder_name} integrates detector ({len(required_items)} items)"


def run_test_file(test_file: Path, verbose: bool = False) -> tuple[int, str]:
    """Run a single test file.

    Args:
        test_file: Path to the test file
        verbose: Whether to show verbose output

    Returns:
        Tuple of (exit_code, output)
    """
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
        cwd=str(Path(__file__).parent.parent),
    )

    output = result.stdout
    if result.stderr:
        output += "\nSTDERR:\n" + result.stderr

    return result.returncode, output


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

    repo_root = Path(__file__).parent.parent

    print("=" * 60)
    print("Semantic Injection Detection Verification Gate")
    print("=" * 60)
    print()

    all_passed = True
    all_output: list[str] = []

    # Check 1: Detector module exists and has required items
    print("[1/8] Checking detector module...")
    code, output = check_detector_module()
    print(f"      {output}")
    if code != 0:
        all_passed = False
    print()

    # Check 2-4: Verify integration in all protected prompt builders
    prompt_builders = [
        (
            repo_root / "src" / "k8s_diag_agent" / "llm" / "drilldown_prompts.py",
            "build_drilldown_prompt()",
        ),
        (
            repo_root / "src" / "k8s_diag_agent" / "llm" / "prompts.py",
            "build_assessment_prompt()",
        ),
    ]

    # Check for compose_review_enrichment_prompt with fallback to legacy location
    REVIEW_ENRICHMENT_PROMPT_CANDIDATES = (
        repo_root / "src" / "k8s_diag_agent" / "external_analysis" / "openai_compatible_adapter_prompt.py",
        repo_root / "src" / "k8s_diag_agent" / "external_analysis" / "llamacpp_adapter_prompt.py",  # legacy compat only
    )

    review_prompt_path = next(
        (path for path in REVIEW_ENRICHMENT_PROMPT_CANDIDATES if path.exists()),
        None,
    )

    if review_prompt_path is None:
        print(f"ERROR: Prompt builder not found. Checked: {REVIEW_ENRICHMENT_PROMPT_CANDIDATES}")
        return 1

    prompt_builders.append((review_prompt_path, "compose_review_enrichment_prompt()"))

    check_num = 2
    for prompt_file, builder_name in prompt_builders:
        print(f"[{check_num}/8] Checking {builder_name} integration...")
        code, output = check_integration_in_prompt_builder(prompt_file, builder_name)
        print(f"      {output}")
        if code != 0:
            all_passed = False
        print()
        check_num += 1

    # Check 5: Unit tests
    print("[5/8] Running semantic injection detector unit tests...")
    code, output = run_unit_tests(args.verbose)
    all_output.append(output)
    if code == 0:
        print("      PASS: Detector unit tests")
    else:
        print("      FAIL: Detector unit tests")
        all_passed = False
    print()

    # Check 6: Drilldown prompt integration tests
    print("[6/8] Running drilldown prompt integration tests...")
    code, output = run_prompt_integration_tests(args.verbose)
    all_output.append(output)
    if code == 0:
        print("      PASS: Drilldown prompt integration tests")
    else:
        print("      FAIL: Drilldown prompt integration tests")
        all_passed = False
    print()

    # Check 7: Assessment prompt tests
    print("[7/8] Running assessment prompt injection tests...")
    test_file = repo_root / "tests" / "test_semantic_injection_assessment_prompt.py"
    code, output = run_test_file(test_file, args.verbose)
    all_output.append(output)
    if code == 0:
        print("      PASS: Assessment prompt injection tests")
    else:
        print("      FAIL: Assessment prompt injection tests")
        all_passed = False
    print()

    # Check 8: Review enrichment prompt tests (split into detection and boundaries)
    print("[8/8] Running review enrichment prompt injection tests...")
    review_test_files = [
        repo_root / "tests" / "test_semantic_injection_review_enrichment_detection.py",
        repo_root / "tests" / "test_semantic_injection_review_enrichment_boundaries.py",
    ]
    review_all_passed = True
    for test_file in review_test_files:
        code, output = run_test_file(test_file, args.verbose)
        all_output.append(output)
        if code != 0:
            review_all_passed = False
            print(f"      FAIL: {test_file.name}")
        else:
            print(f"      PASS: {test_file.name}")
    if review_all_passed:
        print("      PASS: Review enrichment prompt injection tests")
    else:
        print("      FAIL: Review enrichment prompt injection tests")
        all_passed = False
    print()

    # Summary
    print("=" * 60)
    if all_passed:
        print("VERIFICATION GATE: PASSED")
        print("=" * 60)
        print()
        print("Semantic injection detection coverage:")
        print("  - Detector module exists and is properly defined")
        print("  - build_drilldown_prompt() integrates detector")
        print("  - build_assessment_prompt() integrates detector")
        print("  - compose_review_enrichment_prompt() integrates detector")
        print("  - Detector unit tests pass")
        print("  - Drilldown prompt integration tests pass")
        print("  - Assessment prompt tests pass")
        print("  - Review enrichment prompt tests pass")
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