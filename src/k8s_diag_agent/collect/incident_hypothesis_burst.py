"""Hypothesis burst module for automatic diagnosis loop.

This module provides:
- HypothesisBurst: Model for a hypothesis burst output
- HypothesisCandidate: Individual ranked hypothesis candidate with falsifier fields
- CandidateCheck: Discriminating check for hypothesis testing
- run_hypothesis_burst(): Generate ranked hypotheses from incident signals

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls (deterministic baseline)
- No Kubernetes calls
- No execution
- Hypotheses first, evidence second
- Falsifiers are REQUIRED - hypotheses without them are rejected

This module is a facade that re-exports from specialized modules:
- incident_hypothesis_burst_models: HypothesisCandidate, HypothesisBurst, etc.
- incident_hypothesis_burst_generator: run_hypothesis_burst, validate functions
"""

from __future__ import annotations

# Re-export generator functions
from .incident_hypothesis_burst_generator import (
    run_hypothesis_burst,
    validate_candidate_checks,
    validate_check_id,
    validate_hypothesis_candidates,
)

# Re-export models
from .incident_hypothesis_burst_models import (
    MAX_CANDIDATE_CHECKS,
    MAX_HYPOTHESES,
    SCHEMA_VERSION,
    CandidateCheck,
    HypothesisBurst,
    HypothesisCandidate,
    HypothesisCandidateClass,
    HypothesisValidationError,
)

__all__ = [
    "SCHEMA_VERSION",
    "HypothesisCandidateClass",
    "HypothesisCandidate",
    "HypothesisValidationError",
    "CandidateCheck",
    "HypothesisBurst",
    "MAX_HYPOTHESES",
    "MAX_CANDIDATE_CHECKS",
    "validate_check_id",
    "validate_hypothesis_candidates",
    "validate_candidate_checks",
    "run_hypothesis_burst",
]
