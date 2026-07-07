"""Unit tests for tool_approval_types module.

Tests schema types and enums for approval streams.
Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-SPLIT01
"""
from __future__ import annotations

from k8s_diag_agent.collect.tool_approval_types import (
    APPROVAL_SCHEMA_VERSION,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalState,
    ApprovalStream,
)


class TestSchemaVersion:
    def test_schema_version_is_defined(self) -> None:
        """Schema version should be a non-empty string."""
        assert APPROVAL_SCHEMA_VERSION == "1.0"


class TestApprovalRequest:
    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce serializable output."""
        request = ApprovalRequest(
            request_id="test-id",
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
        original = ApprovalRequest(
            request_id="test-id",
            tool_id="kubectl_scale",
            approval_class="operator_approval",
            rationale="Scale deployment",
        )
        data = original.to_dict()
        reconstructed = ApprovalRequest.from_dict(data)
        assert reconstructed.tool_id == original.tool_id
        assert reconstructed.approval_class == original.approval_class


class TestApprovalDecision:
    def test_is_pending(self) -> None:
        """Should correctly identify pending state."""
        decision = ApprovalDecision(request_id="test", decision=ApprovalState.PENDING.value)
        assert decision.is_terminal is False

    def test_is_approved_property(self) -> None:
        """is_approved should return True for approved decisions."""
        decision = ApprovalDecision(request_id="test", decision=ApprovalState.APPROVED.value)
        assert decision.is_approved is True
        assert decision.is_terminal is True

    def test_is_rejected_property(self) -> None:
        """is_rejected should return True for rejected decisions."""
        decision = ApprovalDecision(request_id="test", decision=ApprovalState.REJECTED.value)
        assert decision.is_rejected is True
        assert decision.is_terminal is True

    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce serializable output."""
        decision = ApprovalDecision(
            request_id="test-id",
            decision=ApprovalState.APPROVED.value,
            operator_id="op@example.com",
        )
        d = decision.to_dict()
        assert isinstance(d, dict)
        assert d["decision"] == ApprovalState.APPROVED.value


class TestApprovalStream:
    def test_empty_stream_properties(self) -> None:
        """Empty stream should have correct properties."""
        stream = ApprovalStream(
            stream_id="stream-1",
            session_id="session-1",
        )
        assert stream.has_pending is False
        assert stream.approval_count == 0
        assert stream.approval_rate == 0.0

    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce serializable output."""
        stream = ApprovalStream(
            stream_id="stream-1",
            session_id="session-roundtrip",
            pending_requests=(),
            decisions=(),
        )
        d = stream.to_dict()
        assert isinstance(d, dict)
        assert d["session_id"] == "session-roundtrip"
        assert len(d["pending_requests"]) == 0

    def test_approval_rate_calculation(self) -> None:
        """Should calculate approval rate correctly."""
        decisions = (
            ApprovalDecision(request_id="1", decision=ApprovalState.APPROVED.value),
            ApprovalDecision(request_id="2", decision=ApprovalState.REJECTED.value),
        )
        stream = ApprovalStream(
            stream_id="stream-1",
            session_id="session-rate",
            decisions=decisions,
        )
        assert stream.approval_rate == 0.5
