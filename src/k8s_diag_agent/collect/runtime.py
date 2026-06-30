"""Alias for incident_diagnosis_loop_runtime for backward compatibility."""
from .incident_diagnosis_loop_runtime import (
    P4C_DIAGNOSIS_SUBDIR,
    P4C_LOOP_PASSES_SUBDIR,
    RUNTIME_SCHEMA_VERSION,
    GateSummary,
    LoopRuntimeState,
    build_policy_enforced_pass_artifact,
    gate_checks,
    run_policy_enforced_loop,
    run_policy_enforced_loop_pass,
)

# Re-export from new focused modules for compatibility
from .incident_diagnosis_loop_runtime_contract import (
    PASS_ARTIFACT_FIELDS,
    DiagnosisLoopPolicy,
    LoopStopReason,
)
from .incident_diagnosis_loop_runtime_rendering import (
    render_gate_summary,
    render_loop_summary,
    render_runtime_summary,
)

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
