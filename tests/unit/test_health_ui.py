import json
import shutil
import tempfile
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from k8s_diag_agent.external_analysis.config import (
    AutoDrilldownPolicy,
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from k8s_diag_agent.external_analysis.deterministic_next_check_promotion import (
    collect_promoted_queue_entries,
    write_deterministic_next_check_promotion,
)
from k8s_diag_agent.external_analysis.next_check_approval import record_next_check_approval
from k8s_diag_agent.health.adaptation import HealthProposal
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.loop import (
    DrilldownArtifact,
    HealthAssessmentArtifact,
    HealthRating,
    HealthSnapshotRecord,
    HealthTarget,
)
from k8s_diag_agent.health.notifications import NotificationArtifact
from k8s_diag_agent.health.ui import (
    _PLANNER_NEXT_ACTION_HINTS,
    _PLANNER_STATUS_ENRICHMENT_FAILED,
    _PLANNER_STATUS_ENRICHMENT_NOT_ATTEMPTED,
    _PLANNER_STATUS_ENRICHMENT_SUCCESS_NO_CHECKS,
    _PLANNER_STATUS_PLANNER_MISSING,
    _PLANNER_STATUS_PLANNER_PRESENT,
    _PLANNER_STATUS_POLICY_DISABLED,
    _build_next_check_planner_availability,
    _build_next_check_queue,
    _build_provider_execution,
    _build_review_enrichment_status,
    _classify_blocked_candidate,
    _classify_deterministic_next_check,
    _classify_execution_failure,
    _classify_execution_success,
    _derive_priority_rationale,
    _serialize_review_enrichment,
    write_health_ui_index,
)
from k8s_diag_agent.health.ui_planner_queue import _derive_ranking_reason
from k8s_diag_agent.models import ConfidenceLevel


class HealthUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_status_index(
        self,
        settings: ExternalAnalysisSettings,
        adapters: tuple[str, ...] | None = None,
    ) -> dict[str, object]:
        output_dir = self.tmpdir / "runs" / "health"
        status_path = write_health_ui_index(
            output_dir,
            run_id="status-run",
            run_label="status-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[],
            notifications=[],
            external_analysis_settings=settings,
            available_adapters=adapters,
        )
        return cast(dict[str, object], json.loads(status_path.read_text(encoding="utf-8")))

    def _auto_drilldown_artifact(self, status: ExternalAnalysisStatus) -> ExternalAnalysisArtifact:
        return ExternalAnalysisArtifact(
            tool_name="auto",
            run_id="status-run",
            cluster_label="cluster-a",
            status=status,
            provider="default",
            purpose=ExternalAnalysisPurpose.AUTO_DRILLDOWN,
        )

    def _dummy_drilldown(self) -> DrilldownArtifact:
        timestamp = datetime.now(UTC)
        return DrilldownArtifact(
            run_label="status-run",
            run_id="status-run-1",
            timestamp=timestamp,
            snapshot_timestamp=timestamp,
            context="cluster-a",
            label="cluster-a",
            cluster_id="cluster-a",
            trigger_reasons=(),
            missing_evidence=(),
            evidence_summary={},
            affected_namespaces=(),
            affected_workloads=(),
            warning_events=(),
            non_running_pods=(),
            pod_descriptions={},
            rollout_status=(),
            collection_timestamps={
                "warning_events": timestamp.isoformat(),
                "pods": timestamp.isoformat(),
                "rollouts": timestamp.isoformat(),
            },
        )

    def test_ui_index_contains_expected_keys(self) -> None:
        target = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="prod",
            cluster_role="primary",
            baseline_cohort="fleet",
        )
        snapshot = ClusterSnapshot.from_dict(
            {
                "metadata": {
                    "cluster_id": "cluster-alpha",
                    "captured_at": "2026-01-01T00:00:00Z",
                    "control_plane_version": "v1.26.0",
                    "node_count": 2,
                },
                "health_signals": {
                    "node_conditions": {"ready": 2},
                    "pod_counts": {"non_running": 0},
                    "warning_events": (),
                    "job_failures": 0,
                },
            }
        )
        record = HealthSnapshotRecord(
            target=target,
            snapshot=snapshot,
            path=self.tmpdir / "snapshot.json",
            baseline_policy=BaselinePolicy.empty(),
            baseline_policy_path="health-baseline.json",
        )
        artifact = HealthAssessmentArtifact(
            run_label="health-run",
            run_id="health-run-1",
            timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id="cluster-alpha",
            snapshot_path=str(record.path),
            assessment={"observed_signals": [], "findings": []},
            missing_evidence=(),
            health_rating=HealthRating.HEALTHY,
        )
        drilldown = DrilldownArtifact(
            run_label="health-run",
            run_id="health-run-1",
            timestamp=snapshot.metadata.captured_at,
            snapshot_timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id="cluster-alpha",
            trigger_reasons=("warning_event_threshold",),
            missing_evidence=(),
            evidence_summary={"foo": "bar"},
            affected_namespaces=("default",),
            affected_workloads=(),
            warning_events=(),
            non_running_pods=(),
            pod_descriptions={},
            rollout_status=(),
            collection_timestamps={"warning_events": "2026-01-01T00:00:00Z"},
        )
        proposal = HealthProposal(
            proposal_id="p1",
            source_run_id="health-run-1",
            source_artifact_path="runs/health/review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold",
            rationale="test",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="test",
            rollback_note="test",
        )
        external_path = self.tmpdir / "runs" / "health" / "external-analysis" / "analysis.json"
        external_path.parent.mkdir(parents=True, exist_ok=True)
        external_artifact = ExternalAnalysisArtifact(
            tool_name="k8sgpt",
            run_id="health-run-1",
            cluster_label=target.label,
            source_artifact="assessments/cluster-alpha.json",
            summary="analysis complete",
            findings=("finding1",),
            suggested_next_checks=("check1",),
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=str(external_path),
            provider="k8sgpt",
            duration_ms=150,
        )
        review_artifact = ExternalAnalysisArtifact(
            tool_name="k8sgpt",
            run_id="health-run-1",
            cluster_label="review",
            source_artifact="runs/health/reviews/health-run-1-review.json",
            summary="Review enrichment summary",
            findings=(),
            suggested_next_checks=(),
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/run-1-review-enrichment-k8sgpt.json",
            provider="k8sgpt",
            duration_ms=210,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={
                "triageOrder": ["cluster-b", "cluster-a"],
                "topConcerns": ["ingress latency", "storage delays"],
                "evidenceGaps": ["CDN metrics"],
                "nextChecks": ["Inspect ingress logs"],
                "focusNotes": ["Prioritize cluster-b"],
            },
        )
        plan_payload = {
            "review_path": "runs/health/reviews/health-run-1-review.json",
            "enrichment_artifact_path": "external-analysis/run-1-review-enrichment-k8sgpt.json",
            "candidates": [
                {
                    "description": "kubectl logs -n default deployment/alpha",
                    "targetCluster": "cluster-alpha",
                    "sourceReason": "warning_event_threshold",
                    "expectedSignal": "logs",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "riskLevel": "low",
                    "estimatedCost": "low",
            "confidence": "high",
            "priorityLabel": "primary",
            "gatingReason": None,
                    "duplicateOfExistingEvidence": False,
                    "duplicateEvidenceDescription": None,
                    "candidateId": "candidate-control-plane",
                    "candidateIndex": 0,
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                }
            ],
            "status": "success",
            "summary": "Planned 1 next-check candidate",
            "candidateCount": 1,
        }
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id="health-run-1",
            cluster_label="health-run",
            run_label="health-run",
            source_artifact="runs/health/reviews/health-run-1-review.json",
            summary="Planned 1 next-check candidate",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/health-run-1-next-check-plan.json",
            provider="llamacpp",
            duration_ms=25,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        auto_path = external_path.parent / "auto-drilldown.json"
        auto_artifact = ExternalAnalysisArtifact(
            tool_name="llm-autodrilldown",
            run_id="health-run-1",
            cluster_label=target.label,
            source_artifact="drilldowns/cluster-alpha.json",
            summary="auto insight",
            findings=("auto-finding",),
            suggested_next_checks=("auto-check",),
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=str(auto_path),
            provider="default",
            duration_ms=180,
            purpose=ExternalAnalysisPurpose.AUTO_DRILLDOWN,
        )
        notification = NotificationArtifact(
            kind="degraded-health",
            summary="threshold exceeded",
            details={"missing": ["event"]},
            run_id="health-run-1",
            cluster_label=target.label,
            context=target.context,
        )
        output_dir = self.tmpdir / "runs" / "health"
        notification_path = output_dir / "notifications" / "20260101-degraded-health.json"
        notification_path.parent.mkdir(parents=True, exist_ok=True)
        notification_record = (notification, notification_path)
        history_entries = [
            {
                "tool_name": "k8sgpt",
                "status": "success",
                "timestamp": "2025-12-31T23:58:00Z",
                "duration_ms": 150,
            },
            {
                "tool_name": "llm-autodrilldown",
                "status": "success",
                "timestamp": "2025-12-31T23:57:00Z",
                "duration_ms": 180,
            },
            {
                "tool_name": "k8sgpt",
                "status": "failed",
                "timestamp": "2025-12-31T23:56:00Z",
                "duration_ms": 220,
            },
        ]
        history_dir = output_dir / "external-analysis"
        history_dir.mkdir(parents=True, exist_ok=True)
        for idx, entry in enumerate(history_entries, start=1):
            path = history_dir / f"history-{idx}.json"
            path.write_text(json.dumps(entry), encoding="utf-8")
        settings = ExternalAnalysisSettings(
            auto_drilldown=AutoDrilldownPolicy(enabled=True, provider="default", max_per_run=3)
        )
        result_path = write_health_ui_index(
            output_dir,
            run_id="health-run-1",
            run_label="health-run",
            collector_version="1.0",
            records=[record],
            assessments=[artifact],
            drilldowns=[drilldown],
            proposals=[proposal],
            external_analysis=[
                review_artifact,
                external_artifact,
                auto_artifact,
                plan_artifact,
            ],
            notifications=[notification_record],
            external_analysis_settings=settings,
        )
        self.assertTrue(result_path.exists())
        data = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertIn("run", data)
        self.assertIn("clusters", data)
        self.assertIn("drilldowns", data)
        self.assertIn("latest_drilldown", data)
        self.assertIn("proposals", data)
        self.assertEqual(len(data["clusters"]), 1)
        self.assertEqual(len(data["drilldowns"]), 1)
        self.assertEqual(len(data["proposals"]), 1)
        cluster_entry = data["clusters"][0]
        self.assertIn("cluster_class", cluster_entry)
        self.assertIn("cluster_role", cluster_entry)
        self.assertIn("artifact_paths", cluster_entry)
        self.assertIn("fleet_status", data)
        self.assertIn("proposal_status_summary", data)
        self.assertIn("artifact_path", data["latest_drilldown"])
        self.assertIn("artifact_path", data["proposals"][0])
        self.assertIn("drilldown_availability", data)
        self.assertEqual(data["drilldown_availability"]["available"], 1)
        self.assertIn("notification_history", data)
        self.assertEqual(data["notification_history"][0]["kind"], "degraded-health")
        self.assertIn("external_analysis", data)
        self.assertEqual(data["external_analysis"]["count"], 4)
        self.assertEqual(data["run"]["notification_count"], 1)
        self.assertIn("latest_assessment", data)
        self.assertEqual(data["latest_assessment"]["cluster_label"], "cluster-alpha")
        self.assertIn("artifact_path", data["latest_assessment"])
        llm_stats = data["run"].get("llm_stats")
        self.assertIsNotNone(llm_stats)
        self.assertEqual(llm_stats["totalCalls"], 3)
        self.assertEqual(llm_stats["successfulCalls"], 3)
        self.assertEqual(llm_stats["failedCalls"], 0)
        self.assertEqual(llm_stats["p50LatencyMs"], 180)
        self.assertEqual(llm_stats["providerBreakdown"][0]["provider"], "k8sgpt")
        self.assertEqual(llm_stats["scope"], "current_run")
        historical_stats = data["run"].get("historical_llm_stats")
        self.assertIsNotNone(historical_stats)
        self.assertEqual(historical_stats["totalCalls"], 3)
        self.assertEqual(historical_stats["successfulCalls"], 2)
        self.assertEqual(historical_stats["failedCalls"], 1)
        self.assertEqual(historical_stats["lastCallTimestamp"], "2025-12-31T23:58:00Z")
        self.assertEqual(historical_stats["p50LatencyMs"], 180)
        self.assertEqual(historical_stats["p95LatencyMs"], 220)
        self.assertEqual(historical_stats["p99LatencyMs"], 220)
        self.assertEqual(historical_stats["scope"], "retained_history")
        self.assertEqual(historical_stats["providerBreakdown"][0]["provider"], "k8sgpt")
        self.assertEqual(historical_stats["providerBreakdown"][1]["provider"], "llm-autodrilldown")
        llm_policy = data["run"].get("llm_policy")
        self.assertIsNotNone(llm_policy)
        auto_policy = llm_policy["auto_drilldown"]
        self.assertTrue(auto_policy["enabled"])
        self.assertEqual(auto_policy["provider"], "default")
        self.assertEqual(auto_policy["maxPerRun"], 3)

    def test_deterministic_next_checks_projection_appears(self) -> None:
        data = self._build_sample_deterministic_run_index()
        deterministic = data["run"].get("deterministic_next_checks")
        self.assertIsNotNone(deterministic)
        assert isinstance(deterministic, dict)
        self.assertEqual(deterministic.get("clusterCount"), 1)
        self.assertEqual(deterministic.get("totalNextCheckCount"), 1)
        cluster_entry = deterministic["clusters"][0]
        self.assertEqual(cluster_entry.get("label"), "cluster-beta")
        self.assertEqual(cluster_entry.get("topProblem"), "tcpdump-investigation")
        self.assertEqual(cluster_entry.get("deterministicNextCheckCount"), 1)
        summaries = cluster_entry.get("deterministicNextCheckSummaries")
        self.assertIsInstance(summaries, list)
        self.assertEqual(summaries[0]["description"], "Capture tcpdump")
        self.assertEqual(summaries[0]["method"], "kubectl exec")
        self.assertEqual(cluster_entry.get("assessmentArtifactPath"), "assessments/cluster-beta.json")
        self.assertEqual(cluster_entry.get("drilldownArtifactPath"), "drilldowns/cluster-beta.json")

    def test_classifies_summary_as_incident_when_tied_to_top_problem(self) -> None:
        summary = {
            "description": "Check crashing pod logs",
            "owner": "platform",
            "method": "kubectl logs",
            "evidenceNeeded": ["pod logs"],
        }
        result = _classify_deterministic_next_check(summary, "pod restart")
        self.assertEqual(result.get("workstream"), "incident")
        self.assertEqual(result.get("urgency"), "high")
        self.assertTrue(result.get("isPrimaryTriage"))
        self.assertIn("pod restart", str(result.get("whyNow")))

    def test_classifies_general_status_checks_as_evidence(self) -> None:
        summary = {
            "description": "Review node status overview",
            "owner": "platform engineer",
            "method": "kubectl describe nodes",
            "evidenceNeeded": [],
        }
        result = _classify_deterministic_next_check(summary, None)
        self.assertEqual(result.get("workstream"), "evidence")
        self.assertEqual(result.get("urgency"), "medium")
        self.assertFalse(result.get("isPrimaryTriage"))
        self.assertIn("Gather additional evidence", str(result.get("whyNow")))

    def test_classifies_version_parity_checks_as_drift(self) -> None:
        summary = {
            "description": "Compare baseline release parity",
            "owner": "platform",
            "method": "kubectl get helmrelease",
            "evidenceNeeded": ["helm release list"],
        }
        result = _classify_deterministic_next_check(summary, None)
        self.assertEqual(result.get("workstream"), "drift")
        self.assertEqual(result.get("urgency"), "low")
        self.assertFalse(result.get("isPrimaryTriage"))
        self.assertIn("drift", str(result.get("whyNow")).lower())

    def test_drift_summary_promotes_to_incident_when_directly_tied_to_symptom(self) -> None:
        summary = {
            "description": "Validate baseline parity for pods that kept crashing",
            "owner": "platform engineer",
            "method": "kubectl get helmrelease",
            "evidenceNeeded": ["crashloop data"],
        }
        result = _classify_deterministic_next_check(summary, "pod crash")
        self.assertEqual(result.get("workstream"), "incident")
        self.assertEqual(result.get("urgency"), "high")
    def test_queue_explanation_counts_align_with_deterministic_projection(self) -> None:
        data = self._build_sample_deterministic_run_index()
        run_entry = data["run"]
        deterministic = run_entry.get("deterministic_next_checks")
        queue_explanation = run_entry.get("next_check_queue_explanation")
        self.assertIsNotNone(deterministic)
        self.assertIsNotNone(queue_explanation)
        cluster_state = queue_explanation["clusterState"]
        self.assertEqual(
            deterministic.get("totalNextCheckCount"),
            cluster_state.get("deterministicNextCheckCount"),
        )
        self.assertEqual(
            deterministic.get("clusterCount"),
            cluster_state.get("deterministicClusterCount"),
        )
        self.assertEqual(
            bool(deterministic.get("totalNextCheckCount")),
            bool(queue_explanation.get("deterministicNextChecksAvailable")),
        )
        self.assertEqual(
            cluster_state.get("degradedClusterCount"),
            len(cluster_state.get("degradedClusterLabels", [])),
        )

    def test_generic_checks_are_contextualized_and_scored(self) -> None:
        data = self._build_generic_next_checks_index()
        deterministic = data["run"].get("deterministic_next_checks")
        self.assertIsNotNone(deterministic)
        assert isinstance(deterministic, dict)
        cluster_entry = deterministic["clusters"][0]
        summaries = cluster_entry.get("deterministicNextCheckSummaries", [])
        self.assertGreaterEqual(len(summaries), 3)
        descriptions = [str(summary.get("description") or "") for summary in summaries]
        self.assertTrue(any("cluster-generic" in desc for desc in descriptions))
        self.assertTrue(any("pod-crash" in desc for desc in descriptions))
        self.assertEqual(descriptions[0], "Capture tcpdump")
        for summary in summaries:
            self.assertIsInstance(summary.get("priorityScore"), int)

    def _build_sample_deterministic_run_index(self) -> dict[str, object]:
        target = HealthTarget(
            context="cluster-beta",
            label="cluster-beta",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="prod",
            cluster_role="primary",
            baseline_cohort="fleet",
        )
        snapshot = ClusterSnapshot.from_dict(
            {
                "metadata": {
                    "cluster_id": "cluster-beta",
                    "captured_at": "2026-01-02T00:00:00Z",
                    "control_plane_version": "v1.26.0",
                    "node_count": 2,
                },
                "health_signals": {
                    "node_conditions": {"ready": 2},
                    "pod_counts": {"non_running": 0},
                    "warning_events": (),
                    "job_failures": 0,
                },
            }
        )
        record = HealthSnapshotRecord(
            target=target,
            snapshot=snapshot,
            path=self.tmpdir / "snapshot-beta.json",
            baseline_policy=BaselinePolicy.empty(),
            baseline_policy_path="baseline.json",
        )
        assessment = HealthAssessmentArtifact(
            run_label="run-deterministic",
            run_id="run-deterministic-1",
            timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id=target.label,
            snapshot_path=str(record.path),
            assessment={
                "next_evidence_to_collect": [
                    {
                        "description": "Capture tcpdump",
                        "owner": "platform",
                        "method": "kubectl exec",
                        "evidence_needed": ["tcpdump output"],
                    }
                ],
            },
            missing_evidence=(),
            health_rating=HealthRating.DEGRADED,
        )
        assessment.artifact_path = "assessments/cluster-beta.json"
        drilldown = DrilldownArtifact(
            run_label="run-deterministic",
            run_id="run-deterministic-1",
            timestamp=snapshot.metadata.captured_at,
            snapshot_timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id=target.label,
            trigger_reasons=("tcpdump-investigation",),
            missing_evidence=(),
            evidence_summary={"note": "tcpdump pending"},
            affected_namespaces=(),
            affected_workloads=(),
            warning_events=(),
            non_running_pods=(),
            pod_descriptions={},
            rollout_status=(),
            collection_timestamps={
                "pods": snapshot.metadata.captured_at.isoformat(),
            },
            artifact_path="drilldowns/cluster-beta.json",
        )
        output_dir = self.tmpdir / "runs" / "health"
        result_path = write_health_ui_index(
            output_dir,
            run_id="run-deterministic-1",
            run_label="run-deterministic",
            collector_version="1.0",
            records=[record],
            assessments=[assessment],
            drilldowns=[drilldown],
            proposals=[],
            external_analysis=[],
            notifications=[],
        )
        return cast(dict[str, object], json.loads(result_path.read_text(encoding="utf-8")))

    def _build_generic_next_checks_index(self) -> dict[str, object]:
        target = HealthTarget(
            context="cluster-generic",
            label="cluster-generic",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="prod",
            cluster_role="primary",
            baseline_cohort="fleet",
        )
        snapshot = ClusterSnapshot.from_dict(
            {
                "metadata": {
                    "cluster_id": "cluster-generic",
                    "captured_at": "2026-01-03T00:00:00Z",
                    "control_plane_version": "v1.26.0",
                    "node_count": 3,
                },
                "health_signals": {
                    "node_conditions": {"ready": 3},
                    "pod_counts": {"non_running": 1},
                    "warning_events": (),
                    "job_failures": 0,
                },
            }
        )
        record = HealthSnapshotRecord(
            target=target,
            snapshot=snapshot,
            path=self.tmpdir / "snapshot-generic.json",
            baseline_policy=BaselinePolicy.empty(),
            baseline_policy_path="baseline.json",
        )
        assessment = HealthAssessmentArtifact(
            run_label="generic-run",
            run_id="generic-run-1",
            timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id=target.label,
            snapshot_path=str(record.path),
            assessment={
                "next_evidence_to_collect": [
                    {
                        "description": "Capture tcpdump",
                        "owner": "platform",
                        "method": "kubectl exec",
                        "evidence_needed": ["tcpdump output"],
                    },
                    {
                        "description": "Review node, pod, and control plane status before taking action.",
                        "owner": "platform engineer",
                        "method": "kubectl",
                        "evidence_needed": ["nodes", "pods", "control plane version"],
                    },
                    {
                        "description": "Investigate the flagged nodes, pods, jobs, and warning events.",
                        "owner": "platform engineer",
                        "method": "kubectl",
                        "evidence_needed": ["nodes", "pods", "jobs", "events"],
                    },
                ]
            },
            missing_evidence=(),
            health_rating=HealthRating.DEGRADED,
        )
        assessment.artifact_path = "assessments/cluster-generic.json"
        drilldown = DrilldownArtifact(
            run_label="generic-run",
            run_id="generic-run-1",
            timestamp=snapshot.metadata.captured_at,
            snapshot_timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id=target.label,
            trigger_reasons=("pod-crash",),
            missing_evidence=(),
            evidence_summary={"note": "tcpdump pending"},
            affected_namespaces=("default",),
            affected_workloads=(
                {
                    "kind": "Deployment",
                    "namespace": "default",
                    "name": "web",
                    "phase": "CrashLoopBackOff",
                    "reason": "CrashLoopBackOff",
                },
            ),
            warning_events=(),
            non_running_pods=(),
            pod_descriptions={},
            rollout_status=(),
            collection_timestamps={"pods": snapshot.metadata.captured_at.isoformat()},
            artifact_path="drilldowns/cluster-generic.json",
        )
        output_dir = self.tmpdir / "runs" / "health-generic"
        result_path = write_health_ui_index(
            output_dir,
            run_id="generic-run-1",
            run_label="generic-run",
            collector_version="1.0",
            records=[record],
            assessments=[assessment],
            drilldowns=[drilldown],
            proposals=[],
            external_analysis=[],
            notifications=[],
        )
        return cast(dict[str, object], json.loads(result_path.read_text(encoding="utf-8")))

    def test_next_check_plan_includes_approval_metadata(self) -> None:
        run_id = "approval-run"
        run_label = "approval-run"
        output_dir = self.tmpdir / "runs" / "health"
        artifact_dir = output_dir / "external-analysis"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        plan_artifact_path = "external-analysis/approval-plan.json"
        candidate_description = "Inspect control plane pods"
        plan_payload: dict[str, object] = {
            "status": "success",
            "summary": "Approval candidate",
            "artifactPath": plan_artifact_path,
            "review_path": "reviews/approval-run-review.json",
            "enrichment_artifact_path": "external-analysis/approval-review.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": candidate_description,
                    "targetCluster": "cluster-a",
                    "requiresOperatorApproval": True,
                    "safeToAutomate": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "candidate-control-plane",
                    "candidateIndex": 0,
                    "normalizationReason": "selection_default",
                    "safetyReason": "unknown_command",
                    "approvalReason": "unknown_command",
                    "duplicateReason": None,
                    "blockingReason": "unknown_command",
                }
            ],
        }
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id=run_id,
            run_label=run_label,
            cluster_label=run_label,
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/approval-plan.json",
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        write_external_analysis_artifact(artifact_dir / "approval-plan.json", plan_artifact)
        approval_artifact = record_next_check_approval(
            runs_dir=output_dir,
            run_id=run_id,
            run_label=run_label,
            plan_artifact_path=plan_artifact_path,
            candidate_index=0,
            candidate_description=candidate_description,
            target_cluster="cluster-a",
        )
        settings = ExternalAnalysisSettings()
        index_path = write_health_ui_index(
            output_dir,
            run_id=run_id,
            run_label=run_label,
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[plan_artifact, approval_artifact],
            notifications=[],
            external_analysis_settings=settings,
        )
        data = json.loads(index_path.read_text(encoding="utf-8"))
        plan_entry = data["run"].get("next_check_plan")
        self.assertIsNotNone(plan_entry)
        candidate_entry = plan_entry["candidates"][0]
        self.assertEqual(candidate_entry.get("approvalStatus"), "approved")
        self.assertIsNotNone(candidate_entry.get("approvalArtifactPath"))
        self.assertIsNotNone(candidate_entry.get("approvalTimestamp"))

    def test_build_next_check_queue_orders_statuses(self) -> None:
        plan_entry: dict[str, object] = {
            "candidates": [
                {
                    "candidateId": "approved-ready",
                    "description": "Candidate awaiting run",
                    "requiresOperatorApproval": True,
                    "approvalState": "approved",
                    "executionState": "unexecuted",
                    "safeToAutomate": False,
                    "priorityLabel": "primary",
                },
                {
                    "candidateId": "safe-ready",
                    "description": "Safe to automate",
                    "requiresOperatorApproval": False,
                    "safeToAutomate": True,
                    "executionState": "unexecuted",
                    "priorityLabel": "secondary",
                },
                {
                    "candidateId": "approval-needed",
                    "description": "Requires approval",
                    "requiresOperatorApproval": True,
                    "approvalState": "approval-required",
                    "executionState": "unexecuted",
                    "safeToAutomate": False,
                    "priorityLabel": "fallback",
                },
                {
                    "candidateId": "failed",
                    "description": "Failed execution",
                    "requiresOperatorApproval": False,
                    "safeToAutomate": True,
                    "executionState": "executed-failed",
                    "priorityLabel": "secondary",
                },
                {
                    "candidateId": "completed",
                    "description": "Already executed",
                    "requiresOperatorApproval": False,
                    "safeToAutomate": True,
                    "executionState": "executed-success",
                    "priorityLabel": "secondary",
                },
                {
                    "candidateId": "duplicate",
                    "description": "Duplicate evidence",
                    "requiresOperatorApproval": False,
                    "safeToAutomate": False,
                    "duplicateOfExistingEvidence": True,
                    "priorityLabel": "fallback",
                },
                {
                    "candidateId": "approval-stale",
                    "description": "Stale approval",
                    "requiresOperatorApproval": True,
                    "approvalState": "approval-stale",
                    "executionState": "unexecuted",
                    "safeToAutomate": False,
                    "priorityLabel": "secondary",
                },
            ]
        }
        plan_entry["artifactPath"] = "external-analysis/queue-plan.json"
        queue = _build_next_check_queue(plan_entry, {})
        statuses = [entry.get("queueStatus") for entry in queue]
        self.assertEqual(
            statuses,
            [
                "approved-ready",
                "safe-ready",
                "approval-needed",
                "failed",
                "completed",
                "duplicate-or-stale",
                "duplicate-or-stale",
            ],
        )
        self.assertEqual(queue[0].get("candidateIndex"), 0)
        self.assertEqual(queue[1].get("candidateIndex"), 1)
        self.assertEqual(
            queue[0].get("planArtifactPath"),
            "external-analysis/queue-plan.json",
        )
        self.assertIsNotNone(queue[0].get("commandPreview"))
        self.assertIn("targetContext", queue[0])

    def test_collect_promoted_queue_entries_exposes_deterministic_source(self) -> None:
        runs_dir = self.tmpdir / "runs" / "health"
        run_id = "promo-run"
        run_label = "promo-run"
        summary = {
            "description": "Inspect promoted logs",
            "method": "kubectl logs",
            "whyNow": "Immediate triage",
            "workstream": "incident",
            "evidenceNeeded": ["logs"],
        }
        artifact, payload = write_deterministic_next_check_promotion(
            runs_dir=runs_dir,
            run_id=run_id,
            run_label=run_label,
            cluster_label="cluster-deterministic",
            target_context="prod",
            summary=summary,
        )
        entries = collect_promoted_queue_entries(runs_dir, run_id)
        self.assertTrue(entries)
        entry = entries[0]
        self.assertEqual(entry.get("sourceType"), "deterministic")
        self.assertEqual(entry.get("queueStatus"), "approval-needed")
        self.assertEqual(entry.get("planArtifactPath"), artifact.artifact_path)

    def test_next_check_plan_marks_stale_approval_when_plan_changes(self) -> None:
        run_id = "stale-run"
        run_label = "stale-run"
        output_dir = self.tmpdir / "runs" / "health"
        artifact_dir = output_dir / "external-analysis"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        plan_path = "external-analysis/stale-plan-new.json"
        plan_payload: dict[str, object] = {
            "status": "success",
            "summary": "Stale approval candidate",
            "artifactPath": plan_path,
            "review_path": "reviews/stale-run-review.json",
            "enrichment_artifact_path": "external-analysis/stale-run-review.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": "Inspect stale pods",
                    "targetCluster": "cluster-a",
                    "requiresOperatorApproval": True,
                    "safeToAutomate": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "candidate-stale",
                    "candidateIndex": 0,
                    "normalizationReason": "selection_default",
                    "safetyReason": "unknown_command",
                    "approvalReason": "unknown_command",
                    "duplicateReason": None,
                    "blockingReason": "unknown_command",
                }
            ],
        }
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id=run_id,
            run_label=run_label,
            cluster_label=run_label,
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=plan_path,
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        write_external_analysis_artifact(artifact_dir / "stale-plan-new.json", plan_artifact)
        stale_plan_path = "external-analysis/stale-plan-old.json"
        approval_artifact = record_next_check_approval(
            runs_dir=output_dir,
            run_id=run_id,
            run_label=run_label,
            plan_artifact_path=stale_plan_path,
            candidate_index=0,
            candidate_id="candidate-stale",
            candidate_description="Inspect stale pods",
            target_cluster="cluster-a",
        )
        settings = ExternalAnalysisSettings()
        index_path = write_health_ui_index(
            output_dir,
            run_id=run_id,
            run_label=run_label,
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[plan_artifact, approval_artifact],
            notifications=[],
            external_analysis_settings=settings,
        )
        data = json.loads(index_path.read_text(encoding="utf-8"))
        plan_entry = data["run"].get("next_check_plan")
        self.assertIsNotNone(plan_entry)
        candidate_entry = plan_entry["candidates"][0]
        self.assertEqual(candidate_entry.get("approvalStatus"), "approval-stale")

    def test_next_check_plan_exports_orphaned_approvals(self) -> None:
        run_id = "orphan-run"
        run_label = "orphan-run"
        output_dir = self.tmpdir / "runs" / "health"
        artifact_dir = output_dir / "external-analysis"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        plan_path = "external-analysis/orphan-plan.json"
        plan_payload: dict[str, object] = {
            "status": "success",
            "summary": "Orphaned approval",
            "artifactPath": plan_path,
            "review_path": "reviews/orphan-run-review.json",
            "enrichment_artifact_path": "external-analysis/orphan-run-review.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": "Inspect current pods",
                    "targetCluster": "cluster-a",
                    "requiresOperatorApproval": True,
                    "safeToAutomate": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "candidate-present",
                    "candidateIndex": 0,
                    "normalizationReason": "selection_default",
                    "safetyReason": "unknown_command",
                    "approvalReason": "unknown_command",
                    "duplicateReason": None,
                    "blockingReason": "unknown_command",
                }
            ],
        }
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id=run_id,
            run_label=run_label,
            cluster_label=run_label,
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=plan_path,
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        write_external_analysis_artifact(artifact_dir / "orphan-plan.json", plan_artifact)
        orphan_artifact = record_next_check_approval(
            runs_dir=output_dir,
            run_id=run_id,
            run_label=run_label,
            plan_artifact_path=plan_path,
            candidate_index=1,
            candidate_id="candidate-missing",
            candidate_description="Inspect missing pods",
            target_cluster="cluster-b",
        )
        settings = ExternalAnalysisSettings()
        index_path = write_health_ui_index(
            output_dir,
            run_id=run_id,
            run_label=run_label,
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[plan_artifact, orphan_artifact],
            notifications=[],
            external_analysis_settings=settings,
        )
        data = json.loads(index_path.read_text(encoding="utf-8"))
        plan_entry = data["run"].get("next_check_plan")
        self.assertIsNotNone(plan_entry)
        orphaned = plan_entry.get("orphanedApprovals") or []
        self.assertEqual(len(orphaned), 1)
        entry = orphaned[0]
        self.assertEqual(entry.get("approvalStatus"), "approval-orphaned")
        self.assertEqual(entry.get("candidateId"), "candidate-missing")

    def test_next_check_plan_uses_index_fallback_for_legacy_approvals(self) -> None:
        run_id = "legacy-run"
        run_label = "legacy-run"
        output_dir = self.tmpdir / "runs" / "health"
        artifact_dir = output_dir / "external-analysis"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        plan_path = "external-analysis/legacy-plan.json"
        plan_payload: dict[str, object] = {
            "status": "success",
            "summary": "Legacy index approval",
            "artifactPath": plan_path,
            "review_path": "reviews/legacy-run-review.json",
            "enrichment_artifact_path": "external-analysis/legacy-run-review.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": "Inspect legacy pods",
                    "targetCluster": "cluster-a",
                    "requiresOperatorApproval": True,
                    "safeToAutomate": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateIndex": 0,
                    "normalizationReason": "selection_default",
                    "safetyReason": "unknown_command",
                    "approvalReason": "unknown_command",
                    "duplicateReason": None,
                    "blockingReason": "unknown_command",
                }
            ],
        }
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id=run_id,
            run_label=run_label,
            cluster_label=run_label,
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=plan_path,
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        write_external_analysis_artifact(artifact_dir / "legacy-plan.json", plan_artifact)
        approval_artifact = record_next_check_approval(
            runs_dir=output_dir,
            run_id=run_id,
            run_label=run_label,
            plan_artifact_path=plan_path,
            candidate_index=0,
            candidate_id=None,
            candidate_description="Inspect legacy pods",
            target_cluster="cluster-a",
        )
        settings = ExternalAnalysisSettings()
        index_path = write_health_ui_index(
            output_dir,
            run_id=run_id,
            run_label=run_label,
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[plan_artifact, approval_artifact],
            notifications=[],
            external_analysis_settings=settings,
        )
        data = json.loads(index_path.read_text(encoding="utf-8"))
        plan_entry = data["run"].get("next_check_plan")
        self.assertIsNotNone(plan_entry)
        candidate_entry = plan_entry["candidates"][0]
        self.assertEqual(candidate_entry.get("approvalStatus"), "approved")

    def test_next_check_plan_outcome_summary_reflects_artifacts(self) -> None:
        run_id = "outcome-run"
        run_label = "outcome-run"
        output_dir = self.tmpdir / "runs" / "health"
        artifact_dir = output_dir / "external-analysis"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        plan_path = "external-analysis/outcome-plan.json"
        plan_payload: dict[str, object] = {
            "status": "success",
            "summary": "Outcome summary test",
            "artifactPath": plan_path,
            "review_path": "reviews/outcome-run-review.json",
            "enrichment_artifact_path": "external-analysis/outcome-run-review.json",
            "candidateCount": 5,
            "candidates": [
                {
                    "description": "Inspect approved candidate",
                    "targetCluster": "cluster-a",
                    "safeToAutomate": False,
                    "requiresOperatorApproval": True,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "approved-executed",
                    "candidateIndex": 0,
                },
                {
                    "description": "Approval pending candidate",
                    "targetCluster": "cluster-a",
                    "safeToAutomate": False,
                    "requiresOperatorApproval": True,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "approval-required",
                    "candidateIndex": 1,
                },
                {
                    "description": "Stale approval candidate",
                    "targetCluster": "cluster-a",
                    "safeToAutomate": False,
                    "requiresOperatorApproval": True,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "stale-approval",
                    "candidateIndex": 2,
                },
                {
                    "description": "Executed failure",
                    "targetCluster": "cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "executed-failed",
                    "candidateIndex": 3,
                },
                {
                    "description": "Unused safe candidate",
                    "targetCluster": "cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                    "candidateId": "safe-unused",
                    "candidateIndex": 4,
                },
            ],
        }
        plan_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id=run_id,
            run_label=run_label,
            cluster_label=run_label,
            summary="Planner",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=plan_path,
            provider="planner",
            duration_ms=10,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan_payload,
        )
        write_external_analysis_artifact(artifact_dir / "outcome-plan.json", plan_artifact)
        approved_artifact = record_next_check_approval(
            runs_dir=output_dir,
            run_id=run_id,
            run_label=run_label,
            plan_artifact_path=plan_path,
            candidate_index=0,
            candidate_id="approved-executed",
            candidate_description="Inspect approved candidate",
            target_cluster="cluster-a",
        )
        stale_plan_path = "external-analysis/outcome-plan-old.json"
        stale_artifact = record_next_check_approval(
            runs_dir=output_dir,
            run_id=run_id,
            run_label=run_label,
            plan_artifact_path=stale_plan_path,
            candidate_index=2,
            candidate_id="stale-approval",
            candidate_description="Stale approval candidate",
            target_cluster="cluster-a",
        )
        success_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id=run_id,
            run_label=run_label,
            cluster_label="cluster-a",
            summary="Executed success",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/outcome-exec-success.json",
            provider="runner",
            duration_ms=45,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={
                "candidateId": "approved-executed",
                "candidateIndex": 0,
            },
        )
        failure_artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id=run_id,
            run_label=run_label,
            cluster_label="cluster-a",
            summary="Execution failed",
            status=ExternalAnalysisStatus.FAILED,
            artifact_path="external-analysis/outcome-exec-failed.json",
            provider="runner",
            duration_ms=62,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={
                "candidateId": "executed-failed",
                "candidateIndex": 3,
            },
        )
        index_path = write_health_ui_index(
            output_dir,
            run_id=run_id,
            run_label=run_label,
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[
                plan_artifact,
                approved_artifact,
                stale_artifact,
                success_artifact,
                failure_artifact,
            ],
            notifications=[],
            external_analysis_settings=ExternalAnalysisSettings(),
        )
        raw = cast(dict[str, object], json.loads(index_path.read_text(encoding="utf-8")))
        plan_entry = raw["run"].get("next_check_plan")
        self.assertIsNotNone(plan_entry)
        assert isinstance(plan_entry, dict)
        candidates = plan_entry.get("candidates") or []
        candidate_map = {
            str(entry.get("candidateId")): entry for entry in candidates if isinstance(entry, Mapping)
        }
        approved = candidate_map.get("approved-executed") or {}
        self.assertEqual(approved.get("executionState"), "executed-success")
        self.assertEqual(approved.get("outcomeStatus"), "executed-success")
        self.assertEqual(approved.get("approvalState"), "approved")
        pending = candidate_map.get("approval-required") or {}
        self.assertEqual(pending.get("approvalState"), "approval-required")
        self.assertEqual(pending.get("outcomeStatus"), "approval-required")
        stale = candidate_map.get("stale-approval") or {}
        self.assertEqual(stale.get("approvalState"), "approval-stale")
        failed = candidate_map.get("executed-failed") or {}
        self.assertEqual(failed.get("executionState"), "executed-failed")
        self.assertEqual(failed.get("outcomeStatus"), "executed-failed")
        unused = candidate_map.get("safe-unused") or {}
        self.assertEqual(unused.get("outcomeStatus"), "not-used")
        counts = {entry.get("status"): entry.get("count") for entry in plan_entry.get("outcomeCounts") or []}
        self.assertEqual(counts.get("executed-success"), 1)
        self.assertEqual(counts.get("approval-required"), 1)
        self.assertEqual(counts.get("executed-failed"), 1)
        self.assertEqual(counts.get("not-used"), 1)
        self.assertEqual(counts.get("approval-stale"), 1)
        self.assertEqual(plan_entry.get("orphanedApprovalCount"), 0)

    def test_failed_review_enrichment_artifact_still_exposed(self) -> None:
        output_dir = self.tmpdir / "runs" / "health"
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact = ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id="failed-run",
            cluster_label="cluster-a",
            source_artifact="runs/health/reviews/failed-run-review.json",
            summary="Failure insight",
            findings=(),
            suggested_next_checks=(),
            status=ExternalAnalysisStatus.FAILED,
            artifact_path="external-analysis/failed-run-review-enrichment.json",
            provider="reviewer",
            duration_ms=100,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={
                "topConcerns": ["latency"],
                "nextChecks": ["examine"],
            },
        )
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="reviewer")
        )
        result_path = write_health_ui_index(
            output_dir,
            run_id="failed-run",
            run_label="failed-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[artifact],
            notifications=[],
            external_analysis_settings=settings,
        )
        data = json.loads(result_path.read_text(encoding="utf-8"))
        enrichment = data["run"].get("review_enrichment")
        self.assertIsNotNone(enrichment)
        self.assertEqual(enrichment["status"], "failed")
        self.assertEqual(enrichment.get("provider"), "reviewer")
        status_entry = data["run"].get("review_enrichment_status")
        self.assertIsNone(status_entry)

    def test_historical_llm_stats_handles_missing_durations(self) -> None:
        output_dir = self.tmpdir / "runs" / "health"
        history_dir = output_dir / "external-analysis"
        history_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "tool_name": "k8sgpt",
            "status": "success",
            "timestamp": "2025-12-31T23:50:00Z",
        }
        (history_dir / "missing-duration.json").write_text(json.dumps(entry), encoding="utf-8")
        result_path = write_health_ui_index(
            output_dir,
            run_id="health-run-missing",
            run_label="health-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[],
            notifications=[],
            external_analysis_settings=ExternalAnalysisSettings(),
        )
        data = json.loads(result_path.read_text(encoding="utf-8"))
        historical_stats = data["run"].get("historical_llm_stats")
        self.assertIsNotNone(historical_stats)
        self.assertEqual(historical_stats["totalCalls"], 1)
        self.assertEqual(historical_stats["successfulCalls"], 1)
        self.assertEqual(historical_stats["failedCalls"], 0)
        self.assertEqual(historical_stats["lastCallTimestamp"], "2025-12-31T23:50:00Z")
        self.assertIsNone(historical_stats["p50LatencyMs"])
        self.assertIsNone(historical_stats["p95LatencyMs"])
        self.assertIsNone(historical_stats["p99LatencyMs"])
        self.assertEqual(historical_stats["scope"], "retained_history")

    def test_run_stats_include_durations_from_reviews(self) -> None:
        output_dir = self.tmpdir / "runs" / "health"
        reviews_dir = output_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        durations = [8, 11, 15, 18, 30]
        for idx, seconds in enumerate(durations, start=1):
            run_id = f"health-run-20260101T00000{idx}Z"
            start = datetime.strptime(run_id[-16:], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            finish = start + timedelta(seconds=seconds)
            review_path = reviews_dir / f"{run_id}-review.json"
            review_path.write_text(
                json.dumps({"run_id": run_id, "timestamp": finish.isoformat()}),
                encoding="utf-8",
            )
        target = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        snapshot = ClusterSnapshot.from_dict(
            {
                "metadata": {
                    "cluster_id": "cluster-alpha",
                    "captured_at": "2026-01-01T00:00:00Z",
                    "control_plane_version": "v1.26.0",
                    "node_count": 2,
                },
                "health_signals": {
                    "node_conditions": {"ready": 2},
                    "pod_counts": {"non_running": 0},
                    "warning_events": (),
                    "job_failures": 0,
                },
            }
        )
        record = HealthSnapshotRecord(
            target=target,
            snapshot=snapshot,
            path=self.tmpdir / "snapshot.json",
            baseline_policy=BaselinePolicy.empty(),
            baseline_policy_path="baseline.json",
        )
        artifact = HealthAssessmentArtifact(
            run_label="health-run",
            run_id="health-run-1",
            timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id="cluster-alpha",
            snapshot_path=str(record.path),
            assessment={"observed_signals": [], "findings": []},
            missing_evidence=(),
            health_rating=HealthRating.HEALTHY,
        )
        result_path = write_health_ui_index(
            output_dir,
            run_id="health-run-1",
            run_label="health-run",
            collector_version="1.0",
            records=[record],
            assessments=[artifact],
            drilldowns=[],
            proposals=[],
            external_analysis=[],
            notifications=[],
            external_analysis_settings=ExternalAnalysisSettings(),
        )
        data = json.loads(result_path.read_text(encoding="utf-8"))
        stats = data.get("run_stats")
        self.assertIsInstance(stats, dict)
        self.assertEqual(stats.get("total_runs"), len(durations))
        self.assertEqual(stats.get("last_run_duration_seconds"), durations[-1])
        self.assertEqual(stats.get("p50_run_duration_seconds"), 15)
        self.assertEqual(stats.get("p95_run_duration_seconds"), 30)
        self.assertEqual(stats.get("p99_run_duration_seconds"), 30)

    def test_llm_policy_budget_exhausted_when_drilldowns_exceed_budget(self) -> None:
        target = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        snapshot = ClusterSnapshot.from_dict(
            {
                "metadata": {
                    "cluster_id": "cluster-alpha",
                    "captured_at": "2026-01-01T00:00:00Z",
                    "control_plane_version": "v1.26.0",
                    "node_count": 2,
                },
                "health_signals": {
                    "node_conditions": {"ready": 2},
                    "pod_counts": {"non_running": 0},
                    "warning_events": (),
                    "job_failures": 0,
                },
            }
        )
        record = HealthSnapshotRecord(
            target=target,
            snapshot=snapshot,
            path=self.tmpdir / "snapshot.json",
            baseline_policy=BaselinePolicy.empty(),
            baseline_policy_path="baseline.json",
        )
        artifact = HealthAssessmentArtifact(
            run_label="health-run",
            run_id="health-run-1",
            timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id="cluster-alpha",
            snapshot_path=str(record.path),
            assessment={"observed_signals": [], "findings": []},
            missing_evidence=(),
            health_rating=HealthRating.HEALTHY,
        )
        drilldown_one = DrilldownArtifact(
            run_label="health-run",
            run_id="health-run-1",
            timestamp=snapshot.metadata.captured_at,
            snapshot_timestamp=snapshot.metadata.captured_at,
            context=target.context,
            label=target.label,
            cluster_id="cluster-alpha",
            trigger_reasons=("warning_event_threshold",),
            missing_evidence=(),
            evidence_summary={"foo": "bar"},
            affected_namespaces=("default",),
            affected_workloads=(),
            warning_events=(),
            non_running_pods=(),
            pod_descriptions={},
            rollout_status=(),
            collection_timestamps={"warning_events": "2026-01-01T00:00:00Z"},
            pattern_details={},
            artifact_path="drilldowns/cluster-alpha.json",
        )
        drilldown_two = DrilldownArtifact(
            run_label="health-run",
            run_id="health-run-1",
            timestamp=snapshot.metadata.captured_at,
            snapshot_timestamp=snapshot.metadata.captured_at,
            context="cluster-beta",
            label="cluster-beta",
            cluster_id="cluster-beta",
            trigger_reasons=("warning_event_threshold",),
            missing_evidence=(),
            evidence_summary={"foo": "bar"},
            affected_namespaces=("default",),
            affected_workloads=(),
            warning_events=(),
            non_running_pods=(),
            pod_descriptions={},
            rollout_status=(),
            collection_timestamps={"warning_events": "2026-01-01T00:00:00Z"},
            pattern_details={},
            artifact_path="drilldowns/cluster-beta.json",
        )
        proposal = HealthProposal(
            proposal_id="p1",
            source_run_id="health-run-1",
            source_artifact_path="runs/health/review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold",
            rationale="test",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="test",
            rollback_note="test",
        )
        notification = NotificationArtifact(
            kind="degraded-health",
            summary="threshold exceeded",
            details={"missing": ["event"]},
            run_id="health-run-1",
            cluster_label=target.label,
            context=target.context,
        )
        notification_path = (
            self.tmpdir / "runs" / "health" / "notifications" / "budget.json"
        )
        notification_path.parent.mkdir(parents=True, exist_ok=True)
        notification_record = (notification, notification_path)
        auto_artifact = ExternalAnalysisArtifact(
            tool_name="llm-autodrilldown",
            run_id="health-run-1",
            cluster_label=target.label,
            source_artifact="drilldowns/cluster-alpha.json",
            summary="auto insight",
            findings=("auto-f",),
            suggested_next_checks=("auto-check",),
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/auto.json",
            provider="llm-provider",
            duration_ms=100,
            purpose=ExternalAnalysisPurpose.AUTO_DRILLDOWN,
        )
        settings = ExternalAnalysisSettings(
            auto_drilldown=AutoDrilldownPolicy(enabled=True, provider="llm-provider", max_per_run=1)
        )
        output_dir = self.tmpdir / "runs" / "health"
        result_path = write_health_ui_index(
            output_dir,
            run_id="health-run-1",
            run_label="health-run",
            collector_version="1.0",
            records=[record],
            assessments=[artifact],
            drilldowns=[drilldown_one, drilldown_two],
            proposals=[proposal],
            external_analysis=[auto_artifact],
            notifications=[notification_record],
            external_analysis_settings=settings,
        )
        data = json.loads(result_path.read_text(encoding="utf-8"))
        llm_policy = data["run"].get("llm_policy")
        assert llm_policy is not None
        auto_policy = llm_policy["auto_drilldown"]
        self.assertTrue(auto_policy["budgetExhausted"])

    def test_run_entry_preserves_review_enrichment_config_without_artifact(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        )
        data = self._write_status_index(settings, adapters=("llamacpp",))
        run_entry = cast(dict[str, object], data["run"])
        config = run_entry.get("review_enrichment_config")
        self.assertIsNotNone(config)
        assert isinstance(config, dict)
        self.assertTrue(config.get("enabled"))
        self.assertEqual(config.get("provider"), "llamacpp")

    def test_run_entry_records_auto_drilldown_config(self) -> None:
        settings = ExternalAnalysisSettings(
            auto_drilldown=AutoDrilldownPolicy(enabled=True, provider="llm-provider", max_per_run=2)
        )
        data = self._write_status_index(settings)
        run_entry = cast(dict[str, object], data["run"])
        config = run_entry.get("auto_drilldown_config")
        self.assertIsNotNone(config)
        assert isinstance(config, dict)
        self.assertTrue(config.get("enabled"))
        self.assertEqual(config.get("provider"), "llm-provider")
        self.assertEqual(config.get("maxPerRun"), 2)

    def test_planner_availability_reports_review_enrichment_not_attempted(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        )
        data = self._write_status_index(settings, adapters=("llamacpp",))
        planner = cast(dict[str, object], data["run"].get("planner_availability"))
        self.assertIsNotNone(planner)
        self.assertEqual(planner["status"], "enrichment-not-attempted")
        self.assertIn("no artifact was recorded", str(planner["reason"]))
        self.assertIsNotNone(planner.get("hint"))
        self.assertIsNone(planner.get("artifactPath"))
        expected_hint = _PLANNER_NEXT_ACTION_HINTS[_PLANNER_STATUS_ENRICHMENT_NOT_ATTEMPTED]
        self.assertEqual(planner.get("nextActionHint"), expected_hint)

    def test_build_next_check_planner_availability_supplies_artifact_paths_and_hints(self) -> None:
        plan_entry = {"summary": "Plan summary", "artifactPath": "external-analysis/plan.json"}
        plan_result = _build_next_check_planner_availability(plan_entry, None, None)
        self.assertEqual(plan_result["status"], _PLANNER_STATUS_PLANNER_PRESENT)
        self.assertEqual(plan_result["artifactPath"], "external-analysis/plan.json")
        self.assertEqual(
            plan_result["nextActionHint"],
            _PLANNER_NEXT_ACTION_HINTS[_PLANNER_STATUS_PLANNER_PRESENT],
        )

        review_failure = {
            "status": "failed",
            "artifactPath": "external-analysis/review-failed.json",
            "errorSummary": "timeout",
        }
        failure_result = _build_next_check_planner_availability(None, review_failure, None)
        self.assertEqual(failure_result["status"], _PLANNER_STATUS_ENRICHMENT_FAILED)
        self.assertEqual(failure_result["artifactPath"], "external-analysis/review-failed.json")
        self.assertEqual(
            failure_result["nextActionHint"],
            _PLANNER_NEXT_ACTION_HINTS[_PLANNER_STATUS_ENRICHMENT_FAILED],
        )

        review_no_checks = {
            "status": "success",
            "artifactPath": "external-analysis/review-no-checks.json",
            "nextChecks": [],
        }
        no_checks_result = _build_next_check_planner_availability(None, review_no_checks, None)
        self.assertEqual(no_checks_result["status"], _PLANNER_STATUS_ENRICHMENT_SUCCESS_NO_CHECKS)
        self.assertEqual(
            no_checks_result["nextActionHint"],
            _PLANNER_NEXT_ACTION_HINTS[_PLANNER_STATUS_ENRICHMENT_SUCCESS_NO_CHECKS],
        )

        review_with_checks = {
            "status": "success",
            "artifactPath": "external-analysis/review-success.json",
            "nextChecks": ["cmd"],
            "summary": "Ran enrichment",
        }
        missing_result = _build_next_check_planner_availability(None, review_with_checks, None)
        self.assertEqual(missing_result["status"], _PLANNER_STATUS_PLANNER_MISSING)
        self.assertEqual(
            missing_result["artifactPath"], "external-analysis/review-success.json"
        )
        self.assertEqual(
            missing_result["nextActionHint"],
            _PLANNER_NEXT_ACTION_HINTS[_PLANNER_STATUS_PLANNER_MISSING],
        )

        disabled_result = _build_next_check_planner_availability(
            None, None, {"status": "policy-disabled"}
        )
        self.assertEqual(disabled_result["status"], _PLANNER_STATUS_POLICY_DISABLED)
        self.assertIsNone(disabled_result.get("artifactPath"))
        self.assertEqual(
            disabled_result["nextActionHint"],
            _PLANNER_NEXT_ACTION_HINTS[_PLANNER_STATUS_POLICY_DISABLED],
        )

    def test_review_enrichment_status_disabled_by_policy(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=False, provider="llamacpp")
        )
        data = self._write_status_index(settings)
        status = data["run"].get("review_enrichment_status")
        self.assertIsNotNone(status)
        assert isinstance(status, dict)
        self.assertEqual(status["status"], "policy-disabled")
        self.assertFalse(status["policyEnabled"])
        self.assertEqual(status["adapterAvailable"], None)

    def test_review_enrichment_status_requires_provider_configuration(self) -> None:
        settings = ExternalAnalysisSettings(review_enrichment=ReviewEnrichmentPolicy(enabled=True))
        data = self._write_status_index(settings)
        run_entry = cast(dict[str, object], data["run"])
        status = cast(dict[str, object], run_entry["review_enrichment_status"])
        self.assertEqual(status["status"], "provider-missing")
        self.assertFalse(status["providerConfigured"])

    def test_review_enrichment_status_detects_missing_adapter(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        )
        data = self._write_status_index(settings, adapters=("k8sgpt",))
        run_entry = cast(dict[str, object], data["run"])
        status = cast(dict[str, object], run_entry["review_enrichment_status"])
        self.assertEqual(status["status"], "adapter-unavailable")
        self.assertFalse(status["adapterAvailable"])

    def test_review_enrichment_status_awaiting_next_run(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        )
        status = _build_review_enrichment_status(
            settings,
            adapters=("llamacpp",),
            has_artifact=False,
            run_config={"enabled": False, "provider": None},
        )
        self.assertIsNotNone(status)
        status_dict = cast(dict[str, object], status)
        self.assertEqual(status_dict["status"], "awaiting-next-run")
        self.assertFalse(bool(status_dict.get("runEnabled")))

    def test_review_enrichment_status_not_attempted(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        )
        status = _build_review_enrichment_status(
            settings,
            adapters=("llamacpp",),
            has_artifact=False,
            run_config={"enabled": True, "provider": "llamacpp"},
        )
        self.assertIsNotNone(status)
        status_dict = cast(dict[str, object], status)
        self.assertEqual(status_dict["status"], "not-attempted")
        self.assertTrue(bool(status_dict.get("runEnabled")))
        self.assertEqual(status_dict.get("runProvider"), "llamacpp")
        self.assertEqual(status_dict.get("provider"), "llamacpp")

    def test_review_enrichment_status_unknown_when_missing_metadata(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        )
        status = _build_review_enrichment_status(
            settings,
            adapters=("llamacpp",),
            has_artifact=False,
            run_config=None,
        )
        self.assertIsNotNone(status)
        status_dict = cast(dict[str, object], status)
        self.assertEqual(status_dict["status"], "unknown")

    def test_review_enrichment_reflects_persisted_artifact(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        )
        output_dir = self.tmpdir / "runs" / "health"
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="status-run",
            cluster_label="status-run",
            run_label="status-run",
            source_artifact="reviews/status-run-review.json",
            summary="Adapter missing",
            status=ExternalAnalysisStatus.SKIPPED,
            artifact_path="external-analysis/status-run-review-enrichment-llamacpp.json",
            provider="llamacpp",
            timestamp=datetime.now(UTC),
            duration_ms=0,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            skip_reason="Adapter missing",
        )
        artifact_path = output_dir / "external-analysis" / "status-run-review-enrichment-llamacpp.json"
        write_external_analysis_artifact(artifact_path, artifact)
        index_path = write_health_ui_index(
            output_dir,
            run_id="status-run",
            run_label="status-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[],
            notifications=[],
            external_analysis_settings=settings,
        )
        data = cast(dict[str, object], json.loads(index_path.read_text(encoding="utf-8")))
        run_entry = cast(dict[str, object], data["run"])
        enrichment = cast(dict[str, object], run_entry["review_enrichment"])
        self.assertIsNotNone(enrichment)
        self.assertEqual(enrichment["status"], "skipped")
        self.assertEqual(enrichment["skipReason"], "Adapter missing")
        self.assertEqual(enrichment.get("provider"), "llamacpp")

    def test_review_enrichment_matches_artifact_path_when_run_id_missing(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        )
        output_dir = self.tmpdir / "runs" / "health"
        artifact_path = output_dir / "external-analysis" / "status-run-review-enrichment-llamacpp.json"
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="",
            cluster_label="status-run",
            run_label="status-run",
            summary="Path match",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=str(artifact_path),
            provider="llamacpp",
            timestamp=datetime.now(UTC),
            duration_ms=100,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
        )
        write_external_analysis_artifact(artifact_path, artifact)
        index_path = write_health_ui_index(
            output_dir,
            run_id="status-run",
            run_label="status-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=(artifact,),
            notifications=[],
            external_analysis_settings=settings,
        )
        data = cast(dict[str, object], json.loads(index_path.read_text(encoding="utf-8")))
        run_entry = cast(dict[str, object], data["run"])
        enrichment = run_entry.get("review_enrichment")
        self.assertIsNotNone(enrichment)
        self.assertIsNone(run_entry.get("review_enrichment_status"))

    def test_review_enrichment_prefers_run_id_when_present(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        )
        output_dir = self.tmpdir / "runs" / "health"
        artifact_path = output_dir / "external-analysis" / "odd-path.json"
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="status-run",
            cluster_label="status-run",
            run_label="status-run",
            summary="Run ID match",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=str(artifact_path),
            provider="llamacpp",
            timestamp=datetime.now(UTC),
            duration_ms=120,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
        )
        write_external_analysis_artifact(artifact_path, artifact)
        index_path = write_health_ui_index(
            output_dir,
            run_id="status-run",
            run_label="status-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=(artifact,),
            notifications=[],
            external_analysis_settings=settings,
        )
        data = cast(dict[str, object], json.loads(index_path.read_text(encoding="utf-8")))
        run_entry = cast(dict[str, object], data["run"])
        enrichment = run_entry.get("review_enrichment")
        self.assertIsNotNone(enrichment)
        self.assertEqual(enrichment.get("status"), "success")
        self.assertEqual(enrichment.get("summary"), "Run ID match")
        self.assertEqual(enrichment.get("artifactPath"), "external-analysis/odd-path.json")
        self.assertIsNone(run_entry.get("review_enrichment_status"))

    def test_review_enrichment_reflects_failed_artifact(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
        )
        output_dir = self.tmpdir / "runs" / "health"
        failed_artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="status-run",
            cluster_label="status-run",
            run_label="status-run",
            source_artifact="reviews/status-run-review.json",
            summary="Error occurred",
            findings=(),
            suggested_next_checks=(),
            status=ExternalAnalysisStatus.FAILED,
            artifact_path="external-analysis/status-run-review-enrichment-llamacpp.json",
            provider="llamacpp",
            duration_ms=100,
            timestamp=datetime.now(UTC),
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            error_summary="Error occurred",
        )
        failed_path = output_dir / "external-analysis" / "status-run-review-enrichment-llamacpp.json"
        write_external_analysis_artifact(failed_path, failed_artifact)
        index_path = write_health_ui_index(
            output_dir,
            run_id="status-run",
            run_label="status-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[],
            notifications=[],
            external_analysis_settings=settings,
        )
        data = cast(dict[str, object], json.loads(index_path.read_text(encoding="utf-8")))
        run_entry = cast(dict[str, object], data["run"])
        enrichment = cast(dict[str, object], run_entry["review_enrichment"])
        self.assertIsNotNone(enrichment)
        self.assertEqual(enrichment["status"], "failed")
        self.assertEqual(enrichment.get("errorSummary"), "Error occurred")
        self.assertEqual(enrichment.get("provider"), "llamacpp")

    def test_review_enrichment_serialization_handles_snake_case_payload(self) -> None:
        root = self.tmpdir / "runs" / "health"
        artifact_path = root / "external-analysis" / "snake.json"
        artifact = ExternalAnalysisArtifact(
            tool_name="llamacpp",
            run_id="status-run",
            cluster_label="status-run",
            summary="serialized",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path=str(artifact_path),
            provider="llamacpp",
            timestamp=datetime.now(UTC),
            duration_ms=120,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={
                "triage_order": ["cluster-a"],
                "top_concerns": ("latency",),
                "evidenceGaps": ["metrics"],
                "next_checks": "check logs",
                "focusNotes": ("note",),
            },
        )
        serialized = _serialize_review_enrichment((artifact,), root, run_id="status-run")
        self.assertIsNotNone(serialized)
        assert serialized is not None
        self.assertEqual(serialized["triageOrder"], ["cluster-a"])
        self.assertEqual(serialized["topConcerns"], ["latency"])
        self.assertEqual(serialized["evidenceGaps"], ["metrics"])
        self.assertEqual(serialized["nextChecks"], ["check logs"])
        self.assertEqual(serialized["focusNotes"], ["note"])

    def test_provider_execution_auto_drilldown_budget_exhausted(self) -> None:
        settings = ExternalAnalysisSettings(
            auto_drilldown=AutoDrilldownPolicy(enabled=True, provider="default", max_per_run=2)
        )
        artifacts = [
            self._auto_drilldown_artifact(ExternalAnalysisStatus.SUCCESS),
            self._auto_drilldown_artifact(ExternalAnalysisStatus.FAILED),
        ]
        execution = _build_provider_execution(
            settings,
            artifacts,
            [self._dummy_drilldown() for _ in range(4)],
            {"enabled": False, "provider": None},
        )
        auto = cast(dict[str, object], execution.get("auto_drilldown"))
        self.assertEqual(auto.get("eligible"), 4)
        self.assertEqual(auto.get("attempted"), 2)
        self.assertEqual(auto.get("succeeded"), 1)
        self.assertEqual(auto.get("failed"), 1)
        self.assertEqual(auto.get("budgetLimited"), 2)
        self.assertIn("Reached max per run", str(auto.get("notes")))

    def test_provider_execution_review_unattempted(self) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="k8sgpt")
        )
        execution = _build_provider_execution(
            settings,
            (),
            (),
            {"enabled": True, "provider": "k8sgpt"},
        )
        review = cast(dict[str, object], execution.get("review_enrichment"))
        self.assertEqual(review.get("eligible"), 1)
        self.assertEqual(review.get("attempted"), 0)
        self.assertEqual(review.get("unattempted"), 1)
        self.assertIn("no artifact", str(review.get("notes")))

    def test_classify_execution_failure_prefers_timeout(self) -> None:
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id="test",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.FAILED,
            timed_out=True,
            error_summary="Command timed out.",
        )
        follow_up = _classify_execution_failure(artifact)
        self.assertIsNotNone(follow_up)
        assert follow_up is not None
        self.assertEqual(follow_up.failure_class, "timed-out")
        self.assertEqual(follow_up.suggested_next_operator_move, "Retry candidate")

    def test_classify_execution_failure_detects_missing_kubectl(self) -> None:
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id="test",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="[Errno 2] No such file or directory: 'kubectl'",
        )
        follow_up = _classify_execution_failure(artifact)
        self.assertIsNotNone(follow_up)
        assert follow_up is not None
        self.assertEqual(follow_up.failure_class, "command-unavailable")
        self.assertEqual(follow_up.suggested_next_operator_move, "Inspect artifact output")

    def test_classify_execution_success_detects_empty_output(self) -> None:
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id="test",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SUCCESS,
            output_bytes_captured=0,
            raw_output="",
        )
        interpretation = _classify_execution_success(artifact)
        self.assertIsNotNone(interpretation)
        assert interpretation is not None
        self.assertEqual(interpretation.result_class, "empty-result")
        self.assertEqual(interpretation.result_summary, "Command completed without producing output.")

    def test_classify_execution_success_flags_truncated_output(self) -> None:
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id="test",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SUCCESS,
            stdout_truncated=True,
            output_bytes_captured=512,
        )
        interpretation = _classify_execution_success(artifact)
        self.assertIsNotNone(interpretation)
        assert interpretation is not None
        self.assertEqual(interpretation.result_class, "partial-result")

    def test_classify_execution_success_prefers_useful_signal(self) -> None:
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-runner",
            run_id="test",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="some logs",
            payload={"commandFamily": "kubectl-logs", "outputBytesCaptured": 128},
        )
        interpretation = _classify_execution_success(artifact)
        self.assertIsNotNone(interpretation)
        assert interpretation is not None
        self.assertEqual(interpretation.result_class, "useful-signal")

    def test_classify_blocked_candidate_requires_approval(self) -> None:
        candidate = {
            "requiresOperatorApproval": True,
            "approvalState": "approval-required",
            "queueStatus": "approval-needed",
        }
        follow_up = _classify_blocked_candidate(candidate)
        self.assertIsNotNone(follow_up)
        assert follow_up is not None
        self.assertEqual(follow_up.failure_class, "approval-missing-or-stale")
        self.assertEqual(follow_up.suggested_next_operator_move, "Review approval state")

    def test_derive_priority_rationale_duplicate(self) -> None:
        entry: dict[str, object] = {"duplicateOfExistingEvidence": True, "duplicateReason": "logs already collected"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Already covered by existing evidence")

    def test_derive_priority_rationale_stale_approval(self) -> None:
        entry: dict[str, object] = {"approvalState": "approval-stale"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Approval is stale")

    def test_derive_priority_rationale_orphaned_approval(self) -> None:
        entry: dict[str, object] = {"approvalState": "approval-orphaned"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Approval record orphaned")

    def test_derive_priority_rationale_approval_required(self) -> None:
        entry: dict[str, object] = {"requiresOperatorApproval": True, "approvalReason": "high-risk command"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Approval required before execution")

    def test_derive_priority_rationale_safety_gating(self) -> None:
        entry: dict[str, object] = {"safetyReason": "requires root access"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Blocked by safety gating")

    def test_derive_priority_rationale_blocking_reason(self) -> None:
        entry: dict[str, object] = {"blockingReason": "unauthenticated"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Blocked by execution gating")

    def test_derive_priority_rationale_gating_reason(self) -> None:
        entry: dict[str, object] = {"gatingReason": "namespace denied"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Blocked by planner gating")

    def test_derive_priority_rationale_secondary(self) -> None:
        entry: dict[str, object] = {"priorityLabel": "secondary"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Secondary follow-up")

    def test_derive_priority_rationale_fallback(self) -> None:
        entry: dict[str, object] = {"priorityLabel": "fallback"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Fallback candidate")

    def test_derive_priority_rationale_executed_success(self) -> None:
        entry: dict[str, object] = {"executionState": "executed-success"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Already executed")

    def test_derive_priority_rationale_executed_failed(self) -> None:
        entry: dict[str, object] = {"executionState": "executed-failed"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Execution failed")

    def test_derive_priority_rationale_timed_out(self) -> None:
        entry: dict[str, object] = {"executionState": "timed-out"}
        result = _derive_priority_rationale(entry)
        self.assertEqual(result, "Execution failed")

    def test_derive_priority_rationale_returns_null_when_no_rationale(self) -> None:
        entry: dict[str, object] = {"description": "kubectl get pods"}
        result = _derive_priority_rationale(entry)
        self.assertIsNone(result)

    def test_build_next_check_queue_populates_priority_rationale(self) -> None:
        plan_entry: dict[str, object] = {
            "candidates": [
                {"description": "Safe candidate", "requiresOperatorApproval": False, "safeToAutomate": True, "executionState": "unexecuted", "priorityLabel": "primary"},
                {"description": "Needs approval", "requiresOperatorApproval": True, "approvalState": "approval-required", "executionState": "unexecuted", "safeToAutomate": False, "approvalReason": "high-risk"},
                {"description": "Duplicate", "duplicateOfExistingEvidence": True, "duplicateReason": "already covered"},
                {"description": "Failed", "safeToAutomate": True, "executionState": "executed-failed", "priorityLabel": "secondary"},
            ],
            "artifactPath": "external-analysis/queue-plan.json",
        }
        queue = _build_next_check_queue(plan_entry, {})
        # Find each entry by description and verify its rationale independently
        by_description: dict[str, dict[str, object]] = {str(entry.get("description") or ""): entry for entry in queue}
        safe_entry = by_description.get("Safe candidate")
        self.assertIsNotNone(safe_entry)
        assert safe_entry is not None
        self.assertIsNone(safe_entry.get("priorityRationale"))
        approval_entry = by_description.get("Needs approval")
        self.assertIsNotNone(approval_entry)
        assert approval_entry is not None
        self.assertEqual(approval_entry.get("priorityRationale"), "Approval required before execution")
        failed_entry = by_description.get("Failed")
        self.assertIsNotNone(failed_entry)
        assert failed_entry is not None
        self.assertEqual(failed_entry.get("priorityRationale"), "Execution failed")
        dup_entry = by_description.get("Duplicate")
        self.assertIsNotNone(dup_entry)
        assert dup_entry is not None
        self.assertEqual(dup_entry.get("priorityRationale"), "Already covered by existing evidence")

    # Tests for _derive_ranking_reason - structured categories
    def test_derive_ranking_reason_duplicate(self) -> None:
        entry: dict[str, object] = {"duplicateOfExistingEvidence": True}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "duplicate")

    def test_derive_ranking_reason_approval_gated(self) -> None:
        entry: dict[str, object] = {"requiresOperatorApproval": True, "approvalState": "approval-required"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "approval-gated")

    def test_derive_ranking_reason_stale_approval(self) -> None:
        entry: dict[str, object] = {"approvalState": "approval-stale"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "stale-approval")

    def test_derive_ranking_reason_orphaned_approval(self) -> None:
        entry: dict[str, object] = {"approvalState": "approval-orphaned"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "stale-approval")

    def test_derive_ranking_reason_safety_gated(self) -> None:
        entry: dict[str, object] = {"safetyReason": "requires root access"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "safety-gated")

    def test_derive_ranking_reason_execution_gated(self) -> None:
        entry: dict[str, object] = {"blockingReason": "unauthenticated"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "execution-gated")

    def test_derive_ranking_reason_planner_gated(self) -> None:
        entry: dict[str, object] = {"gatingReason": "namespace denied"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "planner-gated")

    def test_derive_ranking_reason_already_executed(self) -> None:
        entry: dict[str, object] = {"executionState": "executed-success"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "already-executed")

    def test_derive_ranking_reason_execution_failed(self) -> None:
        entry: dict[str, object] = {"executionState": "executed-failed"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "execution-failed")

    def test_derive_ranking_reason_timed_out(self) -> None:
        entry: dict[str, object] = {"executionState": "timed-out"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "execution-failed")

    def test_derive_ranking_reason_deterministic_secondary(self) -> None:
        entry: dict[str, object] = {"priorityLabel": "secondary"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "deterministic-secondary")

    def test_derive_ranking_reason_fallback(self) -> None:
        entry: dict[str, object] = {"priorityLabel": "fallback"}
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "fallback")

    def test_derive_ranking_reason_null_when_no_category(self) -> None:
        entry: dict[str, object] = {"description": "kubectl logs", "priorityLabel": "primary"}
        result = _derive_ranking_reason(entry)
        self.assertIsNone(result)

    def test_derive_ranking_reason_priority_order(self) -> None:
        """Duplicate takes precedence over approval-gated."""
        entry: dict[str, object] = {
            "duplicateOfExistingEvidence": True,
            "requiresOperatorApproval": True,
        }
        result = _derive_ranking_reason(entry)
        self.assertEqual(result, "duplicate")


# Tests for artifact_id threading in UI serialization
class TestArtifactIdUiSerialization(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_external_analysis_serialization_includes_artifact_id(self) -> None:
        """New external artifacts include artifact_id in UI serialization."""
        artifact = ExternalAnalysisArtifact(
            tool_name="k8sgpt",
            run_id="test-run",
            cluster_label="cluster-a",
            summary="Test analysis",
            status=ExternalAnalysisStatus.SUCCESS,
            artifact_path="external-analysis/test.json",
            provider="k8sgpt",
            duration_ms=100,
        )
        output_dir = self.tmpdir / "runs" / "health"
        index_path = write_health_ui_index(
            output_dir,
            run_id="test-run",
            run_label="test-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[artifact],
            notifications=[],
            external_analysis_settings=ExternalAnalysisSettings(),
        )
        data = json.loads(index_path.read_text(encoding="utf-8"))
        ea_data = cast(dict[str, object], data["external_analysis"])
        artifacts = cast(list[dict[str, object]], ea_data["artifacts"])
        self.assertEqual(len(artifacts), 1)
        entry = artifacts[0]
        self.assertIn("artifact_id", entry)
        self.assertIsNotNone(entry["artifact_id"])
        # Verify it matches UUID format
        artifact_id = str(entry["artifact_id"])
        self.assertEqual(len(artifact_id), 36)
        self.assertEqual(artifact_id[8], "-")
        self.assertEqual(artifact_id[13], "-")

    def test_external_analysis_serialization_handles_legacy_without_artifact_id(self) -> None:
        """Legacy artifacts without artifact_id deserialize gracefully."""
        # Simulate a legacy artifact dict without artifact_id field
        legacy_dict = {
            "tool_name": "k8sgpt",
            "run_id": "legacy-run",
            "run_label": "legacy-run",
            "cluster_label": "cluster-legacy",
            "status": "success",
            "summary": "Legacy analysis",
            "findings": [],
            "suggested_next_checks": [],
            "timestamp": "2026-01-01T00:00:00Z",
            "artifact_path": "external-analysis/legacy.json",
            "duration_ms": 50,
            "provider": "k8sgpt",
            "purpose": "manual",
            "payload": {},
            "error_summary": None,
            "skip_reason": None,
        }
        legacy_artifact = ExternalAnalysisArtifact.from_dict(legacy_dict)
        self.assertIsNone(legacy_artifact.artifact_id)

        output_dir = self.tmpdir / "runs" / "health"
        index_path = write_health_ui_index(
            output_dir,
            run_id="legacy-run",
            run_label="legacy-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[legacy_artifact],
            notifications=[],
            external_analysis_settings=ExternalAnalysisSettings(),
        )
        data = json.loads(index_path.read_text(encoding="utf-8"))
        ea_data = cast(dict[str, object], data["external_analysis"])
        artifacts = cast(list[dict[str, object]], ea_data["artifacts"])
        self.assertEqual(len(artifacts), 1)
        entry = artifacts[0]
        # Legacy artifact should not have artifact_id in serialized output
        self.assertNotIn("artifact_id", entry)

    def test_multiple_external_analysis_artifacts_have_unique_artifact_ids(self) -> None:
        """Multiple artifacts get unique artifact_ids in UI serialization."""
        artifacts = [
            ExternalAnalysisArtifact(
                tool_name="k8sgpt",
                run_id="test-run",
                cluster_label="cluster-a",
                summary=f"Analysis {i}",
                status=ExternalAnalysisStatus.SUCCESS,
                artifact_path=f"external-analysis/test-{i}.json",
                provider="k8sgpt",
                duration_ms=100,
            )
            for i in range(3)
        ]
        output_dir = self.tmpdir / "runs" / "health"
        index_path = write_health_ui_index(
            output_dir,
            run_id="test-run",
            run_label="test-run",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=artifacts,
            notifications=[],
            external_analysis_settings=ExternalAnalysisSettings(),
        )
        data = json.loads(index_path.read_text(encoding="utf-8"))
        ea_data = cast(dict[str, object], data["external_analysis"])
        serialized_artifacts = cast(list[dict[str, object]], ea_data["artifacts"])
        artifact_ids = [entry.get("artifact_id") for entry in serialized_artifacts]
        # All artifact_ids should be unique and present
        self.assertEqual(len(artifact_ids), 3)
        self.assertEqual(len(set(artifact_ids)), 3)
        for aid in artifact_ids:
            self.assertIsNotNone(aid)

    def test_build_next_check_queue_populates_structured_ranking_reason(self) -> None:
        plan_entry: dict[str, object] = {
            "candidates": [
                {"description": "Check duplicate", "duplicateOfExistingEvidence": True},
                {"description": "Check approval", "requiresOperatorApproval": True, "approvalState": "approval-required"},
                {"description": "Check secondary", "priorityLabel": "secondary"},
                {"description": "Check no reason", "priorityLabel": "primary"},
            ],
            "artifactPath": "external-analysis/queue-plan.json",
        }
        queue = _build_next_check_queue(plan_entry, {})
        by_description: dict[str, dict[str, object]] = {
            str(entry.get("description") or ""): entry for entry in queue
        }
        dup = by_description.get("Check duplicate")
        self.assertIsNotNone(dup)
        assert dup is not None
        self.assertEqual(dup.get("rankingReason"), "duplicate")
        approval = by_description.get("Check approval")
        self.assertIsNotNone(approval)
        assert approval is not None
        self.assertEqual(approval.get("rankingReason"), "approval-gated")
        secondary = by_description.get("Check secondary")
        self.assertIsNotNone(secondary)
        assert secondary is not None
        self.assertEqual(secondary.get("rankingReason"), "deterministic-secondary")
        no_reason = by_description.get("Check no reason")
        self.assertIsNotNone(no_reason)
        assert no_reason is not None
        self.assertIsNone(no_reason.get("rankingReason"))
