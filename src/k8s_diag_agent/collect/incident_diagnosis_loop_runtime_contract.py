"""Contract definitions for the diagnosis loop runtime.

This module re-exports contract/state types from related modules for
a stable public import surface.

Re-exports:
- LoopRuntimeState: Runtime state across passes
- RUNTIME_SCHEMA_VERSION: Schema version constant
- PASS_ARTIFACT_FIELDS: Required artifact fields
- DiagnosisLoopPolicy: Policy configuration
- LoopStopReason: Typed loop stop reasons
"""
from __future__ import annotations

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    PASS_ARTIFACT_FIELDS,
    DiagnosisLoopPolicy,
    LoopStopReason,
)
from k8s_diag_agent.collect.runtime_state import (
    RUNTIME_SCHEMA_VERSION,
    LoopRuntimeState,
)

__all__ = [
    # State
    "LoopRuntimeState",
    "RUNTIME_SCHEMA_VERSION",
    # Policy
    "DiagnosisLoopPolicy",
    "LoopStopReason",
    # Contracts
    "PASS_ARTIFACT_FIELDS",
]
