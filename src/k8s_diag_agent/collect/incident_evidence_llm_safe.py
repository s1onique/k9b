"""LLM-safe evidence types for redacted summaries.

This module provides types and helpers that enforce LLM-safe evidence boundaries.
Only sanitized text and safe artifact references cross the LLM/case-file/review-packet boundary.

Design:
- RedactedEvidenceText: redacted text content safe for LLM inputs
- SafeEvidenceExcerpt: bounded excerpt safe for embedding in prompts
- RedactedEvidenceSummary: structured summary with safe ref and redacted text

Invariant: Raw artifact paths, storage refs, and unredacted content
must NOT cross the LLM boundary. Only these safe types are allowed.

Privacy-state hierarchy (from incident_evidence_redaction):
- RawEvidenceText: unprocessed evidence text
- RedactedEvidenceText: text after canonical redaction (NOT inherently LLM-safe)
- LLMSafeEvidenceText: text validated to satisfy LLM-safe policy
- SafeEvidenceExcerpt: bounded excerpt from LLMSafeEvidenceText

Usage:
    from k8s_diag_agent.collect.incident_evidence_llm_safe import (
        RedactedEvidenceText,
        SafeEvidenceExcerpt,
        RedactedEvidenceSummary,
        evidence_artifact_to_llm_safe_summary,
        make_redacted_evidence_text,
        make_safe_evidence_excerpt,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Re-export privacy-state types from incident_evidence_redaction
# These maintain backward compatibility with existing imports
from k8s_diag_agent.collect.incident_evidence_redaction import (
    LLMSafeEvidenceText,
    RawEvidenceText,
    RedactedEvidenceText,
    SafeEvidenceExcerpt,
    project_raw_evidence_text_for_llm,
)
from k8s_diag_agent.collect.incident_evidence_redaction import (
    make_redacted_evidence_text as _redact_make_redacted,
)
from k8s_diag_agent.collect.incident_evidence_types import (
    ArtifactId,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceRole,
    LLMSafeArtifactRef,
    ReviewPacketStorageRef,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RedactedEvidenceSummary:
    """Redacted evidence summary safe for LLM/case-file/review-packet boundaries.

    This dataclass wraps evidence metadata with LLM-safe text and references.
    It enforces that raw artifact paths and unredacted content cannot cross
    the LLM boundary.

    Attributes:
        artifact_id: The artifact identifier (safe to include)
        kind: The evidence kind
        role: The evidence role in the incident
        safe_ref: Optional LLM-safe artifact reference (NOT LocalArtifactPath or ExternalStorageRef)
        summary: LLM-safe text summary of the evidence content (must be LLMSafeEvidenceText)

    Invariant:
        summary must be LLMSafeEvidenceText, not merely RedactedEvidenceText.
        The summary crosses the LLM boundary and must satisfy the stronger
        LLM-safe policy. RedactedEvidenceText is NOT inherently LLM-safe.
    """

    artifact_id: ArtifactId
    kind: EvidenceKind
    role: EvidenceRole
    summary: LLMSafeEvidenceText  # Must be LLM-safe, not merely redacted
    safe_ref: LLMSafeArtifactRef | ReviewPacketStorageRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "kind": self.kind.value,
            "role": self.role.value,
            "safe_ref": str(self.safe_ref) if self.safe_ref else None,
            "summary": str(self.summary),
        }


# -----------------------------------------------------------------------------
# LLM-safe evidence text constructors (delegates to incident_evidence_redaction)
# Use these to create LLM-safe text values at redacted text boundaries.
# -----------------------------------------------------------------------------


def make_redacted_evidence_text(value: str) -> RedactedEvidenceText:
    """Convert a string to a RedactedEvidenceText.

    This is a backward-compatible wrapper that delegates to the canonical
    redaction pipeline in incident_evidence_redaction.

    Args:
        value: The text content to convert

    Returns:
        RedactedEvidenceText

    Raises:
        ValueError: If the value is empty
    """
    return _redact_make_redacted(value)


def make_safe_evidence_excerpt(
    value: LLMSafeEvidenceText | str,
    *,
    max_chars: int | None = None,
) -> SafeEvidenceExcerpt:
    """Create a bounded excerpt from LLM-safe evidence text.

    Safe evidence excerpts are bounded text snippets that are safe for embedding
    directly in LLM prompts. They should be short, focused excerpts.

    This function requires LLMSafeEvidenceText to ensure excerpts can only be
    created from already-approved LLM-safe content.

    Args:
        value: The LLM-safe text (or str for backward compatibility)
        max_chars: Maximum character limit for the excerpt. Default is 500 chars
                  if not specified (backward-compatible default).

    Returns:
        SafeEvidenceExcerpt

    Raises:
        ValueError: If the value is empty
        UnsafeEvidenceTextError: If the text contains residual secrets
    """
    from k8s_diag_agent.collect.incident_evidence_redaction import (
        make_safe_evidence_excerpt as _make_excerpt,
    )

    # For plain str input, treat as untrusted and pass through full validation pipeline.
    # NewType values are runtime strings - we cannot distinguish types at runtime.
    # The type checker provides static safety; runtime accepts str for backward compat.
    if not isinstance(value, str):
        raise TypeError(f"make_safe_evidence_excerpt requires str, got {type(value).__name__}")

    # Default max_chars for backward compatibility
    effective_max_chars = max_chars if max_chars is not None else 500

    # Treat plain str as untrusted input - apply full validation pipeline
    # This raises UnsafeEvidenceTextError on failure (fail-closed)
    validated = project_raw_evidence_text_for_llm(
        RawEvidenceText(value),
        max_chars=effective_max_chars,
    )
    return _make_excerpt(validated, max_chars=effective_max_chars)


# -----------------------------------------------------------------------------
# Explicit projection helper for LLM-safe evidence summaries
# Use this function to convert EvidenceArtifact to RedactedEvidenceSummary
# at the LLM boundary.
# -----------------------------------------------------------------------------


def evidence_artifact_to_llm_safe_summary(
    artifact: EvidenceArtifact,
    *,
    safe_ref: LLMSafeArtifactRef | ReviewPacketStorageRef | None,
    summary: LLMSafeEvidenceText,
) -> RedactedEvidenceSummary:
    """Convert an EvidenceArtifact to a RedactedEvidenceSummary for LLM boundaries.

    This projection function ensures that only LLM-safe content crosses the boundary.
    It enforces that:
    - safe_ref must be LLMSafeArtifactRef or ReviewPacketStorageRef (NOT LocalArtifactPath or ExternalStorageRef)
    - summary must be LLMSafeEvidenceText (NOT merely RedactedEvidenceText)

    Rules:
    - NEVER copy LocalArtifactPath into safe_ref
    - NEVER copy ExternalStorageRef into safe_ref
    - summary must be LLMSafeEvidenceText (validated, not merely redacted)
    - The caller is responsible for content validation before calling this function

    Args:
        artifact: The source evidence artifact
        safe_ref: Optional LLM-safe artifact reference (LLMSafeArtifactRef or ReviewPacketStorageRef only)
        summary: Pre-validated LLM-safe text summary (must be LLMSafeEvidenceText)

    Returns:
        RedactedEvidenceSummary safe for LLM/case-file/review-packet boundaries

    Raises:
        TypeError: If artifact is not an EvidenceArtifact

    Note:
        This function relies on static type checking (mypy/pyright) for safe_ref and summary validation.
        Python's NewType returns the original value at runtime, so we cannot distinguish
        LocalArtifactPath from LLMSafeArtifactRef at runtime. The type checker provides
        this safety guarantee.
    """
    # Type check: ensure we got an EvidenceArtifact
    if not isinstance(artifact, EvidenceArtifact):
        raise TypeError(f"evidence_artifact_to_llm_safe_summary requires EvidenceArtifact, got {type(artifact).__name__}")

    # Note: We trust the type annotations for safe_ref (LLMSafeArtifactRef | ReviewPacketStorageRef | None).
    # The type checker (mypy/pyright) will catch type errors statically.
    # Python's NewType returns the original value at runtime, so we cannot distinguish
    # LocalArtifactPath from LLMSafeArtifactRef at runtime. This is a static type safety guarantee.

    return RedactedEvidenceSummary(
        artifact_id=artifact.artifact_id,
        kind=artifact.kind,
        role=EvidenceRole.SUPPORTING,  # Default role for projected evidence
        safe_ref=safe_ref,
        summary=summary,
    )


# -----------------------------------------------------------------------------
# Outer omission boundary
# Catches UnsafeEvidenceTextError and substitutes safe omission marker
# -----------------------------------------------------------------------------


def safe_project_for_llm_or_omit(
    value: RawEvidenceText,
    *,
    max_chars: int,
) -> LLMSafeEvidenceText:
    """Project raw evidence text for LLM use, substituting omission marker on failure.

    This is the outer boundary function that:
    1. Keeps the lower projection raising UnsafeEvidenceTextError
    2. Catches only that exception
    3. Returns a trusted LLMSafeEvidenceText omission marker via make_safe_omission_marker()

    The omission marker is always returned in full regardless of max_chars.
    This function never directly constructs LLMSafeEvidenceText outside the trusted
    projection module.

    Args:
        value: Raw evidence text to project
        max_chars: Maximum character limit for output

    Returns:
        LLMSafeEvidenceText: Either approved LLM-safe text or SAFE_OMISSION_MARKER

    Guarantees:
        - Raw secret is absent from the result
        - Raw secret is absent from exception text and logs
        - SAFE_OMISSION_MARKER is returned when validation fails
        - The marker is always returned in full
    """
    from k8s_diag_agent.collect.incident_evidence_redaction import (
        UnsafeEvidenceTextError,
        make_safe_omission_marker,
    )

    try:
        return project_raw_evidence_text_for_llm(value, max_chars=max_chars)
    except UnsafeEvidenceTextError:
        # Outer boundary catches failure and substitutes trusted omission marker
        # Uses make_safe_omission_marker() - the only authorized constructor call
        # The exception text never exposes the raw value
        return make_safe_omission_marker()
