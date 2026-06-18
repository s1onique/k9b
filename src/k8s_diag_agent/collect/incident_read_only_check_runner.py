"""Fake in-memory runner for registry-approved read-only checks.

This module provides a deterministic fake runner that:
- Consumes already-planned/accepted check specs from the loop planner
- Revalidates checks against the next-check policy before running
- Runs only fake/in-memory handlers (no Kubernetes, shell, subprocess)
- Produces bounded, JSON-serializable result artifacts
- Enforces check count and result size bounds

Design constraints:
- Pure functions only
- No store mutation
- No Kubernetes client calls
- No shell/subprocess/kubectl
- No LLM calls
- Deterministic with injected timestamps
- Explicit safety metadata

This module does NOT:
- Execute real Kubernetes collectors
- Call kubectl
- Run shell commands
- Instantiate Kubernetes clients
- Persist artifacts to disk
- Mutate incident store
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .incident_fake_handlers import (
    DEFAULT_MAX_CHECKS_TO_RUN,
    DEFAULT_MAX_RESULT_CHARS,
    DEFAULT_MAX_SUMMARY_CHARS,
    FAKE_HANDLERS,
    ReadOnlyCheckHandler,
)
from .incident_next_check_policy import (
    DISALLOWED_ACTIONS,
    validate_next_check_proposal,
)

__all__ = [
    "RUNNER_SCHEMA_VERSION",
    "DEFAULT_MAX_CHECKS_TO_RUN",
    "DEFAULT_MAX_RESULT_CHARS",
    "DEFAULT_MAX_SUMMARY_CHARS",
    "ReadOnlyCheckHandler",
    "run_read_only_checks",
    "run_checks_from_loop_decision",
]


# =============================================================================
# Constants
# =============================================================================

RUNNER_SCHEMA_VERSION = "1.0"

# Check result statuses
STATUS_COMPLETED = "completed"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"


# =============================================================================
# Result Building
# =============================================================================


def _build_safety_metadata() -> dict[str, Any]:
    """Build safety metadata for runner results."""
    return {
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": list(DISALLOWED_ACTIONS),
        "no_kubernetes_client": True,
        "no_shell": True,
        "no_subprocess": True,
        "no_kubectl": True,
        "no_mutation": True,
        "policy_revalidated": True,
        "fake_runner": True,
    }


def _truncate(s: str, max_chars: int) -> str:
    """Truncate string to max_chars, adding ellipsis if truncated."""
    if len(s) <= max_chars:
        return s
    return s[:max_chars - 3] + "..."


def _truncate_result(result: dict[str, Any]) -> dict[str, Any]:
    """Truncate result fields to stay within bounds."""
    truncated = dict(result)

    # Truncate summary at top level
    if "summary" in truncated and isinstance(truncated["summary"], str):
        truncated["summary"] = _truncate(truncated["summary"], DEFAULT_MAX_SUMMARY_CHARS)

    # Truncate observations at top level (common for fake handlers)
    if "observations" in truncated and isinstance(truncated["observations"], list):
        truncated["observations"] = [
            _truncate(str(o), DEFAULT_MAX_RESULT_CHARS) for o in truncated["observations"]
        ]

    # Truncate evidence nested dict
    if "evidence" in truncated and isinstance(truncated["evidence"], dict):
        evidence = dict(truncated["evidence"])
        if "summary" in evidence and isinstance(evidence["summary"], str):
            evidence["summary"] = _truncate(evidence["summary"], DEFAULT_MAX_SUMMARY_CHARS)
        if "observations" in evidence and isinstance(evidence["observations"], list):
            evidence["observations"] = [
                _truncate(str(o), DEFAULT_MAX_RESULT_CHARS) for o in evidence["observations"]
            ]
        truncated["evidence"] = evidence

    return truncated


# =============================================================================
# Policy Revalidation
# =============================================================================


def _revalidate_check(check: Mapping[str, object]) -> tuple[bool, dict[str, Any] | None, str | None]:
    """Revalidate a check against policy.

    Returns:
        Tuple of (accepted, sanitized_check_or_none, rejection_reason_or_none)
    """
    result = validate_next_check_proposal(check)

    if result.accepted and result.validated_check:
        return True, result.validated_check, None
    else:
        return False, None, result.rejection_reason


# =============================================================================
# Main Runner Function
# =============================================================================


def run_read_only_checks(
    *,
    incident_id: str,
    run_id: str,
    accepted_checks: Sequence[Mapping[str, object]],
    now: datetime | None = None,
    max_checks: int = DEFAULT_MAX_CHECKS_TO_RUN,
    fake_handlers: Mapping[str, ReadOnlyCheckHandler] | None = None,
) -> dict[str, object]:
    """Run fake read-only checks for an incident.

    This function:
    1. Revalidates each accepted check against the policy
    2. Runs fake handlers for validated checks
    3. Produces bounded, JSON-serializable results

    Args:
        incident_id: The incident being diagnosed
        run_id: Unique identifier for this run
        accepted_checks: Pre-validated checks from the loop planner
        now: Optional datetime for deterministic timestamps
        max_checks: Maximum number of checks to run
        fake_handlers: Optional override for fake handlers (for testing)

    Returns:
        Dict with schema:
        {
            "schema_version": "1.0",
            "run_id": "...",
            "incident_id": "...",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": [...],
            "checks_requested": int,
            "checks_run": int,
            "checks_skipped": int,
            "checks_rejected": int,
            "results": [...],
            "skipped_checks": [...],
            "rejected_checks": [...],
            "safety_metadata": {...}
        }
    """
    # Resolve timestamp at boundary
    resolved_now = now if now is not None else datetime.now(UTC)

    # Use provided handlers or default registry
    handlers = fake_handlers if fake_handlers is not None else FAKE_HANDLERS

    results: list[dict[str, Any]] = []
    skipped_checks: list[dict[str, Any]] = []
    rejected_checks: list[dict[str, Any]] = []

    checks_run = 0
    checks_skipped = 0
    checks_rejected_count = 0

    # Process each check
    for check in accepted_checks:
        check_id = check.get("check_id")

        # Check max limit
        if checks_run >= max_checks:
            skipped_checks.append({
                "check_id": str(check_id) if check_id else None,
                "reason": f"Exceeds max_checks limit ({max_checks})",
                "bounded": True,
            })
            checks_skipped += 1
            continue

        # Revalidate check
        accepted, sanitized, rejection_reason = _revalidate_check(check)

        if not accepted or sanitized is None:
            rejected_checks.append({
                "check_id": str(check_id) if check_id else None,
                "reason": rejection_reason or "Policy revalidation failed",
                "safety_blocked": True,
            })
            checks_rejected_count += 1
            continue

        validated_check: dict[str, Any] = sanitized
        validated_check_id = validated_check.get("check_id")

        if not validated_check_id or validated_check_id not in handlers:
            # Check ID not in fake handler registry
            skipped_checks.append({
                "check_id": str(validated_check_id),
                "reason": f"No fake handler for check_id '{validated_check_id}'",
                "bounded": True,
            })
            checks_skipped += 1
            continue

        # Get handler and run
        handler = handlers[validated_check_id]

        started_at = resolved_now.isoformat()

        try:
            handler_result = handler(validated_check, now=resolved_now)
            finished_at = resolved_now.isoformat()  # Fake handlers are instant

            # Truncate result if needed
            handler_result_truncated = _truncate_result(dict(handler_result))

            results.append({
                "check_id": validated_check_id,
                "status": STATUS_COMPLETED,
                "read_only": True,
                "parameters": validated_check.get("parameters", {}),
                "summary": handler_result_truncated.get(
                    "summary", f"Fake check '{validated_check_id}' completed"
                ),
                "evidence": handler_result_truncated,
                "started_at": started_at,
                "finished_at": finished_at,
                "bounded": True,
            })
            checks_run += 1

        except Exception as exc:
            # Handler failed - capture bounded error
            finished_at = resolved_now.isoformat()
            error_msg = _truncate(str(exc), DEFAULT_MAX_RESULT_CHARS)

            results.append({
                "check_id": validated_check_id,
                "status": STATUS_FAILED,
                "read_only": True,
                "parameters": validated_check.get("parameters", {}),
                "summary": f"Fake handler failed: {error_msg}",
                "evidence": {"error": error_msg, "fake_handler_failure": True},
                "started_at": started_at,
                "finished_at": finished_at,
                "bounded": True,
            })
            checks_run += 1

    # Build final result
    return {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "run_id": run_id,
        "incident_id": incident_id,
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": list(DISALLOWED_ACTIONS),
        "checks_requested": len(accepted_checks),
        "checks_run": checks_run,
        "checks_skipped": checks_skipped,
        "checks_rejected": checks_rejected_count,
        "results": results,
        "skipped_checks": skipped_checks,
        "rejected_checks": rejected_checks,
        "safety_metadata": _build_safety_metadata(),
    }


# =============================================================================
# Loop Integration Helper
# =============================================================================


def run_checks_from_loop_decision(
    *,
    incident_id: str,
    run_id: str,
    loop_update: Mapping[str, object],
    now: datetime | None = None,
) -> dict[str, object]:
    """Run checks from a loop decision output.

    This helper:
    1. Checks if decision is "run_allowed_read_only_checks"
    2. Extracts accepted_checks from loop_update
    3. Runs checks through the fake runner
    4. Returns skipped/no-op result if decision doesn't allow running

    Args:
        incident_id: The incident being diagnosed
        run_id: Unique identifier for this run
        loop_update: Output from plan_next_diagnosis_pass()
        now: Optional datetime for deterministic timestamps

    Returns:
        Runner result dict, or no-op result if checks shouldn't run
    """
    resolved_now = now if now is not None else datetime.now(UTC)

    # Check decision
    decision = loop_update.get("decision")
    if decision != "run_allowed_read_only_checks":
        return {
            "schema_version": RUNNER_SCHEMA_VERSION,
            "run_id": run_id,
            "incident_id": incident_id,
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": list(DISALLOWED_ACTIONS),
            "checks_requested": 0,
            "checks_run": 0,
            "checks_skipped": 0,
            "checks_rejected": 0,
            "results": [],
            "skipped_checks": [],
            "rejected_checks": [],
            "reason": f"Loop decision '{decision}' does not allow running checks",
            "safety_metadata": _build_safety_metadata(),
        }

    # Extract accepted checks
    accepted_checks = loop_update.get("accepted_checks")
    if not accepted_checks or not isinstance(accepted_checks, list):
        return {
            "schema_version": RUNNER_SCHEMA_VERSION,
            "run_id": run_id,
            "incident_id": incident_id,
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": list(DISALLOWED_ACTIONS),
            "checks_requested": 0,
            "checks_run": 0,
            "checks_skipped": 0,
            "checks_rejected": 0,
            "results": [],
            "skipped_checks": [],
            "rejected_checks": [],
            "reason": "No accepted_checks in loop_update",
            "safety_metadata": _build_safety_metadata(),
        }

    # Run checks - this will revalidate each check
    return run_read_only_checks(
        incident_id=incident_id,
        run_id=run_id,
        accepted_checks=accepted_checks,
        now=resolved_now,
    )
