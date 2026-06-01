"""Durable Alertmanager learning boundary - proposal-oriented aggregation.

This module defines the durable-learning boundary for Alertmanager relevance feedback
and implements a proposal-oriented aggregation path. It is **boundary-definition and
proposal-artifact generation infrastructure**, not a complete end-to-end workflow.

## Models and Constants

Core data models and threshold constants are in `alertmanager_durable_learning_models`:
- DurableFeedbackPattern: Stable feedback pattern that may warrant a proposal
- DurableProposalCandidate: Proposal candidate for operator review
- Threshold constants (_MIN_RUNS_FOR_PROPOSAL, _MIN_INSTANCES_PER_RUN)
- Signal sets (_DURABLE_SIGNALS, _FORBIDDEN_DURABLE_SIGNALS)

## Current Status

This module provides:
- Durable-learning boundary definition (signal classification)
- Pattern aggregation from review artifacts
- Proposal candidate artifact generation

This module does NOT provide:
- Integration with operator proposal UI
- Integration with existing proposal-generation pipeline
- Scheduler/loop wiring for runtime invocation
- Multi-dimension extraction from single artifacts (returns first match only)

## Durable-Learning Boundary

The system distinguishes between run-scoped learning (safe, implemented) and
durable learning (operator-approved, proposal-oriented):

| Signal        | Trustworthy Beyond Single Run? | Durable Mechanism               |
|-------------|-------------------------------|--------------------------------|
| `not_relevant` | YES - with operator review      | Aggregated into proposal       |
| `noisy`      | YES - with operator review      | Aggregated into proposal       |
| `relevant`   | NO - excluded from durable path | None (observational only)      |
| `unsure`     | NO - excluded from durable path | None (never durable)           |

## Proposal Trigger Criteria

A durable proposal candidate is generated when:
1. Same dimension (namespace/cluster/service) marked `noisy` or `not_relevant`
2. Across 3+ distinct runs
3. At least 2 instances per run on average

## Artifact Contract

Proposal candidates are written to:
- `runs/health/alertmanager-durable-proposals/{proposal_id}.json`
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ..identity.artifact import new_artifact_id

# Re-export models and constants for backward compatibility
from .alertmanager_durable_learning_models import (  # noqa: F401 - re-exported for backward compatibility
    _DURABLE_SIGNALS,
    _FORBIDDEN_DURABLE_SIGNALS,
    _MIN_INSTANCES_PER_RUN,
    _MIN_RUNS_FOR_PROPOSAL,
    DurableFeedbackPattern,
    DurableProposalCandidate,
)


def _is_review_artifact(path: Path) -> bool:
    """Check if a path is an Alertmanager relevance review artifact."""
    return "-next-check-execution-alertmanager-review-" in path.name


def _parse_review_artifact(path: Path) -> dict[str, Any] | None:
    """Parse an Alertmanager relevance review artifact.

    Returns None if the file cannot be parsed or is not a review artifact.
    """
    try:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return None


def _extract_feedback_from_artifact(raw: dict[str, Any]) -> tuple[str, str, str] | None:
    """Extract feedback signal from a review artifact.

    Returns:
        (dimension, value, signal) tuple or None if not extractable
    """
    relevance = raw.get("alertmanager_relevance")
    if not relevance or relevance in _FORBIDDEN_DURABLE_SIGNALS:
        return None

    if relevance not in _DURABLE_SIGNALS:
        return None

    provenance = raw.get("alertmanager_provenance")
    if not provenance:
        return None

    # Extract matched dimensions and values from provenance
    matched_dims = provenance.get("matchedDimensions", [])
    matched_vals = provenance.get("matchedValues", {})

    if not isinstance(matched_dims, list) or not isinstance(matched_vals, dict):
        return None

    results: list[tuple[str, str, str]] = []
    for dim in matched_dims:
        if not isinstance(dim, str):
            continue
        vals = matched_vals.get(dim, [])
        if not isinstance(vals, list):
            continue
        for val in vals:
            if isinstance(val, str) and val:
                results.append((dim, val, relevance))

    return results[0] if results else None


def _scan_review_artifacts(root: Path) -> list[dict[str, Any]]:
    """Scan for Alertmanager relevance review artifacts across runs.

    Args:
        root: The health run root directory

    Returns:
        List of parsed review artifact data
    """
    external_analysis_dir = root / "external-analysis"
    if not external_analysis_dir.exists():
        return []

    artifacts: list[dict[str, Any]] = []
    for path in external_analysis_dir.iterdir():
        if not path.is_file() or not _is_review_artifact(path):
            continue
        parsed = _parse_review_artifact(path)
        if parsed:
            artifacts.append(parsed)

    return artifacts


def aggregate_feedback_patterns(
    root: Path,
    cluster_filter: str | None = None,
) -> tuple[DurableFeedbackPattern, ...]:
    """Aggregate Alertmanager feedback patterns across runs.

    This scans all Alertmanager relevance review artifacts and groups them
    by dimension/value/signal to identify stable patterns.

    Args:
        root: The health run root directory
        cluster_filter: Optional cluster label to filter by

    Returns:
        Tuple of DurableFeedbackPattern objects, sorted by run_count desc
    """
    artifacts = _scan_review_artifacts(root)

    # Group by (dimension, value, signal)
    patterns: dict[tuple[str, str, str], dict[str, Any]] = {}

    for raw in artifacts:
        # Filter by cluster if specified
        cluster = raw.get("cluster_label", "")
        if cluster_filter and cluster != cluster_filter:
            continue

        feedback = _extract_feedback_from_artifact(raw)
        if not feedback:
            continue

        dimension, value, signal = feedback
        key = (dimension, value, signal)

        if key not in patterns:
            patterns[key] = {
                "dimension": dimension,
                "values": set(),
                "signal": signal,
                "run_ids": set(),
                "total_instances": 0,
                "source_artifacts": [],
                "first_seen": None,
                "last_seen": None,
                "cluster_labels": set(),
            }

        p = patterns[key]
        p["values"].add(value)
        p["run_ids"].add(raw.get("run_id", "unknown"))
        p["total_instances"] += 1
        p["source_artifacts"].append(raw.get("source_artifact", ""))

        # Track timestamps
        ts = raw.get("timestamp") or raw.get("reviewed_at")
        if ts:
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if p["first_seen"] is None or dt < p["first_seen"]:
                    p["first_seen"] = dt
                if p["last_seen"] is None or dt > p["last_seen"]:
                    p["last_seen"] = dt
            except ValueError:
                pass

        if cluster:
            p["cluster_labels"].add(cluster)

    # Convert to DurableFeedbackPattern objects
    result: list[DurableFeedbackPattern] = []
    for key, data in patterns.items():
        if data["total_instances"] < _MIN_INSTANCES_PER_RUN:
            continue  # Skip patterns with insufficient evidence

        result.append(DurableFeedbackPattern(
            dimension=data["dimension"],
            values=frozenset(data["values"]),
            signal=data["signal"],
            run_count=len(data["run_ids"]),
            total_instances=data["total_instances"],
            source_artifacts=tuple(data["source_artifacts"]),
            first_seen=data["first_seen"] or datetime.now(UTC),
            last_seen=data["last_seen"] or datetime.now(UTC),
            cluster_labels=frozenset(data["cluster_labels"]),
        ))

    # Sort by run_count descending (most stable first)
    result.sort(key=lambda p: (-p.run_count, -p.total_instances))
    return tuple(result)


def generate_proposal_candidates(
    patterns: tuple[DurableFeedbackPattern, ...],
    cluster_label: str,
) -> tuple[DurableProposalCandidate, ...]:
    """Generate proposal candidates from aggregated feedback patterns.

    Args:
        patterns: Aggregated feedback patterns
        cluster_label: Primary cluster for proposals

    Returns:
        Tuple of proposal candidates that meet the actionable threshold
    """
    candidates: list[DurableProposalCandidate] = []

    for idx, pattern in enumerate(patterns):
        if not pattern.is_actionable:
            continue

        # Use index to ensure uniqueness even with rapid calls
        base_id = new_artifact_id()[:10]
        proposal_id = f"alertmanager-durable-{base_id}-{idx:03d}"

        candidates.append(DurableProposalCandidate(
            proposal_id=proposal_id,
            pattern=pattern,
            cluster_label=cluster_label,
        ))

    return tuple(candidates)


def write_proposal_candidates(
    output_dir: Path,
    candidates: tuple[DurableProposalCandidate, ...],
) -> tuple[Path, ...]:
    """Write proposal candidates as durable artifacts.

    Args:
        output_dir: Directory for alertmanager-durable-proposals
        candidates: Proposal candidates to write

    Returns:
        Tuple of paths to written artifacts
    """
    proposals_dir = output_dir / "alertmanager-durable-proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for candidate in candidates:
        path = proposals_dir / f"{candidate.proposal_id}.json"
        # Use write to create artifact (unique ID prevents collision)
        path.write_text(json.dumps(candidate.to_dict(), indent=2), encoding="utf-8")
        written.append(path)

    return tuple(written)


def scan_and_propose(
    root: Path,
    cluster_filter: str | None = None,
    write_artifacts: bool = True,
) -> tuple[DurableProposalCandidate, ...]:
    """Scan artifacts and generate proposal candidates.

    This is the main entry point for durable learning. It:
    1. Scans all Alertmanager relevance review artifacts
    2. Aggregates stable feedback patterns
    3. Generates proposal candidates for actionable patterns
    4. Optionally writes proposal artifacts to disk

    Args:
        root: The health run root directory
        cluster_filter: Optional cluster label to filter by
        write_artifacts: Whether to write proposal artifacts (default True)

    Returns:
        Tuple of generated proposal candidates
    """
    patterns = aggregate_feedback_patterns(root, cluster_filter)
    cluster = cluster_filter or "global"

    candidates = generate_proposal_candidates(patterns, cluster)

    if write_artifacts and candidates:
        write_proposal_candidates(root, candidates)

    return candidates


# =============================================================================
# BOUNDARY ENFORCEMENT - Functions that MUST NOT exist
# =============================================================================
# The following behaviors are FORBIDDEN by the durable-learning boundary:
#
# 1. NO silent cross-run ranking changes
#    - Do NOT add _rank_candidates cross-run suppression logic
#    - Do NOT persist feedback to a ranking权重 file
#
# 2. NO sparse feedback promotion
#    - Do NOT generate proposals from < 3 runs
#    - Do NOT generate proposals from < 2 instances per run average
#
# 3. NO forbidden signals in durable learning
#    - Do NOT make `relevant` signal drive future ranking
#    - Do NOT make `unsure` signal become automatic learning
#
# 4. NO hidden LLM-driven policy
#    - Do NOT let inference engine invent durable policy
#    - All durable effects require explicit operator review
#
# If you find code that violates these boundaries, file a bug immediately.
# =============================================================================
