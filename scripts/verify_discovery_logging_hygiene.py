#!/usr/bin/env python3
"""Discovery Logging Hygiene Verification Gate.

This script verifies that discovery strategy files do not contain unsafe
logging patterns that could leak raw kubectl/stderr errors.

Forbidden patterns:
1. _logger.warning(...) - raw warning logs can leak sensitive error text
2. exc_info=True - logging exceptions with traceback leaks sensitive data
3. stderr in logging - raw subprocess stderr interpolated into logger calls

Scope:
    - src/k8s_diag_agent/external_analysis/*discovery*strategy*.py

Usage:
    python scripts/verify_discovery_logging_hygiene.py
    python scripts/verify_discovery_logging_hygiene.py --verbose
    python scripts/verify_discovery_logging_hygiene.py --sentinel  # self-test with synthetic violations

Exit codes:
    0 - All checks passed
    1 - One or more forbidden patterns detected
    2 - Sentinel test failed (self-test mode detected regressions)

See: ACT: Add gate for unsafe discovery fallback logging
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple


# Named tuple for forbidden pattern entries
class _ForbiddenPattern(NamedTuple):
    pattern: re.Pattern[str]
    name: str
    explanation: str


# Patterns that indicate unsafe logging in discovery strategies
_FORBIDDEN_PATTERNS: list[_ForbiddenPattern] = [
    # 1. _logger.warning - raw warnings can leak error text
    _ForbiddenPattern(
        re.compile(r'_logger\.warning\s*\('),
        "_logger.warning(...)",
        "raw warning log - may leak sensitive error text",
    ),
    # 2. exc_info=True - logging exception with traceback leaks sensitive data
    _ForbiddenPattern(
        re.compile(r'exc_info\s*=\s*True'),
        "exc_info=True",
        "exception traceback logging - may leak sensitive data",
    ),
    # 3. stderr interpolated into logger calls
    _ForbiddenPattern(
        re.compile(r'_logger\.[a-z]+\([^)]*\.stderr'),
        "stderr in logger call",
        "raw stderr interpolation - may leak sensitive error text",
    ),
]


# Export for test imports
__all__ = [
    "_FORBIDDEN_PATTERNS",
    "check_file_for_patterns",
    "check_all_files",
    "find_discovery_strategy_files",
]


def find_discovery_strategy_files(repo_root: Path) -> list[Path]:
    """Find all discovery strategy files in the target scope."""
    external_analysis_dir = repo_root / "src" / "k8s_diag_agent" / "external_analysis"
    
    if not external_analysis_dir.exists():
        return []
    
    # Match files that:
    # - Are in external_analysis directory
    # - Contain "discovery" and "strategy" in their name
    # - Are Python files
    strategy_files = []
    for pattern in external_analysis_dir.glob("*discovery*strategy*.py"):
        strategy_files.append(pattern)
    for pattern in external_analysis_dir.glob("*strategy*discovery*.py"):
        strategy_files.append(pattern)
    
    return sorted(set(strategy_files))


def check_file_for_patterns(
    file_path: Path,
    patterns: list[_ForbiddenPattern],
) -> list[tuple[int, str, str]]:
    """Check a file for forbidden logging patterns.
    
    Returns:
        List of (line_number, pattern_name, explanation) for each violation.
    """
    violations: list[tuple[int, str, str]] = []
    
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return [(0, "FILE_READ_ERROR", str(e))]
    
    lines = content.split("\n")
    
    for line_num, line in enumerate(lines, start=1):
        # Skip comment lines
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        for pattern, name, explanation in patterns:
            if pattern.search(line):
                violations.append((line_num, name, explanation))
    
    return violations


def check_all_files(
    files: list[Path],
    patterns: list[_ForbiddenPattern],
) -> dict[Path, list[tuple[int, str, str]]]:
    """Check all files for forbidden patterns.
    
    Returns:
        Dict mapping file paths to lists of violations.
    """
    results: dict[Path, list[tuple[int, str, str]]] = {}
    
    for file_path in files:
        violations = check_file_for_patterns(file_path, patterns)
        if violations:
            results[file_path] = violations
    
    return results


def run_sentinel_test() -> tuple[bool, str]:
    """Run sentinel self-test with synthetic violations.
    
    Creates a temporary file with known violations and verifies the
    checker correctly detects them. This ensures the verifier itself
    works correctly.
    
    Returns:
        Tuple of (passed, output_message)
    """
    sentinel_content = '''"""Sentinel test file - DO NOT COMMIT."""
from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def test_function():
    # VIOLATION 1: _logger.warning
    _logger.warning("This is a raw warning that should be detected")
    
    # VIOLATION 2: exc_info=True
    try:
        pass
    except Exception:
        _logger.error("Error occurred", exc_info=True)
    
    # VIOLATION 3: stderr in logger call
    result = subprocess.run(["kubectl", "get", "pods"], capture_output=True)
    _logger.debug("Command failed: %s", result.stderr)
'''
    
    # Write to a temporary file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_sentinel_discovery_strategy.py",
        delete=False,
    ) as f:
        f.write(sentinel_content)
        sentinel_path = Path(f.name)
    
    try:
        violations = check_file_for_patterns(
            sentinel_path,
            _FORBIDDEN_PATTERNS,
        )
        
        expected_counts = {
            "_logger.warning(...)": 1,
            "exc_info=True": 1,
            "stderr in logger call": 1,
        }
        
        actual_counts: dict[str, int] = {}
        for _, name, _ in violations:
            actual_counts[name] = actual_counts.get(name, 0) + 1
        
        output_lines = ["Sentinel Self-Test Results:", ""]
        all_passed = True
        
        for pattern_name, expected_count in expected_counts.items():
            actual_count = actual_counts.get(pattern_name, 0)
            if actual_count == expected_count:
                output_lines.append(
                    f"  PASS: Detected {actual_count}x {pattern_name}"
                )
            else:
                output_lines.append(
                    f"  FAIL: Expected {expected_count}x {pattern_name}, "
                    f"got {actual_count}x"
                )
                all_passed = False
        
        if not violations:
            output_lines.append("  FAIL: No violations detected (sentinel failed)")
            all_passed = False
        
        return all_passed, "\n".join(output_lines)
    
    finally:
        # Clean up temporary file
        sentinel_path.unlink(missing_ok=True)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify discovery strategy logging hygiene"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose output including file contents",
    )
    parser.add_argument(
        "--sentinel",
        action="store_true",
        help="Run sentinel self-test to verify the checker works",
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("Discovery Logging Hygiene Verification Gate")
    print("=" * 60)
    print()
    
    # Find the repository root
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    
    # Find discovery strategy files
    strategy_files = find_discovery_strategy_files(repo_root)
    
    print(f"[SCOPE] Checking {len(strategy_files)} discovery strategy files:")
    for f in strategy_files:
        print(f"         - {f.relative_to(repo_root)}")
    print()
    
    # Run sentinel test first if requested
    if args.sentinel:
        print("[SENTINEL] Running self-test with synthetic violations...")
        sentinel_passed, sentinel_output = run_sentinel_test()
        print(sentinel_output)
        print()
        if not sentinel_passed:
            print("SENTINEL TEST FAILED - Verifier itself is broken")
            return 2
        print("SENTINEL TEST PASSED - Verifier correctly detects violations")
        print()
    
    # Check all files
    print("[CHECK] Scanning for forbidden patterns...")
    violations_map = check_all_files(strategy_files, _FORBIDDEN_PATTERNS)
    
    # Report results
    if violations_map:
        print()
        print("FORBIDDEN PATTERNS DETECTED:")
        print("-" * 40)
        
        total_violations = 0
        for file_path, violations in violations_map.items():
            rel_path = file_path.relative_to(repo_root)
            print(f"\n  {rel_path}:")
            
            for line_num, pattern_name, explanation in violations:
                print(f"    Line {line_num}: {pattern_name}")
                print(f"             {explanation}")
                total_violations += 1
        
        print()
        print("=" * 60)
        print(f"VERIFICATION GATE: FAILED ({total_violations} violation(s))")
        print("=" * 60)
        print()
        print("Forbidden patterns enforced:")
        print("  1. _logger.warning(...) - raw warning logs leak error text")
        print("  2. exc_info=True - exception traceback logging leaks data")
        print("  3. stderr in logger call - raw stderr interpolation leaks data")
        print()
        print("Use structured logging via discovery_structured_logging module.")
        return 1
    else:
        print()
        print("=" * 60)
        print("VERIFICATION GATE: PASSED")
        print("=" * 60)
        print()
        print("All discovery strategy files comply with logging hygiene:")
        print("  - No _logger.warning() fallback paths")
        print("  - No exc_info=True in logger calls")
        print("  - No raw stderr interpolation in logger calls")
        return 0


if __name__ == "__main__":
    sys.exit(main())
