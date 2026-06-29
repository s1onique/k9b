"""Data models for the health loop.

This module contains pure data definitions (dataclasses, enums) used across
the health loop implementation. These have no runner logic or side effects.

Split from loop.py for LLM-friendly file sizes while preserving the public
import contract through the loop.py facade.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class HealthLoopStatus(StrEnum):
    """Status of a health loop execution."""

    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class HealthLoopResult:
    """Result of a health loop execution.

    This is a simple result type combining all outputs from a health run.
    Used for the public API and backward compatibility.
    """

    def __init__(
        self,
        status: HealthLoopStatus,
        assessments: list | None = None,
        triggers: list | None = None,
        drilldowns: list | None = None,
        external_artifacts: list | None = None,
        error: str | None = None,
    ) -> None:
        self.status = status
        self.assessments = assessments or []
        self.triggers = triggers or []
        self.drilldowns = drilldowns or []
        self.external_artifacts = external_artifacts or []
        self.error = error


@dataclass(frozen=True)
class ManualComparison:
    """Manual comparison between two clusters.

    This is a lightweight model for specifying peer comparisons that should
    always be performed regardless of automatic trigger policy.
    """

    primary: str
    secondary: str
