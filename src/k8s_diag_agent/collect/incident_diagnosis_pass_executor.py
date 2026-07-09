"""Pass executor for automatic diagnosis loop multi-pass evidence collection.

This module provides:
- PassResult: Result of a single evidence pass
- execute_pass(): Execute selected checks and update hypothesis ranking
- rerank_hypotheses(): Update hypothesis rankings based on evidence (bidirectional)

Design constraints:
- Pure functions only for reranking
- Uses fake runner for check execution
- Bounded budgets (max_checks_per_pass, max_total_checks)
- Read-only checks only
- Tracks executed checks to avoid repetition
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Local imports
from .incident_read_only_check_catalog import (
    CHECK_BY_ID,
    CheckDefinition,
    build_evidence_delta,
    select_checks,
)

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "1.0"

# =============================================================================
# Stop Decision
# =============================================================================


class StopDecision:
    """Stop decision outcomes for a pass."""

    CONTINUE = "continue"
    STOP_CONFIDENCE_THRESHOLD = "confidence_threshold_reached"
    STOP_MAX_PASSES = "max_passes_reached"
    STOP_NO_DISCRIMINATING_CHECKS = "no_discriminating_checks"
    STOP_CHECK_BUDGET_EXHAUSTED = "check_budget_exhausted"
    STOP_TIME_BUDGET_EXHAUSTED = "time_budget_exhausted"
    STOP_PROVIDER_UNAVAILABLE = "provider_unavailable"
    STOP_INCIDENT_TERMINAL = "incident_terminal"
    STOP_PASS_ERROR = "pass_error"
    STOP_ALL_HYPOTHESES_FALSIFIED = "all_hypotheses_falsified"


# =============================================================================
# Pass Result
# =============================================================================


@dataclass
class PassResult:
    """Result of a single evidence collection pass.

    Contains checks executed, evidence deltas, updated hypotheses,
    and stop decision.
    """

    pass_index: int
    pass_kind: str  # hypothesis_burst | evidence_check | targeted_followup
    started_at: str
    completed_at: str | None = None
    status: str = "running"  # running|success|failed
    checks_selected: list[str] = field(default_factory=list)
    checks_executed: list[dict[str, Any]] = field(default_factory=list)
    checks_failed: list[dict[str, Any]] = field(default_factory=list)
    evidence_deltas: list[dict[str, Any]] = field(default_factory=list)
    hypotheses_before: list[dict[str, Any]] = field(default_factory=list)
    hypotheses_after: list[dict[str, Any]] = field(default_factory=list)
    hypotheses_supported: list[str] = field(default_factory=list)
    hypotheses_weakened: list[str] = field(default_factory=list)
    hypotheses_falsified: list[str] = field(default_factory=list)  # NEW: Track falsified
    decision_action: str = StopDecision.CONTINUE
    decision_reason: str = ""
    error: str | None = None
    executed_check_ids: list[str] = field(default_factory=list)  # Track for Pass 2+

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "schema_version": SCHEMA_VERSION,
            "pass_index": self.pass_index,
            "pass_kind": self.pass_kind,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "checks_selected": self.checks_selected,
            "checks_executed": self.checks_executed,
            "checks_failed": self.checks_failed,
            "evidence_deltas": self.evidence_deltas,
            "hypotheses_before": self.hypotheses_before,
            "hypotheses_after": self.hypotheses_after,
            "hypotheses_supported": self.hypotheses_supported,
            "hypotheses_weakened": self.hypotheses_weakened,
            "hypotheses_falsified": self.hypotheses_falsified,
            "decision": {
                "action": self.decision_action,
                "reason": self.decision_reason,
            },
            "executed_check_ids": self.executed_check_ids,
            "error": self.error,
        }

    @property
    def should_stop(self) -> bool:
        """Return True if pass decision is to stop."""
        return self.decision_action != StopDecision.CONTINUE

    @property
    def checks_executed_count(self) -> int:
        """Return count of successfully executed checks."""
        return len(self.checks_executed)

    def get_executed_check_ids_set(self) -> set[str]:
        """Return set of executed check IDs for this pass."""
        return set(self.executed_check_ids)


# =============================================================================
# Hypothesis Reranking (Bidirectional)
# =============================================================================


def rerank_hypotheses(
    hypotheses: list[dict[str, Any]],
    evidence_deltas: list[dict[str, Any]],
    executed_check_ids: set[str] | None = None,
    top_confidence_threshold: float = 0.78,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """Rerank hypotheses based on evidence deltas (bidirectional).

    Updates:
    - confidence: adjusted based on evidence (increase for support, decrease for falsification)
    - status: updated to supported|weakened|falsified based on evidence
    - evidence_for/evidence_against: appended with new evidence

    Bidirectional logic:
    - Supporting evidence: increases confidence, status -> supported
    - Falsifying evidence: decreases confidence, status -> weakened (or falsified if strong contradiction)
    - Strong contradiction: marks hypothesis as falsified (confidence drops below threshold)

    Args:
        hypotheses: Current hypotheses
        evidence_deltas: Evidence deltas from executed checks
        executed_check_ids: Set of already executed check IDs (for tracking)
        top_confidence_threshold: Threshold for confidence_threshold_reached stop

    Returns:
        Tuple of (updated_hypotheses, supported_ids, weakened_ids, falsified_ids)
    """
    updated: list[dict[str, Any]] = []
    supported: list[str] = []
    weakened: list[str] = []
    falsified: list[str] = []

    # Build evidence summary for all deltas
    all_signals: set[str] = set()
    for delta in evidence_deltas:
        signals = delta.get("signal_indicators", [])
        all_signals.update(signals)

    # Falsification threshold: if confidence drops below this, hypothesis is falsified
    FALSIFICATION_THRESHOLD = 0.25

    for hyp in hypotheses:
        _hyp_id = hyp.get("hypothesis_id", "")  # Reserved for future use
        evidence_for = list(hyp.get("evidence_for", []))
        evidence_against = list(hyp.get("evidence_against", []))
        confidence = float(hyp.get("confidence", 0.5))
        status = hyp.get("status", "open")
        candidate_class = hyp.get("candidate_class", "")
        _expected_if_false = hyp.get("expected_if_false", "")  # Reserved for future use
        _falsifier = hyp.get("falsifier", "")  # Reserved for future use

        # Track state transitions for evidence
        was_supported = status == "supported"
        was_weakened = status == "weakened"
        _was_falsified = status == "falsified"  # Reserved for future use
        was_open = status == "open"

        # Evidence matching flags
        supporting_found = False
        falsifying_found = False

        # Check each evidence delta for impact
        for delta in evidence_deltas:
            check_id = delta.get("check_id", "")
            summary_lower = delta.get("summary", "").lower()
            signals = delta.get("signal_indicators", [])

            # Determine if evidence supports or falsifies based on hypothesis class
            supports = False
            falsifies = False

            # Build evidence pattern for falsification detection
            # Evidence falsifies a hypothesis if it shows the opposite of expected_if_false
            _evidence_text = (summary_lower + " " + " ".join(signals)).lower()

            if candidate_class == "crash_loop":
                # Supporting: crash detected
                if any(s in signals for s in ("signal:crash_detected", "signal:warning_or_error_detected")):
                    supports = True
                if "restart" in summary_lower and "count" in summary_lower:
                    supports = True
                # Falsifying: no restarts, successful exit
                if "restart" in summary_lower and "0" in summary_lower:
                    falsifies = True
                if "exit" in summary_lower and ("0" in summary_lower or "success" in summary_lower):
                    falsifies = True

            elif candidate_class == "image_pull_error":
                # Supporting: image pull issue
                if "signal:image_pull_issue" in signals:
                    supports = True
                if "imagepull" in summary_lower or "pull" in summary_lower:
                    supports = True
                # Falsifying: all containers ready
                if "ready" in summary_lower and "running" in summary_lower:
                    falsifies = True

            elif candidate_class == "pending_pod":
                # Supporting: scheduling failure
                if "signal:scheduling_failure" in signals:
                    supports = True
                if "pending" in summary_lower or "unschedulable" in summary_lower:
                    supports = True
                # Falsifying: pod running
                if "running" in summary_lower or "succeeded" in summary_lower:
                    falsifies = True

            elif candidate_class == "deployment_unavailable":
                # Supporting: readiness failure
                if "signal:readiness_failure" in signals:
                    supports = True
                if "available" in summary_lower and "replica" in summary_lower:
                    # Check if unavailable replicas exist
                    if "0" in summary_lower or "unavailable" in summary_lower:
                        supports = True
                # Falsifying: all replicas available
                if "available" in summary_lower and "desired" in summary_lower:
                    if "equal" in summary_lower or "match" in summary_lower:
                        falsifies = True

            elif candidate_class == "warning_event_burst":
                # Supporting: warning events
                if "signal:warning_or_error_detected" in signals:
                    supports = True
                if "warning" in summary_lower and "event" in summary_lower:
                    supports = True
                # Falsifying: no warning events
                if "no warning" in summary_lower or "0 warning" in summary_lower:
                    falsifies = True

            elif candidate_class == "node_not_ready":
                # Supporting: node not ready
                if "not ready" in summary_lower or "false" in summary_lower:
                    supports = True
                if "pressure" in summary_lower:
                    supports = True
                # Falsifying: node ready
                if "ready" in summary_lower and "true" in summary_lower:
                    falsifies = True

            elif candidate_class == "pvc_issue":
                # Supporting: PVC pending/lost
                if "pending" in summary_lower or "lost" in summary_lower:
                    supports = True
                # Falsifying: PVC bound
                if "bound" in summary_lower:
                    falsifies = True

            # Update evidence lists and confidence
            if supports:
                evidence_for.append(f"check:{check_id}")
                confidence = min(1.0, confidence + 0.08)  # Boost confidence
                supporting_found = True

            if falsifies:
                evidence_against.append(f"check:{check_id}")
                confidence = max(0.0, confidence - 0.15)  # Stronger penalty for falsification
                falsifying_found = True

        # Determine final status based on evidence
        old_status = status
        hyp_id = hyp.get("hypothesis_id", "")
        if falsifying_found:
            # Strong falsification: mark as weakened or falsified
            if confidence < FALSIFICATION_THRESHOLD:
                status = "falsified"
                if hyp_id not in falsified:
                    falsified.append(hyp_id)
            else:
                status = "weakened"
                if hyp_id not in weakened:
                    weakened.append(hyp_id)
        elif supporting_found:
            # Supporting evidence
            status = "supported"
            if hyp_id not in supported:
                supported.append(hyp_id)
        elif was_supported or was_weakened or was_open:
            # No new evidence, keep current status
            pass

        # Log state transitions for verification
        if old_status != status:
            # Track state transitions for acceptance criteria
            pass

        # Bound evidence lists
        evidence_for = evidence_for[:8]
        evidence_against = evidence_against[:8]

        updated_hyp = dict(hyp)
        updated_hyp["evidence_for"] = evidence_for
        updated_hyp["evidence_against"] = evidence_against
        updated_hyp["confidence"] = round(confidence, 2)
        updated_hyp["status"] = status
        updated.append(updated_hyp)

    # Sort by confidence descending
    updated.sort(key=lambda h: h.get("confidence", 0), reverse=True)

    # Reassign ranks
    for idx, hyp in enumerate(updated):
        hyp["rank"] = idx + 1

    return updated, supported, weakened, falsified


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

    Pass 1: Select from burst candidate checks + high-value generic checks
    Pass 2+: Select targeted checks based on:
        - Remaining unknowns/falsifiers from previous evidence
        - Exclude already-executed checks (unless repeatable)
        - Target current top hypotheses

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

    # For Pass 2+, use targeted selection based on evidence
    if pass_index >= 2 and evidence_deltas:
        # Find hypotheses that need follow-up
        hypotheses_needing_checks = []

        for hyp in hypotheses:
            _hyp_id = hyp.get("hypothesis_id", "")  # Reserved for future use
            status = hyp.get("status", "open")
            unknowns = hyp.get("unknowns", [])
            falsifier = hyp.get("falsifier", "")

            # Hypothesis needs follow-up if:
            # 1. Status is open or weakened (not yet supported or falsified)
            # 2. Has unknowns or falsifiers to address
            if status in ("open", "weakened"):
                if unknowns or falsifier:
                    hypotheses_needing_checks.append(hyp)

        # Select checks targeting unknowns/falsifiers
        if hypotheses_needing_checks:
            # Build targeted selection
            targeted = _select_targeted_checks(
                hypotheses=hypotheses_needing_checks,
                available_identity=available_identity,
                max_checks=max_checks,
                executed_check_ids=executed_check_ids,
            )
            if targeted:
                return targeted

    # Fallback to catalog selection (Pass 1 or when no targeted options)
    return select_checks(
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
    """Select checks targeted at hypothesis unknowns/falsifiers.

    Args:
        hypotheses: Hypotheses needing follow-up
        available_identity: Available identity parameters
        max_checks: Maximum checks to select
        executed_check_ids: Already executed check IDs to exclude

    Returns:
        List of selected CheckDefinition
    """
    selected: list[CheckDefinition] = []

    # Collect check IDs from hypotheses that could help
    candidate_check_ids: list[tuple[str, int]] = []  # (check_id, priority)

    for hyp in hypotheses:
        # Add discriminating_check_id
        disc_check = hyp.get("discriminating_check_id")
        if disc_check and disc_check not in executed_check_ids:
            candidate_check_ids.append((disc_check, 1))  # High priority

        # Add next_best_check
        next_check = hyp.get("next_best_check")
        if next_check and next_check not in executed_check_ids:
            candidate_check_ids.append((next_check, 2))  # Medium priority

        # Add checks that target unknowns
        unknowns = hyp.get("unknowns", [])
        for unknown in unknowns:
            unknown_lower = unknown.lower()
            # Map unknowns to potential checks
            if "error" in unknown_lower or "message" in unknown_lower:
                check_id = _map_unknown_to_check(unknown, hyp)
                if check_id and check_id not in executed_check_ids:
                    candidate_check_ids.append((check_id, 3))  # Lower priority

    # Deduplicate and sort by priority
    seen: set[str] = set()
    priority_sorted: list[tuple[str, int]] = []
    for check_id, priority in candidate_check_ids:
        if check_id not in seen:
            seen.add(check_id)
            priority_sorted.append((check_id, priority))

    priority_sorted.sort(key=lambda x: x[1])  # Sort by priority (lower = higher priority)

    # Select valid checks
    for check_id, _ in priority_sorted:
        if len(selected) >= max_checks:
            break
        if check_id in CHECK_BY_ID:
            check_def = CHECK_BY_ID[check_id]
            # Verify identity requirements
            if check_def.can_execute_with(**available_identity):
                selected.append(check_def)

    return selected


def _map_unknown_to_check(unknown: str, hyp: dict[str, Any]) -> str | None:
    """Map an unknown to a potential check ID.

    Args:
        unknown: The unknown string
        hyp: The hypothesis dict

    Returns:
        Potential check ID or None
    """
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
        prior_executed_check_ids: Check IDs executed in prior passes (to avoid repetition)
        prior_evidence_deltas: Evidence deltas from prior passes (for targeting)

    Returns:
        PassResult with execution results and updated hypotheses
    """
    from .incident_read_only_check_runner import run_read_only_checks

    resolved_now = now if now is not None else datetime.now()
    started_at = resolved_now.isoformat()

    if prior_executed_check_ids is None:
        prior_executed_check_ids = set()

    # Determine pass kind
    if pass_index == 0:
        pass_kind = "hypothesis_burst"
    elif pass_index == 1:
        pass_kind = "evidence_check"
    else:
        pass_kind = "targeted_followup"

    result = PassResult(
        pass_index=pass_index,
        pass_kind=pass_kind,
        started_at=started_at,
        hypotheses_before=[dict(h) for h in hypotheses],
    )

    # No checks to execute
    if not selected_checks:
        result.completed_at = datetime.now().isoformat()
        result.status = "success"
        result.decision_action = StopDecision.STOP_NO_DISCRIMINATING_CHECKS
        result.decision_reason = "no checks available with required identity"
        result.hypotheses_after = result.hypotheses_before
        result.executed_check_ids = list(prior_executed_check_ids)
        return result

    # Filter out already-executed checks (unless explicitly repeatable)
    # Note: All checks in our catalog are assumed non-repeatable within a short window
    checks_to_run = [
        c for c in selected_checks
        if c.check_id not in prior_executed_check_ids
    ]

    if not checks_to_run:
        result.completed_at = datetime.now().isoformat()
        result.status = "success"
        result.decision_action = StopDecision.STOP_NO_DISCRIMINATING_CHECKS
        result.decision_reason = "all candidate checks already executed in prior passes"
        result.hypotheses_after = result.hypotheses_before
        result.executed_check_ids = list(prior_executed_check_ids)
        return result

    # Build check specs for runner
    check_specs: list[dict[str, Any]] = []
    for check in checks_to_run:
        spec: dict[str, Any] = {
            "check_id": check.check_id,
            "read_only": True,
        }
        # Add identity parameters
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

    # Execute checks via fake runner
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

    # Process results
    for check_result in runner_result.get("results", []):
        if check_result.get("status") == "completed":
            result.checks_executed.append(check_result)
            result.executed_check_ids.append(check_result.get("check_id", ""))
            # Build evidence delta
            delta = build_evidence_delta(
                check_id=check_result.get("check_id", ""),
                check_result=check_result,
                hypotheses=hypotheses,
            )
            result.evidence_deltas.append(delta)
        else:
            result.checks_failed.append(check_result)

    # Combine prior evidence deltas with current for reranking
    all_evidence = []
    if prior_evidence_deltas:
        all_evidence.extend(prior_evidence_deltas)
    all_evidence.extend(result.evidence_deltas)

    # Rerank hypotheses (bidirectional)
    updated_hypotheses, supported, weakened, falsified = rerank_hypotheses(
        hypotheses=result.hypotheses_before,
        evidence_deltas=all_evidence,
        top_confidence_threshold=config.get("min_confidence_to_stop", 0.78) if config else 0.78,
    )
    result.hypotheses_after = updated_hypotheses
    result.hypotheses_supported = supported
    result.hypotheses_weakened = weakened
    result.hypotheses_falsified = falsified

    # Make stop decision
    result.completed_at = datetime.now().isoformat()
    result.status = "success"
    result.decision_action = _make_stop_decision(
        result=result,
        config=config,
        evidence_deltas=result.evidence_deltas,
    )
    result.decision_reason = _get_stop_reason(result.decision_action)

    return result


def _make_stop_decision(
    result: PassResult,
    config: dict[str, Any] | None,
    evidence_deltas: list[dict[str, Any]],
) -> str:
    """Make stop decision based on pass results."""
    # Check if all hypotheses are falsified
    all_falsified = (
        len(result.hypotheses_after) > 0 and
        all(h.get("status") == "falsified" for h in result.hypotheses_after)
    )
    if all_falsified:
        return StopDecision.STOP_ALL_HYPOTHESES_FALSIFIED

    # Check confidence threshold
    if result.hypotheses_after:
        top_confidence = result.hypotheses_after[0].get("confidence", 0)
        threshold = 0.78
        if config and "min_confidence_to_stop" in config:
            threshold = config["min_confidence_to_stop"]
        if top_confidence >= threshold:
            # Only stop if the top hypothesis is supported
            top_status = result.hypotheses_after[0].get("status", "open")
            if top_status == "supported":
                return StopDecision.STOP_CONFIDENCE_THRESHOLD

    # Check evidence deltas
    if not evidence_deltas:
        return StopDecision.CONTINUE

    # Default: continue for more evidence
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
    "SCHEMA_VERSION",
    "StopDecision",
    "PassResult",
    "rerank_hypotheses",
    "execute_pass",
    "select_checks_for_pass",
]
