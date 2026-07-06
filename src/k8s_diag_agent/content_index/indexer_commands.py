"""Content indexer command operations.

This module provides the high-level rebuild, update, and validate operations.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .indexer_contract import ContentIndexRoots, IndexerConfig, IndexerSummary
from .indexer_core import ContentIndexer
from .schema import CONTENT_INDEX_SCHEMA_VERSION
from .storage import (
    atomically_replace_database,
    count_items,
    create_temp_database,
    get_connection,
    get_content_items_by_path_kind,
    get_schema_version,
    tombstone_content_item,
    update_indexed_at,
    validate_database,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Rebuild Operation
# =============================================================================


def rebuild_index(
    target_db_path: Path,
    roots: ContentIndexRoots,
    config: IndexerConfig | None = None,
) -> IndexerSummary:
    """Rebuild the content index from scratch.

    Creates a new temp database, indexes all sources, validates,
    and atomically replaces the target.

    Args:
        target_db_path: Path to the target database.
        roots: Content index roots.
        config: Indexer configuration.

    Returns:
        IndexerSummary with operation results.
    """
    # Create temp database
    temp_path, temp_conn = create_temp_database()

    try:
        # Initialize indexer
        indexer = ContentIndexer(roots, config)

        # Index all sources
        summary = indexer.discover_and_index(temp_conn, force_reproject=True)

        # Validate temp database
        validation = validate_database(temp_conn)
        if not validation["valid"]:
            summary.errors.extend(validation["errors"])
            summary.status = "failed"
            return summary

        # Atomically replace target
        atomically_replace_database(target_db_path, temp_path)
        summary.status = "ok"

    except Exception:
        # Clean up temp database on failure
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    finally:
        temp_conn.close()

    return summary


# =============================================================================
# Update Operation
# =============================================================================


def update_index(
    db_path: Path,
    roots: ContentIndexRoots,
    config: IndexerConfig | None = None,
) -> IndexerSummary:
    """Incrementally update the content index.

    Discovers current sources, compares fingerprints, and updates
    changed/deleted items.

    Args:
        db_path: Path to the database.
        roots: Content index roots.
        config: Indexer configuration.

    Returns:
        IndexerSummary with operation results.
    """
    # Connect to existing database
    if not db_path.exists():
        # No existing database, do a rebuild
        return rebuild_index(db_path, roots, config)

    conn = get_connection(db_path)

    try:
        # Check schema version
        schema_version = get_schema_version(conn)
        if schema_version != CONTENT_INDEX_SCHEMA_VERSION:
            # Schema mismatch, need rebuild
            conn.close()
            return rebuild_index(db_path, roots, config)

        # Initialize indexer
        indexer = ContentIndexer(roots, config)

        # Import discovery here to avoid circular import
        from .indexer_discovery import discover_sources, make_content_id

        # Get existing items by path kind
        existing_items: dict[str, Any] = {}
        for path_kind, _ in roots.get_active_roots():
            items = get_content_items_by_path_kind(conn, path_kind)
            for item in items:
                existing_items[item.content_id] = item

        # Discover current sources
        discovered = discover_sources(roots, config)
        discovered_ids: set[str] = set()

        for abs_path, rel_path, path_kind in discovered:
            content_id = make_content_id(path_kind, rel_path)
            discovered_ids.add(content_id)

            try:
                indexer._index_file(conn, abs_path, rel_path, path_kind, False)
            except Exception as e:
                error_msg = f"Failed to index {rel_path}: {e}"
                logger.error(error_msg)
                indexer.summary.errors.append(error_msg)
                if config and config.strict_mode:
                    raise

        # Tombstone missing items
        for content_id, item in existing_items.items():
            if content_id not in discovered_ids and not item.deleted:
                if tombstone_content_item(conn, content_id):
                    indexer.summary.items_tombstoned += 1

        # Update indexed_at
        update_indexed_at(conn)

        indexer._finish_operation()
        return indexer.summary

    finally:
        conn.close()


# =============================================================================
# Validate Operation
# =============================================================================


def validate_index(db_path: Path) -> dict[str, Any]:
    """Validate the content index.

    Args:
        db_path: Path to the database.

    Returns:
        Validation result dictionary.
    """
    if not db_path.exists():
        return {
            "valid": False,
            "errors": ["Database file does not exist"],
        }

    conn = get_connection(db_path)

    try:
        result = validate_database(conn)

        # Add counts
        counts = count_items(conn)
        result["counts"] = counts

        return result

    finally:
        conn.close()
