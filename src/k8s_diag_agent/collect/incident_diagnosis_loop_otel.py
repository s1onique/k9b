"""OTel span helpers for diagnosis loop runtime.

This module provides OTel span/event emission stubs that can be wired
to the actual OTel infrastructure when deployed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .incident_diagnosis_loop_policy import DiagnosisLoopPolicy

if TYPE_CHECKING:
    pass


# =============================================================================
# Runtime OTel Span Helpers
# =============================================================================


def emit_loop_span(
    run_id: str,
    incident_id: str,
    policy: DiagnosisLoopPolicy,
    event: str,
) -> None:
    """Emit OTel span/event for loop run.

    In production, this would emit to OTel. For now, this is a stub
    that can be wired to the actual OTel infrastructure.

    Args:
        run_id: Unique identifier for this loop run
        incident_id: The incident being diagnosed
        policy: The policy in effect
        event: The event name (started, completed, failed)
    """
    # TODO: Wire to actual OTel span emitter
    # Span name: k9b.diagnosis_loop.run
    # Attributes:
    #   - k9b.incident.id
    #   - k9b.loop.run_id
    #   - k9b.loop.max_passes
    #   - k9b.loop.max_checks
    pass


def emit_pass_span(
    run_id: str,
    pass_index: int,
    decision: str,
    stop_reason: str | None,
    checks_accepted: int,
    checks_rejected: int,
) -> None:
    """Emit OTel span/event for loop pass.

    Args:
        run_id: Unique identifier for this loop run
        pass_index: The pass number
        decision: The loop decision
        stop_reason: The stop reason if stopped
        checks_accepted: Number of checks accepted
        checks_rejected: Number of checks rejected
    """
    # TODO: Wire to actual OTel span emitter
    # Span name: k9b.diagnosis_loop.pass
    # Attributes:
    #   - k9b.loop.run_id
    #   - k9b.loop.pass_index
    #   - k9b.loop.decision
    #   - k9b.loop.stop_reason
    pass


def emit_check_gate_span(
    run_id: str,
    pass_index: int,
    check_id: str,
    accepted: bool,
    rejection_reason: str | None,
) -> None:
    """Emit OTel span/event for check gate.

    Args:
        run_id: Unique identifier for this loop run
        pass_index: The pass number
        check_id: The check that was gated
        accepted: Whether the check was accepted
        rejection_reason: Reason for rejection if not accepted
    """
    # TODO: Wire to actual OTel span emitter
    # Span name: k9b.diagnosis_loop.check_gate
    # Attributes:
    #   - k9b.loop.run_id
    #   - k9b.loop.pass_index
    #   - k9b.check.id
    #   - k9b.check.accepted
    #   - k9b.check.rejection_reason
    pass
