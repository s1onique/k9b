"""Shared LLM provider interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMAssessmentInput:
    primary_snapshot: dict[str, Any]
    secondary_snapshot: dict[str, Any]
    comparison: dict[str, Any]
    comparison_metadata: dict[str, Any] | None
    collection_statuses: dict[str, dict[str, Any]]


class LLMProvider(ABC):
    """Provider contract for producing structured assessments."""

    @abstractmethod
    def assess(
        self,
        prompt: str,
        payload: LLMAssessmentInput,
        *,
        validate_schema: bool = True,
    ) -> dict[str, Any]:
        ...
