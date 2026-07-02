"""Contract types (dataclasses) for OTel demo backend diagnosis helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import Literal

# =============================================================================
# P4c Outcome Types
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


# =============================================================================
# Incident Detail Types
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


# =============================================================================
# Invocation Result Types
# =============================================================================


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
        # Import here to avoid circular imports; will be resolved at module load
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_failure_reasons import (
            FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
        )

        if self.error_class in (
            FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
        ):
            return True
        return False

    def is_runtime_state(self) -> bool:
        """Check if this is a runtime state (budget_exhausted, not eligible)."""
        # Import here to avoid circular imports
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_failure_reasons import (
            FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
        )

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


__all__ = [
    "P4cDiagnosisOutcome",
    "BackendIncidentDetail",
    "TargetedDiagnosisInvocationResult",
    "TargetedDiagnosisPollResult",
    "BackendIncidentFetchResult",
]
