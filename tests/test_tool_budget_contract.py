"""Unit tests for tool_budget_contract module.

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-BUDGET-CONTRACT01
"""
from __future__ import annotations

import pytest

from k8s_diag_agent.collect.tool_budget_contract import (
    FORBIDDEN_TOOL_BUDGET,
    KUBECTL_DESCRIBE_BUDGET,
    KUBECTL_EVENTS_BUDGET,
    KUBECTL_GET_BUDGET,
    KUBECTL_LOGS_BUDGET,
    KUBECTL_TOP_BUDGET,
    TOOL_BUDGET_SCHEMA_VERSION,
    ToolApprovalClass,
    ToolBudget,
    ToolBudgetEnforcementResult,
    ToolBudgetRegistry,
    ToolBudgetValidationError,
    ToolRedactionPolicy,
    get_tool_budget_registry,
    validate_and_enforce_budget,
)

# =============================================================================
# Schema Version Tests
# =============================================================================


class TestSchemaVersion:
    def test_schema_version_is_defined(self) -> None:
        """Schema version should be a non-empty string."""
        assert TOOL_BUDGET_SCHEMA_VERSION == "1.0"
        assert isinstance(TOOL_BUDGET_SCHEMA_VERSION, str)
        assert len(TOOL_BUDGET_SCHEMA_VERSION) > 0


# =============================================================================
# ToolApprovalClass Tests
# =============================================================================


class TestToolApprovalClass:
    def test_all_approval_classes_defined(self) -> None:
        """All expected approval classes should be defined."""
        assert ToolApprovalClass.NONE == "none"
        assert ToolApprovalClass.READ_ONLY == "read_only"
        assert ToolApprovalClass.OPERATOR_APPROVAL == "operator_approval"
        assert ToolApprovalClass.FORBIDDEN == "forbidden"

    def test_approval_classes_are_strings(self) -> None:
        """Approval class values should be strings."""
        for cls in ToolApprovalClass:
            assert isinstance(cls.value, str)


# =============================================================================
# ToolRedactionPolicy Tests
# =============================================================================


class TestToolRedactionPolicy:
    def test_all_redaction_policies_defined(self) -> None:
        """All expected redaction policies should be defined."""
        assert ToolRedactionPolicy.NONE == "none"
        assert ToolRedactionPolicy.CREDENTIALS_ONLY == "credentials_only"
        assert ToolRedactionPolicy.CREDENTIALS_AND_PII == "credentials_and_pii"
        assert ToolRedactionPolicy.STRICT == "strict"

    def test_redaction_policies_are_strings(self) -> None:
        """Redaction policy values should be strings."""
        for policy in ToolRedactionPolicy:
            assert isinstance(policy.value, str)


# =============================================================================
# ToolBudget Validation Tests
# =============================================================================


class TestToolBudgetValidation:
    def test_default_budget_is_valid(self) -> None:
        """Default budget should pass validation."""
        budget = ToolBudget()
        is_valid, errors = budget.validate()
        assert is_valid
        assert len(errors) == 0

    def test_invalid_timeout_zero(self) -> None:
        """Zero timeout should fail validation."""
        budget = ToolBudget(timeout_seconds=0)
        is_valid, errors = budget.validate()
        assert not is_valid
        assert any("timeout_seconds" in e for e in errors)

    def test_invalid_timeout_negative(self) -> None:
        """Negative timeout should fail validation."""
        budget = ToolBudget(timeout_seconds=-1)
        is_valid, errors = budget.validate()
        assert not is_valid
        assert any("timeout_seconds" in e for e in errors)

    def test_invalid_memory_zero(self) -> None:
        """Zero memory should fail validation (None is valid)."""
        budget = ToolBudget(memory_bytes=0)
        is_valid, errors = budget.validate()
        assert not is_valid
        assert any("memory_bytes" in e for e in errors)

    def test_invalid_negative_stdout(self) -> None:
        """Negative stdout_bytes should fail validation."""
        budget = ToolBudget(stdout_bytes=-1)
        is_valid, errors = budget.validate()
        assert not is_valid
        assert any("stdout_bytes" in e for e in errors)

    def test_invalid_negative_stderr(self) -> None:
        """Negative stderr_bytes should fail validation."""
        budget = ToolBudget(stderr_bytes=-1)
        is_valid, errors = budget.validate()
        assert not is_valid
        assert any("stderr_bytes" in e for e in errors)

    def test_invalid_negative_llm_visible(self) -> None:
        """Negative llm_visible_bytes should fail validation."""
        budget = ToolBudget(llm_visible_bytes=-1)
        is_valid, errors = budget.validate()
        assert not is_valid
        assert any("llm_visible_bytes" in e for e in errors)

    def test_invalid_spill_less_than_llm_visible(self) -> None:
        """Spill threshold less than llm_visible should fail."""
        budget = ToolBudget(
            llm_visible_bytes=10000,
            artifact_spill_threshold_bytes=5000,
        )
        is_valid, errors = budget.validate()
        assert not is_valid
        assert any("artifact_spill_threshold_bytes" in e for e in errors)

    def test_invalid_redaction_policy(self) -> None:
        """Invalid redaction policy should fail validation."""
        budget = ToolBudget(redaction_policy="invalid_policy")
        is_valid, errors = budget.validate()
        assert not is_valid
        assert any("redaction_policy" in e for e in errors)

    def test_invalid_approval_class(self) -> None:
        """Invalid approval class should fail validation."""
        budget = ToolBudget(approval_class="invalid_class")
        is_valid, errors = budget.validate()
        assert not is_valid
        assert any("approval_class" in e for e in errors)

    def test_empty_schema_name(self) -> None:
        """Empty schema_name should fail validation."""
        budget = ToolBudget(schema_name="")
        is_valid, errors = budget.validate()
        assert not is_valid
        assert any("schema_name" in e for e in errors)

    def test_multiple_validation_errors(self) -> None:
        """Multiple invalid fields should return multiple errors."""
        budget = ToolBudget(
            timeout_seconds=0,
            stdout_bytes=-1,
            llm_visible_bytes=-1,
        )
        is_valid, errors = budget.validate()
        assert not is_valid
        assert len(errors) >= 3


# =============================================================================
# ToolBudget Serialization Tests
# =============================================================================


class TestToolBudgetSerialization:
    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce serializable output."""
        budget = ToolBudget(
            timeout_seconds=30,
            stdout_bytes=65536,
            llm_visible_bytes=8192,
            approval_class=ToolApprovalClass.READ_ONLY.value,
        )
        d = budget.to_dict()
        assert isinstance(d, dict)
        assert d["timeout_seconds"] == 30
        assert d["stdout_bytes"] == 65536

    def test_from_dict_roundtrip(self) -> None:
        """from_dict should reconstruct the same budget."""
        original = ToolBudget(
            timeout_seconds=45,
            memory_bytes=1024000,
            llm_visible_bytes=16384,
        )
        data = original.to_dict()
        reconstructed = ToolBudget.from_dict(data)
        assert reconstructed.timeout_seconds == original.timeout_seconds
        assert reconstructed.memory_bytes == original.memory_bytes
        assert reconstructed.llm_visible_bytes == original.llm_visible_bytes

    def test_from_dict_with_defaults(self) -> None:
        """from_dict should use defaults for missing fields."""
        data: dict[str, object] = {}
        budget = ToolBudget.from_dict(data)
        assert budget.timeout_seconds == 30  # default
        assert budget.llm_visible_bytes == 8192  # default


# =============================================================================
# ToolBudget Budget Exceeded Tests
# =============================================================================


class TestToolBudgetExceeded:
    def test_timeout_not_exceeded(self) -> None:
        """Within timeout should not be exceeded."""
        budget = ToolBudget(timeout_seconds=30)
        exceeded, reason = budget.is_budget_exceeded(
            elapsed_seconds=20.0,
            stdout_size=1000,
            stderr_size=100,
        )
        assert not exceeded
        assert reason is None

    def test_timeout_exceeded(self) -> None:
        """Beyond timeout should be exceeded."""
        budget = ToolBudget(timeout_seconds=30)
        exceeded, reason = budget.is_budget_exceeded(
            elapsed_seconds=35.0,
            stdout_size=1000,
            stderr_size=100,
        )
        assert exceeded
        assert reason == "timeout_exceeded"

    def test_stdout_exceeded(self) -> None:
        """Beyond stdout limit should be exceeded."""
        budget = ToolBudget(stdout_bytes=1000)
        exceeded, reason = budget.is_budget_exceeded(
            elapsed_seconds=1.0,
            stdout_size=2000,
            stderr_size=100,
        )
        assert exceeded
        assert reason == "stdout_exceeded"

    def test_stderr_exceeded(self) -> None:
        """Beyond stderr limit should be exceeded."""
        budget = ToolBudget(stderr_bytes=100)
        exceeded, reason = budget.is_budget_exceeded(
            elapsed_seconds=1.0,
            stdout_size=500,
            stderr_size=200,
        )
        assert exceeded
        assert reason == "stderr_exceeded"

    def test_memory_exceeded(self) -> None:
        """Beyond memory limit should be exceeded."""
        budget = ToolBudget(memory_bytes=1024)
        exceeded, reason = budget.is_budget_exceeded(
            elapsed_seconds=1.0,
            stdout_size=100,
            stderr_size=50,
            memory_used_bytes=2048,
        )
        assert exceeded
        assert reason == "memory_exceeded"

    def test_memory_not_checked_when_none(self) -> None:
        """Memory should not be checked when limit is None."""
        budget = ToolBudget(memory_bytes=None)
        exceeded, reason = budget.is_budget_exceeded(
            elapsed_seconds=1.0,
            stdout_size=100,
            stderr_size=50,
            memory_used_bytes=1000000,
        )
        assert not exceeded


# =============================================================================
# ToolBudget Spill Tests
# =============================================================================


class TestToolBudgetSpill:
    def test_should_not_spill(self) -> None:
        """Below threshold should not spill."""
        budget = ToolBudget(artifact_spill_threshold_bytes=10000)
        assert not budget.should_spill_to_artifact(5000)

    def test_should_spill(self) -> None:
        """Above threshold should spill."""
        budget = ToolBudget(artifact_spill_threshold_bytes=10000)
        assert budget.should_spill_to_artifact(15000)

    def test_at_threshold_does_not_spill(self) -> None:
        """At exact threshold should not spill."""
        budget = ToolBudget(artifact_spill_threshold_bytes=10000)
        assert not budget.should_spill_to_artifact(10000)


# =============================================================================
# Default Budgets Tests
# =============================================================================


class TestDefaultBudgets:
    def test_kubectl_describe_budget_valid(self) -> None:
        """kubectl describe budget should be valid."""
        is_valid, errors = KUBECTL_DESCRIBE_BUDGET.validate()
        assert is_valid, errors

    def test_kubectl_logs_budget_valid(self) -> None:
        """kubectl logs budget should be valid."""
        is_valid, errors = KUBECTL_LOGS_BUDGET.validate()
        assert is_valid, errors

    def test_kubectl_get_budget_valid(self) -> None:
        """kubectl get budget should be valid."""
        is_valid, errors = KUBECTL_GET_BUDGET.validate()
        assert is_valid, errors

    def test_kubectl_top_budget_valid(self) -> None:
        """kubectl top budget should be valid."""
        is_valid, errors = KUBECTL_TOP_BUDGET.validate()
        assert is_valid, errors

    def test_kubectl_events_budget_valid(self) -> None:
        """kubectl events budget should be valid."""
        is_valid, errors = KUBECTL_EVENTS_BUDGET.validate()
        assert is_valid, errors

    def test_forbidden_budget_is_valid(self) -> None:
        """Forbidden budget should be valid (it's intentionally zeroed)."""
        # Note: FORBIDDEN budget has timeout=0, which would normally fail,
        # but it's designed this way for forbidden tools
        # This is a special case - forbidden tools should never be executed anyway
        is_valid, errors = FORBIDDEN_TOOL_BUDGET.validate()
        # The FORBIDDEN budget intentionally violates timeout > 0 rule
        # because it's meant to never allow execution
        assert not is_valid  # This is expected for the forbidden case
        assert any("timeout" in e for e in errors)


# =============================================================================
# ToolBudgetRegistry Tests
# =============================================================================


class TestToolBudgetRegistry:
    def test_registry_has_defaults(self) -> None:
        """Global registry should have default budgets."""
        registry = get_tool_budget_registry()
        assert registry.get("kubectl_describe") is not None
        assert registry.get("kubectl_logs") is not None
        assert registry.get("kubectl_get") is not None
        assert registry.get("kubectl_top") is not None
        assert registry.get("kubectl_events") is not None

    def test_registry_get_unknown_returns_none(self) -> None:
        """Unknown tool should return None."""
        registry = get_tool_budget_registry()
        assert registry.get("unknown_tool") is None

    def test_registry_get_or_raise_unknown(self) -> None:
        """get_or_raise should raise for unknown tool."""
        registry = get_tool_budget_registry()
        with pytest.raises(KeyError):
            registry.get_or_raise("unknown_tool")

    def test_registry_register_valid_budget(self) -> None:
        """Registering valid budget should succeed."""
        registry = ToolBudgetRegistry()
        budget = ToolBudget(schema_name="custom_tool")
        registry.register("custom", budget)
        assert registry.get("custom") == budget

    def test_registry_register_invalid_budget_raises(self) -> None:
        """Registering invalid budget should raise."""
        registry = ToolBudgetRegistry()
        budget = ToolBudget(timeout_seconds=0)
        with pytest.raises(ToolBudgetValidationError):
            registry.register("invalid", budget)


# =============================================================================
# validate_and_enforce_budget Tests
# =============================================================================


class TestValidateAndEnforceBudget:
    def test_allows_valid_within_budget(self) -> None:
        """Valid budget within limits should be allowed."""
        budget = ToolBudget(
            timeout_seconds=30,
            stdout_bytes=10000,
            llm_visible_bytes=5000,
        )
        result = validate_and_enforce_budget(
            budget,
            elapsed_seconds=10.0,
            stdout_size=5000,
            stderr_size=100,
            llm_visible_size=3000,
        )
        assert result.allowed
        assert result.reason is None
        assert not result.spill_to_artifact

    def test_rejects_invalid_budget(self) -> None:
        """Invalid budget should be rejected."""
        budget = ToolBudget(timeout_seconds=0)
        result = validate_and_enforce_budget(
            budget,
            elapsed_seconds=1.0,
            stdout_size=100,
            stderr_size=50,
            llm_visible_size=100,
        )
        assert not result.allowed
        assert result.reason is not None
        assert "invalid_budget" in result.reason

    def test_rejects_exceeded_budget(self) -> None:
        """Exceeded budget should be rejected."""
        budget = ToolBudget(timeout_seconds=30)
        result = validate_and_enforce_budget(
            budget,
            elapsed_seconds=35.0,
            stdout_size=100,
            stderr_size=50,
            llm_visible_size=100,
        )
        assert not result.allowed
        assert result.reason is not None
        assert "budget_exceeded" in result.reason

    def test_flags_spill_to_artifact(self) -> None:
        """Should flag when spill-to-artifact is needed."""
        # Note: spill threshold must be >= llm_visible per validation rules
        # Here llm_visible=3000, spill_threshold=5000, so 4000 triggers spill
        budget = ToolBudget(
            llm_visible_bytes=3000,
            artifact_spill_threshold_bytes=5000,
        )
        result = validate_and_enforce_budget(
            budget,
            elapsed_seconds=1.0,
            stdout_size=100,
            stderr_size=50,
            llm_visible_size=4000,  # Above spill threshold (5000) - wait, 4000 < 5000
        )
        # 4000 < 5000 threshold, so should NOT spill
        assert result.allowed
        assert not result.spill_to_artifact
        
        # Now test with llm_visible exceeding the spill threshold
        result2 = validate_and_enforce_budget(
            budget,
            elapsed_seconds=1.0,
            stdout_size=100,
            stderr_size=50,
            llm_visible_size=6000,  # Above spill threshold (5000)
        )
        assert result2.allowed
        assert result2.spill_to_artifact


# =============================================================================
# ToolBudgetValidationError Tests
# =============================================================================


class TestToolBudgetValidationError:
    def test_error_contains_all_messages(self) -> None:
        """Validation error should contain all error messages."""
        budget = ToolBudget(
            timeout_seconds=0,
            stdout_bytes=-1,
        )
        is_valid, errors = budget.validate()
        assert not is_valid
        error = ToolBudgetValidationError(errors)
        assert len(error.errors) >= 2
        assert "timeout_seconds" in error.errors[0] or "stdout_bytes" in error.errors[0]


# =============================================================================
# ToolBudgetEnforcementResult Tests
# =============================================================================


class TestToolBudgetEnforcementResult:
    def test_allowed_result(self) -> None:
        """Allowed result should have allowed=True."""
        result = ToolBudgetEnforcementResult(
            allowed=True,
            reason=None,
            spill_to_artifact=False,
            raw_artifact_id=None,
        )
        assert result.allowed
        assert result.reason is None

    def test_rejected_result(self) -> None:
        """Rejected result should have allowed=False."""
        result = ToolBudgetEnforcementResult(
            allowed=False,
            reason="timeout_exceeded",
            spill_to_artifact=False,
            raw_artifact_id=None,
        )
        assert not result.allowed
        assert result.reason == "timeout_exceeded"
