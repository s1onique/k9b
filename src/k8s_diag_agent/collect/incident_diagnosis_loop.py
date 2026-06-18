"""Bounded multi-pass incident diagnosis loop.

This module is a facade that re-exports the public API from split modules.

For the full implementation, see:
- incident_diagnosis_loop_models: Enums, constants, dataclasses
- incident_diagnosis_loop_state: State management functions
- incident_diagnosis_loop_stops: Stop condition checkers
- incident_diagnosis_loop_proposals: Proposal extraction
- incident_diagnosis_loop_planner: Main planning function

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution, promotion, or remediation
- Deterministic state transitions
- Explicit safety metadata

This module does NOT:
- Execute checks
- Instantiate Kubernetes clients
- Call shell/subprocess
- Persist loop state
- Turn LLM text into executable commands
"""

from .incident_diagnosis_loop_models import (
    DEFAULT_MAX_PASSES,
    LOOP_SCHEMA_VERSION,
    MAX_MISSING_EVIDENCE_FOR_CREDIBLE,
    MIN_HIGH_CONFIDENCE_EVIDENCE,
    Confidence,
    DiagnosisPass,
    LoopDecision,
    LoopState,
    RootCauseCandidate,
    StopReason,
)
from .incident_diagnosis_loop_planner import (
    plan_next_diagnosis_pass,
)
from .incident_diagnosis_loop_proposals import (
    extract_next_check_proposals,
)
from .incident_diagnosis_loop_state import (
    add_pass_to_state,
    create_initial_loop_state,
    increment_pass,
    record_planned_checks,
    stop_loop,
)
from .incident_diagnosis_loop_stops import (
    build_root_cause_candidate,
    check_budget_exhausted,
    check_low_confidence_no_progress,
    check_no_checks_proposed,
    check_no_safe_checks,
    check_root_cause_found,
    check_safety_blocked,
)

__all__ = [
    # Constants
    "LOOP_SCHEMA_VERSION",
    "DEFAULT_MAX_PASSES",
    "MIN_HIGH_CONFIDENCE_EVIDENCE",
    "MAX_MISSING_EVIDENCE_FOR_CREDIBLE",
    # Enums
    "LoopDecision",
    "StopReason",
    "Confidence",
    # Models
    "RootCauseCandidate",
    "DiagnosisPass",
    "LoopState",
    # State functions
    "create_initial_loop_state",
    "increment_pass",
    "add_pass_to_state",
    "stop_loop",
    "record_planned_checks",
    # Stop condition functions
    "build_root_cause_candidate",
    "check_root_cause_found",
    "check_budget_exhausted",
    "check_no_checks_proposed",
    "check_no_safe_checks",
    "check_low_confidence_no_progress",
    "check_safety_blocked",
    # Proposal extraction
    "extract_next_check_proposals",
    # Main planning function
    "plan_next_diagnosis_pass",
]
