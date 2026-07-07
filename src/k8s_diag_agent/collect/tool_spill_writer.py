"""Spill artifact writer.

This module contains artifact writing functionality:
- write_raw_tool_artifact: Writes raw tool output to immutable artifact

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-SPILL-ARTIFACT01
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .tool_spill_types import RawToolOutputArtifact, ToolOutputContentType

# =============================================================================
# Artifact Writing
# =============================================================================


def write_raw_tool_artifact(
    artifact_dir: Path,
    source_tool: str,
    raw_content: str,
    content_type: ToolOutputContentType,
    budget_snapshot: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[RawToolOutputArtifact, Path]:
    """Write raw tool output to immutable artifact.

    Args:
        artifact_dir: Directory to write artifact
        source_tool: Tool identifier (e.g., "kubectl_get")
        raw_content: Raw output content
        content_type: Detected content type
        budget_snapshot: Optional budget state at capture time
        metadata: Optional additional metadata

    Returns:
        Tuple of (artifact, path)
    """
    # Import here to avoid circular dependency
    from ..identity.artifact import new_artifact_id, write_append_only_json_artifact

    artifact_id = new_artifact_id()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    artifact = RawToolOutputArtifact(
        schema_version="1.0",
        artifact_id=artifact_id,
        source_tool=source_tool,
        content_type=content_type.value,
        raw_content=raw_content,
        size_bytes=len(raw_content.encode("utf-8")),
        timestamp=timestamp,
        budget_snapshot=budget_snapshot,
        metadata=metadata or {},
    )

    # Generate artifact path
    artifact_path = artifact_dir / f"tool-raw-{artifact_id}.json"

    # Write with immutability enforcement
    write_append_only_json_artifact(artifact_path, artifact.to_dict())

    return artifact, artifact_path


__all__ = [
    "write_raw_tool_artifact",
]
