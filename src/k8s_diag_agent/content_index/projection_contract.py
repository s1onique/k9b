"""Content projection contract constants.

This module defines the contract for allowed fields and projection kinds.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

# =============================================================================
# Allowed Projection Fields
# =============================================================================

# Fields that are safe to include in projections
ALLOWED_PROJECTION_FIELDS = frozenset({
    "content_id",
    "content_kind",
    "schema_version",
    "status",
    "severity",
    "candidate_class",
    "namespace",
    "object_kind",
    "object_name",
    "created_at",
    "updated_at",
    "first_observed_at",
    "last_observed_at",
    "counts",
    "safe_title",
    "safe_summary",
    # Nested field names in counts structure
    "traces",
    "spans",
    "http_spans",
    "iterations",
    "endpoints",
    "slowest_endpoint",
})


# =============================================================================
# Projection Kinds
# =============================================================================

# api_summary: Minimal summary for list views
PROJECTION_API_SUMMARY = "api_summary"

# api_detail: More detailed summary for detail views
PROJECTION_API_DETAIL = "api_detail"
