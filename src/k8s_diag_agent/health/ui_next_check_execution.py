"""Next-check execution history and classification logic for UI rendering.

This module is a compatibility facade that re-exports all public names
from the split modules:
- ui_next_check_execution_history: history building and record types
- ui_next_check_execution_classification: failure classification constants and helpers

Existing callers continue to import from this module without changes.
"""

from __future__ import annotations

# Re-export classification module - failure classification constants and helpers
from .ui_next_check_execution_classification import (
    _FAILURE_ACTIONS,
    _FAILURE_CLASS_APPROVAL_MISSING,
    _FAILURE_CLASS_BLOCKED_BY_GATING,
    _FAILURE_CLASS_COMMAND_FAILED,
    _FAILURE_CLASS_COMMAND_UNAVAILABLE,
    _FAILURE_CLASS_CONTEXT_UNAVAILABLE,
    _FAILURE_CLASS_TIMED_OUT,
    _FAILURE_CLASS_UNKNOWN,
    _FAILURE_DEFAULT_SUMMARIES,
    _classify_blocked_candidate,
)

# Re-export history module - execution history assembly and record types
from .ui_next_check_execution_history import (
    FailureFollowUp,
    NextCheckExecutionRecord,
    ResultInterpretation,
    _apply_failure_follow_up,
    _apply_result_interpretation,
    _build_next_check_execution_history,
    _classify_execution_failure,
    _classify_execution_success,
    _collect_next_check_execution_records,
    _derive_outcome_status,
    _determine_execution_state,
    _latest_outcome_artifact,
    _load_usefulness_review_artifacts,
)

__all__ = [
    # History module
    "_build_next_check_execution_history",
    "_classify_execution_success",
    "_classify_execution_failure",
    "_apply_result_interpretation",
    "_apply_failure_follow_up",
    "_collect_next_check_execution_records",
    "_load_usefulness_review_artifacts",
    "_derive_outcome_status",
    "_determine_execution_state",
    "_latest_outcome_artifact",
    "NextCheckExecutionRecord",
    "ResultInterpretation",
    "FailureFollowUp",
    # Classification module
    "_classify_blocked_candidate",
    "_FAILURE_CLASS_TIMED_OUT",
    "_FAILURE_CLASS_COMMAND_UNAVAILABLE",
    "_FAILURE_CLASS_CONTEXT_UNAVAILABLE",
    "_FAILURE_CLASS_COMMAND_FAILED",
    "_FAILURE_CLASS_BLOCKED_BY_GATING",
    "_FAILURE_CLASS_APPROVAL_MISSING",
    "_FAILURE_CLASS_UNKNOWN",
    "_FAILURE_ACTIONS",
    "_FAILURE_DEFAULT_SUMMARIES",
]
