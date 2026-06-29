"""Shared test helpers for incident report API tests.

This module provides common imports, fixtures, and utilities used across
incident report test modules.
"""

from __future__ import annotations

from typing import Any, cast

from k8s_diag_agent.ui.api_payloads import CrossClusterFindingPayload


def _sample_freshness(status: str) -> dict[str, object]:
    """Return a sample freshness payload."""
    return {
        "ageSeconds": 60 if status == "fresh" else 600 if status == "stale" else 120,
        "expectedIntervalSeconds": 300,
        "status": status,
    }


def _require_cross_cluster_findings(
    report: dict[str, Any] | Any,
) -> list[CrossClusterFindingPayload]:
    """Helper to require crossClusterFindings list, asserting presence."""
    findings = report.get("crossClusterFindings")
    assert findings is not None
    return cast(list[CrossClusterFindingPayload], findings)


def _require_str(value: str | None) -> str:
    """Helper to require a non-None string value."""
    assert value is not None
    return value
