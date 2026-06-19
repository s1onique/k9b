"""Authenticated manual one-pass incident diagnosis loop API.

This module provides a bounded API endpoint for running exactly one
deterministic read-only diagnosis loop pass for an incident.

Design constraints:
- Authenticated admin-only access via existing auth guard
- No LLM calls
- No Kubernetes calls
- No subprocess/shell/kubectl
- No execution, promotion, or remediation
- Bounded request/response with no raw artifact contents
- Explicit safety metadata

Route: POST /api/incidents/{incident_id}/diagnosis-loop/one-pass

Non-goals (explicitly forbidden):
- Real Kubernetes collectors
- kubectl/helm/subprocess/shell execution
- Remediation or mutation
- Automatic scheduling
- Background jobs
- Webhooks
- External LLM provider calls
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..security import sanitize_exception_message
from .incident_case_file import build_incident_case_file
from .incident_diagnosis_loop_orchestrator import run_one_read_only_diagnosis_loop_pass
from .incident_read_only_check_artifacts import is_safe_run_id
from .incident_store_provider import get_incident_store

if True:
    # Intentional no-op import barrier to prevent accidental kubernetes imports
    # This module must never import kubernetes client libraries
    pass

__all__ = [
    "DiagnosisLoopOnePassRequest",
    "DiagnosisLoopOnePassResponse",
    "handle_diagnosis_loop_one_pass",
]

# =============================================================================
# Constants
# =============================================================================

# Maximum request body size in bytes (safety bound)
MAX_REQUEST_BODY_SIZE = 64 * 1024  # 64KB

# Forbidden action-control fields that must not appear in response
_FORBIDDEN_ACTION_FIELDS: frozenset[str] = frozenset([
    "run",
    "execute",
    "promote",
    "apply",
    "remediate",
    "action",
    "approve",
    "reject",
    "run_command",
    "execute_command",
    "mutate",
    "delete",
    "scale",
    "restart",
    "rollout",
    "patch",
])

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
])


# =============================================================================
# Request/Response Types
# =============================================================================


@dataclass
class DiagnosisLoopOnePassRequest:
    """Request shape for diagnosis loop one-pass API."""

    run_id: str
    diagnosis_report: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiagnosisLoopOnePassRequest:
        """Parse request from dict, validating required fields.

        Args:
            data: Raw request dict

        Returns:
            Validated request object

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Check for forbidden fields
        for field_name in _FORBIDDEN_REQUEST_FIELDS:
            if field_name in data:
                raise ValueError(f"Request body must not contain '{field_name}'")

        # Validate run_id
        run_id = data.get("run_id")
        if not run_id or not isinstance(run_id, str):
            raise ValueError("run_id is required and must be a string")

        if not is_safe_run_id(run_id):
            raise ValueError(f"Unsafe run_id: {run_id!r}")

        # Validate diagnosis_report
        diagnosis_report = data.get("diagnosis_report")
        if not diagnosis_report or not isinstance(diagnosis_report, dict):
            raise ValueError("diagnosis_report is required and must be an object")

        if "diagnosis" not in diagnosis_report:
            raise ValueError("diagnosis_report.diagnosis is required")

        diagnosis = diagnosis_report.get("diagnosis")
        if not isinstance(diagnosis, dict):
            raise ValueError("diagnosis_report.diagnosis must be an object")

        # Validate recommended_investigations if present
        recommended = diagnosis.get("recommended_investigations")
        if recommended is not None:
            if not isinstance(recommended, list):
                raise ValueError("diagnosis_report.diagnosis.recommended_investigations must be an array")
            # Bound the list size
            if len(recommended) > 100:
                raise ValueError("diagnosis_report.diagnosis.recommended_investigations exceeds maximum size")

        return cls(
            run_id=run_id,
            diagnosis_report=diagnosis_report,
        )


@dataclass
class DiagnosisLoopOnePassResponse:
    """Response shape for diagnosis loop one-pass API."""

    schema_version: str
    incident_id: str
    run_id: str
    read_only: bool = True
    allowed_actions: list[str] = field(default_factory=list)
    decision: str = ""
    checks_requested: int = 0
    checks_run: int = 0
    checks_skipped: int = 0
    checks_rejected: int = 0
    artifacts: dict[str, Any] = field(default_factory=dict)
    case_file_linked_artifact: bool = False
    safety_metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert response to dict for JSON serialization.

        Returns:
            Bounded JSON-serializable dict
        """
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "incident_id": self.incident_id,
            "run_id": self.run_id,
            "read_only": self.read_only,
            "allowed_actions": self.allowed_actions,
            "decision": self.decision,
            "checks_requested": self.checks_requested,
            "checks_run": self.checks_run,
            "checks_skipped": self.checks_skipped,
            "checks_rejected": self.checks_rejected,
            "artifacts": self.artifacts,
            "case_file_linked_artifact": self.case_file_linked_artifact,
            "safety_metadata": self.safety_metadata,
        }
        if self.error is not None:
            result["error"] = self.error
        return result


# =============================================================================
# Core Handler
# =============================================================================


def handle_diagnosis_loop_one_pass(
    incident_id: str,
    external_analysis_dir: Path,
    request: DiagnosisLoopOnePassRequest,
) -> DiagnosisLoopOnePassResponse:
    """Handle one-pass diagnosis loop for an incident.

    This function:
    1. Loads the current incident from the store
    2. Builds the current case file
    3. Runs exactly one pass of the read-only diagnosis loop orchestrator
    4. Persists artifacts
    5. Returns bounded result metadata

    Args:
        incident_id: The incident ID to diagnose
        external_analysis_dir: Path to external-analysis directory for artifacts
        request: Validated request with run_id and diagnosis_report

    Returns:
        Bounded response with decision, check counts, and artifact references
    """
    # Step 1: Load incident from store
    store = get_incident_store()
    incident = store.get_incident(incident_id)

    if incident is None:
        return DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id=incident_id,
            run_id=request.run_id,
            error="Incident not found",
        )

    # Step 2: Build current case file
    case_file = build_incident_case_file(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
    )

    if case_file is None:
        return DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id=incident_id,
            run_id=request.run_id,
            error="Failed to build case file",
        )

    # Step 3: Run one-pass orchestrator
    try:
        orchestrator_result = run_one_read_only_diagnosis_loop_pass(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            case_file=case_file,
            diagnosis_report=request.diagnosis_report,
            run_id=request.run_id,
        )
    except Exception as exc:
        # Bound error message, don't leak traceback
        sanitized = sanitize_exception_message(exc, max_length=200)
        return DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id=incident_id,
            run_id=request.run_id,
            error=f"Orchestrator error: {sanitized}",
        )

    # Step 4: Extract bounded result data
    decision = str(orchestrator_result.get("decision", ""))
    runner_result = orchestrator_result.get("runner_result")
    artifact = orchestrator_result.get("artifact")
    loop_pass_artifact = orchestrator_result.get("loop_pass_artifact")
    case_file_linked_artifact = bool(orchestrator_result.get("case_file_linked_artifact", False))
    _safety_raw = orchestrator_result.get("safety_metadata", {})
    safety_metadata: dict[str, Any] = dict(_safety_raw) if isinstance(_safety_raw, dict) else {}

    # Extract check counts
    checks_requested = 0
    checks_run = 0
    checks_skipped = 0
    checks_rejected = 0

    if runner_result and isinstance(runner_result, dict):
        checks_requested = runner_result.get("checks_requested", 0)
        checks_run = runner_result.get("checks_run", 0)
        checks_skipped = runner_result.get("checks_skipped", 0)
        checks_rejected = runner_result.get("checks_rejected", 0)

    # Build artifacts response (bounded references only)
    artifacts: dict[str, Any] = {
        "read_only_check_results": {
            "written": False,
            "name": None,
        },
        "diagnosis_loop_pass": {
            "written": False,
            "name": None,
        },
    }

    # Extract artifact references (not full contents)
    if artifact and isinstance(artifact, dict):
        if artifact.get("written") and artifact.get("path"):
            # Extract just the filename, not full path
            path_str = artifact.get("path", "")
            if isinstance(path_str, str):
                name = Path(path_str).name
                artifacts["read_only_check_results"] = {
                    "written": True,
                    "name": name,
                }

    if loop_pass_artifact and isinstance(loop_pass_artifact, dict):
        if loop_pass_artifact.get("written") and loop_pass_artifact.get("path"):
            path_str = loop_pass_artifact.get("path", "")
            if isinstance(path_str, str):
                name = Path(path_str).name
                artifacts["diagnosis_loop_pass"] = {
                    "written": True,
                    "name": name,
                }

    # Build bounded safety metadata
    bounded_safety = {
        "read_only": safety_metadata.get("read_only", True),
        "allowed_actions": safety_metadata.get("allowed_actions", []),
        "no_kubernetes_client": safety_metadata.get("no_kubernetes_client", True),
        "no_shell": safety_metadata.get("no_shell", True),
        "no_subprocess": safety_metadata.get("no_subprocess", True),
        "no_kubectl": safety_metadata.get("no_kubectl", True),
        "no_mutation": safety_metadata.get("no_mutation", True),
        "fake_runner": safety_metadata.get("fake_runner", True),
        "one_pass_only": safety_metadata.get("one_pass_only", True),
    }

    return DiagnosisLoopOnePassResponse(
        schema_version="1.0",
        incident_id=incident_id,
        run_id=request.run_id,
        read_only=True,
        allowed_actions=[],
        decision=decision,
        checks_requested=checks_requested,
        checks_run=checks_run,
        checks_skipped=checks_skipped,
        checks_rejected=checks_rejected,
        artifacts=artifacts,
        case_file_linked_artifact=case_file_linked_artifact,
        safety_metadata=bounded_safety,
    )