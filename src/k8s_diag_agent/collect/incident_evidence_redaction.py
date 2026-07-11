"""Explicit evidence privacy-state types and LLM-safe projection helpers.

Privacy states are intentionally distinct for static checking:

1. ``RawEvidenceText``: unprocessed evidence text from collection.
2. ``RedactedEvidenceText``: text after canonical redaction, not inherently LLM-safe.
3. ``LLMSafeEvidenceText``: redacted text approved for LLM use.
4. ``SafeEvidenceExcerpt``: bounded excerpt from already LLM-safe text.

Allowed transitions:

* ``RawEvidenceText`` -> ``RedactedEvidenceText`` via ``redact_evidence_text``
* ``RedactedEvidenceText`` -> ``LLMSafeEvidenceText`` via
  ``approve_redacted_evidence_text``
* ``LLMSafeEvidenceText`` -> ``SafeEvidenceExcerpt`` via
  ``make_safe_evidence_excerpt``

The projection is fail-closed: residual secret validation raises
``UnsafeEvidenceTextError`` with fixed, non-sensitive error text.
"""

from __future__ import annotations

from typing import NewType

from k8s_diag_agent.security.redaction_policy import (
    REDACTION_PATTERNS,
    SAFE_PLACEHOLDER_RE,
    SensitiveTextCategory,
)
from k8s_diag_agent.security.redaction_policy import (
    redact_sensitive_text as _policy_redact,
)
from k8s_diag_agent.security.redaction_policy import (
    sensitive_text_category as _sensitive_text_category,
)

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)

SAFE_OMISSION_MARKER = "[REDACTED:UNSAFE_EVIDENCE]"


class UnsafeEvidenceTextError(ValueError):
    """Raised when evidence contains residual sensitive content after redaction."""

    def __init__(
        self,
        *,
        reason: str,
        pattern_category: str | None = None,
    ) -> None:
        super().__init__("Evidence text contains residual sensitive content after redaction")
        self.reason = reason
        self.pattern_category = pattern_category

    def __repr__(self) -> str:
        return f"{type(self).__name__}(reason={self.reason!r}, pattern_category={self.pattern_category!r})"


def _contains_known_safe_placeholder(value: str) -> bool:
    """Return true only when ``value`` is exactly a supported placeholder."""
    stripped = value.strip()
    return SAFE_PLACEHOLDER_RE.fullmatch(stripped) is not None


def _has_residual_secret(value: str) -> bool:
    """Check already-redacted text for residual sensitive patterns."""
    if _contains_known_safe_placeholder(value):
        return False
    return any(pattern.search(value) for pattern in REDACTION_PATTERNS)


def _classify_residual_pattern(value: str) -> str:
    """Classify the first residual sensitive pattern by policy category."""
    category = _sensitive_text_category(value)
    if category is not None:
        return str(category.value)
    return str(SensitiveTextCategory.UNKNOWN.value)


def is_placeholder_shaped(value: str) -> bool:
    """Return true for strings that look like redaction placeholders."""
    stripped = value.strip()
    return stripped.startswith("[REDACTED") or stripped.startswith("[redacted")


def redact_evidence_text(value: RawEvidenceText) -> RedactedEvidenceText:
    """Apply the canonical evidence redactor to raw text."""
    if not value:
        return RedactedEvidenceText("")
    return RedactedEvidenceText(_policy_redact(value))


def approve_redacted_evidence_text(value: RedactedEvidenceText) -> LLMSafeEvidenceText:
    """Validate that redacted text satisfies the LLM-safe policy."""
    if not value:
        return LLMSafeEvidenceText(value)

    stripped = value.strip()
    if is_placeholder_shaped(stripped) and not SAFE_PLACEHOLDER_RE.fullmatch(stripped):
        raise UnsafeEvidenceTextError(
            reason="malformed_placeholder",
            pattern_category="placeholder",
        )

    if _has_residual_secret(value):
        raise UnsafeEvidenceTextError(
            reason="residual_secret",
            pattern_category=_classify_residual_pattern(value),
        )

    return LLMSafeEvidenceText(value)


def project_raw_evidence_text_for_llm(
    value: RawEvidenceText,
    *,
    max_chars: int,
) -> LLMSafeEvidenceText:
    """Redact, validate, truncate, revalidate, and approve raw evidence text."""
    if not value:
        return LLMSafeEvidenceText(RedactedEvidenceText(""))

    redacted = redact_evidence_text(value)
    approve_redacted_evidence_text(redacted)
    truncated = RedactedEvidenceText(redacted[:max_chars]) if len(redacted) > max_chars else redacted
    approve_redacted_evidence_text(truncated)
    return LLMSafeEvidenceText(truncated)


def make_safe_omission_marker() -> LLMSafeEvidenceText:
    """Create the trusted LLM-safe omission marker for fail-closed boundaries."""
    return LLMSafeEvidenceText(RedactedEvidenceText(SAFE_OMISSION_MARKER))


def make_safe_evidence_excerpt(
    value: LLMSafeEvidenceText,
    *,
    max_chars: int,
) -> SafeEvidenceExcerpt:
    """Create a bounded excerpt from already-approved LLM-safe evidence."""
    if not value:
        raise ValueError("SafeEvidenceExcerpt cannot be empty")
    if len(value) <= max_chars:
        return SafeEvidenceExcerpt(value)
    return SafeEvidenceExcerpt(LLMSafeEvidenceText(RedactedEvidenceText(value[:max_chars])))


def make_redacted_evidence_text(value: str) -> RedactedEvidenceText:
    """Backward-compatible helper that redacts a non-empty string."""
    if not value:
        raise ValueError("RedactedEvidenceText cannot be empty")
    return redact_evidence_text(RawEvidenceText(value))


__all__ = [
    "RawEvidenceText",
    "RedactedEvidenceText",
    "LLMSafeEvidenceText",
    "SafeEvidenceExcerpt",
    "SAFE_OMISSION_MARKER",
    "UnsafeEvidenceTextError",
    "approve_redacted_evidence_text",
    "is_placeholder_shaped",
    "make_safe_evidence_excerpt",
    "make_safe_omission_marker",
    "make_redacted_evidence_text",
    "project_raw_evidence_text_for_llm",
    "redact_evidence_text",
]
