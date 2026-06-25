"""Authenticated incident one-pass diagnosis service API.

This module provides an API endpoint that calls the incident diagnosis service
(run_incident_one_pass_diagnosis) with proper dependency injection and safety.

Design constraints:
- Authenticated admin-only access via existing auth guard
- No LLM calls (provider injected via request/dependencies)
- No Kubernetes calls
- No subprocess/shell/kubectl
- No execution, promotion, or remediation
- Bounded request/response with no raw artifact contents
- Explicit safety metadata
- Fail-closed on missing providers/handlers

Route: POST /api/incidents/{incident_id}/one-pass-diagnosis

Non-goals (explicitly forbidden):
- Real Kubernetes collectors
- kubectl/helm/subprocess/shell execution
- Remediation or mutation
- Automatic scheduling
- Background jobs
- Webhooks
- Production LLM provider calls (must use injected provider)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..security import sanitize_exception_message
from .incident_diagnosis_service import (
    ArtifactWriter,
    DiagnosisProvider,
    IncidentDiagnosisServiceResult,
    IncidentOnePassServiceRequest,
    run_incident_one_pass_diagnosis,
)
from .incident_store_provider import get_incident_store

if TYPE_CHECKING:
    from .incident_read_only_check_runner import ReadOnlyCheckHandler

if True:
    # Intentional no-op import barrier to prevent accidental kubernetes imports
    # This module must never import kubernetes client libraries
    pass

__all__ = [
    "OnePassServiceRequest",
    "OnePassServiceResponse",
    "handle_one_pass_diagnosis_service",
]

# =============================================================================
# Constants
# =============================================================================

# Maximum request body size in bytes (safety bound)
MAX_REQUEST_BODY_SIZE = 64 * 1024  # 64KB


# =============================================================================
# Helpers
# =============================================================================


def _is_safe_incident_id(incident_id: str) -> bool:
    """Validate incident ID for safety.

    Args:
        incident_id: The incident ID to validate

    Returns:
        True if safe, False otherwise
    """
    if not incident_id or not isinstance(incident_id, str):
        return False
    # Length check
    if len(incident_id) > 128:
        return False
    # No path traversal
    if ".." in incident_id or "/" in incident_id or "\\" in incident_id:
        return False
    # No command injection characters
    if any(c in incident_id for c in ["`", "$", ";", "|", "&", "\n", "\r", "\0"]):
        return False
    return True


# Forbidden request body fields
_FORBIDDEN_REQUEST_FIELDS: frozenset[str] = frozenset([
    "external_analysis_dir",
    "external_analysis_path",
    "artifact_root",
    "fs_path",
    "path",
    "run",
    "execute",
    "mutate",
    "delete",
    "scale",
    "restart",
    "rollout",
    "patch",
    "apply",
    "remediate",
    "llm_provider",
    "diagnosis_provider",
    "fake_handlers",
    "golden_case_mode",
])


# =============================================================================
# Request/Response Types
# =============================================================================


@dataclass
class OnePassServiceRequest:
    """Request shape for one-pass diagnosis service API.

    This is the external API request, distinct from the internal
    IncidentOnePassServiceRequest used by the service layer.
    """

    incident_id: str
    # Optional: run_id for tracking (auto-generated if not provided)
    run_id: str | None = None

    @classmethod
    def from_dict(cls, data: object) -> OnePassServiceRequest:
        """Parse request from dict, validating required fields.

        Args:
            data: Raw request dict

        Returns:
            Validated request object

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Reject non-dict input (e.g., [], null, etc.)
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")

        # Check for forbidden fields
        for field_name in _FORBIDDEN_REQUEST_FIELDS:
            if field_name in data:
                raise ValueError(f"Request body must not contain '{field_name}'")

        # Validate incident_id
        incident_id = data.get("incident_id")
        if not incident_id or not isinstance(incident_id, str):
            raise ValueError("incident_id is required and must be a string")

        if not _is_safe_incident_id(incident_id):
            raise ValueError(f"Unsafe incident_id: {incident_id!r}")

        # Validate run_id if provided
        run_id = data.get("run_id")
        if run_id is not None and not isinstance(run_id, str):
            raise ValueError("run_id must be a string if provided")

        return cls(
            incident_id=incident_id,
            run_id=run_id if run_id else None,
        )


@dataclass
class OnePassServiceResponse:
    """Response shape for one-pass diagnosis service API.

    Maps from IncidentDiagnosisServiceResult to HTTP API response format.
    Includes all required fields from the service DTO.
    """

    schema_version: str
    incident_id: str
    run_id: str
    category: str = ""
    root_cause: str = ""
    confidence: str = "unknown"
    description: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    read_only: bool = True
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions_observed: list[str] = field(default_factory=list)
    mutation_proposals_observed: list[str] = field(default_factory=list)
    decision: str = ""
    checks_run: int = 0
    next_checks: list[dict[str, Any]] = field(default_factory=list)
    artifact_written: bool = False
    artifact_name: str | None = None
    error: str | None = None
    # Provider proof fields for live-lab smoke testing
    provider_configured: bool = False
    provider_invocation_attempted: bool = False

    @classmethod
    def from_service_result(
        cls,
        result: IncidentDiagnosisServiceResult,
        default_run_id: str = "",
    ) -> OnePassServiceResponse:
        """Create response from service result.

        Args:
            result: The service-layer result
            default_run_id: Fallback run_id if result has empty run_id

        Returns:
            API response object
        """
        return cls(
            schema_version="1.0",
            incident_id=result.incident_id,
            run_id=result.run_id or default_run_id,
            category=result.category,
            root_cause=result.root_cause,
            confidence=result.confidence,
            description=result.description,
            evidence_refs=result.evidence_refs,
            read_only=result.read_only,
            allowed_actions=result.allowed_actions,
            forbidden_actions_observed=result.forbidden_actions_observed,
            mutation_proposals_observed=result.mutation_proposals_observed,
            decision=result.decision,
            checks_run=result.checks_run,
            next_checks=result.next_checks,
            artifact_written=result.artifact_written,
            artifact_name=result.artifact_name,
            error=result.error,
            # Provider proof fields for live-lab smoke testing
            provider_configured=result.provider_configured,
            provider_invocation_attempted=result.provider_invocation_attempted,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert response to dict for JSON serialization.

        Returns:
            Bounded JSON-serializable dict
        """
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "incident_id": self.incident_id,
            "run_id": self.run_id,
            "category": self.category,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "description": self.description,
            "evidence_refs": self.evidence_refs,
            "read_only": self.read_only,
            "allowed_actions": self.allowed_actions,
            "forbidden_actions_observed": self.forbidden_actions_observed,
            "mutation_proposals_observed": self.mutation_proposals_observed,
            "decision": self.decision,
            "checks_run": self.checks_run,
            "next_checks": self.next_checks,
            "artifact_written": self.artifact_written,
            # Provider proof fields for live-lab smoke testing
            "provider_configured": self.provider_configured,
            "provider_invocation_attempted": self.provider_invocation_attempted,
        }
        if self.artifact_name is not None:
            result["artifact_name"] = self.artifact_name
        if self.error is not None:
            result["error"] = self.error
        return result


# =============================================================================
# Core Handler
# =============================================================================


def handle_one_pass_diagnosis_service(
    incident_id: str,
    external_analysis_dir: Path,
    request: OnePassServiceRequest,
    diagnosis_provider: DiagnosisProvider | None = None,
    fake_handlers: dict[str, ReadOnlyCheckHandler] | None = None,
    artifact_writer: ArtifactWriter | None = None,
    # Golden-case mode for ACT-local verification
    golden_case_mode: bool = False,
    golden_case_manifest: dict[str, object] | None = None,
    golden_case_case_dir: Path | None = None,
    golden_case_evidence_provider: object | None = None,
) -> OnePassServiceResponse:
    """Handle one-pass diagnosis service request.

    This function:
    1. Validates the incident exists
    2. Builds the service request with injected dependencies
    3. Calls run_incident_one_pass_diagnosis()
    4. Returns bounded response metadata

    Args:
        incident_id: The incident ID to diagnose
        external_analysis_dir: Path to external-analysis directory for artifacts
        request: Validated API request
        diagnosis_provider: Optional LLM diagnosis provider (injected)
        fake_handlers: Optional fake read-only handlers (injected for testing)
        artifact_writer: Optional artifact writer (injected for testing)
        golden_case_mode: Enable golden-case enforcement (for ACT-local verification)
        golden_case_manifest: Manifest dict for golden-case mode
        golden_case_case_dir: Case directory for golden-case mode
        golden_case_evidence_provider: Evidence provider for golden-case mode

    Returns:
        Bounded response with diagnosis outcome
    """
    from datetime import UTC, datetime

    # Step 1: Validate incident exists
    store = get_incident_store()
    incident = store.get_incident(incident_id)

    if incident is None:
        return OnePassServiceResponse(
            schema_version="1.0",
            incident_id=incident_id,
            run_id=request.run_id or "unknown",
            error="Incident not found",
        )

    # Step 2: Build service request with dependencies
    now = datetime.now(UTC)
    service_request = IncidentOnePassServiceRequest(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
        diagnosis_provider=diagnosis_provider,
        fake_handlers=fake_handlers,
        artifact_writer=artifact_writer,
        now=now,
        golden_case_mode=golden_case_mode,
        golden_case_manifest=golden_case_manifest,
        golden_case_case_dir=golden_case_case_dir,
        golden_case_evidence_provider=golden_case_evidence_provider,
        enforce_fake_handlers=golden_case_mode,  # Require fake handlers in golden-case mode
        use_live_command_guard=True,  # Always block live-command fallback
    )

    # Step 3: Run diagnosis service
    try:
        service_result = run_incident_one_pass_diagnosis(service_request)
    except Exception as exc:
        # Bound error message, don't leak traceback
        sanitized = sanitize_exception_message(exc, max_length=200)
        return OnePassServiceResponse(
            schema_version="1.0",
            incident_id=incident_id,
            run_id=request.run_id or "unknown",
            error=f"Service error: {sanitized}",
        )

    # Step 4: Convert to API response
    return OnePassServiceResponse.from_service_result(
        service_result,
        default_run_id=request.run_id or "",
    )
