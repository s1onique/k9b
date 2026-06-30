# scripts/k9b_otel_demo_lab_deployment_helm.py
"""Helm command and value helpers for OTel Demo Lab deployment.

Provides reusable helpers for:
- Helm chart version validation
- Helm error classification
- Connectivity error classification
"""

from __future__ import annotations

import json
import re
import subprocess

from .k9b_lab_common_helpers import log
from .k9b_otel_demo_lab_constants import (
    FAILURE_CLUSTER_API_TIMEOUT,
    FAILURE_HELM_CHART_VERSION_NOT_FOUND,
)

# Patterns that indicate cluster_api_timeout
_CLUSTER_API_TIMEOUT_PATTERNS = [
    re.compile(r"i/o timeout", re.IGNORECASE),
    re.compile(r"dial tcp.*timeout", re.IGNORECASE),
    re.compile(r"connection refused", re.IGNORECASE),
    re.compile(r"no route to host", re.IGNORECASE),
    re.compile(r"network is unreachable", re.IGNORECASE),
]


def _classify_helm_chart_version_error(error_output: str) -> str | None:
    """Classify Helm chart version not found error.

    Returns the failure class string if classified, None otherwise.

    Only classifies version-specific errors, not generic "chart not found" errors
    (which could be repo issues, network problems, etc.).
    """
    if not error_output:
        return None

    # Check for version-specific not found patterns
    version_not_found_patterns = [
        re.compile(r"no chart version found", re.IGNORECASE),
        re.compile(r"couldn'?t find that version", re.IGNORECASE),
        re.compile(r"version .+ not found", re.IGNORECASE),
        re.compile(r"no .+ version .+ found", re.IGNORECASE),
    ]

    for pattern in version_not_found_patterns:
        if pattern.search(error_output):
            return FAILURE_HELM_CHART_VERSION_NOT_FOUND

    return None


def _validate_chart_version(repo_name: str, chart: str, version: str) -> tuple[bool, str]:
    """Validate that the requested chart version exists in the Helm repo.

    Returns:
        Tuple of (is_valid, message). If invalid, message contains available versions.
    """
    log(f"Validating chart version {version} for {chart}")

    # Search for available versions
    search_cmd = ["helm", "search", "repo", chart, "--versions", "--output", "json"]
    result = subprocess.run(search_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        log(f"Warning: Could not search Helm repo: {result.stderr}")
        return True, "Could not validate version"

    try:
        data = json.loads(result.stdout)
        versions = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "version" in item:
                    versions.append(item["version"])

        if version in versions:
            log(f"Chart version {version} is available")
            return True, ""
        else:
            available = ", ".join(versions[:10])  # Limit to first 10
            if len(versions) > 10:
                available += f", ... ({len(versions)} total)"
            return False, available
    except (json.JSONDecodeError, KeyError):
        log("Warning: Could not parse helm search output")
        return True, ""


def _classify_connectivity_error(error_output: str) -> str | None:
    """Classify a kubectl connectivity error.

    Returns the failure class string if classified, None otherwise.
    """
    if not error_output:
        return None

    for pattern in _CLUSTER_API_TIMEOUT_PATTERNS:
        if pattern.search(error_output):
            return FAILURE_CLUSTER_API_TIMEOUT

    # Generic check for timeout keywords
    if "timeout" in error_output.lower():
        return FAILURE_CLUSTER_API_TIMEOUT

    return None
