"""Durable Alertmanager learning boundary - proposal-oriented aggregation.

This module defines the durable-learning boundary for Alertmanager relevance feedback
and implements a proposal-oriented aggregation path. It is **boundary-definition and
proposal-artifact generation infrastructure**, not a complete end-to-end workflow.

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

### Feedback Signal Trustworthiness

| Signal        | Trustworthy Beyond Single Run? | Durable Mechanism               |
|-------------|-------------------------------|--------------------------------|
| `not_relevant` | YES - with operator review      | Aggregated into proposal       |
| `noisy`      | YES - with operator review      | Aggregated into proposal       |
| `relevant`   | NO - excluded from durable path | None (observational only)      |
| `unsure`     | NO - excluded from durable path | None (never durable)           |

### Cross-Run Behavior Classification

1. **Run-scoped only** (existing behavior in `alertmanager_feedback.py`):
   - `not_relevant` and `noisy` feedback suppresses similar candidates within the same run
   - No cross-run persistence of learned weighting

2. **Proposal candidates** (this module):
   - Stable patterns of `not_relevant`/`noisy` judgments are aggregated
   - Aggregated into a durable proposal candidate artifact
   - Requires explicit operator review before any ranking change
   - Does NOT silently alter future runs

3. **Never durable** (hard boundary):
   - `relevant` never silently strengthens future ranking (excluded from extraction)
   - `unsure` never becomes automatic learning (excluded from extraction)
   - Sparse feedback (< 3 runs with < 2 instances/run) never produces proposals
   - No hidden cross-run heuristics

### Design Constraints

- artifact-first: aggregation derives from review artifacts, not memory
- evidence-first: requires stable evidence before proposal
- preserve operator trust: no silent ranking drift
- run-scoped only: no hidden cross-run behavior
- operator-visible: all durable effects are inspectable
- proposal/policy surfaces: prefer approval over silent change
- no LLM inference: no model-driven durable policy from sparse feedback

## Proposal Trigger Criteria

A durable proposal candidate is generated when:
1. Same dimension (namespace/cluster/service) marked `noisy` or `not_relevant`
2. Across 3+ distinct runs
3. At least 2 instances per run on average

**Note:** The "intervening `relevant` judgment" rule described in earlier docs is NOT
implemented. `relevant` signals are simply excluded from extraction (treated as noise
in the durable context). Future work could implement active cancellation logic if needed.

## Artifact Contract

Proposal candidates are written to:
- `runs/health/alertmanager-durable-proposals/{proposal_id}.json`

Each proposal candidate:
- References source review artifacts
- Documents evidence count and pattern stability
- Includes expected benefit and confidence
- Carries promotion payload for operator review

## Scan Scope

`_scan_review_artifacts(root)` scans `root / "external-analysis"` for review artifacts.
This is scoped to a single health root directory. The scan will capture all review
artifacts that operators have written during normal workflow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..identity.artifact import new_artifact_id

# Minimum runs and instances required before considering a proposal.
# This prevents sparse feedback from driving premature proposals.
_MIN_RUNS_FOR_PROPOSAL = 3
_MIN_INSTANCES_PER_RUN = 2

# Signals that can become durable learning (proposal candidates)
_DURABLE_SIGNALS = frozenset(("not_relevant", "noisy"))

# Signals that are NEVER durable
_FORBIDDEN_DURABLE_SIGNALS = frozenset(("relevant", "unsure"))


@dataclass(frozen=True)
class DurableFeedbackPattern:
    """A stable feedback pattern that may warrant a proposal.

    Represents a dimension that has been repeatedly marked as noisy/not_relevant
    across multiple runs, forming the basis for a proposal candidate.
    """
    dimension: str  # "namespace", "cluster", "service"
    values: frozenset[str]  # specific values marked
    signal: str  # "not_relevant" or "noisy"
    run_count: int  # number of runs with this pattern
    total_instances: int  # total judgment instances
    source_artifacts: tuple[str, ...]  # paths to source review artifacts
    first_seen: datetime
    last_seen: datetime
    cluster_labels: frozenset[str]  # clusters where this was observed

    @property
    def meets_proposal_threshold(self) -> bool:
        """Check if this pattern meets criteria for a proposal candidate."""
        return (
            self.run_count >= _MIN_RUNS_FOR_PROPOSAL
            and self.total_instances >= self.run_count * _MIN_INSTANCES_PER_RUN
        )

    @property
    def is_actionable(self) -> bool:
        """Check if this pattern is actionable (meets threshold and is allowed)."""
        return (
            self.signal in _DURABLE_SIGNALS
            and self.meets_proposal_threshold
        )

    @property
    def proposal_rationale(self) -> str:
        """Generate rationale text for a proposal based on this pattern."""
        if self.signal == "noisy":
            return (
                f"Consider reducing Alertmanager influence for {self.dimension} "
                f"'{', '.join(sorted(self.values))}' - marked noisy across "
                f"{self.run_count} runs with {self.total_instances} total instances"
            )
        else:
            return (
                f"Consider stop-tracking Alertmanager {self.dimension} "
                f"'{', '.join(sorted(self.values))}' - marked not relevant across "
                f"{self.run_count} runs with {self.total_instances} total instances"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "values": sorted(self.values),
            "signal": self.signal,
            "run_count": self.run_count,
            "total_instances": self.total_instances,
            "source_artifacts": list(self.source_artifacts),
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "cluster_labels": sorted(self.cluster_labels),
            "meets_proposal_threshold": self.meets_proposal_threshold,
            "is_actionable": self.is_actionable,
            "proposal_rationale": self.proposal_rationale,
        }


@dataclass
class DurableProposalCandidate:
    """A proposal candidate for operator review.

    This is a durable artifact that represents a potential policy change
    based on stable feedback patterns. It requires explicit operator
    approval before any ranking modification.
    """
    proposal_id: str
    pattern: DurableFeedbackPattern
    cluster_label: str  # primary cluster for the proposal
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    proposal_type: str = "alertmanager_dimension_suppression"

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposal_type": self.proposal_type,
            "cluster_label": self.cluster_label,
            "created_at": self.created_at.isoformat(),
            "pattern": self.pattern.to_dict(),
            "expected_benefit": f"Reduced noise from {self.pattern.dimension} "
                               f"'{', '.join(sorted(self.pattern.values))}'",
            "confidence": self._compute_confidence(),
            "promotion_payload": self._build_promotion_payload(),
        }

    def _compute_confidence(self) -> str:
        """Compute confidence based on evidence stability."""
        if self.pattern.run_count >= 5 and self.pattern.total_instances >= 10:
            return "high"
        elif self.pattern.run_count >= 4 and self.pattern.total_instances >= 6:
            return "medium"
        return "low"

    def _build_promotion_payload(self) -> dict[str, Any]:
        """Build promotion payload for operator review tooling."""
        return {
            "action": "suppress_dimension",
            "dimension": self.pattern.dimension,
            "values": list(self.pattern.values),
            "signal": self.pattern.signal,
            "evidence": {
                "run_count": self.pattern.run_count,
                "total_instances": self.pattern.total_instances,
                "cluster_labels": list(self.pattern.cluster_labels),
            },
        }


def _is_review_artifact(path: Path) -> bool:
    """Check if a path is an Alertmanager relevance review artifact."""
    return "-next-check-execution-alertmanager-review-" in path.name


def _parse_review_artifact(path: Path) -> dict[str, Any] | None:
    """Parse an Alertmanager relevance review artifact.

    Returns None if the file cannot be parsed or is not a review artifact.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
