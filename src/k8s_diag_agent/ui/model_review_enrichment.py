"""View models for review enrichment UI layer.

This module contains review-enrichment-related view model dataclasses and builders
extracted from model.py. It exists to enable incremental modularization without
changing behavior.

Dependency direction:
- model_review_enrichment.py -> model_primitives.py
- model_review_enrichment.py -> model_alertmanager.py (for AlertmanagerEvidenceReferenceView)

model.py imports from model_review_enrichment.py for re-export compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .model_alertmanager import (
    AlertmanagerEvidenceReferenceView,
    _build_alertmanager_evidence_reference_view,
)
from .model_primitives import (
    _coerce_optional_bool,
    _coerce_optional_str,
    _coerce_sequence,
    _coerce_str,
)


@dataclass(frozen=True)
class ReviewEnrichmentStatusView:
    """View model for review enrichment status."""
    status: str
    reason: str | None
    provider: str | None
    policy_enabled: bool
    provider_configured: bool
    adapter_available: bool | None
    run_enabled: bool | None = None
    run_provider: str | None = None


@dataclass(frozen=True)
class ReviewEnrichmentView:
    """View model for review enrichment."""
    status: str
    provider: str | None
    timestamp: str | None
    summary: str | None
    triage_order: tuple[str, ...]
    top_concerns: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    next_checks: tuple[str, ...]
    focus_notes: tuple[str, ...]
    alertmanager_evidence_references: tuple[AlertmanagerEvidenceReferenceView, ...]
    artifact_path: str | None
    error_summary: str | None
    skip_reason: str | None


def _build_review_enrichment_view(raw: object | None) -> ReviewEnrichmentView | None:
    """Build ReviewEnrichmentView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return None
    triage = raw.get("triageOrder") or raw.get("triage_order")
    concerns = raw.get("topConcerns") or raw.get("top_concerns")
    gaps = raw.get("evidenceGaps") or raw.get("evidence_gaps")
    checks = raw.get("nextChecks") or raw.get("next_checks")
    focus = raw.get("focusNotes") or raw.get("focus_notes")

    # Extract alertmanager evidence references
    am_refs_raw = raw.get("alertmanagerEvidenceReferences") or raw.get("alertmanager_evidence_references")
    am_refs: tuple[AlertmanagerEvidenceReferenceView, ...] = ()
    if isinstance(am_refs_raw, Sequence) and not isinstance(am_refs_raw, str | bytes):
        am_refs = tuple(
            _build_alertmanager_evidence_reference_view(entry)
            for entry in am_refs_raw
            if isinstance(entry, Mapping)
        )

    return ReviewEnrichmentView(
        status=_coerce_str(raw.get("status")),
        provider=_coerce_optional_str(raw.get("provider")),
        timestamp=_coerce_optional_str(raw.get("timestamp")),
        summary=_coerce_optional_str(raw.get("summary")),
        triage_order=_coerce_sequence(triage),
        top_concerns=_coerce_sequence(concerns),
        evidence_gaps=_coerce_sequence(gaps),
        next_checks=_coerce_sequence(checks),
        focus_notes=_coerce_sequence(focus),
        alertmanager_evidence_references=am_refs,
        artifact_path=_coerce_optional_str(raw.get("artifactPath")),
        error_summary=_coerce_optional_str(raw.get("errorSummary")),
        skip_reason=_coerce_optional_str(raw.get("skipReason")),
    )


def _build_review_enrichment_status_view(raw: object | None) -> ReviewEnrichmentStatusView | None:
    """Build ReviewEnrichmentStatusView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return None
    return ReviewEnrichmentStatusView(
        status=_coerce_str(raw.get("status")),
        reason=_coerce_optional_str(raw.get("reason")),
        provider=_coerce_optional_str(raw.get("provider")),
        policy_enabled=bool(raw.get("policyEnabled")),
        provider_configured=bool(raw.get("providerConfigured")),
        adapter_available=_coerce_optional_bool(raw.get("adapterAvailable")),
        run_enabled=_coerce_optional_bool(raw.get("runEnabled")),
        run_provider=_coerce_optional_str(raw.get("runProvider")),
    )
