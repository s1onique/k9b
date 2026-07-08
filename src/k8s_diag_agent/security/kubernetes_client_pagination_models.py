"""Pagination and log result models for Kubernetes client operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaginationMetadata:
    """Metadata about pagination results."""
    total: int | None = None
    remaining: int = 0
    truncated: bool = False
    continuation_token: str | None = None
    items_returned: int = 0


@dataclass(frozen=True)
class BoundedPodLogResult:
    """Result from bounded pod log collection."""
    logs: str
    truncated: bool
    truncation_reason: str | None = None
    bytes_read: int = 0
    bytes_limit: int = 0
    tail_lines: int | None = None
    duration_seconds: float = 0.0


__all__ = [
    "BoundedPodLogResult",
    "PaginationMetadata",
]
