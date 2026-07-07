"""Spill-to-artifact behavior for large tool outputs.

This module is a compatibility facade that re-exports all public symbols
from the spill artifact submodules. The actual implementation has been
split into focused modules:

- tool_spill_types: Schema types and enums
- tool_spill_content: Content detection and size computation
- tool_spill_writer: Artifact writing functionality
- tool_spill_pipeline: Main spill pipeline functions

For new code, import directly from submodules:
    from k8s_diag_agent.collect.tool_spill_types import ToolOutputSpillResult
    from k8s_diag_agent.collect.tool_spill_pipeline import spill_tool_output

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-SPILL-ARTIFACT01
"""

# Re-export all public symbols from submodules
from .tool_spill_content import (
    compute_size_bytes,
    detect_content_type,
    should_spill,
)
from .tool_spill_pipeline import (
    create_tool_output_result,
    spill_tool_output,
)
from .tool_spill_types import (
    SPILL_SCHEMA_VERSION,
    RawToolOutputArtifact,
    SpillReason,
    ToolOutputContentType,
    ToolOutputSpillResult,
)
from .tool_spill_writer import (
    write_raw_tool_artifact,
)

__all__ = [
    # Version
    "SPILL_SCHEMA_VERSION",
    # Enums
    "SpillReason",
    "ToolOutputContentType",
    # Core result schema
    "ToolOutputSpillResult",
    # Raw artifact schema
    "RawToolOutputArtifact",
    # Core functions
    "detect_content_type",
    "should_spill",
    "compute_size_bytes",
    "write_raw_tool_artifact",
    "spill_tool_output",
    # Helpers
    "create_tool_output_result",
]
