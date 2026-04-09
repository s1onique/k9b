import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from k8s_diag_agent.external_analysis.config import (
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from k8s_diag_agent.health.ui import write_health_ui_index
from k8s_diag_agent.ui.api import (
    _build_freshness_payload,
    build_cluster_detail_payload,
    build_fleet_payload,
    build_notifications_payload,
    build_proposals_payload,
    build_run_payload,
)
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.ui_index_sample import sample_ui_index


def _sample_deterministic_next_checks() -> dict[str, object]:
    return {
        "clusterCount": 1,
        "totalNextCheckCount": 1,
        "clusters": [
            {
                "label": "cluster-a",
                "context": "cluster-a",
                "topProblem": "warning_event_threshold",
                "deterministicNextCheckCount": 1,
                "deterministicNextCheckSummaries": [
                    {
                        "description": "capture tcpdump",
                        "owner": "platform",
                        "method": "kubectl exec",
                        "evidenceNeeded": ["tcpdump"],
                    }
                ],
                "drilldownAvailable": True,
                "assessmentArtifactPath": "assessments/cluster-a.json",
                "drilldownArtifactPath": "drilldowns/cluster-a.json",
            }
        ],
    }


class UIApiTests(unittest.TestCase):
    def setUp(self) -> None:
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["deterministic_next_checks"] = _sample_deterministic_next_checks()
        self.context = build_ui_context(index)

    def test_run_payload_contains_artifacts(self) -> None:
        payload = build_run_payload(self.context)
        self.assertEqual(payload["runId"], "run-1")
        labels = {link["label"] for link in payload["artifacts"]}
        self.assertIn("Assessment JSON", labels)
        self.assertIn("Drilldown JSON", labels)

    def test_run_payload_includes_stats(self) -> None:
        payload = build_run_payload(self.context)
        stats = payload["runStats"]
        self.assertEqual(stats["totalRuns"], 3)
        self.assertEqual(stats["lastRunDurationSeconds"], 42)

    def test_run_payload_includes_llm_stats(self) -> None:
        payload = build_run_payload(self.context)
        llm_stats = payload["llmStats"]
        self.assertEqual(llm_stats["totalCalls"], 3)
        self.assertEqual(llm_stats["successfulCalls"], 2)
        providers = {entry["provider"] for entry in llm_stats["providerBreakdown"]}
        self.assertIn("k8sgpt", providers)
        self.assertIn("llm-autodrilldown", providers)
        historical = payload["historicalLlmStats"]
        self.assertIsNotNone(historical)
        assert historical is not None
        self.assertEqual(historical["totalCalls"], 5)
        self.assertEqual(historical["scope"], "retained_history")
        activity = payload["llmActivity"]
        self.assertEqual(activity["summary"]["retainedEntries"], 3)
        self.assertEqual(activity["entries"][0]["status"], "success")
        llm_policy = payload["llmPolicy"]
        self.assertIsNotNone(llm_policy)
        assert llm_policy is not None
        auto_policy = llm_policy["autoDrilldown"]
        self.assertEqual(auto_policy["provider"], "default")
        self.assertEqual(auto_policy["usedThisRun"], 1)
        self.assertEqual(auto_policy["failedThisRun"], 1)
        self.assertFalse(auto_policy["budgetExhausted"])
        review_enrichment = payload.get("reviewEnrichment")
        self.assertIsNotNone(review_enrichment)
        assert review_enrichment is not None
        self.assertEqual(review_enrichment["status"], "success")
        self.assertEqual(review_enrichment["triageOrder"], ["cluster-b", "cluster-a"])
        self.assertIsNone(payload.get("reviewEnrichmentStatus"))

        provider_execution = payload.get("providerExecution")
        self.assertIsNotNone(provider_execution)
        assert provider_execution is not None
        auto_exec = provider_execution.get("autoDrilldown") or {}
        self.assertEqual(auto_exec.get("eligible"), 2)
        self.assertEqual(auto_exec.get("attempted"), 1)
        self.assertEqual(auto_exec.get("failed"), 1)
        self.assertEqual(auto_exec.get("budgetLimited"), 1)
        review_exec = provider_execution.get("reviewEnrichment") or {}
        self.assertEqual(review_exec.get("eligible"), 1)
        self.assertEqual(review_exec.get("attempted"), 1)
        planner_availability = payload.get("plannerAvailability")
        self.assertIsNotNone(planner_availability)
        assert planner_availability is not None
        self.assertEqual(planner_availability["status"], "planner-present")
        self.assertEqual(
            planner_availability["reason"],
            "3 provider-suggested next checks normalized into safe/approval/duplicate categories.",
        )
        self.assertIsNone(planner_availability.get("hint"))
        self.assertEqual(
            planner_availability.get("artifactPath"),
            "runs/health/external-analysis/health-run-20260408T061911Z-next-check-plan.json",
        )
        self.assertEqual(
            planner_availability.get("nextActionHint"),
            "Inspect the planner artifact for candidate context before taking any next-check action.",
        )

    def test_run_payload_includes_freshness(self) -> None:
        payload = build_run_payload(self.context)
        freshness = payload.get("freshness")
        self.assertIsNotNone(freshness)
        assert freshness is not None
        self.assertEqual(freshness.get("expectedIntervalSeconds"), 300)
        self.assertIsInstance(freshness.get("ageSeconds"), int)
        self.assertIn(freshness.get("status"), ("fresh", "delayed", "stale", None))

    def test_run_payload_includes_next_check_queue(self) -> None:
        payload = build_run_payload(self.context)
        queue = payload.get("nextCheckQueue")
        self.assertIsNotNone(queue)
        assert isinstance(queue, list)
        statuses = [entry.get("queueStatus") for entry in queue]
        self.assertIn("approval-needed", statuses)
        self.assertIn("completed", statuses)
        self.assertTrue(all("queueStatus" in entry for entry in queue))
        first_entry = queue[0]
        self.assertIn("commandPreview", first_entry)
        self.assertIn("planArtifactPath", first_entry)

    def test_run_payload_reconstructs_review_enrichment_from_artifact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs" / "health"
            runs_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = runs_dir / "external-analysis" / "status-run-review-enrichment-llamacpp.json"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
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
                duration_ms=120,
                purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            )
            write_external_analysis_artifact(artifact_path, artifact)
            settings = ExternalAnalysisSettings(
                review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
            )
            index_path = write_health_ui_index(
                runs_dir,
                run_id="status-run",
                run_label="status-run",
                collector_version="tests",
                records=(),
                assessments=(),
                drilldowns=(),
                proposals=(),
                external_analysis=(artifact,),
                notifications=(),
                external_analysis_settings=settings,
            )
            raw_index = json.loads(index_path.read_text(encoding="utf-8"))
            context = build_ui_context(raw_index)
            payload = build_run_payload(context)
            review_enrichment = payload.get("reviewEnrichment")
            self.assertIsNotNone(review_enrichment)
            assert isinstance(review_enrichment, dict)
            self.assertEqual(review_enrichment["status"], "success")
            self.assertIsNone(payload.get("reviewEnrichmentStatus"))

    def test_run_payload_prefers_run_id_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs" / "health"
            runs_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = runs_dir / "external-analysis" / "odd-path.json"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
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
                duration_ms=130,
                purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            )
            write_external_analysis_artifact(artifact_path, artifact)
            settings = ExternalAnalysisSettings(
                review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="llamacpp")
            )
            index_path = write_health_ui_index(
                runs_dir,
                run_id="status-run",
                run_label="status-run",
                collector_version="tests",
                records=(),
                assessments=(),
                drilldowns=(),
                proposals=(),
                external_analysis=(artifact,),
                notifications=(),
                external_analysis_settings=settings,
            )
            raw_index = json.loads(index_path.read_text(encoding="utf-8"))
            context = build_ui_context(raw_index)
            payload = build_run_payload(context)
            review_enrichment = payload.get("reviewEnrichment")
            self.assertIsNotNone(review_enrichment)
            assert isinstance(review_enrichment, dict)
            self.assertEqual(review_enrichment.get("status"), "success")
            self.assertEqual(review_enrichment.get("summary"), "Run ID match")
            self.assertIsNone(payload.get("reviewEnrichmentStatus"))

    def test_run_payload_includes_next_check_plan(self) -> None:
        index = sample_ui_index()
        plan_payload = {
            "status": "success",
            "summary": "Planned single check",
            "artifactPath": "external-analysis/plan.json",
            "reviewPath": "reviews/run-1-review.json",
            "enrichmentArtifactPath": "external-analysis/run-1-review-enrichment-k8sgpt.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": "kubectl logs deployment/alpha",
                    "targetCluster": "cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "riskLevel": "low",
                    "estimatedCost": "low",
                    "confidence": "high",
                    "priorityLabel": "primary",
                    "gatingReason": None,
                    "duplicateOfExistingEvidence": False,
                    "duplicateEvidenceDescription": None,
                    "candidateId": "candidate-logs",
                    "candidateIndex": 0,
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                }
            ],
            "orphanedApprovals": [],
        }
        run_entry = cast(dict[str, object], index["run"])
        run_entry["next_check_plan"] = plan_payload
        index["next_check_plan"] = plan_payload
        context = build_ui_context(index)
        payload = build_run_payload(context)
        plan = payload.get("nextCheckPlan")
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.get("candidateCount"), 1)
        self.assertEqual(plan.get("artifactPath"), "external-analysis/plan.json")
        candidate = plan["candidates"][0]
        self.assertEqual(candidate.get("candidateId"), "candidate-logs")
        self.assertEqual(plan.get("outcomeCounts"), [])
        self.assertEqual(plan.get("orphanedApprovalCount"), 0)

    def test_run_payload_planner_enrichment_not_attempted(self) -> None:
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["next_check_plan"] = None
        run_entry["planner_availability"] = {
            "status": "enrichment-not-attempted",
            "reason": "Review enrichment was not attempted for this run.",
            "hint": "Cluster Detail next checks can still derive from assessment output.",
            "nextActionHint": "Inspect Review Enrichment configuration or provider registration to understand why the planner didn't run.",
        }
        run_entry["deterministic_next_checks"] = _sample_deterministic_next_checks()
        index["next_check_plan"] = None
        context = build_ui_context(index)
        payload = build_run_payload(context)
        self.assertIsNone(payload.get("nextCheckPlan"))
        planner_availability = payload.get("plannerAvailability")
        self.assertIsNotNone(planner_availability)
        assert planner_availability is not None
        self.assertEqual(planner_availability["status"], "enrichment-not-attempted")
        self.assertIn("not attempted", str(planner_availability["reason"]))
        self.assertIsNone(planner_availability.get("artifactPath"))
        self.assertEqual(
            planner_availability.get("nextActionHint"),
            "Inspect Review Enrichment configuration or provider registration to understand why the planner didn't run.",
        )
    
        deterministic = payload.get("deterministicNextChecks")
        self.assertIsNotNone(deterministic)
        assert isinstance(deterministic, dict)
        self.assertEqual(deterministic.get("clusterCount"), 1)
        self.assertEqual(deterministic.get("totalNextCheckCount"), 1)
        cluster_entry = deterministic.get("clusters", [])[0]
        self.assertEqual(cluster_entry.get("label"), "cluster-a")
        self.assertEqual(cluster_entry.get("topProblem"), "warning_event_threshold")
        self.assertEqual(cluster_entry.get("deterministicNextCheckCount"), 1)
        summary_entry = cluster_entry.get("deterministicNextCheckSummaries", [])[0]
        self.assertEqual(summary_entry.get("description"), "capture tcpdump")
        self.assertEqual(summary_entry.get("method"), "kubectl exec")

    def test_cluster_detail_payload_includes_next_check_plan(self) -> None:
        index = sample_ui_index()
        plan_payload = {
            "status": "success",
            "summary": "Planned single check",
            "artifactPath": "external-analysis/plan.json",
            "reviewPath": "reviews/run-1-review.json",
            "enrichmentArtifactPath": "external-analysis/run-1-review-enrichment-k8sgpt.json",
            "candidateCount": 1,
            "candidates": [
                {
                    "description": "kubectl logs deployment/alpha",
                    "targetCluster": "cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "riskLevel": "low",
                    "estimatedCost": "low",
                    "confidence": "high",
                    "gatingReason": None,
                    "duplicateOfExistingEvidence": False,
                    "duplicateEvidenceDescription": None,
                    "candidateId": "candidate-logs",
                    "candidateIndex": 0,
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                }
            ],
            "orphanedApprovals": [],
        }
        run_entry = cast(dict[str, object], index["run"])
        run_entry["next_check_plan"] = plan_payload
        index["next_check_plan"] = plan_payload
        context = build_ui_context(index)
        payload = build_cluster_detail_payload(context)
        plan = payload["nextCheckPlan"]
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["targetCluster"], "cluster-a")
        self.assertEqual(plan[0].get("candidateId"), "candidate-logs")

    def test_run_payload_includes_execution_history(self) -> None:
        payload = build_run_payload(self.context)
        history = payload.get("nextCheckExecutionHistory")
        self.assertIsNotNone(history)
        assert history is not None
        self.assertTrue(len(history) >= 1)
        entry = history[0]
        self.assertEqual(entry.get("status"), "success")
        self.assertFalse(entry.get("timedOut"))
        self.assertEqual(entry.get("resultClass"), "useful-signal")
        self.assertEqual(
            entry.get("resultSummary"),
            "Captured control-plane logs that highlight recent kubelet errors.",
        )

    def test_freshness_helper_computes_statuses(self) -> None:
        base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        payload = _build_freshness_payload("2026-01-01T00:00:00+00:00", 300, now=base + timedelta(seconds=200))
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["status"], "fresh")
        payload = _build_freshness_payload("2026-01-01T00:00:00+00:00", 300, now=base + timedelta(seconds=500))
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["status"], "delayed")
        payload = _build_freshness_payload("2026-01-01T00:00:00+00:00", 300, now=base + timedelta(seconds=1300))
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["status"], "stale")

    def test_fleet_payload_summarizes_clusters(self) -> None:
        payload = build_fleet_payload(self.context)
        self.assertEqual(payload["clusters"][0]["label"], "cluster-a")
        self.assertTrue(payload["topProblem"]["title"])

    def test_proposals_payload_exposes_lifecycle(self) -> None:
        payload = build_proposals_payload(self.context)
        self.assertEqual(payload["statusSummary"][0]["status"], "pending")
        self.assertEqual(payload["proposals"][0]["lifecycle"][0]["status"], "pending")

    def test_notifications_payload_exports_details(self) -> None:
        payload = build_notifications_payload(self.context)
        notification = payload["notifications"][0]
        self.assertEqual(notification["kind"], "degraded-health")
        self.assertEqual(notification["details"][0]["label"], "warnings")

    def test_cluster_detail_payload_links_related_artifacts(self) -> None:
        payload = build_cluster_detail_payload(self.context)
        self.assertEqual(payload["selectedClusterLabel"], "cluster-a")
        self.assertGreaterEqual(len(payload["artifacts"]), 2)
        self.assertGreaterEqual(len(payload["drilldownCoverage"]), 1)

    def test_cluster_detail_payload_includes_auto_interpretation(self) -> None:
        payload = build_cluster_detail_payload(self.context)
        interpretation = payload.get("autoInterpretation")
        self.assertIsNotNone(interpretation)
        assert interpretation is not None
        self.assertEqual(interpretation["status"], "success")
        self.assertEqual(interpretation["adapter"], "llm-autodrilldown")
