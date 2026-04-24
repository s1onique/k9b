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
"""

from __future__ import annotations

from .api_payloads import (
    AlertmanagerEvidenceReferencePayload,
    ReviewEnrichmentPayload,
    ReviewEnrichmentStatusPayload,
)
from .model import (
    ReviewEnrichmentStatusView,
    ReviewEnrichmentView,
)


def _serialize_review_enrichment(view: ReviewEnrichmentView | None) -> ReviewEnrichmentPayload | None:
    """Serialize review enrichment view to payload dict."""
    if not view:
        return None
    # Serialize alertmanager evidence references if present
    alertmanager_refs: list[AlertmanagerEvidenceReferencePayload] | None = None
    if view.alertmanager_evidence_references:
        alertmanager_refs = [
            {
                "cluster": ref.cluster,
                "matchedDimensions": list(ref.matched_dimensions),
                "reason": ref.reason,
                "usedFor": ref.used_for,
            }
            for ref in view.alertmanager_evidence_references
        ]
    return {
        "status": view.status,
        "provider": view.provider,
        "timestamp": view.timestamp,
        "summary": view.summary,
        "triageOrder": list(view.triage_order),
        "topConcerns": list(view.top_concerns),
        "evidenceGaps": list(view.evidence_gaps),
        "nextChecks": list(view.next_checks),
        "focusNotes": list(view.focus_notes),
        "alertmanagerEvidenceReferences": alertmanager_refs,
        "artifactPath": view.artifact_path,
        "errorSummary": view.error_summary,
        "skipReason": view.skip_reason,
    }


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
