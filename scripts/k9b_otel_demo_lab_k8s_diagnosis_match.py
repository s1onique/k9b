#!/usr/bin/env python3
"""Matching and validation helpers for K8s multi-pass diagnosis.

This module provides helper functions for:
- Matching root-cause terms in diagnosis output
- Validating multi-pass requirements
- Checking read-only contract violations
"""

from __future__ import annotations

import re
from typing import Any

from .k9b_otel_demo_lab_k8s_diagnosis_constants import (
    FORBIDDEN_MUTATING_PATTERNS,
    MIN_REQUIRED_PASSES,
)


def _check_read_only_contract(executed_checks: list[str]) -> tuple[bool, list[str]]:
    """Check if executed checks violate read-only contract.
    
    Args:
        executed_checks: List of executed check identifiers or command strings
        
    Returns:
        Tuple of (is_read_only, violations)
    """
    violations = []
    
    if not executed_checks:
        return True, []
    
    for check in executed_checks:
        check_str = str(check).lower()
        for pattern in FORBIDDEN_MUTATING_PATTERNS:
            if pattern.lower() in check_str:
                violations.append(f"Mutating pattern '{pattern}' found in check: {check}")
    
    return len(violations) == 0, violations


def _check_root_cause_terms(diagnosis_text: str) -> dict[str, bool]:
    """Check if diagnosis contains required root-cause terms.
    
    Args:
        diagnosis_text: Final diagnosis text to check
        
    Returns:
        Dict mapping term names to whether they were found
    """
    text_lower = diagnosis_text.lower()
    
    return {
        "mentions_shipping": "shipping" in text_lower,
        "mentions_node_selector": any(
            p in text_lower for p in ["nodeselector", "node selector"]
        ),
        "mentions_selector_key": "k9b.dev/otel-lab-node" in text_lower,
        "mentions_selector_value": "missing" in text_lower,
        "mentions_no_matching_node": any(
            re.search(p, text_lower) for p in [
                r"no\s+(matching\s+)?node",
                r"no\s+node.*label",
                r"cannot\s+schedule",
                r"unschedulable",
            ]
        ),
    }


def _validate_diagnosis_evidence(evidence: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate diagnosis evidence contains required fields.
    
    Note: This only validates structure. For semantic validation
    (pass count, root cause terms, read-only), use the individual
    check functions.
    
    Args:
        evidence: Diagnosis evidence dict
        
    Returns:
        Tuple of (is_valid, list_of_failures)
    """
    failures: list[str] = []
    
    # Check required fields
    required_fields = [
        "phase",
        "incident_id",
        "pass_count",
        "read_only",
        "root_cause_summary",
    ]
    
    for field in required_fields:
        if field not in evidence:
            failures.append(f"Missing required field: {field}")
    
    return len(failures) == 0, failures


def check_insufficient_passes(evidence: dict[str, Any]) -> tuple[bool, int, int]:
    """Check if diagnosis has minimum required passes.
    
    Args:
        evidence: Diagnosis evidence dict
        
    Returns:
        Tuple of (has_minimum_passes, pass_count, min_required)
    """
    pass_count = evidence.get("pass_count", 0)
    return pass_count >= MIN_REQUIRED_PASSES, pass_count, MIN_REQUIRED_PASSES


def check_missing_root_cause_terms(evidence: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    """Check if diagnosis contains all required root-cause terms.
    
    Args:
        evidence: Diagnosis evidence dict
        
    Returns:
        Tuple of (all_present, term_checks_dict)
    """
    root_cause_summary = str(evidence.get("root_cause_summary", ""))
    term_checks = _check_root_cause_terms(root_cause_summary)
    missing = [k for k, v in term_checks.items() if not v]
    return len(missing) == 0, term_checks


def check_read_only_violations(evidence: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check if diagnosis contains mutating commands.
    
    Args:
        evidence: Diagnosis evidence dict
        
    Returns:
        Tuple of (is_read_only, list_of_violations)
    """
    executed_checks = evidence.get("executed_checks", [])
    return _check_read_only_contract(executed_checks)


def _validate_discovery_evidence(evidence: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate P3c discovery evidence is present and valid.
    
    Args:
        evidence: P3c detection evidence dict
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not evidence:
        return False, "P3c discovery evidence is empty"
    
    if not evidence.get("discovery_success"):
        return False, f"P3c discovery failed: {evidence.get('failure_reason', 'unknown')}"
    
    if not evidence.get("validation_success"):
        return False, "P3c validation failed"
    
    if not evidence.get("incident_id"):
        return False, "P3c discovery missing incident_id"
    
    return True, None


def _check_pass_count(evidence: dict[str, Any]) -> tuple[bool, int]:
    """Check if diagnosis has minimum required passes.
    
    Args:
        evidence: Diagnosis evidence dict
        
    Returns:
        Tuple of (has_minimum_passes, pass_count)
    """
    pass_count = evidence.get("pass_count", 0)
    return pass_count >= MIN_REQUIRED_PASSES, pass_count


def _extract_pass_run_ids(evidence: dict[str, Any]) -> list[str]:
    """Extract pass run IDs from diagnosis evidence.
    
    Args:
        evidence: Diagnosis evidence dict
        
    Returns:
        List of run IDs for each pass
    """
    pass_run_ids = evidence.get("pass_run_ids", [])
    if isinstance(pass_run_ids, list):
        return pass_run_ids
    
    # Try to extract from loop summary
    loop_summary = evidence.get("loop_summary", {})
    if isinstance(loop_summary, dict):
        result_ids: list[str] = loop_summary.get("pass_run_ids") or []
        return result_ids
    
    return []
