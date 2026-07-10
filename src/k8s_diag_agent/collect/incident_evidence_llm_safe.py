"""LLM-safe evidence types for redacted summaries.

This module provides types and helpers that enforce LLM-safe evidence boundaries.
Only sanitized text and safe artifact references cross the LLM/case-file/review-packet boundary.

Design:
- RedactedEvidenceText: redacted text content safe for LLM inputs
- SafeEvidenceExcerpt: bounded excerpt safe for embedding in prompts
- RedactedEvidenceSummary: structured summary with safe ref and redacted text

Invariant: Raw artifact paths, storage refs, and unredacted content
must NOT cross the LLM boundary. Only these safe types are allowed.

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

import re
from dataclasses import dataclass
from typing import Any, NewType

from k8s_diag_agent.collect.incident_evidence_types import (
    ArtifactId,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceRole,
    LLMSafeArtifactRef,
    ReviewPacketStorageRef,
)

# -----------------------------------------------------------------------------
# LLM-safe evidence types for redacted summaries
# These types enforce that only sanitized text and safe artifact references
# cross the LLM/case-file/review-packet boundary.
# -----------------------------------------------------------------------------

RedactedEvidenceText = NewType("RedactedEvidenceText", str)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", str)


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
        summary: Redacted text summary of the evidence content
    """

    artifact_id: ArtifactId
    kind: EvidenceKind
    role: EvidenceRole
    summary: RedactedEvidenceText
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
# LLM-safe evidence text constructors with validation
# Use these to create LLM-safe text values at redacted text boundaries.
# -----------------------------------------------------------------------------

# Patterns that indicate potential secrets/unsafe content (conservative check)
_UNSAFE_PATTERNS = (
    r"password\s*=",
    r"secret\s*=",
    r"token\s*=",
    r"api[_-]?key\s*=",
    r"bearer\s+[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+",
    r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
    r"-----BEGIN\s+CERTIFICATE-----",
)


def make_redacted_evidence_text(value: str) -> RedactedEvidenceText:
    """Convert a string to a RedactedEvidenceText.

    Redacted evidence text is content that has been reviewed and made safe
    for LLM-facing outputs. It should not contain obvious secrets.

    This constructor provides basic validation but is not a full DLP system.
    Callers are responsible for proper redaction before calling this function.

    Args:
        value: The text content to convert

    Returns:
        RedactedEvidenceText

    Raises:
        ValueError: If the value is empty or contains obvious secret patterns
    """
    if not value:
        raise ValueError("RedactedEvidenceText cannot be empty")

    # Check for obvious secret patterns (conservative - errs on the side of caution)
    for pattern in _UNSAFE_PATTERNS:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValueError(
                f"RedactedEvidenceText contains suspicious pattern: {pattern!r}. "
                f"Ensure proper redaction before creating RedactedEvidenceText."
            )

    return RedactedEvidenceText(value)


def make_safe_evidence_excerpt(value: str) -> SafeEvidenceExcerpt:
    """Convert a string to a SafeEvidenceExcerpt.

    Safe evidence excerpts are bounded text snippets that are safe for embedding
    directly in LLM prompts. They should be short, focused excerpts.

    Args:
        value: The excerpt text to convert

    Returns:
        SafeEvidenceExcerpt

    Raises:
        ValueError: If the value is empty
    """
    if not value:
        raise ValueError("SafeEvidenceExcerpt cannot be empty")

    return SafeEvidenceExcerpt(value)


# -----------------------------------------------------------------------------
# Explicit projection helper for LLM-safe evidence summaries
# Use this function to convert EvidenceArtifact to RedactedEvidenceSummary
# at the LLM boundary.
# -----------------------------------------------------------------------------


def evidence_artifact_to_llm_safe_summary(
    artifact: EvidenceArtifact,
    *,
    safe_ref: LLMSafeArtifactRef | ReviewPacketStorageRef | None,
    summary: RedactedEvidenceText,
) -> RedactedEvidenceSummary:
    """Convert an EvidenceArtifact to a RedactedEvidenceSummary for LLM boundaries.

    This projection function ensures that only LLM-safe content crosses the boundary.
    It enforces that:
    - safe_ref must be LLMSafeArtifactRef or ReviewPacketStorageRef (NOT LocalArtifactPath or ExternalStorageRef)
    - summary must already be RedactedEvidenceText (caller is responsible for redaction)

    Rules:
    - NEVER copy LocalArtifactPath into safe_ref
    - NEVER copy ExternalStorageRef into safe_ref
    - summary must already be RedactedEvidenceText
    - The caller is responsible for content redaction before calling this function

    Args:
        artifact: The source evidence artifact
        safe_ref: Optional LLM-safe artifact reference (LLMSafeArtifactRef or ReviewPacketStorageRef only)
        summary: Pre-redacted text summary (must be RedactedEvidenceText)

    Returns:
        RedactedEvidenceSummary safe for LLM/case-file/review-packet boundaries

    Raises:
        TypeError: If artifact is not an EvidenceArtifact

    Note:
        This function relies on static type checking (mypy/pyright) for safe_ref validation.
        Python's NewType returns the original value at runtime, so we cannot distinguish
        LocalArtifactPath from LLMSafeArtifactRef at runtime. The type checker provides
        this safety guarantee.
    """
    # Type check: ensure we got an EvidenceArtifact
    if not isinstance(artifact, EvidenceArtifact):
        raise TypeError(
            f"evidence_artifact_to_llm_safe_summary requires EvidenceArtifact, "
            f"got {type(artifact).__name__}"
        )

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
