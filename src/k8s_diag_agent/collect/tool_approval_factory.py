"""Approval stream factory functions.

This module contains factory functions for creating approval entities:
- create_approval_request: Creates new approval requests
- create_decision: Creates approval decisions
- create_stream: Creates new approval streams
- add_request_to_stream: Adds requests to streams
- add_decision_to_stream: Adds decisions to streams
- requires_approval: Checks if approval class requires explicit approval

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-APPROVAL-STREAM01
"""
from __future__ import annotations

import time
from typing import Any

from .tool_approval_ids import new_request_id, new_stream_id
from .tool_approval_types import (
    APPROVAL_SCHEMA_VERSION,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalState,
    ApprovalStream,
)


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


__all__ = [
    "create_approval_request",
    "create_decision",
    "create_stream",
    "add_request_to_stream",
    "add_decision_to_stream",
    "requires_approval",
]
