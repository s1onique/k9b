# Content Index Module
#
# This module provides schema definitions and contracts for the k9b on-disk
# content index. The index accelerates UI/backend read paths by precomputing
# projections from source artifacts.

from k8s_diag_agent.content_index.schema import (
    CONTENT_INDEX_SCHEMA_VERSION,
    INDEXED_CONTENT_KINDS,
    INDEXED_PATH_KINDS,
    ContentIndexFreshness,
    ContentIndexRecord,
    ContentIndexValidationResult,
    ContentProjectionRecord,
    get_content_kind_validator,
    validate_content_kind,
)

__all__ = [
    "CONTENT_INDEX_SCHEMA_VERSION",
    "INDEXED_CONTENT_KINDS",
    "INDEXED_PATH_KINDS",
    "ContentIndexRecord",
    "ContentIndexFreshness",
    "ContentIndexValidationResult",
    "ContentProjectionRecord",
    "get_content_kind_validator",
    "validate_content_kind",
]
