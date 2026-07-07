"""Approval Stream Protocol for k9b incident workbench.

This module is a compatibility facade that re-exports all public symbols
from the approval stream submodules. The actual implementation has been
split into focused modules:

- tool_approval_types: Schema types and enums
- tool_approval_ids: ID generation
- tool_approval_factory: Factory functions for creating approval entities
- tool_approval_deadline: Deadline checking

For new code, import directly from submodules:
    from k8s_diag_agent.collect.tool_approval_types import ApprovalStream
    from k8s_diag_agent.collect.tool_approval_factory import create_approval_request

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-APPROVAL-STREAM01
"""

# Re-export all public symbols from submodules
from .tool_approval_deadline import (
    check_approval_deadline,
)
from .tool_approval_factory import (
    add_decision_to_stream,
    add_request_to_stream,
    create_approval_request,
    create_decision,
    create_stream,
    requires_approval,
)
from .tool_approval_ids import (
    new_request_id,
    new_stream_id,
)
from .tool_approval_types import (
    APPROVAL_SCHEMA_VERSION,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalState,
    ApprovalStream,
)

__all__ = [
    # Version
    "APPROVAL_SCHEMA_VERSION",
    # Enums
    "ApprovalState",
    # Core schemas
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalStream",
    # ID generation
    "new_request_id",
    "new_stream_id",
    # Factory functions
    "create_approval_request",
    "create_decision",
    "create_stream",
    "add_request_to_stream",
    "add_decision_to_stream",
    # Helpers
    "requires_approval",
    "check_approval_deadline",
]
