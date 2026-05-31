"""Prompt boundary markers for LLM injection risk reduction.

This module defines the canonical boundary markers used across all prompt builders
to clearly separate trusted instructions from untrusted cluster/artifact data.

Boundary Convention:
- System/instruction section: Always first, contains only trusted instructions
- Untrusted data section: Wrapped with BEGIN_UNTRUSTED_CLUSTER_DATA / END_UNTRUSTED_CLUSTER_DATA
- JSON payload fences: Use JSON formatting with explicit field boundaries
- Output schema section: Wrapped with BEGIN_OUTPUT_SCHEMA / END_OUTPUT_SCHEMA
- Rule: Data inside untrusted sections must NEVER override instructions
"""

from __future__ import annotations

# === BOUNDARY MARKERS ===
# Markers to delineate untrusted cluster/artifact data from trusted instructions.
# All cluster data, artifact data, and external inputs must be inside these markers.

BEGIN_UNTRUSTED_CLUSTER_DATA = "===== BEGIN_UNTRUSTED_CLUSTER_DATA ====="
END_UNTRUSTED_CLUSTER_DATA = "===== END_UNTRUSTED_CLUSTER_DATA ====="

# Markers to delineate the expected output schema from data and instructions.
# Schema requirements should remain outside untrusted data boundaries.

BEGIN_OUTPUT_SCHEMA = "===== BEGIN_OUTPUT_SCHEMA ====="
END_OUTPUT_SCHEMA = "===== END_OUTPUT_SCHEMA ====="


def wrap_with_untrusted_markers(content: str) -> str:
    """Wrap content with untrusted data boundary markers."""
    return f"\n{BEGIN_UNTRUSTED_CLUSTER_DATA}\n{content}\n{END_UNTRUSTED_CLUSTER_DATA}\n"


def wrap_with_schema_markers(content: str) -> str:
    """Wrap content with output schema boundary markers."""
    return f"\n{BEGIN_OUTPUT_SCHEMA}\n{content}\n{END_OUTPUT_SCHEMA}\n"
