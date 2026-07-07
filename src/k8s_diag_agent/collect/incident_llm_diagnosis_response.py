"""Response parsing and bounding for LLM diagnosis output.

This module provides helpers for parsing and bounding LLM model output
into structured diagnosis components.

Design constraints:
- Pure functions only
- No store mutation
- No Kubernetes calls
- No LLM calls
- Deterministic in tests
"""

from __future__ import annotations

import json
from typing import Any

__all__ = [
    "parse_model_output",
    "bound_raw_output",
]


def parse_model_output(raw_output: str) -> dict[str, Any]:
    """Parse model output into structured diagnosis components.

    Attempts JSON parsing first, falls back to plain text wrapping.

    Args:
        raw_output: Raw model output string

    Returns:
        Structured diagnosis components dict
    """
    # Try JSON parsing
    raw_output = raw_output.strip()
    try:
        # Handle markdown code blocks if present
        if raw_output.startswith("```"):
            # Strip triple backtick blocks
            lines = raw_output.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw_output = "\n".join(lines).strip()

        parsed = json.loads(raw_output)
        if isinstance(parsed, dict):
            return {
                "summary": parsed.get("summary", ""),
                "likely_causes": parsed.get("likely_causes", []),
                "supporting_evidence": parsed.get("supporting_evidence", []),
                "recommended_investigations": parsed.get("recommended_investigations", []),
                "uncertainties": parsed.get("uncertainties", []),
                "confidence": parsed.get("confidence", "unknown"),
            }
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: wrap plain text
    return {
        "summary": raw_output[:500] if len(raw_output) > 500 else raw_output,
        "likely_causes": [],
        "supporting_evidence": [],
        "recommended_investigations": [],
        "uncertainties": ["Model output was not in expected JSON format"],
        "confidence": "unknown",
    }


def bound_raw_output(raw_output: str, max_chars: int) -> str:
    """Bound raw model output for safety.

    Args:
        raw_output: Raw model output
        max_chars: Maximum allowed length

    Returns:
        Bounded output string
    """
    if len(raw_output) > max_chars:
        return raw_output[:max_chars] + "\n\n[OUTPUT TRUNCATED]"
    return raw_output
