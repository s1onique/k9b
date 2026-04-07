import unittest

from k8s_diag_agent.ui.api import (
    build_cluster_detail_payload,
    build_fleet_payload,
    build_notifications_payload,
    build_proposals_payload,
    build_run_payload,
)
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.ui_index_sample import sample_ui_index


class UIApiTests(unittest.TestCase):
    def setUp(self) -> None:
        index = sample_ui_index()
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
        self.assertEqual(llm_stats["totalCalls"], 2)
        self.assertEqual(llm_stats["successfulCalls"], 2)
        providers = {entry["provider"] for entry in llm_stats["providerBreakdown"]}
        self.assertIn("k8sgpt", providers)
        self.assertIn("llm-autodrilldown", providers)
        historical = payload["historicalLlmStats"]
        self.assertIsNotNone(historical)
        assert historical is not None
        self.assertEqual(historical["totalCalls"], 5)
        self.assertEqual(historical["scope"], "retained_history")

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
