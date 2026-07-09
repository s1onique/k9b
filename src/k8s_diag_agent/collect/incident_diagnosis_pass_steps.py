"""Pass execution steps for automatic diagnosis loop.

This module contains:
- select_checks_for_pass(): Select checks for the next evidence pass
- execute_pass(): Execute selected checks and update hypothesis ranking
- _select_targeted_checks(): Internal targeted check selection
- _map_unknown_to_check(): Map unknowns to check IDs
- _make_stop_decision(): Make stop decision based on pass results
- _get_stop_reason(): Get human-readable stop reason

Design constraints:
- Uses fake runner for check execution
- Bounded budgets (max_checks_per_pass, max_total_checks)
- Read-only checks only
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .incident_diagnosis_pass_contracts import PassResult, StopDecision
from .incident_diagnosis_pass_reranking import rerank_hypotheses
from .incident_read_only_check_catalog import (
    CHECK_BY_ID,
    CheckDefinition,
    build_evidence_delta,
)
from .incident_read_only_check_catalog import (
    select_checks as select_checks_from_catalog,
)

# =============================================================================
# Check Selection for Next Pass (Targeted)
# =============================================================================


def select_checks_for_pass(
    hypotheses: list[dict[str, Any]],
    available_identity: dict[str, str | None],
    pass_index: int,
    max_checks: int = 3,
    executed_check_ids: set[str] | None = None,
    evidence_deltas: list[dict[str, Any]] | None = None,
) -> list[CheckDefinition]:
    """Select checks for the next evidence pass (targeted for Pass 2+).

    Args:
        hypotheses: Current hypotheses
        available_identity: Available identity parameters
        pass_index: Current pass index
        max_checks: Maximum checks to select
        executed_check_ids: Already executed check IDs to exclude
        evidence_deltas: Evidence from previous pass for targeting

    Returns:
        List of selected CheckDefinition
    """
    if executed_check_ids is None:
        executed_check_ids = set()

    if pass_index >= 2 and evidence_deltas:
        hypotheses_needing_checks = []
        for hyp in hypotheses:
            status = hyp.get("status", "open")
            unknowns = hyp.get("unknowns", [])
            falsifier = hyp.get("falsifier", "")
            if status in ("open", "weakened") and (unknowns or falsifier):
                hypotheses_needing_checks.append(hyp)

        if hypotheses_needing_checks:
            targeted = _select_targeted_checks(
                hypotheses=hypotheses_needing_checks,
                available_identity=available_identity,
                max_checks=max_checks,
                executed_check_ids=executed_check_ids,
            )
            if targeted:
                return targeted

    return select_checks_from_catalog(
        hypotheses=hypotheses,
        available_identity=available_identity,
        max_checks=max_checks,
    )


def _select_targeted_checks(
    hypotheses: list[dict[str, Any]],
    available_identity: dict[str, str | None],
    max_checks: int,
    executed_check_ids: set[str],
) -> list[CheckDefinition]:
    """Select checks targeted at hypothesis unknowns/falsifiers."""
    selected: list[CheckDefinition] = []
    candidate_check_ids: list[tuple[str, int]] = []

    for hyp in hypotheses:
        disc_check = hyp.get("discriminating_check_id")
        if disc_check and disc_check not in executed_check_ids:
            candidate_check_ids.append((disc_check, 1))

        next_check = hyp.get("next_best_check")
        if next_check and next_check not in executed_check_ids:
            candidate_check_ids.append((next_check, 2))

        for unknown in hyp.get("unknowns", []):
            unknown_lower = unknown.lower()
            if "error" in unknown_lower or "message" in unknown_lower:
                check_id = _map_unknown_to_check(unknown, hyp)
                if check_id and check_id not in executed_check_ids:
                    candidate_check_ids.append((check_id, 3))

    seen: set[str] = set()
    priority_sorted: list[tuple[str, int]] = []
    for check_id, priority in candidate_check_ids:
        if check_id not in seen:
            seen.add(check_id)
            priority_sorted.append((check_id, priority))

    priority_sorted.sort(key=lambda x: x[1])

    for check_id, _ in priority_sorted:
        if len(selected) >= max_checks:
            break
        if check_id in CHECK_BY_ID:
            check_def = CHECK_BY_ID[check_id]
            if check_def.can_execute_with(**available_identity):
                selected.append(check_def)

    return selected


def _map_unknown_to_check(unknown: str, hyp: dict[str, Any]) -> str | None:
    """Map an unknown to a potential check ID."""
    unknown_lower = unknown.lower()
    candidate_class = hyp.get("candidate_class", "")

    if "log" in unknown_lower or "message" in unknown_lower or "error" in unknown_lower:
        if candidate_class == "crash_loop":
            return "pod_previous_logs_tail"
        return "pod_current_logs_tail"

    if "event" in unknown_lower:
        return "object_recent_events"

    if "status" in unknown_lower or "state" in unknown_lower:
        if candidate_class in ("crash_loop", "pending_pod", "failed_pod"):
            return "pod_status_summary"
        return "pod_container_status_summary"

    return None


# =============================================================================
# Pass Execution
# =============================================================================


def execute_pass(
    pass_index: int,
    incident: dict[str, Any],
    hypotheses: list[dict[str, Any]],
    selected_checks: list[CheckDefinition],
    available_identity: dict[str, str | None],
    config: dict[str, Any] | None = None,
    now: datetime | None = None,
    prior_executed_check_ids: set[str] | None = None,
    prior_evidence_deltas: list[dict[str, Any]] | None = None,
) -> PassResult:
    """Execute a single evidence pass.

    Args:
        pass_index: Pass index (1-based, 0 for hypothesis burst)
        incident: Incident data
        hypotheses: Current hypotheses
        selected_checks: Checks to execute
        available_identity: Available identity parameters
        config: Optional configuration
        now: Optional datetime for deterministic timestamps
        prior_executed_check_ids: Check IDs executed in prior passes
        prior_evidence_deltas: Evidence deltas from prior passes

    Returns:
        PassResult with execution results and updated hypotheses
    """
    from .incident_read_only_check_runner import run_read_only_checks

    resolved_now = now if now is not None else datetime.now()
    started_at = resolved_now.isoformat()

    if prior_executed_check_ids is None:
        prior_executed_check_ids = set()

    pass_kind = "hypothesis_burst" if pass_index == 0 else "evidence_check" if pass_index == 1 else "targeted_followup"

    result = PassResult(
        pass_index=pass_index,
        pass_kind=pass_kind,
        started_at=started_at,
        hypotheses_before=[dict(h) for h in hypotheses],
    )

    if not selected_checks:
        result.completed_at = datetime.now().isoformat()
        result.status = "success"
        result.decision_action = StopDecision.STOP_NO_DISCRIMINATING_CHECKS
        result.decision_reason = "no checks available with required identity"
        result.hypotheses_after = result.hypotheses_before
        result.executed_check_ids = list(prior_executed_check_ids)
        return result

    checks_to_run = [c for c in selected_checks if c.check_id not in prior_executed_check_ids]

    if not checks_to_run:
        result.completed_at = datetime.now().isoformat()
        result.status = "success"
        result.decision_action = StopDecision.STOP_NO_DISCRIMINATING_CHECKS
        result.decision_reason = "all candidate checks already executed in prior passes"
        result.hypotheses_after = result.hypotheses_before
        result.executed_check_ids = list(prior_executed_check_ids)
        return result

    check_specs: list[dict[str, Any]] = []
    for check in checks_to_run:
        spec: dict[str, Any] = {"check_id": check.check_id, "read_only": True}
        if check.requires_namespace and available_identity.get("namespace"):
            spec["namespace"] = available_identity["namespace"]
        if check.requires_object_name and available_identity.get("object_name"):
            spec["object_name"] = available_identity["object_name"]
        if check.requires_pod_name and available_identity.get("pod_name"):
            spec["pod_name"] = available_identity["pod_name"]
        if check.requires_node_name and available_identity.get("node_name"):
            spec["node_name"] = available_identity["node_name"]
        check_specs.append(spec)
        result.checks_selected.append(check.check_id)

    try:
        runner_result = run_read_only_checks(
            incident_id=incident.get("incident_id", "unknown"),
            run_id=f"auto-pass-{pass_index}",
            accepted_checks=check_specs,
            now=resolved_now,
        )
    except Exception as exc:
        result.completed_at = datetime.now().isoformat()
        result.status = "failed"
        result.error = str(exc)[:200]
        result.decision_action = StopDecision.STOP_PASS_ERROR
        result.decision_reason = f"check execution failed: {exc}"
        result.hypotheses_after = result.hypotheses_before
        result.executed_check_ids = list(prior_executed_check_ids)
        return result

    for check_result in runner_result.get("results", []):
        if check_result.get("status") == "completed":
            result.checks_executed.append(check_result)
            result.executed_check_ids.append(check_result.get("check_id", ""))
            delta = build_evidence_delta(
                check_id=check_result.get("check_id", ""),
                check_result=check_result,
                hypotheses=hypotheses,
            )
            result.evidence_deltas.append(delta)
        else:
            result.checks_failed.append(check_result)

    all_evidence = []
    if prior_evidence_deltas:
        all_evidence.extend(prior_evidence_deltas)
    all_evidence.extend(result.evidence_deltas)

    updated_hypotheses, supported, weakened, falsified = rerank_hypotheses(
        hypotheses=result.hypotheses_before,
        evidence_deltas=all_evidence,
        top_confidence_threshold=config.get("min_confidence_to_stop", 0.78) if config else 0.78,
    )
    result.hypotheses_after = updated_hypotheses
    result.hypotheses_supported = supported
    result.hypotheses_weakened = weakened
    result.hypotheses_falsified = falsified

    result.completed_at = datetime.now().isoformat()
    result.status = "success"
    result.decision_action = _make_stop_decision(result, config, result.evidence_deltas)
    result.decision_reason = _get_stop_reason(result.decision_action)

    return result


def _make_stop_decision(
    result: PassResult,
    config: dict[str, Any] | None,
    evidence_deltas: list[dict[str, Any]],
) -> str:
    """Make stop decision based on pass results."""
    all_falsified = (
        len(result.hypotheses_after) > 0 and
        all(h.get("status") == "falsified" for h in result.hypotheses_after)
    )
    if all_falsified:
        return StopDecision.STOP_ALL_HYPOTHESES_FALSIFIED

    if result.hypotheses_after:
        top_confidence = result.hypotheses_after[0].get("confidence", 0)
        threshold = config.get("min_confidence_to_stop", 0.78) if config else 0.78
        if top_confidence >= threshold:
            top_status = result.hypotheses_after[0].get("status", "open")
            if top_status == "supported":
                return StopDecision.STOP_CONFIDENCE_THRESHOLD

    if not evidence_deltas:
        return StopDecision.CONTINUE

    return StopDecision.CONTINUE


def _get_stop_reason(decision: str) -> str:
    """Get human-readable stop reason."""
    reasons = {
        StopDecision.STOP_CONFIDENCE_THRESHOLD: "top hypothesis reached confidence threshold with supporting evidence",
        StopDecision.STOP_MAX_PASSES: "max passes per incident reached",
        StopDecision.STOP_NO_DISCRIMINATING_CHECKS: "no checks available with required identity",
        StopDecision.STOP_CHECK_BUDGET_EXHAUSTED: "total check budget exhausted",
        StopDecision.STOP_TIME_BUDGET_EXHAUSTED: "time budget exhausted",
        StopDecision.STOP_PROVIDER_UNAVAILABLE: "provider unavailable for diagnosis",
        StopDecision.STOP_INCIDENT_TERMINAL: "incident is in terminal state",
        StopDecision.STOP_PASS_ERROR: "pass execution encountered error",
        StopDecision.STOP_ALL_HYPOTHESES_FALSIFIED: "all hypotheses falsified by evidence",
    }
    return reasons.get(decision, "")


__all__ = [
    "execute_pass",
    "select_checks_for_pass",
]
