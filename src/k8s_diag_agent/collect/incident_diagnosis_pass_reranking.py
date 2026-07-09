"""Pass reranking logic for automatic diagnosis loop.

This module contains:
- rerank_hypotheses(): Update hypothesis rankings based on evidence (bidirectional)

Design constraints:
- Pure functions only
- Bidirectional evidence logic
"""

from __future__ import annotations

from typing import Any


def rerank_hypotheses(
    hypotheses: list[dict[str, Any]],
    evidence_deltas: list[dict[str, Any]],
    executed_check_ids: set[str] | None = None,
    top_confidence_threshold: float = 0.78,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """Rerank hypotheses based on evidence deltas (bidirectional).

    Updates:
    - confidence: adjusted based on evidence (increase for support, decrease for falsification)
    - status: updated to supported|weakened|falsified based on evidence
    - evidence_for/evidence_against: appended with new evidence

    Bidirectional logic:
    - Supporting evidence: increases confidence, status -> supported
    - Falsifying evidence: decreases confidence, status -> weakened (or falsified if strong contradiction)
    - Strong contradiction: marks hypothesis as falsified (confidence drops below threshold)

    Args:
        hypotheses: Current hypotheses
        evidence_deltas: Evidence deltas from executed checks
        executed_check_ids: Set of already executed check IDs (for tracking)
        top_confidence_threshold: Threshold for confidence_threshold_reached stop

    Returns:
        Tuple of (updated_hypotheses, supported_ids, weakened_ids, falsified_ids)
    """
    updated: list[dict[str, Any]] = []
    supported: list[str] = []
    weakened: list[str] = []
    falsified: list[str] = []

    # Falsification threshold: if confidence drops below this, hypothesis is falsified
    FALSIFICATION_THRESHOLD = 0.25

    for hyp in hypotheses:
        evidence_for = list(hyp.get("evidence_for", []))
        evidence_against = list(hyp.get("evidence_against", []))
        confidence = float(hyp.get("confidence", 0.5))
        status = hyp.get("status", "open")
        candidate_class = hyp.get("candidate_class", "")

        # Evidence matching flags
        supporting_found = False
        falsifying_found = False

        # Check each evidence delta for impact
        for delta in evidence_deltas:
            check_id = delta.get("check_id", "")
            summary_lower = delta.get("summary", "").lower()
            signals = delta.get("signal_indicators", [])

            # Determine if evidence supports or falsifies
            supports = False
            falsifies = False

            if candidate_class == "crash_loop":
                if any(s in signals for s in ("signal:crash_detected", "signal:warning_or_error_detected")):
                    supports = True
                if "restart" in summary_lower and "count" in summary_lower:
                    supports = True
                if "restart" in summary_lower and "0" in summary_lower:
                    falsifies = True
                if "exit" in summary_lower and ("0" in summary_lower or "success" in summary_lower):
                    falsifies = True

            elif candidate_class == "image_pull_error":
                if "signal:image_pull_issue" in signals:
                    supports = True
                if "imagepull" in summary_lower or "pull" in summary_lower:
                    supports = True
                if "ready" in summary_lower and "running" in summary_lower:
                    falsifies = True

            elif candidate_class == "pending_pod":
                if "signal:scheduling_failure" in signals:
                    supports = True
                if "pending" in summary_lower or "unschedulable" in summary_lower:
                    supports = True
                if "running" in summary_lower or "succeeded" in summary_lower:
                    falsifies = True

            elif candidate_class == "deployment_unavailable":
                if "signal:readiness_failure" in signals:
                    supports = True
                if "available" in summary_lower and "replica" in summary_lower:
                    if "0" in summary_lower or "unavailable" in summary_lower:
                        supports = True
                if "available" in summary_lower and "desired" in summary_lower:
                    if "equal" in summary_lower or "match" in summary_lower:
                        falsifies = True

            elif candidate_class == "warning_event_burst":
                if "signal:warning_or_error_detected" in signals:
                    supports = True
                if "warning" in summary_lower and "event" in summary_lower:
                    supports = True
                if "no warning" in summary_lower or "0 warning" in summary_lower:
                    falsifies = True

            elif candidate_class == "node_not_ready":
                if "not ready" in summary_lower or "false" in summary_lower:
                    supports = True
                if "pressure" in summary_lower:
                    supports = True
                if "ready" in summary_lower and "true" in summary_lower:
                    falsifies = True

            elif candidate_class == "pvc_issue":
                if "pending" in summary_lower or "lost" in summary_lower:
                    supports = True
                if "bound" in summary_lower:
                    falsifies = True

            if supports:
                evidence_for.append(f"check:{check_id}")
                confidence = min(1.0, confidence + 0.08)
                supporting_found = True

            if falsifies:
                evidence_against.append(f"check:{check_id}")
                confidence = max(0.0, confidence - 0.15)
                falsifying_found = True

        # Determine final status
        hyp_id = hyp.get("hypothesis_id", "")
        if falsifying_found:
            if confidence < FALSIFICATION_THRESHOLD:
                status = "falsified"
                if hyp_id not in falsified:
                    falsified.append(hyp_id)
            else:
                status = "weakened"
                if hyp_id not in weakened:
                    weakened.append(hyp_id)
        elif supporting_found:
            status = "supported"
            if hyp_id not in supported:
                supported.append(hyp_id)

        # Bound evidence lists
        evidence_for = evidence_for[:8]
        evidence_against = evidence_against[:8]

        updated_hyp = dict(hyp)
        updated_hyp["evidence_for"] = evidence_for
        updated_hyp["evidence_against"] = evidence_against
        updated_hyp["confidence"] = round(confidence, 2)
        updated_hyp["status"] = status
        updated.append(updated_hyp)

    # Sort by confidence descending and reassign ranks
    updated.sort(key=lambda h: h.get("confidence", 0), reverse=True)
    for idx, hyp in enumerate(updated):
        hyp["rank"] = idx + 1

    return updated, supported, weakened, falsified


__all__ = ["rerank_hypotheses"]
