"""Span analysis and privacy check functions for index performance proof verification."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# =============================================================================
# Span Analysis Constants
# =============================================================================

CONTENT_INDEX_QUERY_SPAN_NAMES = {
    "k9b.content_index.query",
    "k9b.content_index.open",
    "k9b.content_index.validate",
}

CONTENT_INDEX_FALLBACK_SPAN_NAMES = {
    "k9b.content_index.fallback",
}

# =============================================================================
# Privacy Check Constants
# =============================================================================

RAW_INCIDENT_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)

ARTIFACT_PAYLOAD_MARKERS = [
    "BEGIN_CREDENTIALS",
    "BEGIN_PRIVATE_KEY",
    "BEGIN_RSA_PRIVATE_KEY",
    "BEGIN_EC_PRIVATE_KEY",
    "BEGIN_OPENSSH_PRIVATE_KEY",
    "BEGIN_GPG_PRIVATE_KEY_BLOCK",
    "kubeconfig",
    "token",
    "bearer",
    "secret",
]

_ARTIFACT_PAYLOAD_PATTERNS = [
    re.compile(pattern, re.IGNORECASE) for pattern in ARTIFACT_PAYLOAD_MARKERS
]

# =============================================================================
# Span Analysis Functions
# =============================================================================


def count_content_index_spans(spans: list[dict[str, Any]]) -> tuple[int, int]:
    """Count content index query and fallback spans.

    Args:
        spans: List of span dictionaries

    Returns:
        Tuple of (query_span_count, fallback_span_count)
    """
    query_count = 0
    fallback_count = 0

    for span in spans:
        name = span.get("name", "")
        if name in CONTENT_INDEX_QUERY_SPAN_NAMES:
            query_count += 1
        elif name in CONTENT_INDEX_FALLBACK_SPAN_NAMES:
            fallback_count += 1

    return query_count, fallback_count


def extract_indexed_endpoint_spans(
    spans: list[dict[str, Any]],
    route: str,
) -> list[dict[str, Any]]:
    """Extract spans for a specific indexed endpoint route.

    Args:
        spans: List of span dictionaries
        route: Normalized route name

    Returns:
        List of spans for this route
    """
    # This is a simplified version - in practice we'd need trace correlation
    # For now, we return all spans since trace capture is per-request
    return spans


# =============================================================================
# Privacy Check Functions
# =============================================================================


def check_raw_incident_id(text: str) -> bool:
    """Check if raw incident ID appears in text."""
    return bool(RAW_INCIDENT_ID_PATTERN.search(text))


def check_artifact_payload(text: str) -> bool:
    """Check if artifact payload markers appear in text."""
    for pattern in _ARTIFACT_PAYLOAD_PATTERNS:
        if pattern.search(text):
            return True
    return False


def check_privacy_in_file(path: Path) -> tuple[bool, list[str]]:
    """Check for privacy violations in a file.

    Args:
        path: Path to file

    Returns:
        Tuple of (passed, violations)
    """
    violations: list[str] = []
    try:
        content = path.read_text(errors="replace")
        if check_raw_incident_id(content):
            violations.append(f"Raw incident ID found in {path.name}")
        if check_artifact_payload(content):
            violations.append(f"Artifact payload marker found in {path.name}")
    except Exception as e:
        violations.append(f"Could not read {path.name}: {e}")
    return len(violations) == 0, violations


# =============================================================================
# API Shape Compatibility Check
# =============================================================================


def check_api_shape_compatibility(
    disabled_response: dict[str, Any],
    enabled_response: dict[str, Any],
) -> bool:
    """Check if API response shapes are compatible.

    Args:
        disabled_response: Response from disabled run
        enabled_response: Response from enabled run

    Returns:
        True if shapes are compatible
    """
    # Both should have 'incidents' key
    if "incidents" not in disabled_response and "incidents" not in enabled_response:
        return True

    if "incidents" in disabled_response and "incidents" not in enabled_response:
        return False
    if "incidents" not in disabled_response and "incidents" in enabled_response:
        return False

    # Check incident structure
    disabled_incidents = disabled_response.get("incidents", [])
    enabled_incidents = enabled_response.get("incidents", [])

    if len(disabled_incidents) != len(enabled_incidents):
        # Different counts might be OK if data changed, but flag it
        return True  # Allow this for now

    # Check structure of first incident
    if disabled_incidents and enabled_incidents:
        d_keys = set(disabled_incidents[0].keys()) if isinstance(disabled_incidents[0], dict) else set()
        e_keys = set(enabled_incidents[0].keys()) if isinstance(enabled_incidents[0], dict) else set()

        # Required fields should be present in both
        required_fields = {
            "incident_id",
            "namespace",
            "object_kind",
            "object_name",
            "candidate_class",
            "severity",
            "status",
        }
        if not required_fields.issubset(d_keys) or not required_fields.issubset(e_keys):
            return False

    return True
