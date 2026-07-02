#!/usr/bin/env python3
"""Rendering and logging helpers for K8s multi-pass diagnosis phase.

This module contains functions for formatting and logging diagnosis
output. It separates UI rendering from business logic.
"""

from __future__ import annotations

from typing import Any

from scripts.k9b_lab_common_helpers import log


def log_phase_header() -> None:
    """Log the phase header."""
    log("=" * 60)
    log("PHASE P4c: Multi-pass K8s incident diagnosis")
    log("=" * 60)


def log_phase_footer(duration: float) -> None:
    """Log the phase footer.

    Args:
        duration: Phase duration in seconds
    """
    log("=" * 60)
    log("PHASE P4c: Diagnosis complete")
    log(f"  Duration: {duration:.1f}s")
    log("=" * 60)


def log_diagnosis_result(
    success: bool,
    evidence: dict[str, Any],
    term_checks: dict[str, bool],
) -> None:
    """Log diagnosis result summary.

    This function is outcome-aware: if p4c_outcome exists, it logs the normalized
    mode and failure_reasons only. For terminal_single_pass success, it omits
    legacy missing prose terms as validation failures.

    Args:
        success: Whether diagnosis succeeded
        evidence: Evidence dict with diagnosis results
        term_checks: Root cause term check results
    """
    # Use normalized p4c_outcome if available
    p4c_outcome = evidence.get("p4c_outcome")
    if p4c_outcome:
        outcome_success = p4c_outcome.get("success", evidence.get("validation_success", success))
        outcome_mode = p4c_outcome.get("mode", "unknown")
        outcome_pass_count = p4c_outcome.get("pass_count", 0)
        outcome_pass_run_ids = p4c_outcome.get("pass_run_ids", [])
        outcome_failure_reasons = p4c_outcome.get("failure_reasons", [])
        
        # Log PASSED only when success is true, FAILED only when false
        if outcome_success:
            # "terminal" prefix only for terminal_single_pass mode
            if outcome_mode == "terminal_single_pass":
                log("  P4c diagnosis PASSED (terminal single-pass outcome)")
            else:
                log(f"  P4c diagnosis PASSED ({outcome_mode} outcome)")
        else:
            log(f"  P4c diagnosis FAILED ({outcome_mode} outcome)")
        
        log(f"  Success: {outcome_success}")
        log(f"  Incident ID: {evidence.get('incident_id', 'unknown')}")
        log(f"  Pass count: {outcome_pass_count}")
        log(f"  Pass run IDs: {outcome_pass_run_ids}")
        log(f"  Review artifact paths: {p4c_outcome.get('review_artifact_paths', [])}")
        
        if outcome_success:
            # Success: no failure reasons to display
            log(f"  Root cause matches: {term_checks}")
            log("  Failure reason: none")
        else:
            # Failure: show normalized failure reasons only
            log(f"  Root cause matches: {term_checks}")
            if outcome_failure_reasons:
                log(f"  Failure reasons: {outcome_failure_reasons}")
            else:
                log(f"  Failure reason: {evidence.get('failure_reason', 'unknown')}")
    else:
        # Legacy path: no normalized outcome available
        log(f"  Success: {evidence.get('validation_success', success)}")
        log(f"  Incident ID: {evidence.get('incident_id', 'unknown')}")
        log(f"  Pass count: {evidence.get('pass_count', 0)}")
        log(f"  Pass run IDs: {evidence.get('pass_run_ids', [])}")
        log(f"  Root cause matches: {term_checks}")
        log(f"  Failure reason: {evidence.get('failure_reason', 'none')}")


def log_step(step_num: int, description: str) -> None:
    """Log a step header.

    Args:
        step_num: Step number
        description: Step description
    """
    log(f"Step {step_num}: {description}...")


def log_step_result(description: str) -> None:
    """Log a step result.

    Args:
        description: Result description
    """
    log(f"  {description}")


def log_term_check(term: str, found: bool) -> None:
    """Log a root cause term check result.

    Args:
        term: Term name
        found: Whether term was found
    """
    log(f"  {term}: {'FOUND' if found else 'MISSING'}")


def log_validation_result(success: bool, message: str) -> None:
    """Log validation result.

    Args:
        success: Whether validation passed
        message: Validation message
    """
    if success:
        log(f"Validation PASSED: {message}")
    else:
        log(f"Validation FAILED: {message}")


def log_error(error_msg: str) -> None:
    """Log an error message.

    Args:
        error_msg: Error message
    """
    log(f"ERROR: {error_msg}")


def log_diagnosis_progress(
    incident_id: str,
    target_namespace: str,
    diagnosis_started: float | None,
) -> None:
    """Log diagnosis progress info.

    Args:
        incident_id: Incident being diagnosed
        target_namespace: Target namespace
        diagnosis_started: Start timestamp
    """
    log(f"Target: diagnose shipping incident in {target_namespace}")
    if diagnosis_started:
        log(f"Diagnosis started at: {diagnosis_started}")
