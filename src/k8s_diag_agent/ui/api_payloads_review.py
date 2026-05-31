"""TypedDict payload definitions for review and enrichment API responses.

This module contains pure data contracts (TypedDict definitions) for review
enrichment, diagnostic-pack review, and related evidence reference payloads
used by the UI API responses.

Ownership:
    - All TypedDict payload classes defined here represent API response contracts.
    - JSON key names, optional vs required fields, and field types are frozen.
    - Serialization logic lives in api.py and related modules.

Extraction rationale:
    - Review and enrichment contracts are self-contained with well-defined dependencies.
    - Extracting them establishes the review/enrichment contract boundary.
    - Keeping review contracts in a dedicated module makes it easier to audit
      review API contracts without filtering through unrelated payloads.
    - AlertmanagerEvidenceReferencePayload is review-specific (evidence gaps).
"""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "AlertmanagerEvidenceReferencePayload",
    "ReviewEnrichmentPayload",
    "ReviewEnrichmentStatusPayload",
    "DiagnosticPackReviewCandidatePayload",
    "DiagnosticPackReviewPayload",
]


class AlertmanagerEvidenceReferencePayload(TypedDict, total=False):
    """Payload for an Alertmanager evidence reference in review enrichment."""

    cluster: str
    matchedDimensions: list[str]
    reason: str
    usedFor: str


class ReviewEnrichmentPayload(TypedDict, total=False):
    """Payload for review enrichment data."""

    status: str
    provider: str | None
    timestamp: str | None
    summary: str | None
    triageOrder: list[str]
    topConcerns: list[str]
    evidenceGaps: list[str]
    nextChecks: list[str]
    focusNotes: list[str]
    alertmanagerEvidenceReferences: list[AlertmanagerEvidenceReferencePayload] | None
    artifactPath: str | None
    errorSummary: str | None
    skipReason: str | None


class ReviewEnrichmentStatusPayload(TypedDict, total=False):
    """Payload for review enrichment status."""

    status: str
    reason: str | None
    provider: str | None
    policyEnabled: bool
    providerConfigured: bool
    adapterAvailable: bool | None
    runEnabled: bool | None
    runProvider: str | None


class DiagnosticPackReviewCandidatePayload(TypedDict, total=False):
    """Payload for a single diagnostic-pack review candidate."""

    providerReview: dict[str, object] | None


class DiagnosticPackReviewPayload(TypedDict, total=False):
    """Payload for diagnostic-pack review summary."""

    timestamp: str | None
    summary: str | None
    majorDisagreements: list[str]
    missingChecks: list[str]
    rankingIssues: list[str]
    genericChecks: list[str]
    recommendedNextActions: list[str]
    driftMisprioritized: bool
    confidence: str | None
    providerStatus: str | None
    providerSummary: str | None
    providerErrorSummary: str | None
    providerSkipReason: str | None
    providerReview: dict[str, object] | None
    artifactPath: str | None
