"""Content index projections.

This module provides privacy-preserving projections from source content.
Delegates to submodules for implementation details.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

# Re-export from submodules for backward compatibility
from .projection_builder import ProjectionBuilder, ProjectionConfig
from .projection_contract import (
    ALLOWED_PROJECTION_FIELDS,
    PROJECTION_API_DETAIL,
    PROJECTION_API_SUMMARY,
)
from .projection_detection import CONTENT_KIND_PATTERNS, detect_content_kind
from .projection_kinds import (
    create_projections,
    project_generic,
    project_incident,
    project_lab_result,
    project_perf_baseline_summary,
    project_trace_capture_summary,
)
from .projection_safety import (
    contains_forbidden_content,
    strip_forbidden_fields,
    truncate_string,
    validate_projection_safety,
)

__all__ = [
    # Contract
    "ALLOWED_PROJECTION_FIELDS",
    "PROJECTION_API_SUMMARY",
    "PROJECTION_API_DETAIL",
    # Detection
    "CONTENT_KIND_PATTERNS",
    "detect_content_kind",
    # Builder
    "ProjectionConfig",
    "ProjectionBuilder",
    # Safety
    "contains_forbidden_content",
    "strip_forbidden_fields",
    "truncate_string",
    "validate_projection_safety",
    # Kinds
    "create_projections",
    "project_lab_result",
    "project_trace_capture_summary",
    "project_perf_baseline_summary",
    "project_incident",
    "project_generic",
]
