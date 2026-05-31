"""Shared primitive TypedDict payload definitions.

This module contains pure data contracts (TypedDict definitions) that are shared
across multiple payload modules. These definitions are the canonical JSON key schemas
and must remain stable.

Ownership:
    - All TypedDict payload classes defined here represent shared API response contracts.
    - JSON key names, optional vs required fields, and field types are frozen.

Extraction rationale:
    - Primitive payload definitions have minimal dependencies and no side effects.
    - Extracting them into a dedicated module avoids circular imports.
    - Keeping primitives in a shared module ensures contract consistency.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "ArtifactLink",
    "ProblemSummary",
]


class ArtifactLink(TypedDict):
    """Shared artifact link in a run or proposal."""

    label: str
    path: str


class ProblemSummary(TypedDict):
    """Shared problem summary payload."""

    title: str
    detail: str
