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

    Args:
        success: Whether diagnosis succeeded
        evidence: Evidence dict with diagnosis results
        term_checks: Root cause term check results
    """
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
