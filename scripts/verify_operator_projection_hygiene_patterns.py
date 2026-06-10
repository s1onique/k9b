"""Forbidden and allowed patterns for operator projection sanitization hygiene verification.

This module defines the static analysis patterns used to detect unsanitized output
projection in operator-facing API response paths.

Forbidden patterns (bypass sanitization):
    1. str(exc) or f"{exc}" in response payloads (raw exception interpolation)
    2. exc_info=True in non-logger contexts (raw traceback in UI payloads)
    3. stdout/stderr field keys without sanitization in response payloads
    4. artifact.raw_output used directly without sanitize_execution_output
    5. artifact.error_summary used directly without sanitize_execution_output
    6. traceback.format_exc() or format_exception (raw traceback)
    7. raw field keys like "raw_output", "error_summary", "error_message" without sanitization

Allowed patterns (sanitized projection):
    1. sanitized_raw_output from sanitize_execution_output
    2. sanitized_error_summary from sanitize_execution_output
    3. sanitize_exception_message(exc)
    4. sanitize_execution_output(artifact.raw_output, artifact.error_summary)
    5. sanitize_payload() wrapping artifact fields
"""

from __future__ import annotations

import re
from typing import NamedTuple


# Named tuple for forbidden pattern entries
class _ForbiddenPattern(NamedTuple):
    pattern: re.Pattern[str]
    name: str
    explanation: str


# Patterns that indicate unsanitized output projection in operator-facing response paths
FORBIDDEN_PATTERNS: list[_ForbiddenPattern] = [
    # 1. Raw exception interpolation in response payloads
    # Note: logger calls use str(exc) for log fields (allowed)
    # Only flag str(exc) when used directly in response dict construction
    _ForbiddenPattern(
        re.compile(r'["\']error["\']\s*:\s*str\s*\(\s*exc\s*\)'),
        "str(exc) in response payload",
        "raw exception string in API response - use sanitize_exception_message()",
    ),
    # 2. exc_info=True in response context (not in logger calls)
    _ForbiddenPattern(
        re.compile(r'exc_info\s*=\s*True'),
        "exc_info=True in response path",
        "traceback logging in non-logger context may leak sensitive data",
    ),
    # 3. stdout/stderr in response payloads without sanitization
    _ForbiddenPattern(
        re.compile(r'["\']stdout["\']\s*:\s*(?!sanitized)(?!None)(?!["\'])', re.IGNORECASE),
        "stdout in response payload",
        "raw stdout in API response payload without sanitization",
    ),
    _ForbiddenPattern(
        re.compile(r'["\']stderr["\']\s*:\s*(?!sanitized)(?!None)(?!["\'])', re.IGNORECASE),
        "stderr in response payload",
        "raw stderr in API response payload without sanitization",
    ),
    # 4. artifact.raw_output used directly in response dict construction
    # Excludes: local variable assignment, boolean checks, internal filtering
    # Only flags: direct assignment to response dict keys (key: artifact.raw_output)
    _ForbiddenPattern(
        re.compile(r'["\'][a-zA-Z_]+["\']\s*:\s*artifact\.raw_output(?!\s*or\s)(?!\s*and\s)(?!\s*==)(?!\s*!=)(?!\s*\))'),
        "artifact.raw_output in response payload",
        "raw output field in API response - use sanitize_execution_output() call",
    ),
    # 5. artifact.error_summary used directly in response dict construction
    # Excludes: local variable assignment, boolean checks, internal filtering
    # Only flags: direct assignment to response dict keys (key: artifact.error_summary)
    _ForbiddenPattern(
        re.compile(r'["\'][a-zA-Z_]+["\']\s*:\s*artifact\.error_summary(?!\s*or\s)(?!\s*and\s)(?!\s*==)(?!\s*!=)(?!\s*\))'),
        "artifact.error_summary in response payload",
        "raw error_summary field in API response - use sanitize_execution_output() call",
    ),
    # 6. Raw traceback formatting
    _ForbiddenPattern(
        re.compile(r'traceback\.format_(?:exc|exception)'),
        "raw traceback formatting",
        "raw traceback formatting may leak sensitive data",
    ),
    # 7. Direct raw_output/error_summary/error_message field keys in OPERATOR RESPONSE paths
    # Excludes: static strings, .get() calls, internal logging (emit_structured_log)
    # Only flags: direct assignment of unsanitized artifact fields or raw variables
    _ForbiddenPattern(
        re.compile(r'["\']raw_output["\']\s*:\s*artifact\.(raw_output|error_summary)(?!\s*or\s)(?!\s*and\s)(?!\s*==)(?!\s*!=)(?!\s*\))'),
        "raw_output field in operator response",
        "raw_output field in API response - use sanitize_execution_output()",
    ),
    _ForbiddenPattern(
        re.compile(r'["\']error_summary["\']\s*:\s*artifact\.(raw_output|error_summary)(?!\s*or\s)(?!\s*and\s)(?!\s*==)(?!\s*!=)(?!\s*\))'),
        "error_summary field in operator response",
        "error_summary field in API response - use sanitize_execution_output()",
    ),
    _ForbiddenPattern(
        re.compile(r'["\']error_message["\']\s*:\s*artifact\.(raw_output|error_summary)(?!\s*or\s)(?!\s*and\s)(?!\s*==)(?!\s*!=)(?!\s*\))'),
        "error_message field in operator response",
        "error_message field in API response - use sanitize_execution_output()",
    ),
]


# Patterns that indicate SANITIZED projection (these are ALLOWED)
ALLOWED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'sanitized_raw_output'),
    re.compile(r'sanitized_error_summary'),
    re.compile(r'sanitize_execution_output\s*\('),
    re.compile(r'sanitize_exception_message\s*\('),
    re.compile(r'sanitize_payload\s*\('),
]
