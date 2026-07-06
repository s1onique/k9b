"""Content projection builder.

This module provides the ProjectionConfig and ProjectionBuilder classes.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .projection_contract import (
    ALLOWED_PROJECTION_FIELDS,
    PROJECTION_API_DETAIL,
    PROJECTION_API_SUMMARY,
)
from .projection_safety import truncate_string
from .schema import CONTENT_INDEX_SCHEMA_VERSION

if TYPE_CHECKING:
    pass


# =============================================================================
# Projection Configuration
# =============================================================================


@dataclass
class ProjectionConfig:
    """Configuration for projection generation."""

    include_detail: bool = False
    max_summary_length: int = 500
    max_title_length: int = 200


# =============================================================================
# Base Projection Builder
# =============================================================================


@dataclass
class ProjectionBuilder:
    """Builder for creating projections."""

    content_id: str
    content_kind: str
    config: ProjectionConfig = field(default_factory=ProjectionConfig)
    _data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize projection with base data."""
        self._data = {
            "content_id": self.content_id,
            "content_kind": self.content_kind,
            "schema_version": CONTENT_INDEX_SCHEMA_VERSION,
        }

    def add_field(self, key: str, value: Any) -> ProjectionBuilder:
        """Add a field to the projection.

        Args:
            key: Field name.
            value: Field value.

        Returns:
            Self for chaining.
        """
        if key in ALLOWED_PROJECTION_FIELDS:
            self._data[key] = value
        return self

    def add_safe_title(self, title: str | None) -> ProjectionBuilder:
        """Add a safe title field.

        Args:
            title: Title to add.

        Returns:
            Self for chaining.
        """
        if title:
            self._data["safe_title"] = truncate_string(title, self.config.max_title_length)
        return self

    def add_safe_summary(self, summary: str | None) -> ProjectionBuilder:
        """Add a safe summary field.

        Args:
            summary: Summary to add.

        Returns:
            Self for chaining.
        """
        if summary:
            self._data["safe_summary"] = truncate_string(
                summary, self.config.max_summary_length
            )
        return self

    def add_timestamp_field(
        self,
        key: str,
        value: str | datetime | None,
    ) -> ProjectionBuilder:
        """Add a timestamp field with conversion.

        Args:
            key: Field name (must be in allowed fields).
            value: Timestamp value.

        Returns:
            Self for chaining.
        """
        if value is None:
            return self

        if isinstance(value, datetime):
            self._data[key] = value.isoformat()
        elif isinstance(value, str):
            self._data[key] = value
        return self

    def add_status(self, status: str | None) -> ProjectionBuilder:
        """Add a status field.

        Args:
            status: Status value.

        Returns:
            Self for chaining.
        """
        if status:
            self._data["status"] = status
        return self

    def add_severity(self, severity: str | None) -> ProjectionBuilder:
        """Add a severity field.

        Args:
            severity: Severity value.

        Returns:
            Self for chaining.
        """
        if severity:
            self._data["severity"] = severity
        return self

    def add_counts(self, counts: dict[str, int] | None) -> ProjectionBuilder:
        """Add a counts field.

        Args:
            counts: Counts dictionary.

        Returns:
            Self for chaining.
        """
        if counts and isinstance(counts, dict):
            self._data["counts"] = counts
        return self

    def add_namespace(self, namespace: str | None) -> ProjectionBuilder:
        """Add a namespace field.

        Args:
            namespace: Namespace value.

        Returns:
            Self for chaining.
        """
        if namespace:
            self._data["namespace"] = namespace
        return self

    def build_summary(self) -> Any:
        """Build the api_summary projection.

        Returns:
            ContentProjectionRecord for the summary projection.
        """
        from .projection_safety import strip_forbidden_fields
        from .schema import ContentProjectionRecord

        # Clean forbidden fields
        cleaned = strip_forbidden_fields(self._data)

        return ContentProjectionRecord(
            content_id=self.content_id,
            projection_kind=PROJECTION_API_SUMMARY,
            projection_json=json.dumps(cleaned, separators=(",", ":")),
            updated_at=datetime.now(UTC).isoformat(),
        )

    def build_detail(self) -> Any | None:
        """Build the api_detail projection if configured.

        Returns:
            ContentProjectionRecord for the detail projection, or None if not configured.
        """
        from .schema import ContentProjectionRecord

        if not self.config.include_detail:
            return None

        # Add detail-specific fields (already cleaned by strip_forbidden_fields)
        return ContentProjectionRecord(
            content_id=self.content_id,
            projection_kind=PROJECTION_API_DETAIL,
            projection_json=json.dumps(self._data, separators=(",", ":")),
            updated_at=datetime.now(UTC).isoformat(),
        )
