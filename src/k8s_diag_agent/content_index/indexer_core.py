"""Content indexer core orchestrator.

This module provides the main ContentIndexer class that coordinates
source discovery, fingerprinting, projection generation, and storage.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .freshness import check_freshness, fingerprint_file
from .indexer_contract import ContentIndexRoots, IndexerConfig, IndexerSummary
from .indexer_discovery import discover_sources, make_content_id
from .indexer_load import load_json_file
from .projection_builder import ProjectionConfig
from .projection_detection import detect_content_kind
from .projection_kinds import create_projections
from .projection_safety import validate_projection_safety
from .schema import CONTENT_INDEX_SCHEMA_VERSION, ContentIndexRecord, FreshnessStatus, validate_source_path

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ContentIndexer:
    """Content indexer orchestrator.

    Coordinates source discovery, fingerprinting, projection generation,
    and storage operations.
    """

    def __init__(
        self,
        roots: ContentIndexRoots,
        config: IndexerConfig | None = None,
    ):
        """Initialize the indexer.

        Args:
            roots: Content index roots.
            config: Indexer configuration.
        """
        self.roots = roots
        self.config = config or IndexerConfig()
        self.summary = IndexerSummary()

    def _start_operation(self, command: str) -> None:
        """Start an indexing operation."""
        self.summary = IndexerSummary(
            command=command,
            started_at=datetime.now(UTC).isoformat(),
        )

    def _finish_operation(self, status: str = "ok") -> None:
        """Finish an indexing operation."""
        self.summary.finished_at = datetime.now(UTC).isoformat()
        self.summary.status = status

    def discover_and_index(
        self,
        conn: sqlite3.Connection,
        force_reproject: bool = False,
    ) -> IndexerSummary:
        """Discover sources and index them.

        Args:
            conn: Database connection.
            force_reproject: If True, reprocess all items regardless of freshness.

        Returns:
            IndexerSummary with operation results.
        """
        self._start_operation("discover")

        discovered = discover_sources(self.roots, self.config)
        self.summary.items_discovered = len(discovered)

        for abs_path, rel_path, path_kind in discovered:
            try:
                self._index_file(conn, abs_path, rel_path, path_kind, force_reproject)
            except Exception as e:
                error_msg = f"Failed to index {rel_path}: {e}"
                logger.error(error_msg)
                self.summary.errors.append(error_msg)
                if self.config.strict_mode:
                    raise

        self._finish_operation()
        return self.summary

    def _index_file(
        self,
        conn: sqlite3.Connection,
        abs_path: Path,
        rel_path: str,
        path_kind: str,
        force_reproject: bool = False,
    ) -> None:
        """Index a single file.

        Args:
            conn: Database connection.
            abs_path: Absolute path to the file.
            rel_path: Relative path from root.
            path_kind: Source path kind.
            force_reproject: If True, reprocess regardless of freshness.
        """
        # Import storage functions locally to avoid circular imports
        from .storage import (
            get_content_item,
            upsert_content_item,
            upsert_projection,
        )

        # Validate path
        try:
            validate_source_path(rel_path)
        except ValueError as e:
            self.summary.warnings.append(f"Invalid path {rel_path}: {e}")
            self.summary.items_skipped += 1
            return

        # Create content ID
        content_id = make_content_id(path_kind, rel_path)

        # Load content
        data = load_json_file(abs_path)
        if data is None:
            self.summary.items_skipped += 1
            return

        # Detect content kind
        content_kind = detect_content_kind(abs_path, data)
        if content_kind is None:
            self.summary.warnings.append(f"Unknown content kind for {rel_path}")
            self.summary.items_skipped += 1
            return

        # Fingerprint file
        fingerprint = fingerprint_file(abs_path)
        if not fingerprint.is_valid:
            self.summary.warnings.append(
                f"Fingerprint failed for {rel_path}: {fingerprint.error}"
            )
            self.summary.items_skipped += 1
            return

        # Extract validated fingerprint values (guaranteed non-None after is_valid check)
        mtime_ns: int = fingerprint.mtime_ns  # type: ignore[assignment]
        size_bytes: int = fingerprint.size_bytes  # type: ignore[assignment]
        sha256: str = fingerprint.sha256  # type: ignore[assignment]

        # Check if we need to update
        existing_item = None
        try:
            existing_item = get_content_item(conn, content_id)
        except Exception:
            pass

        if existing_item and not force_reproject:
            # Check freshness
            record = ContentIndexRecord(
                content_id=content_id,
                content_kind=content_kind,
                source_path=rel_path,
                source_path_kind=path_kind,
                source_mtime_ns=existing_item.source_mtime_ns,
                source_size_bytes=existing_item.source_size_bytes,
                source_sha256=existing_item.source_sha256,
                schema_version=existing_item.schema_version,
                indexed_at=existing_item.indexed_at,
                deleted=False,
            )
            freshness = check_freshness(record, fingerprint)

            if freshness.is_fresh:
                self.summary.items_unchanged += 1
                return

            if freshness.status == FreshnessStatus.STALE:
                self.summary.items_updated += 1
            else:
                self.summary.items_indexed += 1
        else:
            self.summary.items_indexed += 1

        # Create content record
        now = datetime.now(UTC).isoformat()
        content_record = ContentIndexRecord(
            content_id=content_id,
            content_kind=content_kind,
            source_path=rel_path,
            source_path_kind=path_kind,
            source_mtime_ns=mtime_ns,
            source_size_bytes=size_bytes,
            source_sha256=sha256,
            schema_version=CONTENT_INDEX_SCHEMA_VERSION,
            indexed_at=now,
            deleted=False,
        )

        # Upsert content item
        upsert_content_item(conn, content_record)

        # Create projections
        proj_config = ProjectionConfig(
            include_detail=self.config.include_detail_projections,
        )
        projections = create_projections(
            content_id=content_id,
            content_kind=content_kind,
            file_path=abs_path,
            data=data,
            config=proj_config,
        )

        # Upsert projections
        for proj in projections:
            # Validate projection safety
            is_safe, issues = validate_projection_safety(proj.projection_json)
            if not is_safe:
                self.summary.warnings.append(
                    f"Projection safety warning for {rel_path}: {issues}"
                )

            upsert_projection(conn, proj)
            self.summary.projections_written += 1
