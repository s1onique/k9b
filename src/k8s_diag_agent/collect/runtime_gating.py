"""Check gating logic for pre-execution enforcement.

This module provides gate_checks() which enforces policy BEFORE execution:
- Mutating check rejection
- Sensitive read rejection
- Duplicate fingerprint rejection

CRITICAL: Rejected checks are NEVER passed back for execution.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from k8s_diag_agent.collect.incident_diagnosis_loop_gates import (
    is_mutating_check as _is_mutating_check,
)
from k8s_diag_agent.collect.incident_diagnosis_loop_gates import (
    is_sensitive_read_check as _is_sensitive_read_check,
)
from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
)

from .incident_diagnosis_loop_runtime_utils import compute_fingerprint

if TYPE_CHECKING:
    pass


@dataclass
class GateSummary:
    """Summary of gating decisions for a pass.
    
    This summarizes what was proposed vs accepted/rejected in a single pass.
    """

    proposed: int
    accepted: int
    rejected_mutating: int
    rejected_sensitive: int
    rejected_duplicate: int
    accepted_checks: list[dict[str, Any]]
    rejected_checks: list[dict[str, Any]]
    # Explicit fingerprint tracking for this pass
    accepted_fingerprints: list[str] = field(default_factory=list)
    rejected_fingerprints: list[str] = field(default_factory=list)


def gate_checks(
    proposed_checks: Sequence[Mapping[str, object]],
    policy: DiagnosisLoopPolicy,
    seen_fingerprints: set[str],
) -> tuple[GateSummary, list[str]]:
    """Gate proposed checks against policy.
    
    CRITICAL: This function enforces policy BEFORE execution.
    Rejected checks are NEVER passed back for execution.

    Applies in order:
    1. Mutating check rejection (unless policy allows)
    2. Sensitive read rejection (unless policy allows)  
    3. Duplicate fingerprint rejection (checks against seen_fingerprints)

    Args:
        proposed_checks: Checks proposed by the planner
        policy: The DiagnosisLoopPolicy to enforce
        seen_fingerprints: Set of fingerprints already seen (mutated in place)
            - DUPLICATE fingerprints are added to this set
            - Accepted fingerprints are NOT added (handled by caller)

    Returns:
        Tuple of (GateSummary, list of accepted fingerprints for this pass)
        The caller must add accepted_fingerprints to seen_fingerprints.
    """
    accepted_checks: list[dict[str, Any]] = []
    rejected_checks: list[dict[str, Any]] = []
    accepted_fingerprints: list[str] = []
    rejected_fingerprints: list[str] = []
    rejected_mutating = 0
    rejected_sensitive = 0
    rejected_duplicate = 0

    for check in proposed_checks:
        check_id = str(check.get("check_id", "unknown"))
        check_dict = dict(check)

        # Compute fingerprint upfront for all checks
        fingerprint = compute_fingerprint(check)

        # Check 1: Mutating? (normalize underscores to spaces for pattern matching)
        normalized_check_id = check_id.replace("_", " ")
        is_mutating = _is_mutating_check(normalized_check_id) or _is_mutating_check(check_id) or _is_mutating_check(json.dumps(check))
        if is_mutating:
            if not policy.allow_mutating_checks:
                rejected_checks.append({**check_dict, "rejection_reason": "mutating_check_rejected", "is_unsafe": True})
                rejected_fingerprints.append(fingerprint)
                rejected_mutating += 1
                continue

        # Check 2: Sensitive read? (normalize underscores to spaces for pattern matching)
        is_sensitive = _is_sensitive_read_check(normalized_check_id) or _is_sensitive_read_check(check_id) or _is_sensitive_read_check(json.dumps(check))
        if is_sensitive:
            if not policy.allow_sensitive_reads:
                rejected_checks.append({**check_dict, "rejection_reason": "sensitive_read_denied", "is_sensitive": True})
                rejected_fingerprints.append(fingerprint)
                rejected_sensitive += 1
                continue

        # Check 3: Duplicate fingerprint?
        if fingerprint in seen_fingerprints:
            rejected_checks.append({**check_dict, "rejection_reason": "duplicate_check_fingerprint", "duplicate_fingerprint": fingerprint})
            rejected_fingerprints.append(fingerprint)
            rejected_duplicate += 1
            continue

        # ACCEPTED: Add fingerprint to seen set immediately
        seen_fingerprints.add(fingerprint)
        accepted_checks.append(check_dict)
        accepted_fingerprints.append(fingerprint)

    return (
        GateSummary(
            proposed=len(proposed_checks),
            accepted=len(accepted_checks),
            rejected_mutating=rejected_mutating,
            rejected_sensitive=rejected_sensitive,
            rejected_duplicate=rejected_duplicate,
            accepted_checks=accepted_checks,
            rejected_checks=rejected_checks,
            accepted_fingerprints=accepted_fingerprints,
            rejected_fingerprints=rejected_fingerprints,
        ),
        accepted_fingerprints,
    )


__all__ = ["GateSummary", "gate_checks"]
