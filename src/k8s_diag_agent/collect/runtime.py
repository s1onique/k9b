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

__all__ = [
    "run_policy_enforced_loop_pass",
    "run_policy_enforced_loop",
    "gate_checks",
    "build_policy_enforced_pass_artifact",
    "LoopRuntimeState",
    "GateSummary",
    "RUNTIME_SCHEMA_VERSION",
    "P4C_DIAGNOSIS_SUBDIR",
    "P4C_LOOP_PASSES_SUBDIR",
]
