"""Content indexer contract types.

This module defines the core types for the content indexer.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .schema import CONTENT_INDEX_SCHEMA_VERSION

if TYPE_CHECKING:
    pass


# =============================================================================
# Content Index Roots
# =============================================================================


@dataclass
class ContentIndexRoots:
    """Roots for content discovery.

    Attributes:
        incident_store: Path to incident store directory.
        artifact_root: Path to artifact root directory.
        lab_root: Path to lab output directory.
        trace_capture_root: Path to trace capture directory.
        perf_baseline_root: Path to performance baseline directory.
    """

    incident_store: Path | None = None
    artifact_root: Path | None = None
    lab_root: Path | None = None
    trace_capture_root: Path | None = None
    perf_baseline_root: Path | None = None

    def get_active_roots(self) -> list[tuple[str, Path]]:
        """Get active root paths as (kind, path) tuples."""
        roots: list[tuple[str, Path]] = []
        if self.incident_store:
            roots.append(("incident_store", self.incident_store))
        if self.artifact_root:
            roots.append(("artifact", self.artifact_root))
        if self.lab_root:
            roots.append(("lab", self.lab_root))
        if self.trace_capture_root:
            roots.append(("trace_capture", self.trace_capture_root))
        if self.perf_baseline_root:
            roots.append(("perf_baseline", self.perf_baseline_root))
        return roots


# =============================================================================
# Indexer Configuration
# =============================================================================


@dataclass
class IndexerConfig:
    """Configuration for the indexer."""

    strict_mode: bool = False
    include_detail_projections: bool = False
    max_file_size_mb: int = 100
    skip_unreadable: bool = True


# =============================================================================
# Indexer Summary
# =============================================================================


@dataclass
class IndexerSummary:
    """Summary of an indexing operation.

    Attributes:
        schema_version: Index schema version.
        command: Command that produced this summary.
        index_schema_version: Target schema version.
        started_at: Start timestamp.
        finished_at: Finish timestamp.
        status: Operation status.
        items_discovered: Number of items discovered.
        items_indexed: Number of items indexed.
        items_updated: Number of items updated.
        items_unchanged: Number of items unchanged.
        items_tombstoned: Number of items tombstoned.
        items_skipped: Number of items skipped.
        projections_written: Number of projections written.
        warnings: List of warning messages.
        errors: List of error messages.
    """

    schema_version: str = "k9b.content_index_run.v1"
    command: str = ""
    index_schema_version: str = CONTENT_INDEX_SCHEMA_VERSION
    started_at: str = ""
    finished_at: str = ""
    status: str = "ok"
    items_discovered: int = 0
    items_indexed: int = 0
    items_updated: int = 0
    items_unchanged: int = 0
    items_tombstoned: int = 0
    items_skipped: int = 0
    projections_written: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "schema_version": self.schema_version,
            "command": self.command,
            "index_schema_version": self.index_schema_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "items_discovered": self.items_discovered,
            "items_indexed": self.items_indexed,
            "items_updated": self.items_updated,
            "items_unchanged": self.items_unchanged,
            "items_tombstoned": self.items_tombstoned,
            "items_skipped": self.items_skipped,
            "projections_written": self.projections_written,
            "warnings": self.warnings,
        }
