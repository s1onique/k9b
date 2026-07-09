"""Hypothesis burst generator for automatic diagnosis loop.

This module contains:
- validate_check_id(): Validate that a check ID exists in CHECK_BY_ID
- validate_hypothesis_candidates(): Validate all hypotheses have valid check IDs
- validate_candidate_checks(): Validate all candidate checks have valid check IDs
- _map_alert_to_class(): Map Alertmanager alert name to hypothesis candidate class
- _build_baseline_hypothesis(): Build a single deterministic baseline hypothesis from alert
- _build_baseline_hypotheses(): Build deterministic baseline hypotheses from incident signals
- _build_baseline_checks(): Build discriminating checks for hypotheses
- run_hypothesis_burst(): Generate ranked hypotheses from incident signals

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls (deterministic baseline)
- No Kubernetes calls
- No execution
- Hypotheses first, evidence second
- Falsifiers are REQUIRED - hypotheses without them are rejected
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .incident_hypothesis_burst_models import (
    MAX_CANDIDATE_CHECKS,
    MAX_HYPOTHESES,
    SCHEMA_VERSION,
    CandidateCheck,
    HypothesisBurst,
    HypothesisCandidate,
    HypothesisCandidateClass,
    HypothesisValidationError,
)

# Local imports for check validation
from .incident_read_only_check_catalog import CHECK_BY_ID

# =============================================================================
# Validation Functions
# =============================================================================


def validate_check_id(check_id: str, source: str) -> None:
    """Validate that a check ID exists in CHECK_BY_ID.

    Args:
        check_id: The check ID to validate
        source: Description of where the check ID came from (for error messages)

    Raises:
        HypothesisValidationError: If check_id not found in CHECK_BY_ID
    """
    if check_id not in CHECK_BY_ID:
        raise HypothesisValidationError(
            f"Unknown check_id {check_id!r} from {source}. "
            f"Available checks: {sorted(CHECK_BY_ID.keys())}"
        )


def validate_hypothesis_candidates(hypotheses: list[HypothesisCandidate]) -> list[HypothesisCandidate]:
    """Validate all hypotheses have valid check IDs.

    Args:
        hypotheses: List of hypotheses to validate

    Returns:
        List of validated hypotheses

    Raises:
        HypothesisValidationError: If any hypothesis has invalid check IDs
    """
    validated: list[HypothesisCandidate] = []

    for hyp in hypotheses:
        # Validate next_best_check if present
        if hyp.next_best_check:
            validate_check_id(hyp.next_best_check, f"hypothesis {hyp.hypothesis_id}.next_best_check")

        # Validate discriminating_check_id if present
        if hyp.discriminating_check_id:
            validate_check_id(hyp.discriminating_check_id, f"hypothesis {hyp.hypothesis_id}.discriminating_check_id")

        validated.append(hyp)

    return validated


def validate_candidate_checks(checks: list[CandidateCheck]) -> list[CandidateCheck]:
    """Validate all candidate checks have valid check IDs.

    Args:
        checks: List of candidate checks to validate

    Returns:
        List of validated checks

    Raises:
        HypothesisValidationError: If any check has invalid check ID
    """
    validated: list[CandidateCheck] = []

    for check in checks:
        validate_check_id(check.check_id, f"candidate_check {check.check_id}")
        validated.append(check)

    return validated


# =============================================================================
# Deterministic Baseline Hypothesis Generator
# =============================================================================


def _map_alert_to_class(alert_name: str) -> HypothesisCandidateClass:
    """Map Alertmanager alert name to hypothesis candidate class."""
    alert_lower = alert_name.lower()
    if "crashloop" in alert_lower or "crash_loop" in alert_lower:
        return HypothesisCandidateClass.CRASH_LOOP
    if "imagepull" in alert_lower or "pull" in alert_lower:
        return HypothesisCandidateClass.IMAGE_PULL_ERROR
    if "pending" in alert_lower or "unschedulable" in alert_lower:
        return HypothesisCandidateClass.PENDING_POD
    if "notready" in alert_lower or "unready" in alert_lower:
        return HypothesisCandidateClass.DEPLOYMENT_UNAVAILABLE
    if "failed" in alert_lower:
        return HypothesisCandidateClass.FAILED_POD
    if "warning" in alert_lower or "abnormal" in alert_lower:
        return HypothesisCandidateClass.WARNING_EVENT_BURST
    if "nodeready" in alert_lower or "node_not_ready" in alert_lower:
        return HypothesisCandidateClass.NODE_NOT_READY
    if "pvc" in alert_lower or "persistentvolume" in alert_lower:
        return HypothesisCandidateClass.PVC_ISSUE
    return HypothesisCandidateClass.UNKNOWN


def _build_baseline_hypothesis(
    alert_name: str,
    idx: int,
    namespace: str | None,
    object_name: str | None,
    object_kind: str | None,
) -> HypothesisCandidate:
    """Build a single deterministic baseline hypothesis from alert.

    All falsifier fields are REQUIRED and must be provided.

    Args:
        alert_name: Alert name
        idx: Hypothesis index
        namespace: Namespace from incident
        object_name: Object name from incident
        object_kind: Object kind from incident

    Returns:
        HypothesisCandidate with all falsifier fields
    """
    candidate_class = _map_alert_to_class(alert_name)

    # Build fields based on candidate class
    # Each hypothesis MUST have: falsifier, expected_if_true, expected_if_false
    if candidate_class == HypothesisCandidateClass.CRASH_LOOP:
        statement = "Pod is CrashLooping because the container exits immediately after startup"
        falsifier = "previous logs show normal exit and current pod has no restarts"
        expected_if_true = "container exits with non-zero code in previous logs, high restart count"
        expected_if_false = "previous logs show successful exit (code 0), no restarts in current pod"
        discriminating_check_id = "pod_previous_logs_tail"
        next_check = "pod_previous_logs_tail"
        confidence = 0.72

    elif candidate_class == HypothesisCandidateClass.IMAGE_PULL_ERROR:
        statement = "Container image cannot be pulled due to registry auth or image not found"
        falsifier = "image status shows Ready with all containers started"
        expected_if_true = "ImagePullBackOff or ErrImagePull in container state, waiting containers"
        expected_if_false = "all containers ready and running, no pull errors in events"
        discriminating_check_id = "pod_container_status_summary"
        next_check = "pod_container_status_summary"
        confidence = 0.65

    elif candidate_class == HypothesisCandidateClass.PENDING_POD:
        statement = "Pod cannot be scheduled due to resource constraints or node affinity"
        falsifier = "pod shows Running state with all conditions True"
        expected_if_true = "pod phase is Pending, unschedulable condition present"
        expected_if_false = "pod phase is Running or Succeeded, all conditions True"
        discriminating_check_id = "pod_status_summary"
        next_check = "pod_status_summary"
        confidence = 0.60

    elif candidate_class == HypothesisCandidateClass.DEPLOYMENT_UNAVAILABLE:
        statement = "Deployment has unavailable replicas due to pod failures or pending scheduling"
        falsifier = "all replicas are available and ready"
        expected_if_true = "available replicas < desired replicas, unavailable in conditions"
        expected_if_false = "available replicas == desired replicas, all conditions satisfied"
        discriminating_check_id = "deployment_replica_summary"
        next_check = "deployment_replica_summary"
        confidence = 0.68

    elif candidate_class == HypothesisCandidateClass.FAILED_POD:
        statement = "Pod has entered Failed state due to error in container process"
        falsifier = "pod shows Running or Succeeded state"
        expected_if_true = "pod phase is Failed, terminated with non-zero exit code"
        expected_if_false = "pod phase is Running or Succeeded, no error events"
        discriminating_check_id = "pod_status_summary"
        next_check = "pod_status_summary"
        confidence = 0.70

    elif candidate_class == HypothesisCandidateClass.WARNING_EVENT_BURST:
        statement = "Namespace has abnormal warning events indicating resource issues"
        falsifier = "no warning events in recent period"
        expected_if_true = "warning events present in namespace with BackOff or Failed events"
        expected_if_false = "no warning events, only normal informational events"
        discriminating_check_id = "recent_namespace_warning_events"
        next_check = "recent_namespace_warning_events"
        confidence = 0.55

    elif candidate_class == HypothesisCandidateClass.NODE_NOT_READY:
        statement = "Node is not ready due to network, disk, memory, or PID pressure"
        falsifier = "node shows Ready with all conditions satisfied"
        expected_if_true = "node Ready condition is False, pressure condition present"
        expected_if_false = "node Ready condition is True, no pressure conditions"
        discriminating_check_id = "node_condition_summary"
        next_check = "node_condition_summary"
        confidence = 0.75

    elif candidate_class == HypothesisCandidateClass.PVC_ISSUE:
        statement = "PersistentVolumeClaim is pending due to storage provisioning issues"
        falsifier = "PVC shows Bound state with PV available"
        expected_if_true = "PVC status is Pending or Lost, no bound PV"
        expected_if_false = "PVC status is Bound, PV exists and available"
        discriminating_check_id = "pvc_status_summary"
        next_check = "pvc_status_summary"
        confidence = 0.65

    else:
        statement = "Incident requires additional investigation to determine root cause"
        falsifier = "evidence contradicts generic hypothesis"
        expected_if_true = "warning or error events present in namespace"
        expected_if_false = "no warning events, all pods running normally"
        discriminating_check_id = "object_recent_events"
        next_check = "object_recent_events"
        confidence = 0.40

    # Add context to statement if available
    if namespace and object_name:
        statement = f"{statement} in namespace {namespace} for {object_kind or 'object'} {object_name}"

    # Build evidence_for
    evidence_for = [f"alert:{alert_name}"]
    if namespace:
        evidence_for.append(f"namespace:{namespace}")
    if object_name:
        evidence_for.append(f"object:{object_name}")

    return HypothesisCandidate(
        hypothesis_id=f"h-{idx + 1:03d}",
        rank=idx + 1,
        statement=statement,
        candidate_class=candidate_class,
        confidence=confidence,
        impact="high",
        evidence_for=tuple(evidence_for),
        evidence_against=tuple(),
        unknowns=("root cause timing", "specific error message"),
        # REQUIRED falsifier fields
        falsifier=falsifier,
        expected_if_true=expected_if_true,
        expected_if_false=expected_if_false,
        discriminating_check_id=discriminating_check_id,
        next_best_check=next_check,
        status="open",
        why_now=f"Alert {alert_name} triggered this incident",
    )


def _build_baseline_hypotheses(
    incident: dict[str, Any],
    case_file: dict[str, Any],
) -> list[HypothesisCandidate]:
    """Build deterministic baseline hypotheses from incident signals.

    This is the fallback when provider is unavailable.
    It uses existing evidence only (alert name, namespace, object).
    """
    hypotheses: list[HypothesisCandidate] = []

    # Extract signals from incident
    signals = incident.get("signals", [])
    alert_names = []
    namespace = None
    object_name = None
    object_kind = None

    for signal in signals:
        if isinstance(signal, dict):
            reason = signal.get("reason", "")
            alert_names.append(reason)
            if not namespace:
                namespace = signal.get("namespace")
            if not object_name:
                object_name = signal.get("object_name") or signal.get("pod_name")
                object_kind = signal.get("object_kind")

    # Also check case_file for signals
    case_signals = case_file.get("signals", [])
    for signal in case_signals:
        if isinstance(signal, dict):
            reason = signal.get("reason", "")
            if reason and reason not in alert_names:
                alert_names.append(reason)
            if not namespace:
                namespace = signal.get("namespace")
            if not object_name:
                object_name = signal.get("object_name") or signal.get("pod_name")
                object_kind = signal.get("object_kind")

    # Build hypothesis for each unique alert
    for idx, alert_name in enumerate(alert_names[:MAX_HYPOTHESES]):
        hyp = _build_baseline_hypothesis(
            alert_name=alert_name,
            idx=idx,
            namespace=namespace,
            object_name=object_name,
            object_kind=object_kind,
        )
        hypotheses.append(hyp)

    return hypotheses


def _build_baseline_checks(
    hypotheses: list[HypothesisCandidate],
) -> list[CandidateCheck]:
    """Build discriminating checks for hypotheses."""
    checks: list[CandidateCheck] = []
    targeted_ids = {h.hypothesis_id for h in hypotheses[:3]}

    # Generic checks that apply to multiple hypotheses
    generic_checks = [
        CandidateCheck(
            check_id="recent_namespace_warning_events",
            kind="read_only_kubernetes",
            cost="low",
            expected_value="high",
            targets_hypotheses=tuple(targeted_ids),
            requires={"namespace": True, "object_name": False},
            rationale="Collects warning events that may indicate root cause",
        ),
        CandidateCheck(
            check_id="pod_status_summary",
            kind="read_only_kubernetes",
            cost="low",
            expected_value="high",
            targets_hypotheses=tuple(h.hypothesis_id for h in hypotheses if h.candidate_class in (
                HypothesisCandidateClass.CRASH_LOOP,
                HypothesisCandidateClass.PENDING_POD,
                HypothesisCandidateClass.DEPLOYMENT_UNAVAILABLE,
            )),
            requires={"namespace": True, "object_name": True, "pod_name": False},
            rationale="Provides pod status including restarts, phase, and conditions",
        ),
        CandidateCheck(
            check_id="deployment_replica_summary",
            kind="read_only_kubernetes",
            cost="low",
            expected_value="high",
            targets_hypotheses=tuple(h.hypothesis_id for h in hypotheses if h.candidate_class == HypothesisCandidateClass.DEPLOYMENT_UNAVAILABLE),
            requires={"namespace": True, "object_name": True},
            rationale="Shows available vs desired replicas for deployment",
        ),
    ]

    for check in generic_checks:
        if check.targets_hypotheses:
            checks.append(check)

    return checks[:MAX_CANDIDATE_CHECKS]


# =============================================================================
# Hypothesis Burst Entry Point
# =============================================================================


def run_hypothesis_burst(
    incident: dict[str, Any],
    case_file: dict[str, Any],
    config: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> HypothesisBurst:
    """Generate ranked hypotheses from incident signals.

    This is Pass 0 of the multi-pass diagnosis loop.
    Uses existing evidence only (incident fields, alert compact, review enrichment).
    Does NOT perform Kubernetes reads.

    VALIDATION: All hypotheses MUST have:
    - falsifier (required)
    - expected_if_true (required)
    - expected_if_false (required)
    - All check IDs must exist in CHECK_BY_ID

    Args:
        incident: Incident data including signals
        case_file: Case file with review enrichment and snapshots
        config: Optional configuration (currently unused, for future provider integration)
        now: Optional datetime for deterministic timestamps

    Returns:
        HypothesisBurst with ranked hypotheses and candidate checks

    Raises:
        HypothesisValidationError: If any hypothesis has invalid/missing falsifier fields
    """
    # Build deterministic baseline hypotheses
    hypotheses = _build_baseline_hypotheses(incident, case_file)

    # Build candidate checks
    candidate_checks = _build_baseline_checks(hypotheses)

    # Apply max hypotheses limit
    max_hypotheses = MAX_HYPOTHESES
    if config and "max_hypotheses_per_incident" in config:
        max_hypotheses = min(config["max_hypotheses_per_incident"], MAX_HYPOTHESES)

    limited_hypotheses = hypotheses[:max_hypotheses]

    # Validate hypotheses have falsifier fields (post_init validated individual fields)
    # Now validate check IDs exist in CHECK_BY_ID
    validated_hypotheses = validate_hypothesis_candidates(limited_hypotheses)

    # Validate candidate checks have valid check IDs
    validated_checks = validate_candidate_checks(candidate_checks[:MAX_CANDIDATE_CHECKS])

    # Collect all validated check IDs
    validated_check_ids = set()
    for h in validated_hypotheses:
        if h.discriminating_check_id:
            validated_check_ids.add(h.discriminating_check_id)
        if h.next_best_check:
            validated_check_ids.add(h.next_best_check)
    for c in validated_checks:
        validated_check_ids.add(c.check_id)

    return HypothesisBurst(
        pass_index=0,
        pass_kind="hypothesis_burst",
        hypotheses=tuple(validated_hypotheses),
        candidate_checks=tuple(validated_checks),
        schema_version=SCHEMA_VERSION,
        validated_check_ids=tuple(sorted(validated_check_ids)),
    )


__all__ = [
    "validate_check_id",
    "validate_hypothesis_candidates",
    "validate_candidate_checks",
    "run_hypothesis_burst",
]
