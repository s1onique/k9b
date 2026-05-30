"""Query string parsing utilities for the UI server.

This module contains parsing helpers for query string parameters extracted from
server.py. These utilities handle limit and page parsing for pagination.

Extraction rationale: These are stateless utility functions that can be tested
independently without needing a full handler instance.
"""

from __future__ import annotations


def parse_limit(value: str | None) -> int | None:
    """Parse a limit parameter from query string.

    Args:
        value: The string value to parse, or None.

    Returns:
        Parsed positive integer, or None if value is empty/invalid.
    """
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def parse_page(value: str | None) -> int:
    """Parse a page parameter from query string.

    Args:
        value: The string value to parse, or None.

    Returns:
        Parsed positive integer, or 1 if value is empty/invalid.
    """
    parsed = parse_limit(value)
    return parsed if parsed else 1
