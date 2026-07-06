"""Content index read path for k9b UI APIs.

This module provides disabled-by-default index-backed read operations for
UI-facing k9b backend APIs. It reads from the SQLite content index instead
of scanning the filesystem directly.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .config import ContentIndexConfig, get_default_content_index_db_path
from .projection_contract import PROJECTION_API_DETAIL, PROJECTION_API_SUMMARY
from .schema import CONTENT_INDEX_SCHEMA_VERSION
from .storage_connection import get_connection
from .storage_metadata import get_schema_version
from .storage_validation import validate_database

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


# =============================================================================
# Fallback Reasons (bounded, safe for OTel attributes)
# =============================================================================

class FallbackReason:
    """Bounded fallback reason codes for OTel span attributes.

    These are safe, low-cardinality values that indicate why the index
    read path fell back to the direct read path.
    """

    INDEX_NOT_ENABLED = "index_not_enabled"
    INDEX_NOT_AVAILABLE = "index_not_available"
    INDEX_NOT_FOUND = "index_not_found"
    INDEX_CORRUPT = "index_corrupt"
    INDEX_SCHEMA_MISMATCH = "index_schema_mismatch"
    INDEX_VALIDATION_FAILED = "index_validation_failed"
    INDEX_OPEN_ERROR = "index_open_error"
    PROJECTION_ERROR = "projection_error"


# =============================================================================
# Index Read Result
# =============================================================================


@dataclass(frozen=True)
class IndexReadResult:
    """Result of an index read operation.

    Attributes:
        data: The projected data from the index, or None if index unavailable.
        fallback_reason: Bounded reason code for why fallback occurred, or None.
        schema_version: Schema version from the index, or None.
        count: Number of items returned from the index.
        index_available: Whether the index was available and valid.
    """

    data: dict[str, Any] | None
    fallback_reason: str | None
    schema_version: str | None
    count: int
    index_available: bool

    @classmethod
    def fallback(
        cls,
        reason: str,
        count: int = 0,
    ) -> IndexReadResult:
        """Create a fallback result when index is unavailable."""
        return cls(
            data=None,
            fallback_reason=reason,
            schema_version=None,
            count=count,
            index_available=False,
        )

    @classmethod
    def from_index(
        cls,
        data: dict[str, Any],
        schema_version: str,
        count: int,
    ) -> IndexReadResult:
        """Create a successful index result."""
        return cls(
            data=data,
            fallback_reason=None,
            schema_version=schema_version,
            count=count,
            index_available=True,
        )


# =============================================================================
# Content Index Reader
# =============================================================================


class ContentIndexReader:
    """Reader for content index database.

    This class provides read-only access to the content index for UI APIs.
    It is instantiated per-request and is safe for concurrent read-only access.
    """

    def __init__(self, config: ContentIndexConfig) -> None:
        """Initialize the reader with configuration.

        Args:
            config: Content index configuration.
        """
        self._config = config
        self._conn: sqlite3.Connection | None = None
        self._schema_version: str | None = None

    def _open_index(self) -> bool:
        """Open the index database read-only.

        Returns:
            True if index opened successfully, False otherwise.
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
                return True
            except FileNotFoundError:
                _logger.debug("Content index not found at %s", db_path)
                return False
            except sqlite3.DatabaseError:
                # Corrupt or invalid database file
                _logger.debug("Content index is not a valid database at %s", db_path)
                return False
            except Exception as exc:  # noqa: BLE001
                _logger.debug("Failed to open content index: %s", exc)
                return False

    def _validate_index(self) -> bool:
        """Validate the index schema and metadata.

        Returns:
            True if index is valid, False otherwise.
        """
        from ..observability.internal_spans import internal_span

        if self._conn is None:
            return False

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
                    return False

                # Full validation
                validation_result = validate_database(self._conn)
                if not validation_result["valid"]:
                    _logger.debug(
                        "Content index validation failed: %s",
                        validation_result.get("errors", []),
                    )
                    return False

                self._schema_version = schema_version
                return True
            except sqlite3.DatabaseError:
                _logger.debug("Content index validation failed: corrupt database")
                return False

    def _query_incidents_summary(self) -> list[dict[str, Any]]:
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

    def _query_incident_detail(self, incident_id: str) -> dict[str, Any] | None:
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

    def read_incidents_list(
        self,
    ) -> IndexReadResult:
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
            if not self._open_index():
                return IndexReadResult.fallback(FallbackReason.INDEX_NOT_FOUND)

            if not self._validate_index():
                return IndexReadResult.fallback(FallbackReason.INDEX_SCHEMA_MISMATCH)

            try:
                incidents = self._query_incidents_summary()
                return IndexReadResult.from_index(
                    data={"incidents": incidents, "total": len(incidents)},
                    schema_version=self._schema_version or CONTENT_INDEX_SCHEMA_VERSION,
                    count=len(incidents),
                )
            except Exception as exc:  # noqa: BLE001
                _logger.debug("Failed to query incidents from index: %s", exc)
                return IndexReadResult.fallback(FallbackReason.PROJECTION_ERROR)

    def read_incident_detail(
        self,
        incident_id: str,
    ) -> IndexReadResult:
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
            if not self._open_index():
                return IndexReadResult.fallback(FallbackReason.INDEX_NOT_FOUND)

            if not self._validate_index():
                return IndexReadResult.fallback(FallbackReason.INDEX_SCHEMA_MISMATCH)

            try:
                incident = self._query_incident_detail(incident_id)
                if incident is None:
                    # Incident not in index - this is not a fallback, just not found
                    # Return empty result with valid schema version
                    return IndexReadResult(
                        data=None,
                        fallback_reason=None,
                        schema_version=self._schema_version or CONTENT_INDEX_SCHEMA_VERSION,
                        count=0,
                        index_available=True,
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


# =============================================================================
# Span Attribute Helpers
# =============================================================================


def record_fallback_span(
    span_name: str,
    reason: str,
    enabled: bool,
    schema_version: str | None = None,
) -> None:
    """Record a fallback span with appropriate attributes.

    Args:
        span_name: Name of the span (e.g., "k9b.content_index.fallback").
        reason: Bounded fallback reason code.
        enabled: Whether index was enabled.
        schema_version: Schema version from index if available.
    """
    from ..observability.internal_spans import internal_span

    attrs: dict[str, str | bool] = {
        "k9b.content_index.enabled": str(enabled),
        "k9b.content_index.available": "false",
        "k9b.content_index.fallback.reason": reason,
    }
    if schema_version:
        attrs["k9b.content_index.schema_version"] = schema_version

    with internal_span(span_name, attributes=attrs):
        pass


def record_success_span(
    span_name: str,
    enabled: bool,
    schema_version: str,
    count: int,
) -> None:
    """Record a successful index read span.

    Args:
        span_name: Name of the span (e.g., "k9b.content_index.project_response").
        enabled: Whether index was enabled.
        schema_version: Schema version from index.
        count: Number of items returned.
    """
    from ..observability.internal_spans import internal_span

    attrs: dict[str, str | bool | int] = {
        "k9b.content_index.enabled": str(enabled),
        "k9b.content_index.available": "true",
        "k9b.content_index.schema_version": schema_version,
        "k9b.result.count": count,
    }

    with internal_span(span_name, attributes=attrs):
        pass
