"""Gating logic for manual next-check execution eligibility."""

from __future__ import annotations

from collections.abc import Mapping

from .manual_next_check_commands import ManualNextCheckError
from .manual_next_check_logging import _log_and_raise_gating
from .next_check_planner import BlockingReason, CommandFamily

_ALLOWED_FAMILIES = frozenset({
    CommandFamily.KUBECTL_GET,
    CommandFamily.KUBECTL_DESCRIBE,
    CommandFamily.KUBECTL_LOGS,
    CommandFamily.KUBECTL_GET_CRD,
    CommandFamily.KUBECTL_TOP,
})


def _candidate_blocking_reason(candidate: Mapping[str, object]) -> BlockingReason | None:
    """Extract blocking reason from candidate if present."""
    raw = candidate.get("blockingReason")
    if isinstance(raw, str) and raw:
        try:
            return BlockingReason(raw)
        except ValueError:
            return None
    return None


def check_candidate_gating(
    *,
    candidate: Mapping[str, object],
    family: CommandFamily,
    description: str,
    target_context: str,
    plan_artifact_path: str,
    run_label: str,
    run_id: str,
    candidate_index: int,
    target_cluster: str,
    candidate_id_value: str | None,
) -> None:
    """Check gating conditions for a candidate and raise if not allowed.

    This function validates all gating conditions and raises ManualNextCheckError
    if any condition is not met.

    Args:
        candidate: The candidate dictionary
        family: Parsed command family
        description: Candidate description
        target_context: kubectl context
        plan_artifact_path: Path to the plan artifact
        run_label: Human-readable run identifier
        run_id: Unique run identifier
        candidate_index: Index of the candidate
        target_cluster: Cluster label
        candidate_id_value: Candidate ID
    """
    if not candidate.get("safeToAutomate"):
        blocking_reason = _candidate_blocking_reason(candidate)
        _log_and_raise_gating(
            reason="Candidate is not marked safe to automate.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=None,
            blocking_reason=blocking_reason,
            error_class=ManualNextCheckError,
        )

    requires_approval = bool(candidate.get("requiresOperatorApproval"))
    approval_status = str(candidate.get("approvalStatus") or "").lower()
    if requires_approval and approval_status != "approved":
        blocking_reason = _candidate_blocking_reason(candidate) or BlockingReason.REQUIRES_APPROVAL
        _log_and_raise_gating(
            reason="Candidate requires operator approval before execution.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=None,
            blocking_reason=blocking_reason,
            error_class=ManualNextCheckError,
        )

    if candidate.get("duplicateOfExistingEvidence"):
        _log_and_raise_gating(
            reason="Candidate is a duplicate of existing evidence.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=None,
            blocking_reason=_candidate_blocking_reason(candidate) or BlockingReason.DUPLICATE,
            error_class=ManualNextCheckError,
        )

    if not description:
        _log_and_raise_gating(
            reason="Candidate description is missing.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description="",
            candidate_id=candidate_id_value,
            command_family=family.value,
            blocking_reason=BlockingReason.MISSING_DESCRIPTION,
            error_class=ManualNextCheckError,
        )

    if not target_context:
        _log_and_raise_gating(
            reason="Unable to determine kubectl context for the target cluster.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=family.value,
            blocking_reason=BlockingReason.MISSING_CONTEXT,
            error_class=ManualNextCheckError,
        )


def validate_command_family(
    *,
    family_raw: str,
    family: CommandFamily,
    plan_artifact_path: str,
    run_label: str,
    run_id: str,
    candidate_index: int,
    target_cluster: str,
    target_context: str,
    description: str,
    candidate_id_value: str | None,
) -> None:
    """Validate the command family is allowed for manual execution.

    Args:
        family_raw: Raw family string from candidate
        family: Parsed CommandFamily enum
        plan_artifact_path: Path to the plan artifact
        run_label: Human-readable run identifier
        run_id: Unique run identifier
        candidate_index: Index of the candidate
        target_cluster: Cluster label
        target_context: kubectl context
        description: Candidate description
        candidate_id_value: Candidate ID
    """
    if family not in _ALLOWED_FAMILIES:
        _log_and_raise_gating(
            reason=f"Command family '{family.value}' is not allowed for manual execution.",
            run_label=run_label,
            run_id=run_id,
            plan_artifact_path=plan_artifact_path,
            candidate_index=candidate_index,
            target_cluster=target_cluster or run_label,
            target_context=target_context,
            candidate_description=description,
            candidate_id=candidate_id_value,
            command_family=family.value,
            blocking_reason=BlockingReason.COMMAND_NOT_ALLOWED,
            error_class=ManualNextCheckError,
        )
