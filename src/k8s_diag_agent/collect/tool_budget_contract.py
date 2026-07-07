"""Tool Budget Contract for k9b incident workbench.

This module provides first-class typed contracts for per-tool budgets,
extending the existing loop-level budget system with granular tool execution
controls.

Design principles:
- Every tool must declare its budget envelope before execution
- Budget validation is fail-closed (invalid budgets reject tool execution)
- No production tool may have unbounded LLM-visible output
- Budgets are immutable once declared (enables deterministic replay)

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-BUDGET-CONTRACT01
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# =============================================================================
# Schema version
# =============================================================================

TOOL_BUDGET_SCHEMA_VERSION = "1.0"

# =============================================================================
# Enums
# =============================================================================


class ToolApprovalClass(StrEnum):
    """Approval requirement class for tool execution.

    This defines whether a tool requires operator approval before execution.
    """

    #: No approval required - tool can execute immediately
    NONE = "none"

    #: Read-only tool - requires acknowledgment but not explicit approval
    READ_ONLY = "read_only"

    #: Tool that may have side effects - requires explicit operator approval
    OPERATOR_APPROVAL = "operator_approval"

    #: Tool is forbidden - will never execute regardless of other settings
    FORBIDDEN = "forbidden"


class ToolRedactionPolicy(StrEnum):
    """Redaction policy for tool output.

    Defines how sensitive data is handled in tool output before LLM visibility.
    """

    #: No redaction - output passes through unchanged
    NONE = "none"

    #: Redact credentials, tokens, and API keys only
    CREDENTIALS_ONLY = "credentials_only"

    #: Redact credentials + PII-like patterns (emails, IPs, etc.)
    CREDENTIALS_AND_PII = "credentials_and_pii"

    #: Aggressive redaction - credentials, PII, and kubeconfig paths
    STRICT = "strict"


# =============================================================================
# Tool Budget Contract
# =============================================================================


@dataclass(frozen=True)
class ToolBudget:
    """First-class budget contract for a single tool execution.

    Every tool must declare its budget envelope before execution.
    This enables:
    - Bounded LLM context injection
    - Spill-to-artifact behavior for large outputs
    - Provenance tracking for reduced outputs
    - Fail-closed validation for misconfigured tools

    Validation rules:
    - timeout_seconds > 0
    - stdout_bytes >= 0
    - stderr_bytes >= 0
    - llm_visible_bytes >= 0
    - artifact_spill_threshold_bytes >= llm_visible_bytes
    - memory_bytes is None or memory_bytes > 0
    - approval_class must be valid ToolApprovalClass value
    - redaction_policy must be valid ToolRedactionPolicy value
    - schema_name must be non-empty
    """

    # Schema version for forward compatibility
    schema_version: str = TOOL_BUDGET_SCHEMA_VERSION

    # Time budget
    timeout_seconds: int = 30

    # Memory budget (None = no limit)
    memory_bytes: int | None = None

    # Output capture limits
    stdout_bytes: int = 65536  # 64KB default
    stderr_bytes: int = 16384  # 16KB default

    # LLM visibility budget (hard cap on what enters model context)
    llm_visible_bytes: int = 8192  # 8KB default

    # Spill threshold - write to artifact instead of context if exceeded
    artifact_spill_threshold_bytes: int = 16384  # 16KB default

    # Redaction policy for output
    redaction_policy: str = ToolRedactionPolicy.CREDENTIALS_ONLY.value

    # Approval requirement
    approval_class: str = ToolApprovalClass.READ_ONLY.value

    # Provenance tracking
    provenance_required: bool = True

    # Expected output schema name (for validation)
    schema_name: str = "tool_output"

    # Tool-specific metadata (optional, for debugging)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, list[str]]:
        """Validate budget values.

        Returns:
            Tuple of (is_valid, list of validation error messages)
        """
        errors: list[str] = []

        # Schema version
        if not self.schema_version:
            errors.append("schema_version must be non-empty")

        # Timeout
        if self.timeout_seconds <= 0:
            errors.append(f"timeout_seconds must be > 0, got {self.timeout_seconds}")

        # Memory
        if self.memory_bytes is not None and self.memory_bytes <= 0:
            errors.append(f"memory_bytes must be None or > 0, got {self.memory_bytes}")

        # Output limits
        if self.stdout_bytes < 0:
            errors.append(f"stdout_bytes must be >= 0, got {self.stdout_bytes}")
        if self.stderr_bytes < 0:
            errors.append(f"stderr_bytes must be >= 0, got {self.stderr_bytes}")

        # LLM visibility
        if self.llm_visible_bytes < 0:
            errors.append(f"llm_visible_bytes must be >= 0, got {self.llm_visible_bytes}")

        # Spill threshold
        if self.artifact_spill_threshold_bytes < 0:
            errors.append(
                f"artifact_spill_threshold_bytes must be >= 0, got {self.artifact_spill_threshold_bytes}"
            )
        if self.artifact_spill_threshold_bytes < self.llm_visible_bytes:
            errors.append(
                f"artifact_spill_threshold_bytes ({self.artifact_spill_threshold_bytes}) "
                f"must be >= llm_visible_bytes ({self.llm_visible_bytes})"
            )

        # Redaction policy
        valid_redaction = [p.value for p in ToolRedactionPolicy]
        if self.redaction_policy not in valid_redaction:
            errors.append(
                f"redaction_policy must be one of {valid_redaction}, got '{self.redaction_policy}'"
            )

        # Approval class
        valid_approval = [c.value for c in ToolApprovalClass]
        if self.approval_class not in valid_approval:
            errors.append(
                f"approval_class must be one of {valid_approval}, got '{self.approval_class}'"
            )

        # Schema name
        if not self.schema_name:
            errors.append("schema_name must be non-empty")

        return len(errors) == 0, errors

    def is_budget_exceeded(
        self,
        *,
        elapsed_seconds: float,
        stdout_size: int,
        stderr_size: int,
        memory_used_bytes: int | None = None,
    ) -> tuple[bool, str | None]:
        """Check if execution has exceeded any budget limits.

        Args:
            elapsed_seconds: Time elapsed since execution start
            stdout_size: Current stdout size in bytes
            stderr_size: Current stderr size in bytes
            memory_used_bytes: Current memory usage (if known)

        Returns:
            Tuple of (exceeded, reason) - exceeded=True if any limit reached
        """
        if elapsed_seconds > self.timeout_seconds:
            return True, "timeout_exceeded"

        if stdout_size > self.stdout_bytes:
            return True, "stdout_exceeded"

        if stderr_size > self.stderr_bytes:
            return True, "stderr_exceeded"

        if memory_used_bytes is not None and self.memory_bytes is not None:
            if memory_used_bytes > self.memory_bytes:
                return True, "memory_exceeded"

        return False, None

    def should_spill_to_artifact(self, llm_visible_size: int) -> bool:
        """Check if output should spill to artifact instead of context.

        Args:
            llm_visible_size: Size of the LLM-visible projection in bytes

        Returns:
            True if spill-to-artifact behavior should trigger
        """
        return llm_visible_size > self.artifact_spill_threshold_bytes

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for artifact storage."""
        return {
            "schema_version": self.schema_version,
            "timeout_seconds": self.timeout_seconds,
            "memory_bytes": self.memory_bytes,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "llm_visible_bytes": self.llm_visible_bytes,
            "artifact_spill_threshold_bytes": self.artifact_spill_threshold_bytes,
            "redaction_policy": self.redaction_policy,
            "approval_class": self.approval_class,
            "provenance_required": self.provenance_required,
            "schema_name": self.schema_name,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolBudget:
        """Deserialize from dict."""
        return cls(
            schema_version=data.get("schema_version", TOOL_BUDGET_SCHEMA_VERSION),
            timeout_seconds=data.get("timeout_seconds", 30),
            memory_bytes=data.get("memory_bytes"),
            stdout_bytes=data.get("stdout_bytes", 65536),
            stderr_bytes=data.get("stderr_bytes", 16384),
            llm_visible_bytes=data.get("llm_visible_bytes", 8192),
            artifact_spill_threshold_bytes=data.get("artifact_spill_threshold_bytes", 16384),
            redaction_policy=data.get("redaction_policy", ToolRedactionPolicy.CREDENTIALS_ONLY.value),
            approval_class=data.get("approval_class", ToolApprovalClass.READ_ONLY.value),
            provenance_required=data.get("provenance_required", True),
            schema_name=data.get("schema_name", "tool_output"),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# Budget Validation Error
# =============================================================================


class ToolBudgetValidationError(ValueError):
    """Raised when tool budget validation fails."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Invalid tool budget: {', '.join(errors)}")


# =============================================================================
# Budget Enforcement Helper
# =============================================================================


@dataclass(frozen=True)
class ToolBudgetEnforcementResult:
    """Result of budget enforcement check."""

    allowed: bool
    reason: str | None
    spill_to_artifact: bool
    raw_artifact_id: str | None


def validate_and_enforce_budget(
    budget: ToolBudget,
    *,
    elapsed_seconds: float,
    stdout_size: int,
    stderr_size: int,
    llm_visible_size: int,
    memory_used_bytes: int | None = None,
) -> ToolBudgetEnforcementResult:
    """Validate budget and determine enforcement actions.

    Args:
        budget: The tool budget to enforce
        elapsed_seconds: Time elapsed since execution start
        stdout_size: Current stdout size in bytes
        stderr_size: Current stderr size in bytes
        llm_visible_size: Size of LLM-visible projection
        memory_used_bytes: Current memory usage (if known)

    Returns:
        ToolBudgetEnforcementResult with enforcement decision
    """
    # Validate budget first
    is_valid, errors = budget.validate()
    if not is_valid:
        return ToolBudgetEnforcementResult(
            allowed=False,
            reason=f"invalid_budget: {errors[0]}",
            spill_to_artifact=False,
            raw_artifact_id=None,
        )

    # Check if execution exceeded limits
    exceeded, reason = budget.is_budget_exceeded(
        elapsed_seconds=elapsed_seconds,
        stdout_size=stdout_size,
        stderr_size=stderr_size,
        memory_used_bytes=memory_used_bytes,
    )
    if exceeded:
        return ToolBudgetEnforcementResult(
            allowed=False,
            reason=f"budget_exceeded: {reason}",
            spill_to_artifact=False,
            raw_artifact_id=None,
        )

    # Check spill threshold
    spill = budget.should_spill_to_artifact(llm_visible_size)

    return ToolBudgetEnforcementResult(
        allowed=True,
        reason=None,
        spill_to_artifact=spill,
        raw_artifact_id=None,  # Will be set by caller when artifact is written
    )


# =============================================================================
# Default Budgets for Common Tool Types
# =============================================================================


#: Default budget for kubectl describe operations
KUBECTL_DESCRIBE_BUDGET = ToolBudget(
    timeout_seconds=30,
    stdout_bytes=131072,  # 128KB
    stderr_bytes=8192,    # 8KB
    llm_visible_bytes=16384,  # 16KB
    artifact_spill_threshold_bytes=32768,  # 32KB
    approval_class=ToolApprovalClass.READ_ONLY.value,
    schema_name="kubectl_describe_output",
)

#: Default budget for kubectl logs operations
KUBECTL_LOGS_BUDGET = ToolBudget(
    timeout_seconds=30,
    stdout_bytes=262144,  # 256KB
    stderr_bytes=4096,    # 4KB
    llm_visible_bytes=32768,  # 32KB
    artifact_spill_threshold_bytes=65536,  # 64KB
    approval_class=ToolApprovalClass.READ_ONLY.value,
    schema_name="kubectl_logs_output",
)

#: Default budget for kubectl get operations
KUBECTL_GET_BUDGET = ToolBudget(
    timeout_seconds=20,
    stdout_bytes=65536,  # 64KB
    stderr_bytes=4096,  # 4KB
    llm_visible_bytes=8192,  # 8KB
    artifact_spill_threshold_bytes=16384,  # 16KB
    approval_class=ToolApprovalClass.READ_ONLY.value,
    schema_name="kubectl_get_output",
)

#: Default budget for kubectl top operations
KUBECTL_TOP_BUDGET = ToolBudget(
    timeout_seconds=30,
    stdout_bytes=32768,  # 32KB
    stderr_bytes=4096,   # 4KB
    llm_visible_bytes=8192,  # 8KB
    artifact_spill_threshold_bytes=16384,  # 16KB
    approval_class=ToolApprovalClass.READ_ONLY.value,
    schema_name="kubectl_top_output",
)

#: Budget for events retrieval (usually small)
KUBECTL_EVENTS_BUDGET = ToolBudget(
    timeout_seconds=20,
    stdout_bytes=49152,  # 48KB
    stderr_bytes=2048,   # 2KB
    llm_visible_bytes=12288,  # 12KB
    artifact_spill_threshold_bytes=24576,  # 24KB
    approval_class=ToolApprovalClass.READ_ONLY.value,
    schema_name="kubectl_events_output",
)

#: Budget for forbidden operations (always rejected)
FORBIDDEN_TOOL_BUDGET = ToolBudget(
    timeout_seconds=0,
    memory_bytes=None,
    stdout_bytes=0,
    stderr_bytes=0,
    llm_visible_bytes=0,
    artifact_spill_threshold_bytes=0,
    approval_class=ToolApprovalClass.FORBIDDEN.value,
    schema_name="forbidden",
)


# =============================================================================
# Registry for Tool Budgets
# =============================================================================


@dataclass(frozen=True)
class ToolBudgetRegistry:
    """Registry mapping tool identifiers to their budgets."""

    budgets: dict[str, ToolBudget] = field(default_factory=dict)

    def register(self, tool_id: str, budget: ToolBudget) -> None:
        """Register a budget for a tool."""
        is_valid, errors = budget.validate()
        if not is_valid:
            raise ToolBudgetValidationError(errors)
        object.__setattr__(self, "budgets", {**self.budgets, tool_id: budget})

    def get(self, tool_id: str) -> ToolBudget | None:
        """Get budget for a tool, or None if not registered."""
        return self.budgets.get(tool_id)

    def get_or_raise(self, tool_id: str) -> ToolBudget:
        """Get budget for a tool, raising if not found."""
        budget = self.budgets.get(tool_id)
        if budget is None:
            raise KeyError(f"No budget registered for tool: {tool_id}")
        return budget


#: Global registry for tool budgets
_tool_budget_registry: ToolBudgetRegistry = ToolBudgetRegistry(
    budgets={
        "kubectl_describe": KUBECTL_DESCRIBE_BUDGET,
        "kubectl_logs": KUBECTL_LOGS_BUDGET,
        "kubectl_get": KUBECTL_GET_BUDGET,
        "kubectl_top": KUBECTL_TOP_BUDGET,
        "kubectl_events": KUBECTL_EVENTS_BUDGET,
    }
)


def get_tool_budget_registry() -> ToolBudgetRegistry:
    """Get the global tool budget registry."""
    return _tool_budget_registry


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Version
    "TOOL_BUDGET_SCHEMA_VERSION",
    # Enums
    "ToolApprovalClass",
    "ToolRedactionPolicy",
    # Core classes
    "ToolBudget",
    "ToolBudgetValidationError",
    "ToolBudgetEnforcementResult",
    "ToolBudgetRegistry",
    # Helpers
    "validate_and_enforce_budget",
    "get_tool_budget_registry",
    # Default budgets
    "KUBECTL_DESCRIBE_BUDGET",
    "KUBECTL_LOGS_BUDGET",
    "KUBECTL_GET_BUDGET",
    "KUBECTL_TOP_BUDGET",
    "KUBECTL_EVENTS_BUDGET",
    "FORBIDDEN_TOOL_BUDGET",
]
