import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.collect.cluster_snapshot import (
    ClusterSnapshot,
    WarningEventSummary,
    extract_cluster_snapshots,
)
from k8s_diag_agent.collect.fixture_loader import load_fixture
from k8s_diag_agent.correlate.linkers import correlate_signals
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.drilldown import DrilldownArtifact, DrilldownPod
from k8s_diag_agent.health.loop import (
    HealthAssessmentArtifact,
    HealthRating,
    HealthTarget,
    build_health_assessment,
)
from k8s_diag_agent.health.review_feedback import build_health_review
from k8s_diag_agent.models import Assessment
from k8s_diag_agent.normalize.evidence import normalize_signals
from k8s_diag_agent.reason.diagnoser import build_findings_and_hypotheses
from k8s_diag_agent.recommend.next_steps import build_recommended_action, propose_next_steps
from k8s_diag_agent.render.formatter import assessment_to_dict


def _make_health_artifact(
    run_label: str,
    run_id: str,
    target: HealthTarget,
    snapshot: ClusterSnapshot,
    assessment: dict,
    missing: Sequence[str],
    rating: HealthRating,
) -> HealthAssessmentArtifact:
    return HealthAssessmentArtifact(
        run_label=run_label,
        run_id=run_id,
        timestamp=datetime.now(timezone.utc),
        context=target.context,
        label=target.label,
        cluster_id=snapshot.metadata.cluster_id,
        snapshot_path=f"data/{snapshot.metadata.cluster_id}.json",
        assessment=assessment,
        missing_evidence=tuple(missing),
        health_rating=rating,
    )


def _make_drilldown_artifact(
    run_id: str,
    context: str,
    label: str,
    cluster_id: str,
    trigger_reasons: Sequence[str],
    warnings: Sequence[WarningEventSummary],
    pods: Sequence[DrilldownPod],
    missing_evidence: Sequence[str],
) -> DrilldownArtifact:
    timestamp = datetime.now(timezone.utc)
    namespace_candidates = tuple({pod.namespace for pod in pods if pod.namespace}) or ("default",)
    return DrilldownArtifact(
        run_label="review-run",
        run_id=run_id,
        timestamp=timestamp,
        snapshot_timestamp=timestamp,
        context=context,
        label=label,
        cluster_id=cluster_id,
        trigger_reasons=tuple(trigger_reasons),
        missing_evidence=tuple(missing_evidence),
        evidence_summary={
            "warning_events": sum(int(event.count) for event in warnings),
            "non_running_pods": len(pods),
        },
        affected_namespaces=namespace_candidates,
        affected_workloads=(),
        warning_events=tuple(warnings),
        non_running_pods=tuple(pods),
        pod_descriptions={},
        rollout_status=(),
        collection_timestamps={
            "warning_events": timestamp.isoformat(),
            "pods": timestamp.isoformat(),
            "rollouts": timestamp.isoformat(),
        },
        pattern_details={},
    )


def _make_warning_events(namespace: str, reason: str, message: str, count: int) -> WarningEventSummary:
    return WarningEventSummary(
        namespace=namespace,
        reason=reason,
        message=message,
        count=count,
        last_seen=datetime.now(timezone.utc).isoformat(),
    )


def _pod_from_signal(name: str, status: str) -> DrilldownPod:
    return DrilldownPod(namespace="default", name=name, phase=status, reason=status)


class HealthReviewFeedbackTest(unittest.TestCase):
    def test_review_handles_sanitized_snapshot(self) -> None:
        raw = json.loads(Path("tests/fixtures/snapshots/sanitized-alpha.json").read_text(encoding="utf-8"))
        raw.setdefault("status", {})["missing_evidence"] = ["events"]
        snapshot = ClusterSnapshot.from_dict(raw)
        target = HealthTarget(
            context=snapshot.metadata.cluster_id,
            label=snapshot.metadata.cluster_id,
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        result = build_health_assessment(snapshot, target, None, BaselinePolicy.empty())
        assessment_data = assessment_to_dict(result.assessment)
        assessment_data["findings"].append(
            {
                "id": "baseline-drift",
                "description": "Baseline expectation no longer holds.",
                "supporting_signals": [],
                "layer": "rollout",
            }
        )
        artifact = _make_health_artifact(
            run_label="health",
            run_id="review-sanitized",
            target=target,
            snapshot=snapshot,
            assessment=assessment_data,
            missing=result.missing_evidence,
            rating=result.rating,
        )
        warnings = (_make_warning_events("default", "Noise", "Repeated event", 2),)
        drilldown = _make_drilldown_artifact(
            run_id="review-sanitized",
            context=target.context,
            label=target.label,
            cluster_id=snapshot.metadata.cluster_id,
            trigger_reasons=("warning_event_threshold",),
            warnings=warnings,
            pods=(),
            missing_evidence=result.missing_evidence,
        )
        review = build_health_review("review-sanitized", [artifact], [drilldown], warning_threshold=1)
        self.assertEqual(6, len(review.quality_summary))
        self.assertIn("missing_evidence", review.failure_modes)
        self.assertTrue(any(proposal for proposal in review.proposed_improvements if proposal.id == "warning-event-threshold"))
        self.assertEqual(target.context, review.selected_drilldowns[0].context)

    def test_review_surfaces_pattern_fixture(self) -> None:
        fixture = json.loads(Path("tests/fixtures/snapshots/deterministic-patterns.json").read_text(encoding="utf-8"))
        snapshots = extract_cluster_snapshots(fixture)
        self.assertGreater(len(snapshots), 0)
        snapshot = snapshots[0]
        target = HealthTarget(
            context=snapshot.metadata.cluster_id,
            label=snapshot.metadata.cluster_id,
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        result = build_health_assessment(snapshot, target, None, BaselinePolicy.empty())
        assessment_data = assessment_to_dict(result.assessment)
        artifact = _make_health_artifact(
            run_label="pattern",
            run_id="review-pattern",
            target=target,
            snapshot=snapshot,
            assessment=assessment_data,
            missing=result.missing_evidence,
            rating=result.rating,
        )
        warnings = tuple(snapshot.health_signals.warning_events)
        drilldown = _make_drilldown_artifact(
            run_id="review-pattern",
            context=target.context,
            label=target.label,
            cluster_id=snapshot.metadata.cluster_id,
            trigger_reasons=result.pattern_reasons,
            warnings=warnings,
            pods=(),
            missing_evidence=result.missing_evidence,
        )
        review = build_health_review("review-pattern", [artifact], [drilldown], warning_threshold=1)
        self.assertIn("probe_failure", review.selected_drilldowns[0].reasons)
        self.assertGreaterEqual(len(review.quality_summary), 6)

    def test_review_scores_live_failure_fixture(self) -> None:
        fixture = load_fixture(Path("fixtures/crashloop_incomplete.json"))
        _, signals = normalize_signals(fixture)
        correlated = correlate_signals(signals)
        findings, hypotheses = build_findings_and_hypotheses(signals, correlated)
        next_checks = propose_next_steps(hypotheses)
        action = build_recommended_action()
        assessment_obj = Assessment(
            observed_signals=signals,
            findings=findings,
            hypotheses=hypotheses,
            next_evidence_to_collect=next_checks,
            recommended_action=action,
            safety_level=action.safety_level,
        )
        assessment_data = assessment_to_dict(assessment_obj)
        target = HealthTarget(
            context="live-ctx",
            label="live-ctx",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        missing_items = [
            gap
            for gap_entry in fixture.get("observability_gaps", [])
            for gap in gap_entry.get("missing", [])
        ]
        snapshot = ClusterSnapshot.from_dict(
            {
                "metadata": {
                    "cluster_id": "live",
                    "captured_at": fixture.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "control_plane_version": "v1",
                    "node_count": 3,
                    "pod_count": 5,
                },
                "status": {
                    "helm_error": None,
                    "missing_evidence": missing_items,
                },
            }
        )
        artifact = _make_health_artifact(
            run_label="live",
            run_id="review-live",
            target=target,
            snapshot=snapshot,
            assessment=assessment_data,
            missing=missing_items,
            rating=HealthRating.DEGRADED,
        )
        warning_events = [
            WarningEventSummary(
                namespace=event.get("namespace", "default"),
                reason=event.get("reason", ""),
                message=event.get("message", ""),
                count=int(event.get("count", 0)),
                last_seen=fixture.get("timestamp", ""),
            )
            for event in fixture.get("signals", {}).get("events", [])
        ]
        pods = [
            DrilldownPod(
                namespace=fixture.get("namespace", "default"),
                name=pod.get("name", ""),
                phase=pod.get("status", ""),
                reason=pod.get("last_message", ""),
            )
            for pod in fixture.get("signals", {}).get("pods", [])
        ]
        drilldown = _make_drilldown_artifact(
            run_id="review-live",
            context=target.context,
            label=target.label,
            cluster_id="live",
            trigger_reasons=("CrashLoopBackOff",),
            warnings=tuple(warning_events),
            pods=tuple(pods),
            missing_evidence=[gap for gap_entry in fixture.get("observability_gaps", []) for gap in gap_entry.get("missing", [])],
        )
        review = build_health_review("review-live", [artifact], [drilldown], warning_threshold=2)
        self.assertIn("missing_evidence", review.failure_modes)
        self.assertGreaterEqual(len(review.selected_drilldowns), 1)
