"""Runtime envelope that wraps orchestrator with DiagnosisLoopPolicy enforcement.

This module provides the outer controller layer that:
- Owns the DiagnosisLoopPolicy hard budget limits
- Gates checks BEFORE execution (mutating, sensitive, duplicates)
- Emits pass artifacts with exact PASS_ARTIFACT_FIELDS
- Maps loop decisions to typed LoopStopReason

Design constraints:
- Splits planning from execution: plan first, gate, then execute
- Does NOT replace NextCheckPolicy (planner semantic layer)
- Emits artifacts matching PASS_ARTIFACT_FIELDS
- Deterministic with injected timestamps
- Explicit OTel span boundaries using `with` blocks
- Pre-execution enforcement: rejected checks are NEVER executed

This module is a thin façade that re-exports from focused implementation modules.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    LoopStopReason,
)
from .incident_diagnosis_loop_runtime_contract import (
    PASS_ARTIFACT_FIELDS,
)

# Re-export core functions from focused implementation modules
from .incident_diagnosis_loop_runtime_multi_pass import run_policy_enforced_loop
from .incident_diagnosis_loop_runtime_rendering import (
    render_gate_summary,
    render_loop_summary,
    render_runtime_summary,
)
from .incident_diagnosis_loop_runtime_single_pass import run_policy_enforced_loop_pass
from .runtime_artifacts import (
    P4C_DIAGNOSIS_SUBDIR,
    P4C_LOOP_PASSES_SUBDIR,
    RUNTIME_SCHEMA_VERSION,
    build_policy_enforced_pass_artifact,
)
from .runtime_gating import GateSummary, gate_checks
from .runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    pass

__all__ = [
    # Core runtime functions
    "run_policy_enforced_loop_pass",
    "run_policy_enforced_loop",
    # Gating
    "gate_checks",
    "GateSummary",
    # Artifact building
    "build_policy_enforced_pass_artifact",
    # State
    "LoopRuntimeState",
    "RUNTIME_SCHEMA_VERSION",
    # Constants
    "P4C_DIAGNOSIS_SUBDIR",
    "P4C_LOOP_PASSES_SUBDIR",
    # Contract types
    "DiagnosisLoopPolicy",
    "LoopStopReason",
    "PASS_ARTIFACT_FIELDS",
    # Rendering helpers
    "render_runtime_summary",
    "render_loop_summary",
    "render_gate_summary",
]
