"""Content index storage layer.

This module re-exports all storage functions from focused sub-modules.

Schema Version: k9b.content_index.v1

Modules:
    - storage_connection: Connection management and initialization
    - storage_metadata: Metadata operations
    - storage_items: Content item CRUD
    - storage_projections: Projection CRUD
    - storage_validation: Validation and counts
    - storage_rebuild: Atomic replacement
"""

from __future__ import annotations

# Re-export all public functions from sub-modules
# Connection and initialization
from .storage_connection import (
    create_content_index_temp_path,
    create_temp_database,
    get_connection,
    initialize_database,
)

# Content item operations
from .storage_items import (
    get_all_content_items,
    get_content_item,
    get_content_items_by_path_kind,
    tombstone_content_item,
    upsert_content_item,
)

# Metadata operations
from .storage_metadata import (
    get_metadata,
    get_schema_version,
    update_indexed_at,
)

# Projection operations
from .storage_projections import (
    delete_projection,
    get_projection,
    get_projections_for_item,
    upsert_projection,
)

# Rebuild operations
from .storage_rebuild import atomically_replace_database

# Validation and counts
from .storage_validation import (
    count_by_kind,
    count_items,
    validate_database,
)

__all__ = [
    # Connection
    "get_connection",
    "initialize_database",
    "create_temp_database",
    "create_content_index_temp_path",
    # Metadata
    "get_metadata",
    "update_indexed_at",
    "get_schema_version",
    # Items
    "upsert_content_item",
    "get_content_item",
    "get_all_content_items",
    "tombstone_content_item",
    "get_content_items_by_path_kind",
    # Projections
    "upsert_projection",
    "get_projection",
    "get_projections_for_item",
    "delete_projection",
    # Validation
    "validate_database",
    "count_items",
    "count_by_kind",
    # Rebuild
    "atomically_replace_database",
]
