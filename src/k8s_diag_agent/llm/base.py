"""Shared LLM provider interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class LLMAssessmentInput:
    primary_snapshot: Dict[str, Any]
    secondary_snapshot: Dict[str, Any]
    comparison: Dict[str, Any]
    collection_statuses: Dict[str, Dict[str, Any]]


class LLMProvider(ABC):
    """Provider contract for producing structured assessments."""

    @abstractmethod
    def assess(self, prompt: str, payload: LLMAssessmentInput) -> Dict[str, Any]:
        ...
