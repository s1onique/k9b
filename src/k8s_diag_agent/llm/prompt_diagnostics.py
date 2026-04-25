"""Prompt diagnostics for LLM call accounting and observability.

This module provides structured tracking of prompt composition for llama.cpp
scheduler-time calls. The goal is to make the next timeout self-explanatory
by recording which prompt sections contribute most to token bloat.

Measurement-only: this module does NOT compact, truncate, omit, or rewrite
prompt content. It only measures what is already there.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Estimate: 4 characters per token for llama.cpp-style prompts.
# This is a rough estimate since exact tokenization requires model access.
# Name it clearly to avoid confusion with exact tokenization.
CHARS_PER_TOKEN_ESTIMATE = 4


@dataclass(frozen=True)
class PromptSection:
    """A named section of a prompt for diagnostic tracking."""

    name: str
    text: str


@dataclass(frozen=True)
class PromptSectionDiagnostics:
    """Diagnostics for a single prompt section."""

    name: str
    chars: int
    tokens_estimate: int
    percentage_of_prompt: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "chars": self.chars,
            "tokens_estimate": self.tokens_estimate,
            "percentage_of_prompt": self.percentage_of_prompt,
        }

    @classmethod
    def from_section(cls, section: PromptSection, total_tokens: int) -> PromptSectionDiagnostics:
        """Create diagnostics from a section and total token count."""
        chars = len(section.text)
        tokens_estimate = estimate_tokens_from_chars(chars)
        percentage = (tokens_estimate / total_tokens * 100.0) if total_tokens > 0 else 0.0
        return cls(
            name=section.name,
            chars=chars,
            tokens_estimate=tokens_estimate,
            percentage_of_prompt=round(percentage, 2),
        )


@dataclass(frozen=True)
class PromptDiagnostics:
    """Full prompt diagnostics for an LLM call."""

    provider: str
    operation: str
    # Exact measurement of the actual prompt
    actual_prompt_chars: int
    actual_prompt_tokens_estimate: int
    # Section-based measurement (may differ from actual if sections don't cover everything)
    prompt_chars: int
    prompt_tokens_estimate: int
    prompt_section_count: int
    prompt_sections: tuple[PromptSectionDiagnostics, ...]
    top_prompt_sections: tuple[PromptSectionDiagnostics, ...]
    # Coverage tracking
    section_prompt_chars: int = 0
    section_coverage_ratio: float = 0.0
    section_accounting_exact: bool = True
    max_tokens: int | None = None
    timeout_seconds: int | None = None
    endpoint: str | None = None
    elapsed_ms: int | None = None
    failure_class: str | None = None
    exception_type: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dict for JSON serialization."""
        result: dict[str, object] = {
            "provider": self.provider,
            "operation": self.operation,
            "actual_prompt_chars": self.actual_prompt_chars,
            "actual_prompt_tokens_estimate": self.actual_prompt_tokens_estimate,
            "prompt_chars": self.prompt_chars,
            "prompt_tokens_estimate": self.prompt_tokens_estimate,
            "prompt_section_count": self.prompt_section_count,
            "prompt_sections": [s.to_dict() for s in self.prompt_sections],
            "top_prompt_sections": [s.to_dict() for s in self.top_prompt_sections],
            "section_prompt_chars": self.section_prompt_chars,
            "section_coverage_ratio": round(self.section_coverage_ratio, 4),
            "section_accounting_exact": self.section_accounting_exact,
        }
        if self.max_tokens is not None:
            result["max_tokens"] = self.max_tokens
        if self.timeout_seconds is not None:
            result["timeout_seconds"] = self.timeout_seconds
        if self.endpoint is not None:
            result["endpoint"] = self.endpoint
        if self.elapsed_ms is not None:
            result["elapsed_ms"] = self.elapsed_ms
        if self.failure_class is not None:
            result["failure_class"] = self.failure_class
        if self.exception_type is not None:
            result["exception_type"] = self.exception_type
        return result


def estimate_tokens_from_chars(chars: int) -> int:
    """Estimate token count from character count.

    Uses a simple 4 chars/token estimate. This is honest but approximate -
    the actual tokenization depends on the model and encoding.

    For llama.cpp with typical prompts, English text runs ~3-5 chars/token.
    We use 4 as a middle estimate.
    """
    return max(1, chars // CHARS_PER_TOKEN_ESTIMATE)


def build_prompt_sections(
    sections: Sequence[PromptSection] | Sequence[tuple[str, str]],
) -> tuple[PromptSection, ...]:
    """Build prompt sections tuple from sequence of (name, text) pairs.

    Accepts either PromptSection objects or (name, text) tuples.
    """
    result: list[PromptSection] = []
    for item in sections:
        if isinstance(item, PromptSection):
            result.append(item)
        else:
            name, text = item
            result.append(PromptSection(name=name, text=text))
    return tuple(result)


def build_prompt_diagnostics(
    provider: str,
    operation: str,
    sections: Sequence[PromptSection] | Sequence[tuple[str, str]],
    *,
    actual_prompt_chars: int | None = None,
    max_tokens: int | None = None,
    timeout_seconds: int | None = None,
    endpoint: str | None = None,
    elapsed_ms: int | None = None,
    failure_class: str | None = None,
    exception_type: str | None = None,
) -> PromptDiagnostics:
    """Build complete prompt diagnostics from sections.

    This function:
    1. Computes total char count and token estimate from sections
    2. Compares section total with actual prompt chars if provided
    3. Creates diagnostics for each section with percentage of total
    4. Computes top 5 sections by estimated token count

    Args:
        provider: The LLM provider name (e.g., "llamacpp")
        operation: The operation/purpose (e.g., "review-enrichment", "auto-drilldown")
        sections: Sequence of PromptSection or (name, text) tuples
        actual_prompt_chars: Exact character count of the actual prompt sent to LLM.
                           If None, defaults to section sum (section_accounting_exact=True).
        max_tokens: The max_tokens completion budget if any
        timeout_seconds: The timeout configured for the call
        endpoint: The endpoint URL (will be sanitized)
        elapsed_ms: Time taken for the call
        failure_class: Failure classification if call failed
        exception_type: Exception type name if call failed

    Returns:
        PromptDiagnostics with all computed fields
    """
    prompt_sections = build_prompt_sections(sections)

    # Calculate section-based totals
    section_chars = sum(len(s.text) for s in prompt_sections)
    section_tokens = estimate_tokens_from_chars(section_chars)

    # Determine actual prompt measurement and coverage
    if actual_prompt_chars is not None:
        actual_chars = actual_prompt_chars
        actual_tokens = estimate_tokens_from_chars(actual_chars)
        # Compute coverage ratio
        coverage_ratio = section_chars / actual_chars if actual_chars > 0 else 1.0
        # Accounting is exact if section chars match actual chars within 1% tolerance
        accounting_exact = abs(section_chars - actual_chars) <= max(1, int(actual_chars * 0.01))
    else:
        # No actual measurement provided; use section totals as the actual
        actual_chars = section_chars
        actual_tokens = section_tokens
        coverage_ratio = 1.0
        accounting_exact = True

    # Build section diagnostics using section-based totals for percentages
    section_diags: list[PromptSectionDiagnostics] = []
    for section in prompt_sections:
        section_diags.append(PromptSectionDiagnostics.from_section(section, section_tokens))

    # Top 5 sections by tokens
    sorted_sections = sorted(section_diags, key=lambda s: s.tokens_estimate, reverse=True)
    top_5 = tuple(sorted_sections[:5])

    return PromptDiagnostics(
        provider=provider,
        operation=operation,
        actual_prompt_chars=actual_chars,
        actual_prompt_tokens_estimate=actual_tokens,
        prompt_chars=section_chars,
        prompt_tokens_estimate=section_tokens,
        prompt_section_count=len(prompt_sections),
        prompt_sections=tuple(section_diags),
        top_prompt_sections=top_5,
        section_prompt_chars=section_chars,
        section_coverage_ratio=coverage_ratio,
        section_accounting_exact=accounting_exact,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        endpoint=endpoint,
        elapsed_ms=elapsed_ms,
        failure_class=failure_class,
        exception_type=exception_type,
    )


def build_full_prompt_diagnostics(
    provider: str,
    operation: str,
    actual_prompt: str,
    *,
    max_tokens: int | None = None,
    timeout_seconds: int | None = None,
    endpoint: str | None = None,
    elapsed_ms: int | None = None,
    failure_class: str | None = None,
    exception_type: str | None = None,
) -> PromptDiagnostics:
    """Build prompt diagnostics from an exact prompt string.

    This function creates diagnostics using the actual prompt sent to the LLM,
    ensuring measurement accuracy. Optionally can include named sections for
    additional breakdown.

    Args:
        provider: The LLM provider name (e.g., "llamacpp")
        operation: The operation/purpose (e.g., "review-enrichment", "auto-drilldown")
        actual_prompt: The exact prompt string sent to the LLM
        max_tokens: The max_tokens completion budget if any
        timeout_seconds: The timeout configured for the call
        endpoint: The endpoint URL (will be sanitized)
        elapsed_ms: Time taken for the call
        failure_class: Failure classification if call failed
        exception_type: Exception type name if call failed

    Returns:
        PromptDiagnostics with exact measurements from actual_prompt
    """
    return build_prompt_diagnostics(
        provider=provider,
        operation=operation,
        sections=[("full_prompt", actual_prompt)],
        actual_prompt_chars=len(actual_prompt),
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        endpoint=endpoint,
        elapsed_ms=elapsed_ms,
        failure_class=failure_class,
        exception_type=exception_type,
    )


def log_prompt_diagnostics(diagnostics: PromptDiagnostics) -> dict[str, object]:
    """Prepare structured log dict from prompt diagnostics.

    Returns a dict suitable for structured logging with all relevant fields.
    Does NOT log full prompt content.

    Includes coverage tracking fields for observability:
    - actual_prompt_chars/actual_prompt_tokens_estimate: exact measurement from actual prompt
    - section_prompt_chars: sum of named sections
    - section_coverage_ratio: how well sections cover actual prompt (1.0 = exact)
    - section_accounting_exact: whether section sum matches actual prompt (within 1% tolerance)
    """
    top_names = [s.name for s in diagnostics.top_prompt_sections]
    return {
        "operation": diagnostics.operation,
        "provider": diagnostics.provider,
        "actual_prompt_chars": diagnostics.actual_prompt_chars,
        "actual_prompt_tokens_estimate": diagnostics.actual_prompt_tokens_estimate,
        "prompt_chars": diagnostics.prompt_chars,
        "prompt_tokens_estimate": diagnostics.prompt_tokens_estimate,
        "section_prompt_chars": diagnostics.section_prompt_chars,
        "section_coverage_ratio": diagnostics.section_coverage_ratio,
        "section_accounting_exact": diagnostics.section_accounting_exact,
        "prompt_section_count": diagnostics.prompt_section_count,
        "top_prompt_sections": top_names,
        "timeout_seconds": diagnostics.timeout_seconds,
        "elapsed_ms": diagnostics.elapsed_ms,
        "failure_class": diagnostics.failure_class,
        "exception_type": diagnostics.exception_type,
    }


__all__ = [
    "CHARS_PER_TOKEN_ESTIMATE",
    "PromptSection",
    "PromptSectionDiagnostics",
    "PromptDiagnostics",
    "estimate_tokens_from_chars",
    "build_prompt_sections",
    "build_prompt_diagnostics",
    "build_full_prompt_diagnostics",
    "log_prompt_diagnostics",
]
