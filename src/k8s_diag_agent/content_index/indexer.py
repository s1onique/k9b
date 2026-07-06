"""Content index indexer.

This module provides the main indexing orchestrator that coordinates
source discovery, fingerprinting, projection generation, and storage.
Delegates to submodules for implementation details.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

# Re-export from submodules for backward compatibility
from .indexer_commands import rebuild_index, update_index, validate_index
from .indexer_contract import ContentIndexRoots, IndexerConfig, IndexerSummary
from .indexer_core import ContentIndexer
from .indexer_discovery import INDEX_PATTERNS, discover_sources, make_content_id
from .indexer_load import load_json_file

__all__ = [
    # Contract
    "ContentIndexRoots",
    "IndexerConfig",
    "IndexerSummary",
    # Discovery
    "INDEX_PATTERNS",
    "discover_sources",
    "make_content_id",
    # Load
    "load_json_file",
    # Core
    "ContentIndexer",
    # Commands
    "rebuild_index",
    "update_index",
    "validate_index",
]
