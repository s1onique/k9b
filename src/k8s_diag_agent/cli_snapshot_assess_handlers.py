"""Snapshot assessment CLI handlers extracted from cli_snapshot_handlers.py.

This module contains LLM-based assessment handlers for snapshots.
Extracted to reduce cli_snapshot_handlers.py size.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Import ClusterSnapshot type for type annotations
from .collect.cluster_snapshot import ClusterSnapshot  # noqa: F401
from .compare.two_cluster import compare_snapshots
from .health.artifact_readers import read_cluster_snapshot_artifact
from .llm.assessor_schema import AssessorAssessment
from .llm.prompts import build_assessment_prompt
from .llm.provider import build_assessment_input, get_provider

# =============================================================================
# Assess Snapshots Handler
# =============================================================================


def handle_assess_snapshots(args: argparse.Namespace) -> int:
    """Assess two snapshots using LLM-based comparison."""
    try:
        primary = _load_snapshot(args.snapshot_a)
        secondary = _load_snapshot(args.snapshot_b)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"Unable to load snapshots: {exc}", file=sys.stderr)
        return 1
    comparison = compare_snapshots(primary, secondary)
    prompt = build_assessment_prompt(primary, secondary, comparison)
    provider = get_provider(args.provider)
    payload = build_assessment_input(primary, secondary, comparison)
    try:
        raw_assessment = provider.assess(prompt, payload)
    except Exception as exc:  # noqa: BLE001 - LLM provider errors are diverse
        print(f"LLM assessment failed: {exc}", file=sys.stderr)
        return 1
    try:
        validated = AssessorAssessment.from_dict(raw_assessment)
    except ValueError as exc:
        print(f"LLM assessment returned invalid schema: {exc}", file=sys.stderr)
        return 1
    serialized = validated.to_dict()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    else:
        sys.stdout.write(json.dumps(serialized, indent=2))
        sys.stdout.write("\n")
    if not args.quiet and validated.hypotheses:
        print(
            f"LLM assessment ready. Hypothesis: {validated.hypotheses[0].description}",
            file=sys.stderr,
        )
    return 0


def _load_snapshot(path: Path) -> ClusterSnapshot:
    """Load a ClusterSnapshot from disk using the typed artifact reader."""
    return read_cluster_snapshot_artifact(path)


# Re-export for backward compatibility
__all__ = [
    "handle_assess_snapshots",
]
