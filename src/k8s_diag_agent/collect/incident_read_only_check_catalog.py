"""Read-only check catalog for automatic diagnosis loop.

This module provides:
- CheckDefinition: Individual check specification
- CheckCatalog: Catalog of all available read-only checks
- select_checks(): Select checks based on cost, value, and hypothesis targeting

Design constraints:
- All checks are read-only (list, get, logs with tail limits)
- No mutation, no exec, no kubectl shell
- Bounded timeouts and result sizes

This module is a facade that re-exports from specialized modules:
- incident_read_only_check_catalog_contracts: CheckDefinition, CheckCost, etc.
- incident_read_only_check_catalog_definitions: ALL_CHECKS, CHECK_BY_ID, etc.
"""

from __future__ import annotations

from typing import Any

# Re-export contracts
from .incident_read_only_check_catalog_contracts import (
    SCHEMA_VERSION,
    CheckCost,
    CheckDefinition,
    CheckExpectedValue,
)

# Re-export definitions and catalog functions
from .incident_read_only_check_catalog_definitions import (
    ALL_CHECKS,
)

# Build CHECK_BY_ID from ALL_CHECKS
CHECK_BY_ID: dict[str, CheckDefinition] = {c.check_id: c for c in ALL_CHECKS}


# =============================================================================
# Check Selection
# =============================================================================


def select_checks(
    hypotheses: list[dict[str, Any]],
    available_identity: dict[str, str | None],
    max_checks: int = 3,
) -> list[CheckDefinition]:
    """Select checks based on cost, value, and hypothesis targeting.

    Selection criteria:
    1. Highest expected_value first
    2. Lowest cost
    3. Targets top-ranked hypothesis
    4. Has bounded implementation (in catalog)
    5. Has required identity

    Args:
        hypotheses: List of hypothesis dicts with 'hypothesis_id', 'rank', 'next_best_check'
        available_identity: Available identity (namespace, object_name, pod_name, node_name)
        max_checks: Maximum number of checks to select

    Returns:
        List of selected CheckDefinition objects
    """
    selected: list[CheckDefinition] = []

    # Build set of suggested check IDs from hypotheses
    suggested_ids: set[str] = set()
    for h in hypotheses:
        next_check = h.get("next_best_check")
        if next_check:
            suggested_ids.add(next_check)

    # Sort criteria: prefer suggested > high value > low cost
    def sort_key(check: CheckDefinition) -> tuple[int, int, int]:
        # Suggested by hypothesis (lower = more preferred)
        suggested_rank = 0 if check.check_id in suggested_ids else 1

        # Expected value (high = more preferred, so invert)
        value_order = {"high": 0, "medium": 1, "low": 2}
        value_rank = value_order.get(check.expected_value, 2)

        # Cost (low = more preferred, so invert)
        cost_order = {"low": 0, "medium": 1, "high": 2}
        cost_rank = cost_order.get(check.cost, 2)

        return (suggested_rank, value_rank, cost_rank)

    # Filter and sort checks
    candidate_checks = [
        c for c in ALL_CHECKS
        if c.can_execute_with(**available_identity)
    ]
    candidate_checks.sort(key=sort_key)

    # Select top checks
    for check in candidate_checks:
        if len(selected) >= max_checks:
            break
        selected.append(check)

    return selected


# =============================================================================
# Evidence Delta Builder
# =============================================================================


def build_evidence_delta(
    check_id: str,
    check_result: dict[str, Any],
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build evidence delta from check result.

    Args:
        check_id: The check that was executed
        check_result: Result from the check runner
        hypotheses: Current hypotheses

    Returns:
        Evidence delta dict with check_id, summary, and signal interpretations
    """
    # Extract summary
    summary = check_result.get("summary", "")
    if not summary:
        # Build from evidence
        evidence = check_result.get("evidence", {})
        summary = evidence.get("summary", str(evidence)[:200])

    # Determine signal impact
    signal_indicators = []
    summary_lower = summary.lower()

    # Generic signal detection
    if "warning" in summary_lower or "error" in summary_lower:
        signal_indicators.append("signal:warning_or_error_detected")
    if "not ready" in summary_lower or "unready" in summary_lower:
        signal_indicators.append("signal:readiness_failure")
    if "crashloop" in summary_lower or "crash" in summary_lower:
        signal_indicators.append("signal:crash_detected")
    if "imagepull" in summary_lower or "pull" in summary_lower:
        signal_indicators.append("signal:image_pull_issue")
    if "pending" in summary_lower or "unschedulable" in summary_lower:
        signal_indicators.append("signal:scheduling_failure")
    if "oom" in summary_lower or "killed" in summary_lower:
        signal_indicators.append("signal:memory_pressure")

    return {
        "check_id": check_id,
        "summary": summary[:500],  # Bound summary
        "signal_indicators": signal_indicators,
        "result_keys": list(check_result.keys())[:10],  # Bound keys
    }


__all__ = [
    "SCHEMA_VERSION",
    "CheckCost",
    "CheckExpectedValue",
    "CheckDefinition",
    "ALL_CHECKS",
    "CHECK_BY_ID",
    "select_checks",
    "build_evidence_delta",
]
