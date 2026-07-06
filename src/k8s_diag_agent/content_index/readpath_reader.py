"""Content index reader implementation.

This module provides the ContentIndexReader class that handles database
open/validate/query operations for the content index read path.

Schema Version: k9b.content_index.v1

Ownership:
    - ContentIndexReader: Database open/validate/query logic
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import TYPE_CHECKING, Any

from .config import ContentIndexConfig, get_default_content_index_db_path
from .projection_contract import PROJECTION_API_DETAIL, PROJECTION_API_SUMMARY
from .readpath_contract import (
    FallbackReason,
    IndexOpenResult,
    IndexReadResult,
    IndexValidationResult,
)
from .schema import CONTENT_INDEX_SCHEMA_VERSION
from .storage_connection import get_connection
from .storage_metadata import get_schema_version
from .storage_validation import validate_database

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


# =============================================================================
# Content Index Reader
# =============================================================================


class ContentIndexReader:
    """Reader for content index database.

    This class provides read-only access to the content index for UI APIs.
    It is instantiated per-request and is safe for concurrent read-only access.

    Ownership:
        - Handles database open/validate/query operations
        - Returns typed IndexOpenResult, IndexValidationResult, IndexReadResult
    """

    def __init__(self, config: ContentIndexConfig) -> None:
        """Initialize the reader with configuration.

        Args:
            config: Content index configuration.
        """
        self._config = config
        self._conn: sqlite3.Connection | None = None
        self._schema_version: str | None = None

    def open_index(self) -> IndexOpenResult:
        """Open the index database read-only.

        Returns:
            IndexOpenResult with success/failure information.
        """
        from ..observability.internal_spans import internal_span

        # Determine DB path
        db_path = self._config.db_path
        if db_path is None:
            db_path = get_default_content_index_db_path()

        with internal_span(
            "k9b.content_index.open",
            attributes={"k9b.content_index.enabled": str(self._config.enabled)},
        ):
            try:
                self._conn = get_connection(db_path, read_only=True)
                return IndexOpenResult.success()
            except FileNotFoundError:
                _logger.debug("Content index not found at %s", db_path)
                return IndexOpenResult.not_found()
            except sqlite3.DatabaseError:
                # Corrupt or invalid database file
                _logger.debug("Content index is not a valid database at %s", db_path)
                return IndexOpenResult.corrupt()
            except Exception as exc:  # noqa: BLE001
                _logger.debug("Failed to open content index: %s", exc)
                return IndexOpenResult.error()

    def validate_index(self) -> IndexValidationResult:
        """Validate the index schema and metadata.

        Returns:
            IndexValidationResult with validation status and schema version.
        """
        from ..observability.internal_spans import internal_span

        if self._conn is None:
            return IndexValidationResult.validation_failed()

        with internal_span(
            "k9b.content_index.validate",
            attributes={"k9b.content_index.enabled": str(self._config.enabled)},
        ):
            try:
                # Check schema version
                schema_version = get_schema_version(self._conn)
                if schema_version != CONTENT_INDEX_SCHEMA_VERSION:
                    _logger.debug(
                        "Content index schema version mismatch: expected %s, got %s",
                        CONTENT_INDEX_SCHEMA_VERSION,
                        schema_version,
                    )
                    return IndexValidationResult.schema_mismatch()

                # Full validation
                validation_result = validate_database(self._conn)
                if not validation_result["valid"]:
                    _logger.debug(
                        "Content index validation failed: %s",
                        validation_result.get("errors", []),
                    )
                    return IndexValidationResult.validation_failed()

                self._schema_version = schema_version
                return IndexValidationResult.success(schema_version)
            except sqlite3.DatabaseError:
                _logger.debug("Content index validation failed: corrupt database")
                return IndexValidationResult.validation_failed()

    def query_incidents_summary(self) -> list[dict[str, Any]]:
        """Query incident summaries from the index.

        Returns:
            List of incident summary projections.
        """
        if self._conn is None:
            return []

        cursor = self._conn.execute(
            """
            SELECT p.projection_json
            FROM content_item i
            JOIN content_projection p ON i.content_id = p.content_id
            WHERE i.content_kind = 'incident'
              AND i.deleted = 0
              AND p.projection_kind = ?
            ORDER BY i.content_id
            """,
            (PROJECTION_API_SUMMARY,),
        )

        results = []
        for row in cursor.fetchall():
            try:
                projection = json.loads(row[0])
                results.append(projection)
            except json.JSONDecodeError:
                # Skip malformed projections
                continue

        return results

    def query_incident_detail(self, incident_id: str) -> dict[str, Any] | None:
        """Query a specific incident detail from the index.

        Args:
            incident_id: The incident ID to look up.

        Returns:
            Incident detail projection, or None if not found.
        """
        if self._conn is None:
            return None

        cursor = self._conn.execute(
            """
            SELECT p.projection_json
            FROM content_item i
            JOIN content_projection p ON i.content_id = p.content_id
            WHERE i.content_id = ?
              AND i.content_kind = 'incident'
              AND i.deleted = 0
              AND p.projection_kind = ?
            """,
            (incident_id, PROJECTION_API_DETAIL),
        )

        row = cursor.fetchone()
        if row is None:
            return None

        try:
            data: dict[str, Any] = json.loads(row[0])
            return data
        except json.JSONDecodeError:
            return None

    def read_incidents_list(self) -> IndexReadResult:
        """Read incident list from the content index.

        Returns:
            IndexReadResult with incidents list or fallback result.
        """
        from ..observability.internal_spans import internal_span

        # Fast path: if disabled, skip index entirely
        if not self._config.enabled:
            return IndexReadResult.fallback(FallbackReason.INDEX_NOT_ENABLED)

        # Try to open index
        with internal_span(
            "k9b.content_index.query",
            attributes={"k9b.content_index.query.kind": "list_incidents"},
        ):
            open_result = self.open_index()
            if not open_result.ok:
                return IndexReadResult.fallback(open_result.reason or FallbackReason.INDEX_OPEN_ERROR)

            validate_result = self.validate_index()
            if not validate_result.ok:
                return IndexReadResult.fallback(validate_result.reason or FallbackReason.INDEX_VALIDATION_FAILED)

            try:
                incidents = self.query_incidents_summary()
                return IndexReadResult.from_index(
                    data={"incidents": incidents, "total": len(incidents)},
                    schema_version=self._schema_version or CONTENT_INDEX_SCHEMA_VERSION,
                    count=len(incidents),
                )
            except Exception as exc:  # noqa: BLE001
                _logger.debug("Failed to query incidents from index: %s", exc)
                return IndexReadResult.fallback(FallbackReason.PROJECTION_ERROR)

    def read_incident_detail(self, incident_id: str) -> IndexReadResult:
        """Read a specific incident detail from the content index.

        Args:
            incident_id: The incident ID to look up.

        Returns:
            IndexReadResult with incident detail or fallback result.
        """
        from ..observability.internal_spans import internal_span

        # Fast path: if disabled, skip index entirely
        if not self._config.enabled:
            return IndexReadResult.fallback(FallbackReason.INDEX_NOT_ENABLED)

        # Try to open index
        with internal_span(
            "k9b.content_index.query",
            attributes={"k9b.content_index.query.kind": "incident_detail"},
        ):
            open_result = self.open_index()
            if not open_result.ok:
                return IndexReadResult.fallback(open_result.reason or FallbackReason.INDEX_OPEN_ERROR)

            validate_result = self.validate_index()
            if not validate_result.ok:
                return IndexReadResult.fallback(validate_result.reason or FallbackReason.INDEX_VALIDATION_FAILED)

            try:
                incident = self.query_incident_detail(incident_id)
                if incident is None:
                    # Incident not in index - this is not a fallback, just not found
                    # Return empty result with valid schema version
                    return IndexReadResult.not_found(
                        schema_version=self._schema_version or CONTENT_INDEX_SCHEMA_VERSION,
                    )
                return IndexReadResult.from_index(
                    data=incident,
                    schema_version=self._schema_version or CONTENT_INDEX_SCHEMA_VERSION,
                    count=1,
                )
            except Exception as exc:  # noqa: BLE001
                _logger.debug("Failed to query incident from index: %s", exc)
                return IndexReadResult.fallback(FallbackReason.PROJECTION_ERROR)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> ContentIndexReader:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
