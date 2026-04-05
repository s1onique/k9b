"""Prompt templates for evaluation over snapshot comparisons."""
from __future__ import annotations

import json
from textwrap import dedent
from typing import Dict

from ..collect.cluster_snapshot import ClusterSnapshot
from ..compare.two_cluster import ClusterComparison


def _metadata_summary(snapshot: ClusterSnapshot) -> Dict[str, object]:
    meta = snapshot.metadata
    return {
        "cluster_id": meta.cluster_id,
        "control_plane_version": meta.control_plane_version,
        "node_count": meta.node_count,
        "pod_count": meta.pod_count,
        "region": meta.region,
        "labels": meta.labels,
    }


def build_assessment_prompt(
    primary: ClusterSnapshot, secondary: ClusterSnapshot, comparison: ClusterComparison
) -> str:
    differences = comparison.differences or {}
    prompt = dedent(
        """
        You are a careful Kubernetes diagnostician.
        Summaries of the two snapshots follow.

        Primary snapshot metadata:
        {primary_meta}

        Secondary snapshot metadata:
        {secondary_meta}

        Comparison differences (shallow diff):
        {diff}

        Collection status details:
        {statuses}

        Provide a structured JSON assessment that lists observed signals, findings, hypotheses (with confidence and falsifiable checks), next evidence to collect, recommended actions, safety level, and optional metadata such as probable layer of origin.
        Keep confidence aligned with how much difference exists between the snapshots. If no difference exists, recommend observation-only steps.
        """
    ).format(
        primary_meta=json.dumps(_metadata_summary(primary), indent=2),
        secondary_meta=json.dumps(_metadata_summary(secondary), indent=2),
        diff=json.dumps(differences, indent=2) if differences else "{}",
        statuses=json.dumps(
            {
                "primary": primary.collection_status.to_dict(),
                "secondary": secondary.collection_status.to_dict(),
            },
            indent=2,
        ),
    )
    return prompt
