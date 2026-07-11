"""Shared fixture sources for redaction verifier self-tests."""

from __future__ import annotations

PRIVACY_MODULE_VALID = '''\
"""Trusted privacy-state module."""
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)

SAFE_OMISSION_MARKER = "[REDACTED:UNSAFE_EVIDENCE]"


class UnsafeEvidenceTextError(ValueError):
    pass


def redact_evidence_text(value: RawEvidenceText) -> RedactedEvidenceText:
    return RedactedEvidenceText(str(value))


def approve_redacted_evidence_text(
    value: RedactedEvidenceText,
) -> LLMSafeEvidenceText:
    return LLMSafeEvidenceText(value)


def project_raw_evidence_text_for_llm(
    value: RawEvidenceText,
    *,
    max_chars: int,
) -> LLMSafeEvidenceText:
    return LLMSafeEvidenceText(RedactedEvidenceText(str(value)[:max_chars]))


def make_safe_evidence_excerpt(
    value: LLMSafeEvidenceText,
    *,
    max_chars: int,
) -> SafeEvidenceExcerpt:
    return SafeEvidenceExcerpt(value)
'''

LLM_SAFE_MODULE_VALID = '''\
"""LLM-safe projector module."""
from dataclasses import dataclass
from typing import Any

from k8s_diag_agent.collect.incident_evidence_redaction import (
    LLMSafeEvidenceText,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RedactedEvidenceSummary:
    artifact_id: str
    kind: str
    role: str
    summary: LLMSafeEvidenceText

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "kind": self.kind,
            "role": self.role,
            "summary": str(self.summary),
        }


def evidence_artifact_to_llm_safe_summary(
    artifact: object,
    *,
    safe_ref: "object | None",
    summary: LLMSafeEvidenceText,
) -> RedactedEvidenceSummary:
    return RedactedEvidenceSummary(
        artifact_id=getattr(artifact, "artifact_id", ""),
        kind=getattr(artifact, "kind", ""),
        role="supporting",
        summary=summary,
    )
'''
