"""Unit tests for tool_approval_factory and tool_approval_ids modules.

Tests factory functions and workflow for approval streams.
Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-SPLIT01
"""
from __future__ import annotations

from k8s_diag_agent.collect.tool_approval_factory import (
    add_decision_to_stream,
    add_request_to_stream,
    create_approval_request,
    create_decision,
    create_stream,
    requires_approval,
)
from k8s_diag_agent.collect.tool_approval_ids import new_request_id, new_stream_id
from k8s_diag_agent.collect.tool_approval_types import ApprovalState


class TestIdGeneration:
    def test_new_request_id_format(self) -> None:
        """Request ID should be hex string."""
        request_id = new_request_id()
        assert len(request_id) == 32  # 16 bytes = 32 hex chars
        assert all(c in "0123456789abcdef" for c in request_id)

    def test_new_stream_id_format(self) -> None:
        """Stream ID should be hex string."""
        stream_id = new_stream_id()
        assert len(stream_id) == 32  # 16 bytes = 32 hex chars
        assert all(c in "0123456789abcdef" for c in stream_id)

    def test_ids_are_unique(self) -> None:
        """Generated IDs should be unique."""
        ids = [new_request_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestApprovalRequest:
    def test_create_request(self) -> None:
        """Should create a valid request."""
        request = create_approval_request(
            tool_id="kubectl_delete",
            approval_class="operator_approval",
            rationale="Need to delete pod for recovery",
        )
        assert request.request_id is not None
        assert request.tool_id == "kubectl_delete"
        assert request.approval_class == "operator_approval"
        assert request.rationale == "Need to delete pod for recovery"
        assert request.deadline_seconds == 300
        assert request.created_at is not None


class TestApprovalDecision:
    def test_create_approved_decision(self) -> None:
        """Should create an approved decision."""
        decision = create_decision(
            request_id="test-request-123",
            decision=ApprovalState.APPROVED,
            operator_id="operator@example.com",
            reason="Safe to proceed",
        )
        assert decision.request_id == "test-request-123"
        assert decision.decision == ApprovalState.APPROVED.value
        assert decision.operator_id == "operator@example.com"
        assert decision.is_approved is True

    def test_create_rejected_decision(self) -> None:
        """Should create a rejected decision."""
        decision = create_decision(
            request_id="test-request-456",
            decision=ApprovalState.REJECTED,
            operator_id="operator@example.com",
            reason="Not safe",
        )
        assert decision.decision == ApprovalState.REJECTED.value
        assert decision.is_rejected is True

    def test_decision_with_output_ref(self) -> None:
        """Should include tool output reference when provided."""
        decision = create_decision(
            request_id="test-request-abc",
            decision=ApprovalState.APPROVED,
            tool_output_ref="artifact-id-123",
            execution_duration_ms=1500,
        )
        assert decision.tool_output_ref == "artifact-id-123"
        assert decision.execution_duration_ms == 1500


class TestApprovalStream:
    def test_create_stream(self) -> None:
        """Should create a valid stream."""
        stream = create_stream(session_id="session-123")
        assert stream.stream_id is not None
        assert stream.session_id == "session-123"
        assert len(stream.pending_requests) == 0
        assert len(stream.decisions) == 0

    def test_add_request_to_stream(self) -> None:
        """Should add request to stream."""
        stream = create_stream(session_id="session-456")
        request = create_approval_request(
            tool_id="kubectl_delete",
            approval_class="operator_approval",
            rationale="Test",
        )
        updated = add_request_to_stream(stream, request)
        assert len(updated.pending_requests) == 1
        assert updated.pending_requests[0].tool_id == "kubectl_delete"

    def test_add_decision_to_stream(self) -> None:
        """Should add decision and remove from pending."""
        stream = create_stream(session_id="session-789")
        request = create_approval_request(
            tool_id="kubectl_exec",
            approval_class="operator_approval",
            rationale="Test",
        )
        stream = add_request_to_stream(stream, request)
        decision = create_decision(
            request_id=request.request_id,
            decision=ApprovalState.APPROVED,
        )
        updated = add_decision_to_stream(stream, decision)
        assert len(updated.pending_requests) == 0
        assert len(updated.decisions) == 1


class TestRequiresApproval:
    def test_requires_approval_for_operator_approval(self) -> None:
        """operator_approval should require approval."""
        assert requires_approval("operator_approval") is True

    def test_no_approval_for_none(self) -> None:
        """none should not require approval."""
        assert requires_approval("none") is False

    def test_no_approval_for_read_only(self) -> None:
        """read_only should not require approval."""
        assert requires_approval("read_only") is False

    def test_no_approval_for_empty(self) -> None:
        """Empty string should not require approval."""
        assert requires_approval("") is False

    def test_requires_approval_for_forbidden(self) -> None:
        """forbidden should require approval (will be rejected)."""
        assert requires_approval("forbidden") is True


class TestApprovalIntegration:
    def test_full_approval_workflow(self) -> None:
        """Should support full approval workflow."""
        # Create stream
        stream = create_stream(session_id="incident-123")

        # Request approval
        request = create_approval_request(
            tool_id="kubectl_delete",
            approval_class="operator_approval",
            rationale="Delete pod for restart",
        )
        stream = add_request_to_stream(stream, request)

        assert stream.has_pending is True
        assert requires_approval(request.approval_class) is True

        # Operator approves
        decision = create_decision(
            request_id=request.request_id,
            decision=ApprovalState.APPROVED,
            operator_id="admin@example.com",
            reason="Approved for recovery",
        )
        stream = add_decision_to_stream(stream, decision)

        assert stream.has_pending is False
        assert stream.decisions[0].is_approved is True
