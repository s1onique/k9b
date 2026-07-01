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
from typing import Any

# =============================================================================
# Failure Reason Constants
# =============================================================================

FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR = "backend_incident_fetch_transport_error"
FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR = "backend_incident_fetch_http_error"
FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND = "backend_incident_fetch_not_found"
FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON = "backend_incident_fetch_invalid_json"
FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR = "backend_incident_fetch_contract_error"
FAILURE_BACKEND_INCIDENT_FETCH_FAILED = "backend_incident_fetch_failed"

FAILURE_TARGETED_INVOCATION_HTTP_ERROR = "targeted_automatic_diagnosis_invocation_http_error"
FAILURE_TARGETED_INVOCATION_INVALID_JSON = "targeted_automatic_diagnosis_invocation_invalid_json"
FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR = "targeted_automatic_diagnosis_invocation_transport_error"
FAILURE_TARGETED_LOOP_NOT_COMPLETED = "targeted_automatic_diagnosis_loop_not_completed"
FAILURE_TARGETED_NO_PASS_ARTIFACTS = "targeted_automatic_diagnosis_no_pass_artifacts"
FAILURE_TARGETED_REVIEW_PACKET_MISSING = "targeted_automatic_diagnosis_review_packet_missing"
FAILURE_TARGETED_INSUFFICIENT_PASSES = "targeted_automatic_diagnosis_insufficient_passes"


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
    """Result of invoking the targeted diagnosis-loop one-pass endpoint."""

    success: bool
    http_status: int
    body: str
    json_parsed: bool
    response_data: dict[str, Any] = field(default_factory=dict)
    error_class: str | None = None
    error_detail: str | None = None
    curl_rc: int | None = None
    stderr_prefix: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for evidence."""
        return {
            "success": self.success,
            "http_status": self.http_status,
            "json_parsed": self.json_parsed,
            "error_class": self.error_class,
            "error_detail": self.error_detail,
            "curl_rc": self.curl_rc,
        }


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
