"""Tests for content index storage.

This module re-exports tests from submodules for backward compatibility.
Tests are split into:
- test_content_index_storage_connection.py: Database initialization tests
- test_content_index_storage_items.py: Content item and tombstone tests
- test_content_index_storage_projections.py: Projection CRUD tests
- test_content_index_storage_validation.py: Validation and count tests
"""

from __future__ import annotations

# Re-export all test classes for backward compatibility
from tests.unit.test_content_index_storage_connection import (
    TestDatabaseInitialization,
)
from tests.unit.test_content_index_storage_items import (
    TestContentItemOperations,
    TestTombstoneOperations,
)
from tests.unit.test_content_index_storage_projections import (
    TestProjectionOperations,
)
from tests.unit.test_content_index_storage_validation import (
    TestCountOperations,
    TestValidation,
)

__all__ = [
    "TestDatabaseInitialization",
    "TestContentItemOperations",
    "TestTombstoneOperations",
    "TestProjectionOperations",
    "TestValidation",
    "TestCountOperations",
]
