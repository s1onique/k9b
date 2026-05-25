"""Trigger aggregation helpers for health summary building."""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Skipped malformed artifact: %s", path.name, exc_info=True)
        return {}
    if isinstance(raw, dict):
        return raw
    return {}


def collect_triggers(triggers_dir: Path, run_id: str) -> list[dict[str, Any]]:
    """Collect trigger summaries for a specific run.

    Args:
        triggers_dir: Directory containing trigger JSON files.
        run_id: The run identifier to filter triggers.

    Returns:
        List of trigger summary dicts with keys: primary, secondary, primary_label,
        secondary_label, reasons, notes, comparison_intent, peer_notes.
    """
    triggers: list[dict[str, Any]] = []
    if not triggers_dir.is_dir():
        return triggers
    pattern = f"{run_id}-*-trigger.json"
    for path in sorted(triggers_dir.glob(pattern)):
        data = _load_json(path)
        reasons = tuple(str(item) for item in (data.get("trigger_reasons") or ()) if item)
        notes = str(data.get("notes")) if data.get("notes") else None
        comparison_intent = (
            str(data.get("comparison_intent"))
            if data.get("comparison_intent")
            else None
        )
        peer_notes = str(data.get("peer_notes")) if data.get("peer_notes") else None
        triggers.append({
            "primary": str(data.get("primary") or ""),
            "secondary": str(data.get("secondary") or ""),
            "primary_label": str(data.get("primary_label") or ""),
            "secondary_label": str(data.get("secondary_label") or ""),
            "reasons": reasons,
            "notes": notes,
            "comparison_intent": comparison_intent,
            "peer_notes": peer_notes,
        })
    return triggers


def collect_comparison_summaries(root: Path, run_id: str) -> list[dict[str, Any]]:
    """Collect comparison decision summaries for a specific run.

    Args:
        root: Root directory containing the comparison decisions file.
        run_id: The run identifier.

    Returns:
        List of comparison summary dicts with appropriate keys.

    Raises:
        Re-raises OSError and JSONDecodeError for the caller to handle with logging.
    """
    path = root / f"{run_id}-comparison-decisions.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Sequence):
        return []
    summaries: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        summaries.append({
            "primary_label": str(entry.get("primary_label") or ""),
            "secondary_label": str(entry.get("secondary_label") or ""),
            "policy_eligible": bool(entry.get("policy_eligible")),
            "triggered": bool(entry.get("triggered")),
            "comparison_intent": str(entry.get("comparison_intent") or ""),
            "reason": str(entry.get("reason") or ""),
            "primary_class": str(entry.get("primary_class")) if entry.get("primary_class") is not None else None,
            "secondary_class": str(entry.get("secondary_class")) if entry.get("secondary_class") is not None else None,
            "primary_role": str(entry.get("primary_role")) if entry.get("primary_role") is not None else None,
            "secondary_role": str(entry.get("secondary_role")) if entry.get("secondary_role") is not None else None,
            "primary_cohort": str(entry.get("primary_cohort")) if entry.get("primary_cohort") is not None else None,
            "secondary_cohort": str(entry.get("secondary_cohort")) if entry.get("secondary_cohort") is not None else None,
            "expected_drift_categories": tuple(
                str(item) for item in (entry.get("expected_drift_categories") or ()) if item
            ),
            "ignored_drift_categories": tuple(
                str(item) for item in (entry.get("ignored_drift_categories") or ()) if item
            ),
            "notes": str(entry.get("notes")) if entry.get("notes") else None,
        })
    return summaries
