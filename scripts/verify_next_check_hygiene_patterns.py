"""Forbidden and allowed patterns for next-check sanitization hygiene verification.

This module defines the static analysis patterns used to detect unsanitized output
projection in next-check response paths.

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
"""

from __future__ import annotations

import re
from typing import NamedTuple


# Named tuple for forbidden pattern entries
class _ForbiddenPattern(NamedTuple):
    pattern: re.Pattern[str]
    name: str
    explanation: str


# Patterns that indicate unsanitized output projection in next-check response paths
FORBIDDEN_PATTERNS: list[_ForbiddenPattern] = [
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
ALLOWED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'sanitized_raw_output'),
    re.compile(r'sanitized_error_summary'),
    re.compile(r'sanitize_execution_output\s*\('),
    re.compile(r'sanitize_exception_message\s*\('),
]
