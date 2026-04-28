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
    RunsListPayload,
    _build_freshness_payload,
    _serialize_next_check_queue,
    build_cluster_detail_payload,
    build_fleet_payload,
    build_notifications_payload,
    build_proposals_payload,
    build_run_payload,
    build_runs_list,
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
                    "priorityScore": 85,
                    "workstream": "incident",
                    "urgency": "high",
                    "isPrimaryTriage": True,
                    "whyNow": "Immediate triage for warning_event_threshold",
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

    def test_run_payload_exposes_diagnostic_pack_review_fields(self) -> None:
        payload = build_run_payload(self.context)
        review = payload.get("diagnosticPackReview")
        self.assertIsNotNone(review)
        assert review is not None
        self.assertEqual(review.get("summary"), "Diagnostic pack second opinion")
        self.assertEqual(review.get("providerStatus"), "success")
        self.assertIn("validate diagnostics", review.get("recommendedNextActions", []))
        self.assertEqual(review.get("timestamp"), "2026-01-01T00:15:00Z")
        self.assertEqual(review.get("artifactPath"), "external-analysis/run-1-diagnostic-pack-review.json")

    def test_diagnostic_pack_payload_includes_is_mirror_flag(self) -> None:
        """Test that diagnostic pack payload includes isMirror flag for mirror semantics."""
        from k8s_diag_agent.ui.model import DiagnosticPackView

        # Create a view with is_mirror=True (mirrored latest/ paths)
        mirror_view = DiagnosticPackView(
            path="diagnostic-packs/diagnostic-pack-run-1.zip",
            timestamp="2026-01-01T00:00:00Z",
            label="test-label",
            review_bundle_path="diagnostic-packs/latest/review_bundle.json",
            review_input_14b_path="diagnostic-packs/latest/review_input_14b.json",
            is_mirror=True,
        )
        from k8s_diag_agent.ui.api import _serialize_diagnostic_pack
        payload = _serialize_diagnostic_pack(mirror_view)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload.get("path"), "diagnostic-packs/diagnostic-pack-run-1.zip")
        self.assertEqual(payload.get("reviewBundlePath"), "diagnostic-packs/latest/review_bundle.json")
        self.assertEqual(payload.get("reviewInput14bPath"), "diagnostic-packs/latest/review_input_14b.json")
        self.assertEqual(payload.get("isMirror"), True)

    def test_diagnostic_pack_payload_is_mirror_false_for_run_scoped_paths(self) -> None:
        """Test that isMirror is False when paths point to run-scoped artifacts."""
        from k8s_diag_agent.ui.model import DiagnosticPackView

        # Create a view with is_mirror=False (run-scoped paths)
        run_scoped_view = DiagnosticPackView(
            path="diagnostic-packs/diagnostic-pack-run-1.zip",
            timestamp="2026-01-01T00:00:00Z",
            label="test-label",
            review_bundle_path="diagnostic-packs/run-1/review_bundle.json",
            review_input_14b_path="diagnostic-packs/run-1/review_input_14b.json",
            is_mirror=False,
        )
        from k8s_diag_agent.ui.api import _serialize_diagnostic_pack
        payload = _serialize_diagnostic_pack(run_scoped_view)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload.get("isMirror"), False)

    def test_diagnostic_pack_payload_omits_is_mirror_when_none(self) -> None:
        """Test that isMirror is omitted when is_mirror is None (legacy/preexisting data)."""
        from k8s_diag_agent.ui.model import DiagnosticPackView

        # Create a view without is_mirror (legacy/preexisting data)
        legacy_view = DiagnosticPackView(
            path="diagnostic-packs/diagnostic-pack-run-1.zip",
            timestamp="2026-01-01T00:00:00Z",
            label="test-label",
            review_bundle_path="diagnostic-packs/latest/review_bundle.json",
            review_input_14b_path="diagnostic-packs/latest/review_input_14b.json",
            is_mirror=None,
        )
        from k8s_diag_agent.ui.api import _serialize_diagnostic_pack
        payload = _serialize_diagnostic_pack(legacy_view)
        self.assertIsNotNone(payload)
        assert payload is not None
        # isMirror should not be present when is_mirror is None
        self.assertNotIn("isMirror", payload)

    def test_diagnostic_pack_source_pack_path_present_when_is_mirror_true(self) -> None:
        """Test that sourcePackPath is present when isMirror=true."""
        from k8s_diag_agent.ui.api import _serialize_diagnostic_pack
        from k8s_diag_agent.ui.model import DiagnosticPackView

        # Create a view with is_mirror=True (mirrored latest/ paths)
        mirror_view = DiagnosticPackView(
            path="diagnostic-packs/diagnostic-pack-run-1.zip",
            timestamp="2026-01-01T00:00:00Z",
            label="test-label",
            review_bundle_path="diagnostic-packs/latest/review_bundle.json",
            review_input_14b_path="diagnostic-packs/latest/review_input_14b.json",
            is_mirror=True,
        )
        payload = _serialize_diagnostic_pack(mirror_view)
        self.assertIsNotNone(payload)
        assert payload is not None
        # sourcePackPath should be present when isMirror=true
        self.assertIn("sourcePackPath", payload)
        # sourcePackPath should fall back to path when source_pack_path is not set
        self.assertEqual(payload.get("sourcePackPath"), "diagnostic-packs/diagnostic-pack-run-1.zip")

    def test_diagnostic_pack_source_pack_path_uses_explicit_source_pack_path(self) -> None:
        """Test that sourcePackPath uses explicit source_pack_path when provided."""
        from k8s_diag_agent.ui.api import _serialize_diagnostic_pack
        from k8s_diag_agent.ui.model import DiagnosticPackView

        # Create a view with explicit source_pack_path
        mirror_view = DiagnosticPackView(
            path="diagnostic-packs/diagnostic-pack-run-1.zip",
            timestamp="2026-01-01T00:00:00Z",
            label="test-label",
            review_bundle_path="diagnostic-packs/latest/review_bundle.json",
            review_input_14b_path="diagnostic-packs/latest/review_input_14b.json",
            is_mirror=True,
            source_pack_path="diagnostic-packs/diagnostic-pack-run-1-20260101T000000Z.zip",
        )
        payload = _serialize_diagnostic_pack(mirror_view)
        self.assertIsNotNone(payload)
        assert payload is not None
        # sourcePackPath should use the explicit source_pack_path
        self.assertEqual(
            payload.get("sourcePackPath"),
            "diagnostic-packs/diagnostic-pack-run-1-20260101T000000Z.zip"
        )

    def test_diagnostic_pack_source_pack_path_omitted_when_is_mirror_false(self) -> None:
        """Test that sourcePackPath is omitted when isMirror=false."""
        from k8s_diag_agent.ui.api import _serialize_diagnostic_pack
        from k8s_diag_agent.ui.model import DiagnosticPackView

        # Create a view with is_mirror=False (run-scoped paths)
        run_scoped_view = DiagnosticPackView(
            path="diagnostic-packs/diagnostic-pack-run-1.zip",
            timestamp="2026-01-01T00:00:00Z",
            label="test-label",
            review_bundle_path="diagnostic-packs/run-1/review_bundle.json",
            review_input_14b_path="diagnostic-packs/run-1/review_input_14b.json",
            is_mirror=False,
        )
        payload = _serialize_diagnostic_pack(run_scoped_view)
        self.assertIsNotNone(payload)
        assert payload is not None
        # sourcePackPath should not be present when isMirror=false
        self.assertNotIn("sourcePackPath", payload)

    def test_diagnostic_pack_source_pack_path_omitted_when_is_mirror_none(self) -> None:
        """Test that sourcePackPath is omitted when isMirror is None (legacy data)."""
        from k8s_diag_agent.ui.api import _serialize_diagnostic_pack
        from k8s_diag_agent.ui.model import DiagnosticPackView

        # Create a view without is_mirror (legacy/preexisting data)
        legacy_view = DiagnosticPackView(
            path="diagnostic-packs/diagnostic-pack-run-1.zip",
            timestamp="2026-01-01T00:00:00Z",
            label="test-label",
            review_bundle_path="diagnostic-packs/latest/review_bundle.json",
            review_input_14b_path="diagnostic-packs/latest/review_input_14b.json",
            is_mirror=None,
        )
        payload = _serialize_diagnostic_pack(legacy_view)
        self.assertIsNotNone(payload)
        assert payload is not None
        # sourcePackPath should not be present when is_mirror is None
        self.assertNotIn("sourcePackPath", payload)

    def test_diagnostic_pack_is_mirror_and_source_pack_path_semantically_consistent(self) -> None:
        """Test that isMirror and sourcePackPath are semantically consistent."""
        from k8s_diag_agent.ui.api import _serialize_diagnostic_pack
        from k8s_diag_agent.ui.model import DiagnosticPackView

        # Test case 1: isMirror=true implies sourcePackPath is present
        mirror_view = DiagnosticPackView(
            path="diagnostic-packs/diagnostic-pack-run-1.zip",
            timestamp="2026-01-01T00:00:00Z",
            label="test-label",
            review_bundle_path="diagnostic-packs/latest/review_bundle.json",
            review_input_14b_path="diagnostic-packs/latest/review_input_14b.json",
            is_mirror=True,
        )
        mirror_payload = _serialize_diagnostic_pack(mirror_view)
        self.assertIsNotNone(mirror_payload)
        assert mirror_payload is not None
        # When isMirror=true, sourcePackPath should be present
        self.assertIn("sourcePackPath", mirror_payload)
        self.assertIsNotNone(mirror_payload.get("sourcePackPath"))

        # Test case 2: isMirror=false implies sourcePackPath is absent
        run_scoped_view = DiagnosticPackView(
            path="diagnostic-packs/diagnostic-pack-run-1.zip",
            timestamp="2026-01-01T00:00:00Z",
            label="test-label",
            review_bundle_path="diagnostic-packs/run-1/review_bundle.json",
            review_input_14b_path="diagnostic-packs/run-1/review_input_14b.json",
            is_mirror=False,
        )
        run_scoped_payload = _serialize_diagnostic_pack(run_scoped_view)
        self.assertIsNotNone(run_scoped_payload)
        assert run_scoped_payload is not None
        # When isMirror=false, sourcePackPath should be absent
        self.assertNotIn("sourcePackPath", run_scoped_payload)

    def test_serialize_queue_appends_promoted_entries(self) -> None:
        promotions = [
            {
                "candidateId": "promo-id",
                "description": "Promoted deterministic check",
                "queueStatus": "approval-needed",
                "planArtifactPath": "external-analysis/promo.json",
                "sourceType": "deterministic",
            }
        ]
        serialized = _serialize_next_check_queue(self.context.run.next_check_queue, promotions)
        self.assertEqual(serialized[-1]["candidateId"], "promo-id")
        self.assertEqual(serialized[-1].get("sourceType"), "deterministic")

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
        self.assertEqual(summary_entry.get("workstream"), "incident")
        self.assertEqual(summary_entry.get("urgency"), "high")
        self.assertTrue(summary_entry.get("isPrimaryTriage"))
        self.assertIn("warning_event_threshold", str(summary_entry.get("whyNow")))

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

    def test_freshness_helper_accepts_naive_timestamp(self) -> None:
        """Regression test: naive timestamps should not cause 'can't compare' errors.

        Previously, timestamp strings without timezone info (e.g., "2026-01-01T00:00:00")
        would be parsed as naive datetimes, and comparing them with the UTC-aware now_value
        would raise: TypeError: can't compare offset-naive and offset-aware datetimes

        This test verifies that naive timestamps are normalized to UTC-aware before comparison.
        """
        base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        # Naive timestamp string (no timezone) - this used to cause the comparison error
        naive_timestamp = "2026-01-01T00:00:00"
        # This should NOT raise TypeError: can't compare offset-naive and offset-aware
        payload = _build_freshness_payload(naive_timestamp, 300, now=base + timedelta(seconds=200))
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["status"], "fresh")

    def test_freshness_helper_accepts_z_suffix_timestamp(self) -> None:
        """Test that Z-suffix timestamps (ISO 8601 legacy) work correctly."""
        base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        payload = _build_freshness_payload("2026-01-01T00:00:00Z", 300, now=base + timedelta(seconds=200))
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["status"], "fresh")

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


class RunsListTests(unittest.TestCase):
    """Tests for runs list and review status derivation."""

    def test_derive_review_status_no_executions(self) -> None:
        """Test that review status is 'no-executions' when execution_count is 0."""
        from k8s_diag_agent.ui.api import _derive_review_status

        status = _derive_review_status(0, 0)
        self.assertEqual(status, "no-executions")

    def test_derive_review_status_unreviewed(self) -> None:
        """Test that review status is 'unreviewed' when executions exist but none reviewed."""
        from k8s_diag_agent.ui.api import _derive_review_status

        status = _derive_review_status(5, 0)
        self.assertEqual(status, "unreviewed")

    def test_derive_review_status_partially_reviewed(self) -> None:
        """Test that review status is 'partially-reviewed' when some executions reviewed."""
        from k8s_diag_agent.ui.api import _derive_review_status

        status = _derive_review_status(5, 3)
        self.assertEqual(status, "partially-reviewed")

    def test_derive_review_status_fully_reviewed(self) -> None:
        """Test that review status is 'fully-reviewed' when all executions reviewed."""
        from k8s_diag_agent.ui.api import _derive_review_status

        status = _derive_review_status(5, 5)
        self.assertEqual(status, "fully-reviewed")

    def test_build_runs_list_no_executions_not_triaged(self) -> None:
        """Test that runs with no executions are NOT marked as triaged."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create a review artifact (run exists)
            review_content = {
                "run_id": "run-no-exec",
                "run_label": "Run without executions",
                "timestamp": "2026-01-01T00:00:00Z",
                "cluster_count": 2,
            }
            review_path = reviews_dir / "run-no-exec-review.json"
            review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Build the runs list - no execution artifacts exist
            result = cast(RunsListPayload, build_runs_list(runs_dir))

            self.assertEqual(result["totalCount"], 1)
            run = result["runs"][0]

            # Key assertion: triaged must be False when there are no executions
            self.assertFalse(run["triaged"])
            self.assertEqual(run["reviewStatus"], "no-executions")
            self.assertEqual(run["executionCount"], 0)
            self.assertEqual(run["reviewedCount"], 0)

    def test_build_runs_list_unreviewed_not_triaged(self) -> None:
        """Test that runs with executions but none reviewed are NOT marked as triaged."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            external_analysis_dir = runs_health_dir / "external-analysis"
            reviews_dir.mkdir(parents=True)
            external_analysis_dir.mkdir(parents=True)

            # Create a review artifact (run exists)
            review_content = {
                "run_id": "run-unreviewed",
                "run_label": "Run with unreviewed executions",
                "timestamp": "2026-01-01T00:00:00Z",
                "cluster_count": 2,
            }
            review_path = reviews_dir / "run-unreviewed-review.json"
            review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Create execution artifact WITHOUT usefulness_class (unreviewed)
            execution_content = {
                "run_id": "run-unreviewed",
                "purpose": "next-check-execution",
                "status": "success",
            }
            exec_path = external_analysis_dir / "run-unreviewed-next-check-execution-001.json"
            exec_path.write_text(json.dumps(execution_content), encoding="utf-8")

            # Build the runs list with include_expensive=True to derive execution counts
            result = cast(RunsListPayload, build_runs_list(runs_dir, include_expensive=True))

            self.assertEqual(result["totalCount"], 1)
            run = result["runs"][0]

            # Key assertion: triaged must be False when executions exist but none reviewed
            self.assertFalse(run["triaged"])
            self.assertEqual(run["reviewStatus"], "unreviewed")
            self.assertEqual(run["executionCount"], 1)
            self.assertEqual(run["reviewedCount"], 0)

    def test_build_runs_list_reviewed_is_triaged(self) -> None:
        """Test that runs with reviewed executions ARE marked as triaged."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            external_analysis_dir = runs_health_dir / "external-analysis"
            reviews_dir.mkdir(parents=True)
            external_analysis_dir.mkdir(parents=True)

            # Create a review artifact (run exists)
            review_content = {
                "run_id": "run-reviewed",
                "run_label": "Run with reviewed executions",
                "timestamp": "2026-01-01T00:00:00Z",
                "cluster_count": 2,
            }
            review_path = reviews_dir / "run-reviewed-review.json"
            review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Create execution artifact WITH usefulness_class (reviewed)
            execution_content = {
                "run_id": "run-reviewed",
                "purpose": "next-check-execution",
                "status": "success",
                "usefulness_class": "useful",
            }
            exec_path = external_analysis_dir / "run-reviewed-next-check-execution-001.json"
            exec_path.write_text(json.dumps(execution_content), encoding="utf-8")

            # Build the runs list with include_expensive=True to derive execution counts
            result = cast(RunsListPayload, build_runs_list(runs_dir, include_expensive=True))

            self.assertEqual(result["totalCount"], 1)
            run = result["runs"][0]

            # Key assertion: triaged must be True when executions have been reviewed
            self.assertTrue(run["triaged"])
            self.assertEqual(run["reviewStatus"], "fully-reviewed")
            self.assertEqual(run["executionCount"], 1)
            self.assertEqual(run["reviewedCount"], 1)

    def test_build_runs_list_partial_review_is_triaged(self) -> None:
        """Test that runs with partially reviewed executions ARE marked as triaged."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            external_analysis_dir = runs_health_dir / "external-analysis"
            reviews_dir.mkdir(parents=True)
            external_analysis_dir.mkdir(parents=True)

            # Create a review artifact (run exists)
            review_content = {
                "run_id": "run-partial",
                "run_label": "Run with partial reviews",
                "timestamp": "2026-01-01T00:00:00Z",
                "cluster_count": 2,
            }
            review_path = reviews_dir / "run-partial-review.json"
            review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Create two execution artifacts - one with usefulness_class, one without
            exec1_content = {
                "run_id": "run-partial",
                "purpose": "next-check-execution",
                "status": "success",
                "usefulness_class": "useful",
            }
            exec1_path = external_analysis_dir / "run-partial-next-check-execution-001.json"
            exec1_path.write_text(json.dumps(exec1_content), encoding="utf-8")

            exec2_content = {
                "run_id": "run-partial",
                "purpose": "next-check-execution",
                "status": "success",
            }
            exec2_path = external_analysis_dir / "run-partial-next-check-execution-002.json"
            exec2_path.write_text(json.dumps(exec2_content), encoding="utf-8")

            # Build the runs list with include_expensive=True to derive execution counts
            result = cast(RunsListPayload, build_runs_list(runs_dir, include_expensive=True))

            self.assertEqual(result["totalCount"], 1)
            run = result["runs"][0]

            # Key assertion: triaged must be True when at least one execution has been reviewed
            self.assertTrue(run["triaged"])
            self.assertEqual(run["reviewStatus"], "partially-reviewed")
            self.assertEqual(run["executionCount"], 2)
            self.assertEqual(run["reviewedCount"], 1)

    def test_build_runs_list_different_runs_produce_different_download_paths(self) -> None:
        """Test that two different runs produce two different download paths.
        
        This verifies the fix for the bug where historical runs all pointed to /latest/.
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            diagnostic_packs_dir = runs_health_dir / "diagnostic-packs"
            external_analysis_dir = runs_health_dir / "external-analysis"
            reviews_dir.mkdir(parents=True)
            diagnostic_packs_dir.mkdir(parents=True)
            external_analysis_dir.mkdir(parents=True)

            # Create run-1 with a run-scoped review artifact
            review1_content = {
                "run_id": "run-1",
                "run_label": "Run 1",
                "timestamp": "2026-01-01T00:00:00Z",
                "cluster_count": 2,
            }
            review_path1 = reviews_dir / "run-1-review.json"
            review_path1.write_text(json.dumps(review1_content), encoding="utf-8")

            # Create run-1's run-scoped diagnostic pack
            run1_pack_dir = diagnostic_packs_dir / "run-1"
            run1_pack_dir.mkdir(parents=True, exist_ok=True)
            run1_review_content = {"run_id": "run-1", "entries": []}
            (run1_pack_dir / "next_check_usefulness_review.json").write_text(
                json.dumps(run1_review_content), encoding="utf-8"
            )

            # Add execution artifact for run-1 (to trigger unreviewed status)
            exec1_content = {
                "run_id": "run-1",
                "purpose": "next-check-execution",
                "status": "success",
            }
            (external_analysis_dir / "run-1-next-check-execution-001.json").write_text(
                json.dumps(exec1_content), encoding="utf-8"
            )

            # Create run-2 with a different run-scoped review artifact
            review2_content = {
                "run_id": "run-2",
                "run_label": "Run 2",
                "timestamp": "2026-01-02T00:00:00Z",
                "cluster_count": 3,
            }
            review_path2 = reviews_dir / "run-2-review.json"
            review_path2.write_text(json.dumps(review2_content), encoding="utf-8")

            # Create run-2's run-scoped diagnostic pack
            run2_pack_dir = diagnostic_packs_dir / "run-2"
            run2_pack_dir.mkdir(parents=True, exist_ok=True)
            run2_review_content = {"run_id": "run-2", "entries": []}
            (run2_pack_dir / "next_check_usefulness_review.json").write_text(
                json.dumps(run2_review_content), encoding="utf-8"
            )

            # Add execution artifact for run-2 (to trigger unreviewed status)
            exec2_content = {
                "run_id": "run-2",
                "purpose": "next-check-execution",
                "status": "success",
            }
            (external_analysis_dir / "run-2-next-check-execution-001.json").write_text(
                json.dumps(exec2_content), encoding="utf-8"
            )

            # Build the runs list with include_expensive=True to derive execution counts
            result = cast(RunsListPayload, build_runs_list(runs_dir, include_expensive=True))

            self.assertEqual(result["totalCount"], 2)
            
            # Find each run's download path
            run1_path = None
            run2_path = None
            for run in result["runs"]:
                if run["runId"] == "run-1":
                    run1_path = run["reviewDownloadPath"]
                elif run["runId"] == "run-2":
                    run2_path = run["reviewDownloadPath"]

            # Key assertions: paths must be different and run-scoped
            self.assertIsNotNone(run1_path)
            self.assertIsNotNone(run2_path)
            self.assertNotEqual(run1_path, run2_path)
            assert run1_path is not None  # type narrowing
            assert run2_path is not None  # type narrowing
            self.assertIn("run-1", run1_path)
            self.assertIn("run-2", run2_path)
            self.assertNotIn("/latest/", run1_path)
            self.assertNotIn("/latest/", run2_path)

    def test_build_runs_list_historical_rows_no_latest_fallback(self) -> None:
        """Test that historical rows without run-scoped artifacts do NOT show download links.
        
        This verifies that when only /latest/ exists, historical rows don't show misleading links.
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            diagnostic_packs_dir = runs_health_dir / "diagnostic-packs"
            reviews_dir.mkdir(parents=True)
            diagnostic_packs_dir.mkdir(parents=True)

            # Create an old run (run-old) without a run-scoped artifact
            review_content = {
                "run_id": "run-old",
                "run_label": "Old Run",
                "timestamp": "2025-01-01T00:00:00Z",
                "cluster_count": 2,
            }
            review_path = reviews_dir / "run-old-review.json"
            review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Create execution artifact for the old run (so it needs review)
            external_analysis_dir = runs_health_dir / "external-analysis"
            external_analysis_dir.mkdir(parents=True)
            execution_content = {
                "run_id": "run-old",
                "purpose": "next-check-execution",
                "status": "success",
            }
            (external_analysis_dir / "run-old-next-check-execution-001.json").write_text(
                json.dumps(execution_content), encoding="utf-8"
            )

            # Create a /latest/ diagnostic pack (but NOT run-scoped for run-old)
            latest_dir = diagnostic_packs_dir / "latest"
            latest_dir.mkdir(parents=True, exist_ok=True)
            latest_content = {"run_id": "run-old", "entries": []}
            (latest_dir / "next_check_usefulness_review.json").write_text(
                json.dumps(latest_content), encoding="utf-8"
            )

            # Build the runs list with include_expensive=True to derive execution counts
            result = cast(RunsListPayload, build_runs_list(runs_dir, include_expensive=True))

            self.assertEqual(result["totalCount"], 1)
            run = result["runs"][0]

            # Key assertion: reviewDownloadPath must be None because run-scoped doesn't exist
            # We should NOT fall back to /latest/
            self.assertIsNone(run["reviewDownloadPath"])
            self.assertEqual(run["reviewStatus"], "unreviewed")

    def test_build_runs_list_download_link_only_when_artifact_exists(self) -> None:
        """Test that only rows with real run-scoped artifacts render a live download link.
        
        This verifies the frontend will only show Download when the artifact actually exists.
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            diagnostic_packs_dir = runs_health_dir / "diagnostic-packs"
            reviews_dir.mkdir(parents=True)
            diagnostic_packs_dir.mkdir(parents=True)

            # Create a run WITH run-scoped artifact
            review1_content = {
                "run_id": "run-with-artifact",
                "run_label": "Run with artifact",
                "timestamp": "2026-01-01T00:00:00Z",
                "cluster_count": 2,
            }
            review_path1 = reviews_dir / "run-with-artifact-review.json"
            review_path1.write_text(json.dumps(review1_content), encoding="utf-8")

            # Create run-scoped diagnostic pack
            run1_pack_dir = diagnostic_packs_dir / "run-with-artifact"
            run1_pack_dir.mkdir(parents=True, exist_ok=True)
            run1_review_content = {"run_id": "run-with-artifact", "entries": []}
            (run1_pack_dir / "next_check_usefulness_review.json").write_text(
                json.dumps(run1_review_content), encoding="utf-8"
            )

            # Create execution artifact
            external_analysis_dir = runs_health_dir / "external-analysis"
            external_analysis_dir.mkdir(parents=True)
            execution_content = {
                "run_id": "run-with-artifact",
                "purpose": "next-check-execution",
                "status": "success",
            }
            (external_analysis_dir / "run-with-artifact-next-check-execution-001.json").write_text(
                json.dumps(execution_content), encoding="utf-8"
            )

            # Build the runs list with include_expensive=True to derive execution counts
            result = cast(RunsListPayload, build_runs_list(runs_dir, include_expensive=True))

            self.assertEqual(result["totalCount"], 1)
            run = result["runs"][0]

            # Key assertion: reviewDownloadPath should be set because artifact exists
            self.assertIsNotNone(run["reviewDownloadPath"])
            assert run["reviewDownloadPath"] is not None  # type narrowing
            self.assertIn("run-with-artifact", run["reviewDownloadPath"])
            self.assertIn("next_check_usefulness_review.json", run["reviewDownloadPath"])

    def test_build_runs_list_default_limit_100(self) -> None:
        """Test that default limit is 100 and batch eligibility is computed for returned runs."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create 150 runs with distinct timestamps
            # Each run gets timestamp on a different day spanning Jan-May
            month_days = [31, 28, 31, 30, 31]  # Jan-May
            for i in range(150):
                day_counter = i
                for month_idx, days_in_month in enumerate(month_days):
                    if day_counter < days_in_month:
                        month = month_idx + 1
                        day = day_counter + 1
                        break
                    day_counter -= days_in_month
                review_content = {
                    "run_id": f"run-{i:03d}",
                    "run_label": f"Run {i}",
                    "timestamp": f"2026-{month:02d}-{day:02d}T00:00:00Z",
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"run-{i:03d}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Build the runs list with default limit
            result, timings = build_runs_list(runs_dir, _timings=True)

            # Should return only 100 runs (the default limit)
            self.assertEqual(len(result["runs"]), 100)

            # totalCount should be ALL discovered runs (150), not just returned
            self.assertEqual(result["totalCount"], 150)

            # returnedCount should be the number actually returned
            self.assertEqual(result["returnedCount"], 100)

            # hasMore should be True because totalCount > returnedCount
            self.assertTrue(result["hasMore"])

            # First run should be the most recent (run-149)
            self.assertEqual(result["runs"][0]["runId"], "run-149")

            # Last returned run should be run-050 (index 50 in 0-149)
            self.assertEqual(result["runs"][-1]["runId"], "run-050")

            # All returned runs should have batchEligibility="computed"
            # because they are within the returned window
            for run in result["runs"]:
                self.assertEqual(run["batchEligibility"], "computed")

            # Timing should reflect correct counts
            self.assertEqual(timings.get("rows_considered"), 150)
            self.assertEqual(timings.get("rows_returned"), 100)
            self.assertEqual(timings.get("batch_eligibility_runs_computed"), 100)

    def test_build_runs_list_limit_all(self) -> None:
        """Test that limit=None returns all runs."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create 150 runs
            for i in range(150):
                review_content = {
                    "run_id": f"run-{i:03d}",
                    "run_label": f"Run {i}",
                    "timestamp": f"2026-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z",
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"run-{i:03d}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Build the runs list with limit=None
            result = cast(RunsListPayload, build_runs_list(runs_dir, limit=None))

            # Should return all 150 runs
            self.assertEqual(result["totalCount"], 150)
            self.assertEqual(len(result["runs"]), 150)

    def test_build_runs_list_batch_eligibility_deferred_outside_window(self) -> None:
        """Test that batchEligibility is 'computed' for runs within the returned window.

        The optimization is that runs OUTSIDE the returned window don't get batch eligibility
        computed, but runs WITHIN the returned window DO get it computed.
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create 150 runs with distinct timestamps
            for i in range(150):
                day = 27 - (i // 10)
                hour = 23 - (i % 24)
                month = 2 if i >= 100 else 1
                review_content = {
                    "run_id": f"run-{i:03d}",
                    "run_label": f"Run {i}",
                    "timestamp": f"2026-{month:02d}-{day:02d}T{hour:02d}:00:00Z",
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"run-{i:03d}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Build the runs list with default limit and timings
            result, timings = build_runs_list(runs_dir, _timings=True)

            # Runs within the returned window (first 100) should have batchEligibility="computed"
            for run in result["runs"]:
                self.assertEqual(run["batchEligibility"], "computed")

            # Timing should show 100 runs had batch eligibility computed
            self.assertEqual(timings.get("batch_eligibility_runs_computed"), 100)

            # rows_considered should be 150 (all runs discovered)
            self.assertEqual(timings.get("rows_considered"), 150)

    def test_build_runs_list_include_expensive_computes_all(self) -> None:
        """Test that include_expensive=True computes batch eligibility for all runs."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create 10 runs
            for i in range(10):
                review_content = {
                    "run_id": f"run-{i:03d}",
                    "run_label": f"Run {i}",
                    "timestamp": f"2026-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z",
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"run-{i:03d}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Build the runs list with include_expensive=True
            result = cast(RunsListPayload, build_runs_list(runs_dir, include_expensive=True))

            # All runs should have batchEligibility="computed"
            for run in result["runs"]:
                self.assertEqual(run["batchEligibility"], "computed")

    def test_build_runs_list_limit_explicit(self) -> None:
        """Test that explicit limit works correctly."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create 50 runs with monotonically increasing timestamps
            # Each run gets timestamp on a different day spanning Jan-Mar
            month_days = [31, 28, 31]  # Jan-Mar
            for i in range(50):
                day_counter = i
                for month_idx, days_in_month in enumerate(month_days):
                    if day_counter < days_in_month:
                        month = month_idx + 1
                        day = day_counter + 1
                        break
                    day_counter -= days_in_month
                review_content = {
                    "run_id": f"run-{i:03d}",
                    "run_label": f"Run {i}",
                    "timestamp": f"2026-{month:02d}-{day:02d}T00:00:00Z",
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"run-{i:03d}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Build the runs list with limit=10
            result = cast(RunsListPayload, build_runs_list(runs_dir, limit=10))

            # Should return only 10 runs
            self.assertEqual(len(result["runs"]), 10)

            # totalCount should be ALL discovered runs (50), not just returned
            self.assertEqual(result["totalCount"], 50)

            # First run should be the most recent (run-049)
            self.assertEqual(result["runs"][0]["runId"], "run-049")
            self.assertEqual(result["runs"][-1]["runId"], "run-040")

    def test_build_runs_list_timings_include_rows_metrics(self) -> None:
        """Test that timing metrics include rows_considered and rows_returned."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create 50 runs
            for i in range(50):
                review_content = {
                    "run_id": f"run-{i:03d}",
                    "run_label": f"Run {i}",
                    "timestamp": f"2026-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z",
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"run-{i:03d}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Build the runs list with default limit (100) and timings
            result, timings = build_runs_list(runs_dir, _timings=True)

            # Should have 50 runs considered but only 50 returned (less than limit)
            self.assertEqual(timings.get("rows_considered"), 50)
            self.assertEqual(timings.get("rows_returned"), 50)

    def test_build_runs_list_timings_batch_eligibility_computed_count(self) -> None:
        """Test that batch_eligibility_runs_computed timing is set correctly."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create 50 runs
            for i in range(50):
                review_content = {
                    "run_id": f"run-{i:03d}",
                    "run_label": f"Run {i}",
                    "timestamp": f"2026-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z",
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"run-{i:03d}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Build the runs list with default limit (100 - but only 50 runs exist)
            result, timings = build_runs_list(runs_dir, _timings=True)

            # Should have computed batch eligibility for all 50 runs
            self.assertEqual(timings.get("batch_eligibility_runs_computed"), 50)

    def test_build_runs_list_latest_run_first(self) -> None:
        """Test that the latest run appears first regardless of limit."""

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create runs with different timestamps
            runs = [
                ("old-run", "2025-01-01T00:00:00Z"),
                ("middle-run", "2026-01-15T12:00:00Z"),
                ("newest-run", "2026-02-01T00:00:00Z"),
            ]

            for run_id, timestamp in runs:
                review_content = {
                    "run_id": run_id,
                    "run_label": run_id,
                    "timestamp": timestamp,
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"{run_id}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Build with limit=2
            result = cast(RunsListPayload, build_runs_list(runs_dir, limit=2))

            # First run should be the newest
            self.assertEqual(result["runs"][0]["runId"], "newest-run")
            self.assertEqual(result["runs"][1]["runId"], "middle-run")
