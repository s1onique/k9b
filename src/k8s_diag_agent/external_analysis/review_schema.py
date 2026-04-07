"""Schema helpers for review-enrichment advisory payloads."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class ReviewEnrichmentPayloadError(ValueError):
    """Raised when review-enrichment payload validation fails."""


def _type_name(value: Any) -> str:
    if value is None:
        return "NoneType"
    return type(value).__name__


def _normalize_optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReviewEnrichmentPayloadError(
            f"{path} expected a string but got {_type_name(value)}"
        )
    trimmed = value.strip()
    return trimmed if trimmed else None


def _normalize_string_sequence(value: Any, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items: list[str] = []
        for index, entry in enumerate(value):
            if not isinstance(entry, str):
                raise ReviewEnrichmentPayloadError(
                    f"{path}[{index}] expected a string but got {_type_name(entry)}"
                )
            trimmed = entry.strip()
            if not trimmed:
                raise ReviewEnrichmentPayloadError(
                    f"{path}[{index}] must be a non-empty string"
                )
            items.append(trimmed)
        return tuple(items)
    raise ReviewEnrichmentPayloadError(
        f"{path} expected a list of strings but got {_type_name(value)}"
    )


def _extract_list(raw: Mapping[str, Any], *keys: str) -> tuple[str, ...]:
    for key in keys:
        if key in raw:
            return _normalize_string_sequence(raw[key], key)
    return ()


@dataclass(frozen=True)
class ReviewEnrichmentPayload:
    summary: str | None
    triage_order: tuple[str, ...]
    top_concerns: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    next_checks: tuple[str, ...]
    focus_notes: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: Any) -> "ReviewEnrichmentPayload":
        if not isinstance(raw, Mapping):
            raise ReviewEnrichmentPayloadError(
                f"review enrichment response expected an object but got {_type_name(raw)}"
            )
        summary = _normalize_optional_string(raw.get("summary"), "summary")
        triage = _extract_list(raw, "triageOrder", "triage_order")
        concerns = _extract_list(raw, "topConcerns", "top_concerns")
        gaps = _extract_list(raw, "evidenceGaps", "evidence_gaps")
        checks = _extract_list(raw, "nextChecks", "next_checks")
        focus = _extract_list(raw, "focusNotes", "focus_notes")
        return cls(
            summary=summary,
            triage_order=triage,
            top_concerns=concerns,
            evidence_gaps=gaps,
            next_checks=checks,
            focus_notes=focus,
        )
