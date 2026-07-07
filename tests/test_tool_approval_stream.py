"""Unit tests for tool_approval_stream module.

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-APPROVAL-STREAM01
"""
from __future__ import annotations

from k8s_diag_agent.collect.tool_approval_stream import (
    APPROVAL_SCHEMA_VERSION,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalState,
    add_decision_to_stream,
    add_request_to_stream,
    check_approval_deadline,
    create_approval_request,
    create_decision,
    create_stream,
    new_request_id,
    new_stream_id,
    requires_approval,
)

# =============================================================================
# Schema Version Tests
# =============================================================================


class TestSchemaVersion:
    def test_schema_version_is_defined(self) -> None:
        """Schema version should be a non-empty string."""
        assert APPROVAL_SCHEMA_VERSION == "1.0"


# =============================================================================
# ID Generation Tests
# =============================================================================


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


# =============================================================================
# Approval Request Tests
# =============================================================================


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

    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce serializable output."""
        request = create_approval_request(
            tool_id="kubectl_exec",
            approval_class="operator_approval",
            rationale="Exec into pod for debugging",
            deadline_seconds=600,
        )
        d = request.to_dict()
        assert isinstance(d, dict)
        assert d["tool_id"] == "kubectl_exec"

    def test_from_dict_roundtrip(self) -> None:
        """from_dict should reconstruct the same request."""
        original = create_approval_request(
            tool_id="kubectl_scale",
            approval_class="operator_approval",
            rationale="Scale deployment",
        )
        data = original.to_dict()
        reconstructed = ApprovalRequest.from_dict(data)
        assert reconstructed.tool_id == original.tool_id
        assert reconstructed.approval_class == original.approval_class


# =============================================================================
# Approval Decision Tests
# =============================================================================


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
        assert decision.is_terminal is True

    def test_create_rejected_decision(self) -> None:
        """Should create a rejected decision."""
        decision = create_decision(
            request_id="test-request-456",
            decision=ApprovalState.REJECTED,
            operator_id="operator@example.com",
            reason="Not safe - needs more investigation",
        )

        assert decision.decision == ApprovalState.REJECTED.value
        assert decision.is_rejected is True
        assert decision.is_terminal is True

    def test_create_timeout_decision(self) -> None:
        """Should create a timeout decision."""
        decision = create_decision(
            request_id="test-request-789",
            decision=ApprovalState.TIMEOUT,
        )

        assert decision.decision == ApprovalState.TIMEOUT.value
        assert decision.is_terminal is True

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

    def test_is_pending(self) -> None:
        """Should correctly identify pending state."""
        decision = ApprovalDecision(request_id="test", decision=ApprovalState.PENDING.value)
        assert decision.is_terminal is False

    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce serializable output."""
        decision = create_decision(
            request_id="test-request-def",
            decision=ApprovalState.APPROVED,
            operator_id="op@example.com",
        )
        d = decision.to_dict()
        assert isinstance(d, dict)
        assert d["decision"] == ApprovalState.APPROVED.value


# =============================================================================
# Approval Stream Tests
# =============================================================================


class TestApprovalStream:
    def test_create_stream(self) -> None:
        """Should create a valid stream."""
        stream = create_stream(session_id="session-123")

        assert stream.stream_id is not None
        assert stream.session_id == "session-123"
        assert len(stream.pending_requests) == 0
        assert len(stream.decisions) == 0
        assert stream.has_pending is False

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
        assert updated.has_pending is True

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
        assert updated.has_pending is False

    def test_approval_count(self) -> None:
        """Should count approvals correctly."""
        stream = create_stream(session_id="session-count")

        # Add 2 requests
        for i in range(2):
            request = create_approval_request(
                tool_id=f"tool-{i}",
                approval_class="operator_approval",
                rationale="Test",
            )
            stream = add_request_to_stream(stream, request)

        # Add 1 decision
        decision = create_decision(
            request_id=stream.pending_requests[0].request_id,
            decision=ApprovalState.APPROVED,
        )
        stream = add_decision_to_stream(stream, decision)

        assert stream.approval_count == 2  # 1 pending + 1 decision

    def test_approval_rate(self) -> None:
        """Should calculate approval rate correctly."""
        stream = create_stream(session_id="session-rate")

        # Add 2 decisions - 1 approved, 1 rejected
        for decision_state in [ApprovalState.APPROVED, ApprovalState.REJECTED]:
            request = create_approval_request(
                tool_id="tool",
                approval_class="operator_approval",
                rationale="Test",
            )
            stream = add_request_to_stream(stream, request)
            decision = create_decision(
                request_id=request.request_id,
                decision=decision_state,
            )
            stream = add_decision_to_stream(stream, decision)

        assert stream.approval_rate == 0.5

    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce serializable output."""
        stream = create_stream(session_id="session-roundtrip")
        request = create_approval_request(
            tool_id="kubectl_logs",
            approval_class="operator_approval",
            rationale="Fetch logs",
        )
        stream = add_request_to_stream(stream, request)

        d = stream.to_dict()
        assert isinstance(d, dict)
        assert d["session_id"] == "session-roundtrip"
        assert len(d["pending_requests"]) == 1


# =============================================================================
# Approval Check Tests
# =============================================================================


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


class TestCheckApprovalDeadline:
    def test_non_expired_request(self) -> None:
        """Should return not expired for recent request."""
        request = create_approval_request(
            tool_id="test",
            approval_class="operator_approval",
            rationale="Test",
            deadline_seconds=300,
        )

        is_expired, status = check_approval_deadline(request)
        assert is_expired is False
        assert status.isdigit()  # Remaining seconds

    def test_expired_request(self) -> None:
        """Should return expired for old request."""
        request = ApprovalRequest(
            request_id="old-request",
            tool_id="test",
            approval_class="operator_approval",
            rationale="Test",
            deadline_seconds=1,  # 1 second deadline
            created_at="2020-01-01T00:00:00Z",  # Very old
        )

        is_expired, status = check_approval_deadline(request)
        assert is_expired is True


# =============================================================================
# Integration Tests
# =============================================================================


class TestApprovalIntegration:
    def test_full_approval_workflow(self) -> None:
        """Should support full approval workflow."""
        # Create stream
        stream = create_stream(session_id="incident-123")

        # Request approval for destructive action
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
            tool_output_ref="pod-deleted-artifact-id",
        )
        stream = add_decision_to_stream(stream, decision)

        assert stream.has_pending is False
        assert stream.decisions[0].is_approved is True
        assert stream.decisions[0].tool_output_ref == "pod-deleted-artifact-id"

    def test_rejected_approval_workflow(self) -> None:
        """Should support rejected approval workflow."""
        stream = create_stream(session_id="incident-456")

        request = create_approval_request(
            tool_id="kubectl_delete",
            approval_class="operator_approval",
            rationale="Delete namespace",
        )
        stream = add_request_to_stream(stream, request)

        # Operator rejects
        decision = create_decision(
            request_id=request.request_id,
            decision=ApprovalState.REJECTED,
            operator_id="admin@example.com",
            reason="Too destructive - use scale instead",
        )
        stream = add_decision_to_stream(stream, decision)

        assert stream.has_pending is False
        assert stream.decisions[0].is_rejected is True
        assert stream.decisions[0].reason == "Too destructive - use scale instead"
