"""Diagnosis loop pass artifacts - re-export module.

This module re-exports the public API from the split loader and writer modules
for backward compatibility.

Split modules:
- incident_diagnosis_loop_pass_artifacts_loader: Loading artifacts
- incident_diagnosis_loop_pass_artifacts_writer: Writing artifacts
"""

from __future__ import annotations

# Re-export all public API from loader module
from .incident_diagnosis_loop_pass_artifacts_loader import (
    DEFAULT_MAX_DIAGNOSIS_LOOP_PASS_ARTIFACTS,
    is_safe_run_id,
    load_diagnosis_loop_pass_artifacts_for_incident,
)

# Re-export all public API from writer module
from .incident_diagnosis_loop_pass_artifacts_writer import (
    ARTIFACT_SCHEMA_VERSION,
    write_diagnosis_loop_pass_artifact,
)

__all__ = [
    # Writer
    "write_diagnosis_loop_pass_artifact",
    "ARTIFACT_SCHEMA_VERSION",
    # Loader
    "load_diagnosis_loop_pass_artifacts_for_incident",
    "is_safe_run_id",
    "DEFAULT_MAX_DIAGNOSIS_LOOP_PASS_ARTIFACTS",
]
