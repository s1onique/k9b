"""Backend contracts for P4c K8s diagnosis phase.

This module defines the data contracts (dataclasses, constants) used by
the backend-targeted diagnosis helpers.

Architecture:
- Uses kubectl exec against deploy/k9b-backend -c backend for backend-local HTTP
- Does NOT rely on scheduler periodic automatic diagnosis loop
- Targets POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import Literal

# =============================================================================
# Failure Reason Constants
# =============================================================================

# DNS resolution failures
FAILURE_BACKEND_DNS_RESOLUTION_FAILED = "backend_dns_resolution_failed"

# Endpoint readiness failures
FAILURE_BACKEND_ENDPOINT_NOT_READY = "backend_endpoint_not_ready"

# Incident fetch failures
FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR = "backend_incident_fetch_transport_error"
FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR = "backend_incident_fetch_http_error"
FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND = "backend_incident_fetch_not_found"
FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON = "backend_incident_fetch_invalid_json"
FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR = "backend_incident_fetch_contract_error"
FAILURE_BACKEND_INCIDENT_FETCH_FAILED = "backend_incident_fetch_failed"

# Targeted invocation failures (P4c)
# Transport-level failures
FAILURE_TARGETED_INVOCATION_HTTP_ERROR = "targeted_automatic_diagnosis_invocation_http_error"
FAILURE_TARGETED_INVOCATION_INVALID_JSON = "targeted_automatic_diagnosis_invocation_invalid_json"
FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR = "targeted_automatic_diagnosis_invocation_transport_error"
FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY = "targeted_automatic_diagnosis_backend_empty_reply"

# Runtime state failures (not transport errors)
# Budget exhaustion / not eligible - distinct from transport/HTTP errors
FAILURE_TARGETED_LOOP_NOT_ELIGIBLE = "targeted_automatic_diagnosis_loop_not_eligible"

# Post-invocation failures
FAILURE_TARGETED_LOOP_NOT_COMPLETED = "targeted_automatic_diagnosis_loop_not_completed"
FAILURE_TARGETED_LOOP_NOT_STARTED = "targeted_automatic_diagnosis_loop_not_started"
FAILURE_TARGETED_NO_PASS_ARTIFACTS = "targeted_automatic_diagnosis_no_pass_artifacts"
FAILURE_TARGETED_REVIEW_PACKET_MISSING = "targeted_automatic_diagnosis_review_packet_missing"
FAILURE_TARGETED_INSUFFICIENT_PASSES = "targeted_automatic_diagnosis_insufficient_passes"
FAILURE_TARGETED_BUDGET_EXHAUSTED_BEFORE_REQUIRED_PASSES = (
    "targeted_automatic_diagnosis_budget_exhausted_before_required_passes"
)
FAILURE_TARGETED_BUDGET_LIMIT_TOO_LOW = "targeted_automatic_diagnosis_budget_limit_too_low"
FAILURE_TARGETED_COMPLETED_WITHOUT_OBSERVABLE_PASS = (
    "targeted_automatic_diagnosis_completed_without_observable_pass_artifacts"
)
FAILURE_TARGETED_TERMINAL_NO_CHECKS = "targeted_automatic_diagnosis_terminal_no_checks"


# =============================================================================
# Normalized P4c Outcome
# =============================================================================


@dataclass(frozen=True)
class P4cDiagnosisOutcome:
    """Normalized outcome for P4c diagnosis validation.

    This dataclass provides a single authoritative source for P4c success/failure
    determination. All downstream validation and lab-result rendering must
    consume this normalized outcome instead of re-reading separate raw backend
    JSON and filesystem artifacts with separate criteria.

    Modes:
    - terminal_single_pass: Terminal no-checks decision reached in single pass
    - multipass: Standard multi-pass diagnosis requiring >= 2 passes

    Success criteria:
    - terminal_single_pass: pass_count >= 1, terminal_decision == stop_no_checks_proposed,
      read_only_constraints_satisfied == True, review_artifact exists
    - multipass: pass_count >= 2, root_cause_evidence_satisfied == True,
      read_only_constraints_satisfied == True
    """

    success: bool
    mode: Literal["multipass", "terminal_single_pass"]
    incident_id: str
    pass_count: int
    pass_run_ids: tuple[str, ...]
    review_artifact_paths: tuple[str, ...]
    terminal_decision: str | None
    read_only_constraints_satisfied: bool
    root_cause_evidence_satisfied: bool
    root_cause_evidence_reason: str | None
    failure_reasons: tuple[str, ...] = field(default_factory=tuple())


def compute_p4c_outcome(evidence: dict[str, Any]) -> P4cDiagnosisOutcome:
    """Compute the normalized P4c outcome from diagnosis evidence.

    This function is the SINGLE AUTHORITATIVE SOURCE for P4c outcome classification.
    All downstream validation and lab-result rendering must use the returned
    P4cDiagnosisOutcome instead of re-checking evidence fields.

    Args:
        evidence: Diagnosis evidence dict from phase_p4c_verify_k8s_mult_pass_diagnosis

    Returns:
        P4cDiagnosisOutcome with the definitive success/failure determination
    """
    incident_id = evidence.get("incident_id", "")
    pass_count = evidence.get("pass_count", 0)
    pass_run_ids_raw = evidence.get("pass_run_ids", [])
    pass_run_ids = tuple(str(r) for r in pass_run_ids_raw if r)

    terminal_no_checks_accepted = evidence.get("terminal_no_checks_accepted", False)
    terminal_decision = evidence.get("terminal_decision_reached")

    # Review artifact paths
    review_paths_raw = []
    if evidence.get("review_packet_path"):
        review_paths_raw.append(str(evidence["review_packet_path"]))
    review_artifact_paths = tuple(review_paths_raw)

    # Read-only constraints
    read_only = evidence.get("read_only", True)
    read_only_violations = evidence.get("read_only_violations", [])
    read_only_constraints_satisfied = read_only and len(read_only_violations) == 0

    # Root cause evidence
    root_cause_summary = str(evidence.get("root_cause_summary", ""))

    # Collect failure reasons
    failure_reasons: list[str] = []

    # Determine mode and validate
    if terminal_no_checks_accepted and pass_count >= 1 and evidence.get("real_pass_artifacts_found"):
        # Terminal single-pass mode
        mode: Literal["multipass", "terminal_single_pass"] = "terminal_single_pass"

        # For terminal mode, pass_run_ids should come from review artifact if not set
        if not pass_run_ids:
            review = evidence.get("backend_incident_detail", {})
            if not isinstance(review, dict):
                review = {}
            auto_review = review.get("automatic_diagnosis_review", {}) or {}
            run_id = auto_review.get("run_id")
            if run_id:
                pass_run_ids = (str(run_id),)
            # Also check for run_id in evidence directly (from phase2)
            if not pass_run_ids and evidence.get("review_available"):
                # Use a generated run_id based on incident_id if we have a review
                pass_run_ids = (f"auto-{incident_id}",)

        if not review_artifact_paths and evidence.get("review_packet_path"):
            review_artifact_paths = (str(evidence["review_packet_path"]),)

        # Read-only is required for terminal mode
        if not read_only_constraints_satisfied:
            failure_reasons.append(f"read_only_contract_violated: {read_only_violations}")

        # Terminal mode doesn't require root_cause_evidence in prose
        # (evidence comes from deterministic K8s markers in p4c_verdict)
        p4c_verdict = evidence.get("p4c_verdict", {})
        if isinstance(p4c_verdict, dict):
            root_cause_evidence_satisfied = p4c_verdict.get("success", False)
        else:
            # Fallback: check scheduling markers in evidence
            scheduling_markers_found = _check_terminal_mode_scheduling_markers(evidence)
            root_cause_evidence_satisfied = len(scheduling_markers_found) > 0

        if not root_cause_evidence_satisfied:
            root_cause_evidence_reason = "missing_scheduling_root_cause_evidence"
            failure_reasons.append(root_cause_evidence_reason)
        else:
            root_cause_evidence_reason = None

        # Terminal single-pass success requires:
        # - read_only_constraints_satisfied (checked above)
        # - root_cause_evidence_satisfied (checked above)
        success = read_only_constraints_satisfied and root_cause_evidence_satisfied

    else:
        # Multi-pass mode
        mode = "multipass"
        MIN_REQUIRED = 2  # Local constant to avoid circular import

        if pass_count < MIN_REQUIRED:
            failure_reasons.append(f"insufficient_passes: {pass_count} < {MIN_REQUIRED}")

        if not read_only_constraints_satisfied:
            failure_reasons.append(f"read_only_contract_violated: {read_only_violations}")

        # Root cause evidence from prose terms
        required_terms = ["shipping", "nodeSelector", "k9b.dev/otel-lab-node"]
        missing_terms = [t for t in required_terms if t.lower() not in root_cause_summary.lower()]

        # Check for scheduling evidence
        scheduling_markers = ["FailedScheduling", "Unschedulable", "nodeSelector", "no matching node"]
        scheduling_found = any(m.lower() in root_cause_summary.lower() for m in scheduling_markers)

        if missing_terms:
            root_cause_evidence_reason = f"missing_root_cause_term: {', '.join(missing_terms)}"
            failure_reasons.append(root_cause_evidence_reason)
            root_cause_evidence_satisfied = False
        elif not scheduling_found:
            root_cause_evidence_reason = "missing_scheduling_root_cause_evidence"
            failure_reasons.append(root_cause_evidence_reason)
            root_cause_evidence_satisfied = False
        else:
            root_cause_evidence_reason = None
            root_cause_evidence_satisfied = True

        success = len(failure_reasons) == 0

    return P4cDiagnosisOutcome(
        success=success,
        mode=mode,
        incident_id=incident_id,
        pass_count=pass_count,
        pass_run_ids=pass_run_ids,
        review_artifact_paths=review_artifact_paths,
        terminal_decision=terminal_decision,
        read_only_constraints_satisfied=read_only_constraints_satisfied,
        root_cause_evidence_satisfied=root_cause_evidence_satisfied,
        root_cause_evidence_reason=root_cause_evidence_reason,
        failure_reasons=tuple(failure_reasons),
    )


def _check_terminal_mode_scheduling_markers(evidence: dict[str, Any]) -> list[str]:
    """Check for scheduling markers in terminal mode evidence.

    For terminal no-checks single-pass, scheduling evidence comes from
    deterministic K8s evidence (P2b injection, P3c discovery) rather than
    diagnosis prose.

    Args:
        evidence: Diagnosis evidence dict

    Returns:
        List of scheduling markers found
    """
    found: list[str] = []
    SCHEDULING_MARKERS = ["FailedScheduling", "Unschedulable", "nodeSelector", "no matching node"]

    # Check p4c_verdict for matched evidence
    p4c_verdict = evidence.get("p4c_verdict", {})
    if isinstance(p4c_verdict, dict):
        matched = p4c_verdict.get("matched_evidence", [])
        if isinstance(matched, list):
            found.extend(matched)

    # Check root_cause_summary
    root_cause_summary = str(evidence.get("root_cause_summary", "")).lower()
    for marker in SCHEDULING_MARKERS:
        if marker.lower() in root_cause_summary:
            found.append(marker)

    # Check detection evidence
    detection_evidence = evidence.get("detection_evidence", {})
    if isinstance(detection_evidence, dict):
        summary = str(detection_evidence.get("summary", "")).lower()
        for marker in SCHEDULING_MARKERS:
            if marker.lower() in summary:
                found.append(marker)

    # Deduplicate
    return list(dict.fromkeys(found))


# =============================================================================
# Pass Counting Helper
# =============================================================================


def count_observable_targeted_diagnosis_passes(detail: dict[str, Any]) -> int:
    """Count observable targeted diagnosis passes from incident detail.

    Counting order (most preferred first):
    1. Explicit loop_summary.pass_count when present and an integer
    2. Length of loop_summary.diagnosis_loop_pass_run_ids or pass_run_ids when present
    3. 1 pass when automatic_diagnosis_review is available with a diagnosis-loop
       review-packet artifact and a run_id
    4. 0 otherwise

    This function handles the split-brain state where:
    - automatic_diagnosis_review is available (has review-packet artifact)
    - loop_summary may be null or missing pass info

    Also tolerates both field naming conventions:
    - automatic_diagnosis_loop_summary (newer API)
    - loop_summary (live lab payload)

    Args:
        detail: Incident detail dict from backend API

    Returns:
        Number of observable passes (0 or more)
    """
    # 1. Check loop_summary for explicit pass_count
    # Support both field naming conventions
    loop_summary = detail.get("automatic_diagnosis_loop_summary")
    if not isinstance(loop_summary, dict):
        loop_summary = detail.get("loop_summary")
    if isinstance(loop_summary, dict):
        pass_count = loop_summary.get("pass_count")
        if isinstance(pass_count, int) and pass_count > 0:
            return pass_count

        # 2. Check pass_run_ids in loop_summary (support both field names)
        pass_run_ids = extract_pass_run_ids(loop_summary)
        if pass_run_ids:
            return len(pass_run_ids)

    # 3. Check for diagnosis-loop review-packet in automatic_diagnosis_review
    review = detail.get("automatic_diagnosis_review")
    if isinstance(review, dict):
        available = review.get("available")
        if available is True:
            artifact_type = review.get("artifact_type")
            if artifact_type == "diagnosis-loop-review-packet":
                run_id = review.get("run_id")
                if isinstance(run_id, str) and run_id:
                    return 1

    # 4. Fallback: no observable passes
    return 0


def extract_pass_run_ids(loop_summary: dict[str, Any]) -> list[str]:
    """Extract pass run IDs from loop summary, supporting both field naming conventions.

    This helper handles the split-brain state where:
    - automatic_diagnosis_loop_summary uses pass_run_ids
    - loop_summary (live lab payload) may use diagnosis_loop_pass_run_ids

    Args:
        loop_summary: The loop summary dict from incident detail

    Returns:
        List of pass run IDs (empty if not found or invalid)
    """
    # Support both field naming conventions
    for key in ("pass_run_ids", "diagnosis_loop_pass_run_ids"):
        value = loop_summary.get(key)
        if isinstance(value, (list, tuple)) and value:
            # Filter to valid non-empty strings
            return [item for item in value if isinstance(item, str) and item]
    return []


def is_terminal_no_checks_decision(detail: dict[str, Any]) -> bool:
    """Check if the incident detail shows a terminal no-checks decision.

    A terminal no-checks decision occurs when:
    - automatic_diagnosis_review.available == True
    - automatic_diagnosis_review.artifact_type == "diagnosis-loop-review-packet"
    - automatic_diagnosis_review.decision == "stop_no_checks_proposed"
    - automatic_diagnosis_review.checks_requested == 0
    - automatic_diagnosis_review.checks_run == 0

    Args:
        detail: Incident detail dict from backend API

    Returns:
        True if this is a terminal no-checks decision
    """
    review = detail.get("automatic_diagnosis_review")
    if not isinstance(review, dict):
        return False

    if review.get("available") is not True:
        return False

    if review.get("artifact_type") != "diagnosis-loop-review-packet":
        return False

    if review.get("decision") != "stop_no_checks_proposed":
        return False

    checks_requested = review.get("checks_requested")
    checks_run = review.get("checks_run")

    # Treat None as 0 for comparison purposes
    if (checks_requested or 0) != 0:
        return False

    if (checks_run or 0) != 0:
        return False

    return True


def is_read_only_terminal_decision(detail: dict[str, Any]) -> bool:
    """Check if the terminal decision satisfies read-only constraints.

    A valid read-only terminal decision:
    - Has automatic_diagnosis_review
    - Has review_required_before_any_action == True
    - Has no_remediation_attempted == True

    Args:
        detail: Incident detail dict from backend API

    Returns:
        True if the terminal decision is read-only
    """
    review = detail.get("automatic_diagnosis_review")
    if not isinstance(review, dict):
        return False

    return (
        review.get("review_required_before_any_action") is True
        and review.get("no_remediation_attempted") is True
    )


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class BackendIncidentDetail:
    """Incident detail fetched from backend via GET /api/incidents/{id}."""

    incident_id: str
    status: str
    evidence_count: int
    review_packet_status: str | None
    loop_summary_status: str | None
    review_available: bool
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, incident_id: str, data: dict[str, Any]) -> BackendIncidentDetail:
        """Parse incident detail from backend API response."""
        review_packet = data.get("review_packet", {}) or {}
        loop_summary = data.get("automatic_diagnosis_loop_summary", {}) or {}
        review = data.get("automatic_diagnosis_review", {}) or {}

        return cls(
            incident_id=incident_id,
            status=data.get("status", "unknown"),
            evidence_count=data.get("evidence_count", 0),
            review_packet_status=review_packet.get("status") if isinstance(review_packet, dict) else None,
            loop_summary_status=loop_summary.get("status") if isinstance(loop_summary, dict) else None,
            review_available=review.get("available", False) if isinstance(review, dict) else False,
            raw=data,
        )

    def to_compact_log(self) -> str:
        """Return compact diagnostic log string."""
        return (
            f"incident_id={self.incident_id} "
            f"status={self.status} "
            f"evidence_count={self.evidence_count} "
            f"review_packet.status={self.review_packet_status or 'null'} "
            f"loop_summary.status={self.loop_summary_status or 'null'} "
            f"review_available={self.review_available}"
        )


@dataclass
class TargetedDiagnosisInvocationResult:
    """Result of invoking the targeted diagnosis-loop one-pass endpoint.

    This dataclass captures the outcome of a POST to
    /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass.

    Failure classification semantics:
    - success=True: HTTP 2xx received, JSON parsed, loop invocation processed
    - success=False: Transport/HTTP/JSON failure that blocked invocation

    Note: HTTP 200 with skipped=True (budget_exhausted) is NOT a failure.
    It returns success=True with error_class=FAILURE_TARGETED_LOOP_NOT_ELIGIBLE
    to distinguish runtime state from transport errors.
    """

    success: bool
    http_status: int
    body: str
    json_parsed: bool
    response_data: dict[str, Any] = field(default_factory=dict)
    error_class: str | None = None
    error_detail: str | None = None
    curl_rc: int | None = None
    stderr_prefix: str = ""
    budget_diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for evidence."""
        return {
            "success": self.success,
            "http_status": self.http_status,
            "json_parsed": self.json_parsed,
            "error_class": self.error_class,
            "error_detail": self.error_detail,
            "curl_rc": self.curl_rc,
            "budget_diagnostics": self.budget_diagnostics,
        }

    def is_transport_error(self) -> bool:
        """Check if this is a transport-level failure (not runtime state)."""
        if self.error_class in (
            FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
        ):
            return True
        return False

    def is_runtime_state(self) -> bool:
        """Check if this is a runtime state (budget_exhausted, not eligible)."""
        if self.error_class == FAILURE_TARGETED_LOOP_NOT_ELIGIBLE:
            return True
        return False

    def budget_summary(self) -> str:
        """Return human-readable budget diagnostics summary."""
        if not self.budget_diagnostics:
            return "no budget diagnostics"
        lines = []
        for bd in self.budget_diagnostics:
            status = "EXHAUSTED" if bd.get("exhausted") else "OK"
            lines.append(
                f"{bd.get('name', 'unknown')}: {status} "
                f"used={bd.get('used', 0)} limit={bd.get('limit', 0)} "
                f"remaining={bd.get('remaining', 0)} "
                f"source={bd.get('source', 'unknown')} "
                f"resettable={bd.get('resettable', True)}"
            )
        return "; ".join(lines)


@dataclass
class TargetedDiagnosisPollResult:
    """Result of polling backend for diagnosis state."""

    success: bool
    final_status: str
    loop_summary_status: str | None
    review_available: bool
    attempts: int
    max_attempts: int
    final_detail: BackendIncidentDetail | None = None
    failure_reason: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for evidence."""
        return {
            "success": self.success,
            "final_status": self.final_status,
            "loop_summary_status": self.loop_summary_status,
            "review_available": self.review_available,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "failure_reason": self.failure_reason,
            "error_detail": self.error_detail,
        }


@dataclass
class BackendIncidentFetchResult:
    """Rich result of fetching incident detail from backend.

    Provides precise failure classification for debugging P4c failures
    without live-cluster access. Distinguishes transport, HTTP, JSON,
    and contract errors.
    """

    success: bool
    incident: BackendIncidentDetail | None = None
    error_class: str | None = None
    error_detail: str | None = None
    http_status: int = 0
    curl_rc: int | None = None
    url: str = ""
    api_path: str = ""
    encoded_incident_id: str = ""
    body_prefix: str = ""
    stderr_prefix: str = ""
    json_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for evidence artifact.

        Only includes failure fields when not successful to keep
        artifact compact. Incident is stored separately if needed.
        """
        result: dict[str, Any] = {
            "success": self.success,
            "http_status": self.http_status,
            "curl_rc": self.curl_rc,
            "url": self.url,
            "api_path": self.api_path,
            "encoded_incident_id": self.encoded_incident_id,
        }
        if not self.success:
            result["error_class"] = self.error_class
            result["error_detail"] = self.error_detail
            result["body_prefix"] = self.body_prefix
            result["stderr_prefix"] = self.stderr_prefix
            result["json_error"] = self.json_error
        return result

    def to_log_lines(self) -> list[str]:
        """Generate structured log lines for diagnostics."""
        lines = [
            f"backend_incident_fetch: success={self.success}",
            f"  error_class={self.error_class or 'none'}",
            f"  error_detail={self.error_detail or 'none'}",
            f"  http_status={self.http_status}",
            f"  curl_rc={self.curl_rc}",
            f"  api_path={self.api_path}",
            f"  encoded_incident_id={self.encoded_incident_id}",
        ]
        if self.body_prefix:
            lines.append(f"  body_prefix={self.body_prefix[:100]}")
        if self.stderr_prefix:
            lines.append(f"  stderr_prefix={self.stderr_prefix[:100]}")
        if self.json_error:
            lines.append(f"  json_error={self.json_error}")
        return lines
