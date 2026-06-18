"""Read-only check result artifacts - re-export module.

This module re-exports the public API from the split loader and writer modules
for backward compatibility.

Split modules:
- incident_read_only_check_artifacts_loader: Loading artifacts
- incident_read_only_check_artifacts_writer: Writing artifacts
"""

from __future__ import annotations

# Re-export all public API from loader module
from .incident_read_only_check_artifacts_loader import (
    DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS,
    DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS,
    DEFAULT_MAX_CHECK_RESULTS_PER_ARTIFACT,
    DEFAULT_MAX_READ_ONLY_CHECK_ARTIFACTS,
    is_safe_run_id,
    load_read_only_check_result_artifacts_for_incident,
)

# Re-export all public API from writer module
from .incident_read_only_check_artifacts_writer import (
    ARTIFACT_SCHEMA_VERSION,
    write_read_only_check_result_artifact,
)

__all__ = [
    # Writer
    "write_read_only_check_result_artifact",
    "ARTIFACT_SCHEMA_VERSION",
    # Loader
    "load_read_only_check_result_artifacts_for_incident",
    "is_safe_run_id",
    "DEFAULT_MAX_READ_ONLY_CHECK_ARTIFACTS",
    "DEFAULT_MAX_CHECK_RESULTS_PER_ARTIFACT",
    "DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS",
    "DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS",
]
