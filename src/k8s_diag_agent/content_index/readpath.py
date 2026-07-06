"""Content index read path for k9b UI APIs.

This module provides disabled-by-default index-backed read operations for
UI-facing k9b backend APIs. It reads from the SQLite content index instead
of scanning the filesystem directly.

Schema Version: k9b.content_index.v1

Ownership:
    This module is a thin facade that re-exports from specialized modules:
    - readpath_contract: FallbackReason, IndexOpenResult, IndexValidationResult, IndexReadResult
    - readpath_reader: ContentIndexReader
    - readpath_spans: record_fallback_span, record_success_span
"""

from __future__ import annotations

from .config import ContentIndexConfig

# Re-export from readpath_contract
from .readpath_contract import (
    FallbackReason,
    IndexReadResult,
)

# Re-export from readpath_reader
from .readpath_reader import ContentIndexReader

# Re-export from readpath_spans
from .readpath_spans import (
    record_fallback_span,
    record_success_span,
)

# Import pattern: from k8s_diag_agent.content_index.readpath import (
#     ContentIndexReader,
#     FallbackReason,
#     IndexReadResult,
#     get_incident_from_index,
#     list_incidents_from_index,
#     record_fallback_span,
#     record_success_span,
# )

# Explicitly mark re-exports as part of public API
__all__ = [
    "ContentIndexReader",
    "FallbackReason",
    "IndexReadResult",
    "get_incident_from_index",
    "list_incidents_from_index",
    "record_fallback_span",
    "record_success_span",
]


# =============================================================================
# High-level API Functions
# =============================================================================


def list_incidents_from_index(
    config: ContentIndexConfig,
) -> IndexReadResult:
    """List incidents from the content index.

    Args:
        config: Content index configuration.

    Returns:
        IndexReadResult with incidents list or fallback result.
    """
    reader = ContentIndexReader(config)
    try:
        return reader.read_incidents_list()
    finally:
        reader.close()


def get_incident_from_index(
    config: ContentIndexConfig,
    incident_id: str,
) -> IndexReadResult:
    """Get a specific incident from the content index.

    Args:
        config: Content index configuration.
        incident_id: The incident ID to look up.

    Returns:
        IndexReadResult with incident detail or fallback result.
    """
    reader = ContentIndexReader(config)
    try:
        return reader.read_incident_detail(incident_id)
    finally:
        reader.close()
