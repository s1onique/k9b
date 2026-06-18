"""Scanning and reporting helpers for next-check sanitization hygiene verification.

This module provides the core scanning logic and reporting functions used by
the hygiene verification gate.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import NamedTuple

from verify_next_check_hygiene_patterns import (
    ALLOWED_PATTERNS,
    FORBIDDEN_PATTERNS,
)


# Named tuple type alias for pattern entries (re-exported for external use)
class _ForbiddenPattern(NamedTuple):
    pattern: re.Pattern[str]
    name: str
    explanation: str


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
    
    for pattern in ALLOWED_PATTERNS:
        if pattern.search(context):
            return True
    
    return False


def _is_in_logger_call(line: str) -> bool:
    """Check if a line is a logger call (has _logger.*(.*) pattern)."""
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
            FORBIDDEN_PATTERNS,
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


def format_violations_report(
    violations_map: dict[Path, list[tuple[int, str, str]]],
    repo_root: Path,
) -> tuple[int, str]:
    """Format violations into a report string.
    
    Returns:
        Tuple of (total_violations, report_string)
    """
    output_lines = []
    total_violations = 0
    
    for file_path, violations in violations_map.items():
        rel_path = file_path.relative_to(repo_root)
        output_lines.append(f"\n  {rel_path}:")
        
        for line_num, pattern_name, explanation in violations:
            output_lines.append(f"    Line {line_num}: {pattern_name}")
            output_lines.append(f"             {explanation}")
            total_violations += 1
    
    return total_violations, "\n".join(output_lines)
