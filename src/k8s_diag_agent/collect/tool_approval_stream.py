"""Approval Stream Protocol for k9b incident workbench.

This module provides first-class approval stream functionality that:
- Declares pending approvals before execution
- Tracks approval state transitions
- Records operator decisions with timestamps
- Links approvals to tool outputs
- Enables audit trail reconstruction

Canonical pipeline:
    tool execution request
    → approval class check
    → pending approval declared
    → operator notified
    → operator decision recorded
    → execution proceeds or rejected

Design principles:
- Approvals are declarative (state machine, not polling)
- Approval state is immutable once transitioned
- Decisions are timestamped and attributed
- Failed/timeout decisions are explicit
- No silent execution bypass

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-APPROVAL-STREAM01
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# =============================================================================
# Schema version
# =============================================================================

APPROVAL_SCHEMA_VERSION = "1.0"

# =============================================================================
# Approval State
# =============================================================================


class ApprovalState(StrEnum):
    """State of an approval request."""

    #: Approval has been requested but not yet decided
    PENDING = "pending"

    #: Operator explicitly approved the action
    APPROVED = "approved"

    #: Operator explicitly rejected the action
    REJECTED = "rejected"

    #: Approval timed out waiting for operator
    TIMEOUT = "timeout"

    #: Approval was cancelled (e.g., session ended)
    CANCELLED = "cancelled"


# =============================================================================
# Approval Request Schema
# =============================================================================


@dataclass(frozen=True)
class ApprovalRequest:
    """Request for operator approval before tool execution.

    This schema represents a pending approval that requires operator decision.
    It captures:
    - Tool being requested
    - Approval class (determines urgency)
    - Rationale for the request
    - Deadline for response
    - Operator context
    """

    schema_version: str = APPROVAL_SCHEMA_VERSION
    request_id: str = ""
    tool_id: str = ""
    approval_class: str = ""
    rationale: str = ""
    deadline_seconds: int = 300  # 5 minutes default
    created_at: str = ""
    operator_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "tool_id": self.tool_id,
            "approval_class": self.approval_class,
            "rationale": self.rationale,
            "deadline_seconds": self.deadline_seconds,
            "created_at": self.created_at,
            "operator_context": self.operator_context,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApprovalRequest:
        """Deserialize from dict."""
        return cls(
            schema_version=data.get("schema_version", APPROVAL_SCHEMA_VERSION),
            request_id=data.get("request_id", ""),
            tool_id=data.get("tool_id", ""),
            approval_class=data.get("approval_class", ""),
            rationale=data.get("rationale", ""),
            deadline_seconds=data.get("deadline_seconds", 300),
            created_at=data.get("created_at", ""),
            operator_context=data.get("operator_context", {}),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# Approval Decision Schema
# =============================================================================


@dataclass(frozen=True)
class ApprovalDecision:
    """Decision made by operator for an approval request.

    This schema captures the operator's decision:
    - Which request was decided
    - The decision (approved/rejected/timeout/cancelled)
    - Timestamp of decision
    - Operator identifier (if available)
    - Optional reason for decision
    - Link to resulting tool output (if approved)
    """

    schema_version: str = APPROVAL_SCHEMA_VERSION
    request_id: str = ""
    decision: str = ApprovalState.PENDING.value
    decided_at: str = ""
    operator_id: str | None = None
    reason: str | None = None
    tool_output_ref: str | None = None
    execution_duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "decision": self.decision,
            "decided_at": self.decided_at,
            "operator_id": self.operator_id,
            "reason": self.reason,
            "tool_output_ref": self.tool_output_ref,
            "execution_duration_ms": self.execution_duration_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApprovalDecision:
        """Deserialize from dict."""
        return cls(
            schema_version=data.get("schema_version", APPROVAL_SCHEMA_VERSION),
            request_id=data.get("request_id", ""),
            decision=data.get("decision", ApprovalState.PENDING.value),
            decided_at=data.get("decided_at", ""),
            operator_id=data.get("operator_id"),
            reason=data.get("reason"),
            tool_output_ref=data.get("tool_output_ref"),
            execution_duration_ms=data.get("execution_duration_ms"),
            metadata=data.get("metadata", {}),
        )

    @property
    def is_approved(self) -> bool:
        """Check if decision is approved."""
        return self.decision == ApprovalState.APPROVED.value

    @property
    def is_rejected(self) -> bool:
        """Check if decision is rejected."""
        return self.decision == ApprovalState.REJECTED.value

    @property
    def is_terminal(self) -> bool:
        """Check if decision is terminal (not pending)."""
        return self.decision != ApprovalState.PENDING.value


# =============================================================================
# Approval Stream
# =============================================================================


@dataclass(frozen=True)
class ApprovalStream:
    """Stream of approval requests and decisions.

    This schema represents the complete approval lifecycle:
    - Pending requests awaiting operator decision
    - Completed decisions with outcomes
    - Linked tool executions (if approved)
    """

    schema_version: str = APPROVAL_SCHEMA_VERSION
    stream_id: str = ""
    session_id: str = ""
    pending_requests: tuple[ApprovalRequest, ...] = field(default_factory=tuple)
    decisions: tuple[ApprovalDecision, ...] = field(default_factory=tuple)
    started_at: str = ""
    ended_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "schema_version": self.schema_version,
            "stream_id": self.stream_id,
            "session_id": self.session_id,
            "pending_requests": [r.to_dict() for r in self.pending_requests],
            "decisions": [d.to_dict() for d in self.decisions],
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApprovalStream:
        """Deserialize from dict."""
        pending = [
            ApprovalRequest.from_dict(r) for r in data.get("pending_requests", [])
        ]
        decisions = [
            ApprovalDecision.from_dict(d) for d in data.get("decisions", [])
        ]
        return cls(
            schema_version=data.get("schema_version", APPROVAL_SCHEMA_VERSION),
            stream_id=data.get("stream_id", ""),
            session_id=data.get("session_id", ""),
            pending_requests=tuple(pending),
            decisions=tuple(decisions),
            started_at=data.get("started_at", ""),
            ended_at=data.get("ended_at"),
            metadata=data.get("metadata", {}),
        )

    @property
    def has_pending(self) -> bool:
        """Check if there are pending approvals."""
        return len(self.pending_requests) > 0

    @property
    def approval_count(self) -> int:
        """Count of total approval requests."""
        return len(self.pending_requests) + len(self.decisions)

    @property
    def approval_rate(self) -> float:
        """Calculate approval rate from decisions."""
        if not self.decisions:
            return 0.0
        approved = sum(1 for d in self.decisions if d.is_approved)
        return approved / len(self.decisions)


# =============================================================================
# Approval Factory
# =============================================================================


def new_request_id() -> str:
    """Generate a new request ID."""
    import secrets
    return secrets.token_hex(16)


def new_stream_id() -> str:
    """Generate a new stream ID."""
    import secrets
    return secrets.token_hex(16)


def create_approval_request(
    tool_id: str,
    approval_class: str,
    rationale: str,
    deadline_seconds: int = 300,
    operator_context: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ApprovalRequest:
    """Create a new approval request.

    Args:
        tool_id: Tool identifier requiring approval
        approval_class: Approval class (e.g., "operator_approval")
        rationale: Human-readable reason for the request
        deadline_seconds: Time limit for operator response
        operator_context: Context about the operator session
        metadata: Additional metadata

    Returns:
        New ApprovalRequest
    """
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return ApprovalRequest(
        schema_version=APPROVAL_SCHEMA_VERSION,
        request_id=new_request_id(),
        tool_id=tool_id,
        approval_class=approval_class,
        rationale=rationale,
        deadline_seconds=deadline_seconds,
        created_at=timestamp,
        operator_context=operator_context or {},
        metadata=metadata or {},
    )


def create_decision(
    request_id: str,
    decision: ApprovalState,
    operator_id: str | None = None,
    reason: str | None = None,
    tool_output_ref: str | None = None,
    execution_duration_ms: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> ApprovalDecision:
    """Create an approval decision.

    Args:
        request_id: Request this decision applies to
        decision: The decision made
        operator_id: Operator who made the decision
        reason: Optional reason for the decision
        tool_output_ref: Reference to tool output (if approved)
        execution_duration_ms: How long execution took (if approved)
        metadata: Additional metadata

    Returns:
        New ApprovalDecision
    """
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return ApprovalDecision(
        schema_version=APPROVAL_SCHEMA_VERSION,
        request_id=request_id,
        decision=decision.value,
        decided_at=timestamp,
        operator_id=operator_id,
        reason=reason,
        tool_output_ref=tool_output_ref,
        execution_duration_ms=execution_duration_ms,
        metadata=metadata or {},
    )


def create_stream(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> ApprovalStream:
    """Create a new approval stream.

    Args:
        session_id: Session this stream belongs to
        metadata: Additional metadata

    Returns:
        New ApprovalStream
    """
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return ApprovalStream(
        schema_version=APPROVAL_SCHEMA_VERSION,
        stream_id=new_stream_id(),
        session_id=session_id,
        pending_requests=(),
        decisions=(),
        started_at=timestamp,
        metadata=metadata or {},
    )


def add_request_to_stream(
    stream: ApprovalStream,
    request: ApprovalRequest,
) -> ApprovalStream:
    """Add a pending request to a stream.

    Args:
        stream: The stream to add to
        request: The request to add

    Returns:
        Updated ApprovalStream
    """
    return ApprovalStream(
        schema_version=stream.schema_version,
        stream_id=stream.stream_id,
        session_id=stream.session_id,
        pending_requests=stream.pending_requests + (request,),
        decisions=stream.decisions,
        started_at=stream.started_at,
        ended_at=stream.ended_at,
        metadata=stream.metadata,
    )


def add_decision_to_stream(
    stream: ApprovalStream,
    decision: ApprovalDecision,
) -> ApprovalStream:
    """Add a decision to a stream and remove from pending.

    Args:
        stream: The stream to add to
        decision: The decision to add

    Returns:
        Updated ApprovalStream
    """
    # Remove from pending
    pending = tuple(
        r for r in stream.pending_requests if r.request_id != decision.request_id
    )

    return ApprovalStream(
        schema_version=stream.schema_version,
        stream_id=stream.stream_id,
        session_id=stream.session_id,
        pending_requests=pending,
        decisions=stream.decisions + (decision,),
        started_at=stream.started_at,
        ended_at=stream.ended_at,
        metadata=stream.metadata,
    )


# =============================================================================
# Approval Check Helper
# =============================================================================


def requires_approval(approval_class: str) -> bool:
    """Check if approval class requires explicit approval.

    Args:
        approval_class: The approval class to check

    Returns:
        True if explicit approval is required
    """
    return approval_class not in (
        "none",
        "read_only",
        "",
    )


def check_approval_deadline(
    request: ApprovalRequest,
    current_time_seconds: float | None = None,
) -> tuple[bool, str]:
    """Check if an approval request has exceeded its deadline.

    Args:
        request: The approval request to check
        current_time_seconds: Current time in seconds (defaults to time.time())

    Returns:
        Tuple of (is_expired, time_remaining_or_expired)
    """
    if current_time_seconds is None:
        current_time_seconds = time.time()

    # Parse creation time
    from ..datetime_utils import parse_iso_to_utc

    created = parse_iso_to_utc(request.created_at)
    if created is None:
        return True, "invalid_created_at"


    created_seconds = created.timestamp()
    deadline = created_seconds + request.deadline_seconds

    if current_time_seconds > deadline:
        return True, "expired"

    remaining = deadline - current_time_seconds
    return False, str(int(remaining))


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Version
    "APPROVAL_SCHEMA_VERSION",
    # Enums
    "ApprovalState",
    # Core schemas
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalStream",
    # Factory functions
    "new_request_id",
    "new_stream_id",
    "create_approval_request",
    "create_decision",
    "create_stream",
    "add_request_to_stream",
    "add_decision_to_stream",
    # Helpers
    "requires_approval",
    "check_approval_deadline",
]
