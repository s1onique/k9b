"""Pass executor for automatic diagnosis loop multi-pass evidence collection.

This module provides:
- PassResult: Result of a single evidence pass
- execute_pass(): Execute selected checks and update hypothesis ranking
- rerank_hypotheses(): Update hypothesis rankings based on evidence (bidirectional)

This module is a facade that re-exports from specialized modules.
"""

from __future__ import annotations

# Re-export contracts
from .incident_diagnosis_pass_contracts import (
    SCHEMA_VERSION,
    PassResult,
    StopDecision,
)

# Re-export reranking
from .incident_diagnosis_pass_reranking import rerank_hypotheses

# Re-export steps
from .incident_diagnosis_pass_steps import (
    execute_pass,
    select_checks_for_pass,
)

__all__ = [
    "SCHEMA_VERSION",
    "StopDecision",
    "PassResult",
    "rerank_hypotheses",
    "execute_pass",
    "select_checks_for_pass",
]
