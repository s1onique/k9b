"""View model helpers for the operator UI."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import SupportsInt, cast


@dataclass(frozen=True)
class RunView:
    run_id: str
    run_label: str
    timestamp: str
    collector_version: str
    cluster_count: int
    drilldown_count: int
    proposal_count: int


@dataclass(frozen=True)
class ClusterView:
    label: str
    context: str
    cluster_class: str
    cluster_role: str
    baseline_cohort: str
    node_count: int
    control_plane_version: str
    health_rating: str
    warnings: int
    non_running_pods: int
    baseline_policy_path: str
    missing_evidence: tuple[str, ...]


@dataclass(frozen=True)
class ProposalView:
    proposal_id: str
    target: str
    status: str
    confidence: str
    rationale: str
    expected_benefit: str
    source_run_id: str
    latest_note: str | None


@dataclass(frozen=True)
class FindingsView:
    label: str | None
    context: str | None
    trigger_reasons: tuple[str, ...]
    warning_events: int
    non_running_pods: int
    summary: tuple[tuple[str, str], ...]
    rollout_status: tuple[str, ...]
    pattern_details: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class UIIndexContext:
    run: RunView
    clusters: tuple[ClusterView, ...]
    proposals: tuple[ProposalView, ...]
    latest_findings: FindingsView | None


def load_ui_index(directory: Path) -> Mapping[str, object]:
    path = directory / "ui-index.json"
    text = path.read_text(encoding="utf-8")
    return cast(Mapping[str, object], json.loads(text))


def build_ui_context(index: Mapping[str, object]) -> UIIndexContext:
    run_data = index.get("run") or {}
    run = RunView(
        run_id=_coerce_str(run_data.get("run_id")),
        run_label=_coerce_str(run_data.get("run_label")),
        timestamp=_coerce_str(run_data.get("timestamp")),
        collector_version=_coerce_str(run_data.get("collector_version")),
        cluster_count=_coerce_int(run_data.get("cluster_count")),
        drilldown_count=_coerce_int(run_data.get("drilldown_count")),
        proposal_count=_coerce_int(run_data.get("proposal_count")),
    )
    raw_clusters = index.get("clusters")
    if not isinstance(raw_clusters, Sequence):
        raw_clusters = ()
    clusters = tuple(
        _build_cluster_view(cluster)
        for cluster in sorted(
            (entry for entry in raw_clusters if isinstance(entry, Mapping)),
            key=lambda item: _coerce_str(item.get("label")),
        )
    )
    proposals = tuple(_build_proposal_view(proposal) for proposal in index.get("proposals") or [])
    latest_findings = _build_findings(index.get("latest_drilldown"))
    return UIIndexContext(run=run, clusters=clusters, proposals=proposals, latest_findings=latest_findings)


def _build_cluster_view(cluster: Mapping[str, object]) -> ClusterView:
    return ClusterView(
        label=_coerce_str(cluster.get("label")),
        context=_coerce_str(cluster.get("context")),
        cluster_class=_coerce_str(cluster.get("cluster_class")),
        cluster_role=_coerce_str(cluster.get("cluster_role")),
        baseline_cohort=_coerce_str(cluster.get("baseline_cohort")),
        node_count=_coerce_int(cluster.get("node_count")),
        control_plane_version=_coerce_str(cluster.get("control_plane_version")),
        health_rating=_coerce_str(cluster.get("health_rating")),
        warnings=_coerce_int(cluster.get("warnings")),
        non_running_pods=_coerce_int(cluster.get("non_running_pods")),
        baseline_policy_path=_coerce_str(cluster.get("baseline_policy_path")),
        missing_evidence=_coerce_sequence(cluster.get("missing_evidence")),
    )


def _build_proposal_view(proposal: Mapping[str, object]) -> ProposalView:
    history = proposal.get("lifecycle_history") or []
    latest_entry = history[-1] if isinstance(history, Sequence) and history else None
    note = _coerce_str(latest_entry.get("note")) if latest_entry and isinstance(latest_entry, Mapping) and latest_entry.get("note") else None
    if note == "-":
        note = None
    return ProposalView(
        proposal_id=_coerce_str(proposal.get("proposal_id")),
        target=_coerce_str(proposal.get("target")),
        status=_coerce_str(proposal.get("status")),
        confidence=_coerce_str(proposal.get("confidence")),
        rationale=_coerce_str(proposal.get("rationale")),
        expected_benefit=_coerce_str(proposal.get("expected_benefit")),
        source_run_id=_coerce_str(proposal.get("source_run_id")),
        latest_note=note,
    )


def _build_findings(raw: object | None) -> FindingsView | None:
    if not isinstance(raw, Mapping):
        return None
    return FindingsView(
        label=_coerce_optional_str(raw.get("label")),
        context=_coerce_optional_str(raw.get("context")),
        trigger_reasons=_coerce_sequence(raw.get("trigger_reasons")),
        warning_events=_coerce_int(raw.get("warning_events")),
        non_running_pods=_coerce_int(raw.get("non_running_pods")),
        summary=_serialize_map(raw.get("summary")),
        rollout_status=_coerce_sequence(raw.get("rollout_status")),
        pattern_details=_serialize_map(raw.get("pattern_details")),
    )


def _coerce_str(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_int(value: object | None) -> int:
    if value is None:
        return 0
    if isinstance(value, SupportsInt):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _coerce_sequence(value: object | None) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item) for item in value)
    if value is None:
        return ()
    return (str(value),)


def _serialize_map(value: object | None) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping):
        return ()
    results: list[tuple[str, str]] = []
    for key, entry in value.items():
        results.append((str(key), _stringify(entry)))
    return tuple(results)


def _stringify(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)
