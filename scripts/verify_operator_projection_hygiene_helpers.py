"""Scanning and reporting helpers for operator projection sanitization hygiene verification.

This module provides the core scanning logic and reporting functions used by
the hygiene verification gate for operator-facing UI/API projections.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import NamedTuple

from verify_operator_projection_hygiene_patterns import (
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


def _is_in_structured_log_call(line: str) -> bool:
    """Check if a line is part of a structured log call (emit_structured_log)."""
    return "emit_structured_log" in line


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
                if "artifact.raw_output" in name or "artifact.error_summary" in name:
                    if _has_allowed_sanitization(lines, line_num):
                        continue  # Skip this match - it's used as argument to sanitization
                
                # Special handling for str(exc) in response payloads:
                # Logger calls with str(exc) in extra dict are allowed (for log fields)
                # Structured logging (emit_structured_log) is allowed (internal logging)
                # Only flag str(exc) when used directly in response payloads
                if name == "str(exc) in response payload":
                    if _is_in_logger_call(line):
                        continue  # Skip - logger calls use str(exc) for log fields, not UI
                    # Check if this is in a structured log call - look at wider context
                    context_start = max(0, line_num - 20)
                    context_end = min(len(lines), line_num + 5)
                    context_block = "\n".join(lines[context_start:context_end])
                    if "emit_structured_log" in context_block:
                        continue  # Skip - structured log calls are internal logging, not UI
                    # Check if this is in a logger extra= dict by checking context
                    if "extra=" in line:
                        context_start = max(0, line_num - 10)
                        context_block = "\n".join(lines[context_start:line_num])
                        if re.search(r'_?logger\.[a-z]+\s*\(', context_block):
                            continue  # Skip - logger extra dict uses str(exc)
                
                # Special handling for exc_info=True: skip if in logger call context
                # Internal error-handling logger calls are allowed; only flag in response paths
                if name == "exc_info=True in response path":
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
                    # Also skip if in emit_structured_log context
                    if "emit_structured_log" in context_block:
                        continue  # Skip - structured logging is internal
                    # Flag any exc_info=True not in logger/structured-log context
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


def find_operator_projection_files(repo_root: Path) -> list[Path]:
    """Find all operator-facing projection files in the target scope.
    
    Scope:
        - src/k8s_diag_agent/ui/api_*.py
        - src/k8s_diag_agent/ui/server_*.py
        - src/k8s_diag_agent/ui/model_*.py
        - src/k8s_diag_agent/ui/*projection*.py
        - src/k8s_diag_agent/ui/*summary*.py
        - src/k8s_diag_agent/ui/*status*.py
        - src/k8s_diag_agent/ui/notifications*.py
        - src/k8s_diag_agent/health/ui_projection/*.py
    """
    ui_dir = repo_root / "src" / "k8s_diag_agent" / "ui"
    health_ui_projection_dir = repo_root / "src" / "k8s_diag_agent" / "health" / "ui_projection"
    
    projection_files: list[Path] = []
    
    if ui_dir.exists():
        # API files
        for pattern in ui_dir.glob("api_*.py"):
            projection_files.append(pattern)
        # Server files
        for pattern in ui_dir.glob("server_*.py"):
            projection_files.append(pattern)
        # Model files
        for pattern in ui_dir.glob("model_*.py"):
            projection_files.append(pattern)
        # Projection, summary, status files
        for pattern in ui_dir.glob("*projection*.py"):
            projection_files.append(pattern)
        for pattern in ui_dir.glob("*summary*.py"):
            projection_files.append(pattern)
        for pattern in ui_dir.glob("*status*.py"):
            projection_files.append(pattern)
        # Notifications files
        for pattern in ui_dir.glob("notifications*.py"):
            projection_files.append(pattern)
    
    if health_ui_projection_dir.exists():
        for pattern in health_ui_projection_dir.glob("*.py"):
            projection_files.append(pattern)
    
    return sorted(set(projection_files))


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
    # VIOLATION 1: str(exc) in response payload (not in logger call)
    response = {
        "runs": [],
        "error": str(exc),  # Should use sanitize_exception_message
    }
    
    # VIOLATION 2: artifact.raw_output used directly
    response = {
        "rawOutput": artifact.raw_output,  # Should use sanitize_execution_output
    }
    
    # VIOLATION 3: artifact.error_summary used directly
    response = {
        "errorSummary": artifact.error_summary,  # Should use sanitize_execution_output
    }
    
    # VIOLATION 4: exc_info=True outside logger context
    def handler_without_logger():
        try:
            pass
        except Exception:
            exc_info = True  # exc_info=True would leak traceback if used here
    
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
    
    # ALLOWED: Logger calls use str(exc) for log fields (internal only)
    _logger.warning("Failed to build payload", extra={"error": str(exc)})
    
    # ALLOWED: Structured logging
    from ..structured_logging import emit_structured_log
    emit_structured_log(
        component="test",
        message="Failed to build payload",
        run_id="",
        run_label="",
        severity="ERROR",
        metadata={"error": str(exc)},
    )
'''
    
    # Write to a temporary file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_sentinel_operator_projection.py",
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
            "str(exc) in response payload": 1,
            "artifact.raw_output in response payload": 1,
            "artifact.error_summary in response payload": 1,
            "exc_info=True in response path": 1,
            "stdout in response payload": 1,
            "stderr in response payload": 1,
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
