"""Unit tests for tool_approval_stream module.

This module is a compatibility facade that re-exports all public symbols
from the approval stream submodules.

Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-SPLIT01

Note: Full tests are in:
- test_tool_approval_stream_types.py
- test_tool_approval_stream_workflow.py
"""

# Import from the facade module to verify backward compatibility
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
