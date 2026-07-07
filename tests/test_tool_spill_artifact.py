"""Unit tests for tool_spill_artifact module.

This module is a compatibility facade that re-exports all public symbols
from the spill artifact submodules.

Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-SPLIT01

Note: Full tests are in:
- test_tool_spill_artifact_types.py
- test_tool_spill_artifact_content.py
"""

# Import from the facade module to verify backward compatibility
from k8s_diag_agent.collect.tool_spill_artifact import (
    SPILL_SCHEMA_VERSION,
    RawToolOutputArtifact,
    SpillReason,
    ToolOutputContentType,
    ToolOutputSpillResult,
    compute_size_bytes,
    create_tool_output_result,
    detect_content_type,
    should_spill,
    spill_tool_output,
    write_raw_tool_artifact,
)
