"""Approval stream types and schemas.

This module contains the foundational types for approval streams:
- Schema version
- ApprovalState enum
- Core schemas (ApprovalRequest, ApprovalDecision, ApprovalStream)

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-APPROVAL-STREAM01
"""
from __future__ import annotations

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


__all__ = [
    "APPROVAL_SCHEMA_VERSION",
    "ApprovalState",
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalStream",
]
