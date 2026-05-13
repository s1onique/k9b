"""Review-enrichment serialization functions for the operator UI.

This module contains serializer functions for review-enrichment-related payloads:
- Review enrichment data payload
- Review enrichment status payload

Extracted from api.py to establish a clean separation of concerns.
These functions are re-exported from api.py for backward compatibility.

Ownership reminder:
    - Payload TypedDict classes live in api_payloads.py.
    - Serializer functions live here.
    - api.py is the public serialization surface.

Security note:
    All operator-facing text fields are sanitized at serialization boundary
    to prevent internal context markers like "in-cluster" from leaking to
    the operator UI. This includes summary, triageOrder, topConcerns,
    evidenceGaps, nextChecks, and focusNotes.
"""

from __future__ import annotations

from typing import cast

from ..security.kubectl_context import (
    is_internal_kube_marker,
    sanitize_kubectl_display_command,
    sanitize_operator_text,
)
from .api_payloads import (
    AlertmanagerEvidenceReferencePayload,
    ReviewEnrichmentPayload,
    ReviewEnrichmentStatusPayload,
)
from .model import (
    ReviewEnrichmentStatusView,
    ReviewEnrichmentView,
)


def _sanitize_text_field(value: str | None) -> str | None:
    """Sanitize a single text field to prevent internal marker leaks.

    Uses sanitize_operator_text() to handle both:
    1. Command-like strings (kubectl --context in-cluster) → context removed
    2. Embedded markers in prose (in-cluster is degraded) → "the cluster"

    Args:
        value: The text value to sanitize.

    Returns:
        Sanitized text or None if input is None/empty.
    """
    if value is None:
        return None
    return sanitize_operator_text(value)


def _is_safe_cluster_label(label: str | None) -> bool:
    """Check if a cluster label is safe for operator-facing display.

    Internal execution markers like "in-cluster" are not safe and should
    be filtered out entirely.

    Args:
        label: The cluster label to check.

    Returns:
        True if the label is safe (not an internal marker), False otherwise.
    """
    if label is None:
        return True
    return not is_internal_kube_marker(label)


def _sanitize_command_list(commands: tuple[str, ...]) -> list[str]:
    """Sanitize a list of kubectl commands for operator display.

    Removes internal context markers like "--context in-cluster" from
    each command string.

    Args:
        commands: Tuple of kubectl command strings.

    Returns:
        List of sanitized command strings.
    """
    result: list[str] = []
    for cmd in commands:
        sanitized = sanitize_kubectl_display_command(cmd)
        if sanitized:
            result.append(sanitized)
    return result


def _serialize_review_enrichment(view: ReviewEnrichmentView | None) -> ReviewEnrichmentPayload | None:
    """Serialize review enrichment view to payload dict.

    All operator-facing text fields are sanitized to prevent internal
    context markers like "in-cluster" from leaking to the operator UI.
    """
    if not view:
        return None
    # Serialize alertmanager evidence references if present
    alertmanager_refs: list[AlertmanagerEvidenceReferencePayload] | None = None
    if view.alertmanager_evidence_references:
        refs_list: list[AlertmanagerEvidenceReferencePayload] = []
        for ref in view.alertmanager_evidence_references:
            # _sanitize_text_field preserves str values from non-None inputs
            # The view model has cluster: str and reason: str (non-optional)
            sanitized_cluster = _sanitize_text_field(ref.cluster)
            sanitized_reason = _sanitize_text_field(ref.reason)
            # Both should be non-None str since inputs are non-None str
            assert sanitized_cluster is not None, "sanitize_text_field returned None for non-None str cluster"
            assert sanitized_reason is not None, "sanitize_text_field returned None for non-None str reason"
            refs_list.append({
                "cluster": sanitized_cluster,
                "matchedDimensions": list(ref.matched_dimensions),
                "reason": sanitized_reason,
                "usedFor": ref.used_for,
            })
        alertmanager_refs = refs_list
    return cast(ReviewEnrichmentPayload, {
        "status": view.status,
        "provider": view.provider,
        "timestamp": view.timestamp,
        # Sanitize summary to prevent "in-cluster is in a degraded state" leaks
        "summary": _sanitize_text_field(view.summary),
        # Filter out internal cluster labels like "in-cluster" from triageOrder
        "triageOrder": [label for label in view.triage_order if _is_safe_cluster_label(label)],
        # Sanitize topConcerns prose text
        "topConcerns": [_sanitize_text_field(concern) for concern in view.top_concerns if concern],
        # Sanitize evidenceGaps prose text
        "evidenceGaps": [_sanitize_text_field(gap) for gap in view.evidence_gaps if gap],
        # Sanitize nextChecks kubectl commands (remove --context in-cluster)
        "nextChecks": _sanitize_command_list(view.next_checks),
        # Sanitize focusNotes prose text
        "focusNotes": [_sanitize_text_field(note) for note in view.focus_notes if note],
        "alertmanagerEvidenceReferences": alertmanager_refs,
        "artifactPath": view.artifact_path,
        # Sanitize errorSummary and skipReason to prevent internal markers from leaking
        "errorSummary": _sanitize_text_field(view.error_summary),
        "skipReason": _sanitize_text_field(view.skip_reason),
    })


def _serialize_review_enrichment_status(
    view: ReviewEnrichmentStatusView | None,
) -> ReviewEnrichmentStatusPayload | None:
    """Serialize review enrichment status view to payload dict."""
    if not view:
        return None
    return {
        "status": view.status,
        "reason": view.reason,
        "provider": view.provider,
        "policyEnabled": view.policy_enabled,
        "providerConfigured": view.provider_configured,
        "adapterAvailable": view.adapter_available,
        "runEnabled": view.run_enabled,
        "runProvider": view.run_provider,
    }
