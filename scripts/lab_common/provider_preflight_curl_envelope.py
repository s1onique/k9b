"""Curl envelope parsing for provider health responses.

This module provides functions for parsing the known curl diagnostic envelope
suffix that the wrapper emits after provider health JSON responses:
  - STDERR_BLOCK marker (optional)
  - CURL_EXIT=<code>
  - HTTP_CODE=<code>

Only successful envelopes (CURL_EXIT=0 AND HTTP_CODE=200) are accepted.
Note: STDOUT_BLOCK prefix is stripped by the caller before this parser runs.
"""

from __future__ import annotations

import re


_CURL_EXIT_RE = re.compile(r"^CURL_EXIT=(\d+)$")
_HTTP_CODE_RE = re.compile(r"^HTTP_CODE=(\d{3})$")


def parse_known_curl_envelope_suffix(suffix: str) -> tuple[int, int, str] | None:
    """Parse known successful curl envelope suffix.

    Known successful curl envelope patterns:
    - CURL_EXIT=0\\nHTTP_CODE=200
    - STDERR_BLOCK\\nCURL_EXIT=0\\nHTTP_CODE=200
    - STDERR_BLOCK\\n<debug noise>\\nCURL_EXIT=0\\nHTTP_CODE=200

    Only accepts CURL_EXIT=0 AND HTTP_CODE=200 (successful request).

    Args:
        suffix: The trailing text after JSON body

    Returns:
        Tuple of (curl_exit, http_code, stderr_block) if valid, None otherwise
    """
    lines = suffix.strip().splitlines()
    if not lines:
        return None

    stderr_lines: list[str] = []

    # Check if suffix starts with STDERR_BLOCK
    if lines[0] == "STDERR_BLOCK":
        # Need at least STDERR_BLOCK + CURL_EXIT + HTTP_CODE = 3 lines
        if len(lines) < 3:
            return None

        # Collect stderr content (between STDERR_BLOCK and CURL_EXIT/HTTP_CODE)
        # Lines between first and last two lines are stderr content
        stderr_lines = lines[1:-2]
        metadata_lines = lines[-2:]
    else:
        # No STDERR_BLOCK - expect exactly CURL_EXIT and HTTP_CODE
        metadata_lines = lines

    # Need exactly 2 metadata lines: CURL_EXIT and HTTP_CODE
    if len(metadata_lines) != 2:
        return None

    # Validate CURL_EXIT=0
    curl_match = _CURL_EXIT_RE.fullmatch(metadata_lines[0])
    if curl_match is None:
        return None
    curl_exit = int(curl_match.group(1))
    if curl_exit != 0:
        return None

    # Validate HTTP_CODE=200
    http_match = _HTTP_CODE_RE.fullmatch(metadata_lines[1])
    if http_match is None:
        return None
    http_code = int(http_match.group(1))
    if http_code != 200:
        return None

    return curl_exit, http_code, "\n".join(stderr_lines)
