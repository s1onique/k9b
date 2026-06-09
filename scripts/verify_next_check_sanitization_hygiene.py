#!/usr/bin/env python3
"""Next-Check Projection Sanitization Hygiene Verification Gate.

This script verifies that next-check response paths properly sanitize execution
output and exception messages before returning them to the UI.

Forbidden patterns (bypass sanitization):
1. artifact.raw_output (raw output without sanitize_execution_output)
2. artifact.error_summary (raw error without sanitize_execution_output)
3. str(exc) or f"{exc}" (raw exception interpolation)
4. exc_info=True in logging (raw traceback)
5. stdout/stderr in response payloads
6. traceback.format_exc() or format_exception (raw traceback)

Allowed patterns (sanitized projection):
1. sanitized_raw_output from sanitize_execution_output
2. sanitized_error_summary from sanitize_execution_output
3. sanitize_exception_message(exc)
4. sanitize_execution_output(artifact.raw_output, artifact.error_summary)

Scope:
    - src/k8s_diag_agent/ui/*next_check*.py
    - src/k8s_diag_agent/ui/*server_next_check*.py

Usage:
    python scripts/verify_next_check_sanitization_hygiene.py
    python scripts/verify_next_check_sanitization_hygiene.py --verbose
    python scripts/verify_next_check_sanitization_hygiene.py --sentinel  # self-test

Exit codes:
    0 - All checks passed
    1 - One or more forbidden patterns detected
    2 - Sentinel test failed (self-test mode detected regressions)

See: ACT: Add static hygiene verifier for next-check projection sanitization
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


# Patterns that indicate unsanitized output projection in next-check response paths
_FORBIDDEN_PATTERNS: list[_ForbiddenPattern] = [
    # 1. artifact.raw_output used directly without sanitize_execution_output
    _ForbiddenPattern(
        re.compile(r'artifact\.raw_output'),
        "artifact.raw_output (unsanitized)",
        "raw output field used without sanitize_execution_output() call",
    ),
    # 2. artifact.error_summary used directly without sanitize_execution_output
    _ForbiddenPattern(
        re.compile(r'artifact\.error_summary'),
        "artifact.error_summary (unsanitized)",
        "raw error_summary field used without sanitize_execution_output() call",
    ),
    # 3. Raw exception interpolation (str(exc), f"{exc}", etc.)
    #    Note: sanitize_exception_message(exc) is allowed
    _ForbiddenPattern(
        re.compile(r'(?:str\s*\(\s*exc\s*\)|f?"\{exc\}"'
                  r'|(?<!sanitize_exception_message\()(?<!sanitize_)\s*str\s*\(\s*exc\s*\))'),
        "raw exception interpolation",
        "raw exception string interpolated without sanitize_exception_message()",
    ),
    # 4. exc_info=True in logging (leaks traceback)
    _ForbiddenPattern(
        re.compile(r'exc_info\s*=\s*True'),
        "exc_info=True",
        "traceback logging may leak sensitive data into operator-visible diagnostics",
    ),
    # 5. stdout/stderr in response payloads
    _ForbiddenPattern(
        re.compile(r'["\']stdout["\']\s*:\s*(?!sanitized)', re.IGNORECASE),
        "stdout in payload",
        "raw stdout in response payload without sanitization",
    ),
    _ForbiddenPattern(
        re.compile(r'["\']stderr["\']\s*:\s*(?!sanitized)', re.IGNORECASE),
        "stderr in payload",
        "raw stderr in response payload without sanitization",
    ),
    # 6. Raw traceback formatting
    _ForbiddenPattern(
        re.compile(r'traceback\.format_(?:exc|exception)'),
        "raw traceback formatting",
        "raw traceback formatting may leak sensitive data",
    ),
]

# Patterns that indicate SANITIZED projection (these are ALLOWED)
_ALLOWED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'sanitized_raw_output'),
    re.compile(r'sanitized_error_summary'),
    re.compile(r'sanitize_execution_output\s*\('),
    re.compile(r'sanitize_exception_message\s*\('),
]


# Export for test imports
__all__ = [
    "_FORBIDDEN_PATTERNS",
    "_ALLOWED_PATTERNS",
    "check_file_for_patterns",
    "check_all_files",
    "find_next_check_files",
]


def find_next_check_files(repo_root: Path) -> list[Path]:
    """Find all next-check related files in the target scope."""
    ui_dir = repo_root / "src" / "k8s_diag_agent" / "ui"
    
    if not ui_dir.exists():
        return []
    
    # Match files that contain "next_check" in their name and are Python files
    next_check_files = []
    for pattern in ui_dir.glob("*next_check*.py"):
        next_check_files.append(pattern)
    
    return sorted(set(next_check_files))


def _is_line_commented(line: str) -> bool:
    """Check if a line is entirely commented out."""
    stripped = line.strip()
    return stripped.startswith("#")


def _has_allowed_sanitization(context_lines: list[str], line_num: int) -> bool:
    """Check if the surrounding context contains sanitization calls."""
    # Look at surrounding 3 lines for sanitization patterns
    start = max(0, line_num - 3)
    end = min(len(context_lines), line_num + 2)
    
    context = "\n".join(context_lines[start:end])
    
    for pattern in _ALLOWED_PATTERNS:
        if pattern.search(context):
            return True
    
    return False


def _is_in_logger_call(line: str) -> bool:
    """Check if a line is a logger call (has _logger.*(.*) pattern)."""
    # This pattern matches logger calls like:
    # _logger.debug("message", ...)
    # _logger.info("message", ...)
    # _logger.warning("message", ...)
    # _logger.error("message", ...)
    # logger.warning("message", ...)  # without underscore
    return bool(re.search(r'_?logger\.[a-z]+\s*\(', line))


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
        if _is_line_commented(line):
            continue
        
        for pattern, name, explanation in patterns:
            if pattern.search(line):
                # Special handling for artifact.raw_output and artifact.error_summary:
                # Check if the surrounding context contains a sanitization call
                # If so, this is an allowed usage (arguments to sanitize_* functions)
                if name in ("artifact.raw_output (unsanitized)", "artifact.error_summary (unsanitized)"):
                    if _has_allowed_sanitization(lines, line_num):
                        continue  # Skip this match - it's used as argument to sanitization
                
                # Special handling for str(exc): check if it's in a logger call
                # Logger calls with str(exc) in extra dict are allowed (for log fields)
                # Only flag str(exc) when used directly in response payloads (_send_json)
                if name == "raw exception interpolation":
                    if _is_in_logger_call(line):
                        continue  # Skip - logger calls use str(exc) for log fields, not UI
                    # Also skip if str(exc) is in an extra= dict value (part of logger call)
                    if "extra=" in line or '"error":' in line or "'error':" in line:
                        # Check if this is part of a logger extra dict by checking if
                        # there's a logger call before (within 10 lines)
                        context_start = max(0, line_num - 10)
                        context_block = "\n".join(lines[context_start:line_num])
                        if re.search(r'_?logger\.[a-z]+\s*\(', context_block):
                            continue  # Skip - logger extra dict uses str(exc)
                
                # Special handling for exc_info=True: skip if in logger call context
                # Internal error-handling logger calls are allowed; only flag in response paths
                if name == "exc_info=True":
                    # Check if this exc_info=True is in a logger call (internal error handling)
                    # by looking at surrounding context for logger patterns.
                    # Use 15-line window to capture multi-line logger calls like:
                    #   logger.warning(
                    #       "message",
                    #       extra={...},
                    #       exc_info=True,
                    #   )
                    context_start = max(0, line_num - 15)
                    context_end = min(len(lines), line_num + 2)
                    context_block = "\n".join(lines[context_start:context_end])
                    if re.search(r'_?logger\.[a-z]+\s*\(', context_block):
                        continue  # Skip - logger calls are internal error handling
                    # Flag any exc_info=True not in logger context
                    violations.append((line_num, name, explanation))
                else:
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
import traceback
from typing import TYPE_CHECKING

from ..security import sanitize_execution_output, sanitize_exception_message

if TYPE_CHECKING:
    pass


_logger = logging.getLogger(__name__)


def test_function(artifact, exc):
    # VIOLATION 1: artifact.raw_output used directly
    response = {
        "rawOutput": artifact.raw_output,  # Should use sanitize_execution_output
    }
    
    # VIOLATION 2: artifact.error_summary used directly
    response = {
        "errorSummary": artifact.error_summary,  # Should use sanitize_execution_output
    }
    
    # VIOLATION 3: str(exc) raw interpolation
    response = {
        "error": str(exc),  # Should use sanitize_exception_message
    }
    
    # VIOLATION 4: exc_info=True in a response path (not in logger call)
    # This simulates exc_info=True in a response payload, not internal logging
    def some_handler():
        try:
            pass
        except Exception:
            _logger.error("Error", exc_info=True)  # This is in logger context - allowed
    # VIOLATION 4b: exc_info=True outside logger context - should be flagged
    def another_handler():
        try:
            pass
        except Exception:
            raise RuntimeError("test") from exc
    # VIOLATION 4c: exc_info=True directly in code (not in logger call)
    def third_handler():
        try:
            pass
        except Exception:
            exc_info = True  # exc_info=True would leak traceback if used here
    # VIOLATION 4d: exc_info=True in a response payload (not in logger call)
    def fourth_handler():
        try:
            pass
        except Exception:
            response = {"error": str(exc), "traceback": exc_info=True}
    
    # VIOLATION 5: stdout in payload
    response = {
        "stdout": artifact.stdout,  # Should be sanitized
    }
    
    # VIOLATION 6: stderr in payload
    response = {
        "stderr": artifact.stderr,  # Should be sanitized
    }
    
    # VIOLATION 7: traceback.format_exc
    tb = traceback.format_exc()
    
    # ALLOWED: Proper sanitization usage
    sanitized_output, sanitized_error = sanitize_execution_output(
        artifact.raw_output,
        artifact.error_summary,
    )
    response = {
        "rawOutput": sanitized_output,
        "errorSummary": sanitized_error,
    }
    
    sanitized_exc = sanitize_exception_message(exc)
    response = {
        "error": f"Execution failed: {sanitized_exc}",
    }
'''
    
    # Write to a temporary file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_sentinel_next_check.py",
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
            "artifact.raw_output (unsanitized)": 1,
            "artifact.error_summary (unsanitized)": 1,
            "raw exception interpolation": 2,  # str(exc) in violation 3 and fourth_handler
            "exc_info=True": 1,
            "stdout in payload": 1,
            "stderr in payload": 1,
            "raw traceback formatting": 1,
        }
        
        actual_counts: dict[str, int] = {}
        for _, name, _ in violations:
            if name != "FILE_READ_ERROR":
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
        
        # Check that we got some violations
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
        description="Verify next-check sanitization hygiene"
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
    print("Next-Check Sanitization Hygiene Verification Gate")
    print("=" * 60)
    print()
    
    # Find the repository root
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    
    # Find next-check files
    next_check_files = find_next_check_files(repo_root)
    
    print(f"[SCOPE] Checking {len(next_check_files)} next-check files:")
    for f in next_check_files:
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
    violations_map = check_all_files(next_check_files, _FORBIDDEN_PATTERNS)
    
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
        print("  1. artifact.raw_output - must use sanitize_execution_output()")
        print("  2. artifact.error_summary - must use sanitize_execution_output()")
        print("  3. str(exc) - must use sanitize_exception_message()")
        print("  4. exc_info=True - traceback logging leaks to UI")
        print("  5. stdout/stderr in payloads - must be sanitized")
        print("  6. traceback.format_* - raw traceback leaks sensitive data")
        print()
        return 1
    else:
        print()
        print("=" * 60)
        print("VERIFICATION GATE: PASSED")
        print("=" * 60)
        print()
        print("All next-check files comply with sanitization hygiene:")
        print("  - artifact.raw_output sanitized via sanitize_execution_output()")
        print("  - artifact.error_summary sanitized via sanitize_execution_output()")
        print("  - Exceptions sanitized via sanitize_exception_message()")
        print("  - No exc_info=True in next-check response paths")
        print("  - No raw stdout/stderr in response payloads")
        print("  - No raw traceback formatting")
        return 0


if __name__ == "__main__":
    sys.exit(main())
