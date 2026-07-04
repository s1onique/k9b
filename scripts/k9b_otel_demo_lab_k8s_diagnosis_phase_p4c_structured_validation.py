"""Structured scheduling root-cause validation for P4c diagnosis.

This module provides the canonical structured evidence validation path for P4c.
Structured evidence is the authoritative source when available; prose fallback is legacy-only.

Design rules:
- Structured scheduling evidence is canonical when present
- Prose fallback is legacy-only, used only when structured evidence is absent
- Do not allow Step 6b FAILED + normalized outcome SUCCESS
"""

from __future__ import annotations

from typing import Any


def _validate_p4c_root_cause_structured(
    evidence: dict[str, Any],
) -> tuple[bool, str | None, str]:
    """Validate P4c root-cause using structured scheduling evidence.

    This is the canonical validation path for P4c. Structured evidence is the
    authoritative source when available; prose fallback is legacy-only.

    Args:
        evidence: Evidence dict

    Returns:
        Tuple of (success, validation_source, reason)
        - validation_source: "structured_scheduling_evidence", "prose_fallback", or "failed"
    """
    # Late import to avoid circular imports at module level
    from scripts.k9b_otel_demo_lab_k8s_verdicts import (
        SCHEDULING_ROOT_CAUSE_MARKERS,
        validate_unschedulable_shipping_root_cause,
    )

    scheduling_evidence_raw = evidence.get("scheduling_evidence")

    if isinstance(scheduling_evidence_raw, dict) and scheduling_evidence_raw:
        # PRIMARY PATH: Use structured scheduling evidence validation
        try:
            from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
                SchedulingRootCauseEvidence,
                check_scheduling_root_cause_complete,
            )

            scheduling_evidence = SchedulingRootCauseEvidence.from_dict(scheduling_evidence_raw)

            if check_scheduling_root_cause_complete(scheduling_evidence):
                return (
                    True,
                    "structured_scheduling_evidence",
                    f"complete scheduling evidence: {scheduling_evidence.root_cause_summary[:80]}...",
                )

            # Structured evidence present but incomplete - do NOT silently fall back to prose.
            # This ensures the new durable path is working correctly.
            return (
                False,
                "failed",
                f"structured scheduling evidence incomplete: failed_scheduling={scheduling_evidence.failed_scheduling}, "
                f"unschedulable={scheduling_evidence.unschedulable}, selector_key={scheduling_evidence.selector_key}",
            )
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            # Structured evidence is present but malformed - do NOT fall through to prose fallback.
            # This prevents masking: malformed structured evidence + lucky prose markers = pass.
            # Import logging late to avoid circular imports
            try:
                from scripts.k9b_otel_demo_lab_k8s_diagnosis_render import log as _log

                _log(f"  WARNING: Could not parse structured scheduling_evidence: {e}")
            except ImportError:
                pass

            return (
                False,
                "failed",
                f"structured scheduling evidence malformed: {e}",
            )

    # FALLBACK: Legacy prose-only validation when structured evidence is absent.
    # This is for backward compatibility with older artifacts or non-structured scenarios.
    # NOT the primary path for P4c scheduling diagnosis.
    root_cause_verdict = validate_unschedulable_shipping_root_cause(evidence)

    if root_cause_verdict.success:
        return (
            True,
            "prose_fallback",
            f"prose scheduling markers found: {list(root_cause_verdict.matched_evidence)}",
        )

    return (
        False,
        "failed",
        f"missing scheduling root-cause evidence, required markers: {list(SCHEDULING_ROOT_CAUSE_MARKERS)}",
    )


__all__ = [
    "_validate_p4c_root_cause_structured",
]
