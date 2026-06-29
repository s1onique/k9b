"""Unit tests for incident report golden fixtures.

Regression tests for all hard gates using golden fixtures.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.api_incident_report import (
    _build_incident_report_payload,
    _build_operator_worklist_payload,
)
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.incident_report_fixtures import (
    _fixture_degraded_single_cluster,
    _fixture_deterministic_only_no_command,
    _fixture_healthy_no_incident,
    _fixture_queue_with_command,
    _fixture_stale_provider_enriched_degraded,
    _freshness,
)


class GoldenFixtureHealthyNoIncidentTests(unittest.TestCase):
    """Test the _fixture_healthy_no_incident golden fixture."""

    def test_healthy_report_status_and_title(self) -> None:
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["status"], "healthy")
        self.assertEqual(report["title"], "No degraded clusters detected")

    def test_healthy_report_inferences_empty(self) -> None:
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertFalse(report["inferences"])

    def test_healthy_report_unknowns_empty(self) -> None:
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertFalse(report["unknowns"])

    def test_healthy_report_stale_warnings_empty(self) -> None:
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertFalse(report["staleEvidenceWarnings"])


class GoldenFixtureDegradedSingleClusterTests(unittest.TestCase):
    """Test the _fixture_degraded_single_cluster golden fixture."""

    def test_degraded_report_status_and_title(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["title"], "Degraded health detected in 1 cluster(s)")

    def test_degraded_report_facts_non_empty(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["facts"])

    def test_degraded_report_unknowns_non_empty(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["unknowns"])

    def test_degraded_report_recommended_actions_non_empty(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Verify legacy string list still works
        self.assertTrue(report["recommendedActions"])
        # Verify structured recommendations are also present
        self.assertTrue(report.get("recommendations"))
        self.assertTrue(len(report["recommendations"]) > 0)
        # Verify recommendation claims have required fields
        for rec in report["recommendations"]:
            self.assertEqual(rec["claimType"], "recommendation")
            self.assertTrue(rec["safetyLevel"])

    def test_degraded_report_derived_non_empty(self) -> None:
        """Derived claims should be populated from assessment health rating."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Derived list exists
        self.assertIn("derived", report)
        self.assertTrue(len(report["derived"]) > 0)
        # Each derived claim has required fields
        for d in report["derived"]:
            self.assertEqual(d["claimType"], "derived")
            self.assertIn("statement", d)
            self.assertIn("sourceArtifactRefs", d)
            self.assertIn("confidence", d)

    def test_degraded_report_facts_not_health_rating(self) -> None:
        """Health rating should appear in derived, not facts."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Health rating statement should NOT be in facts
        fact_statements = [f["statement"] for f in report["facts"]]
        self.assertFalse(
            any("health rating is" in s for s in fact_statements),
            f"Health rating should not be in facts: {fact_statements}",
        )
        # Health rating should be in derived
        derived_statements = [d["statement"] for d in report["derived"]]
        self.assertTrue(
            any("health rating is" in s for s in derived_statements),
            f"Health rating should be in derived: {derived_statements}",
        )

    def test_degraded_report_source_refs_no_unknown(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        paths = [ref["path"] for ref in report["sourceArtifactRefs"]]
        self.assertNotIn("unknown", paths)

    def test_degraded_worklist_counts_consistent(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        total = worklist["totalItems"]
        completed = worklist["completedItems"]
        pending = worklist["pendingItems"]
        blocked = worklist["blockedItems"]
        self.assertEqual(total, completed + pending + blocked)

    def test_degraded_worklist_items_have_all_required_fields(self) -> None:
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertTrue(worklist["items"])
        for item in worklist["items"]:
            self.assertIn("rank", item)
            self.assertIn("title", item)
            self.assertIn("reason", item)
            self.assertIn("expectedEvidence", item)
            self.assertIn("safetyNote", item)
            self.assertIn("approvalState", item)
            self.assertIn("executionState", item)
            self.assertIn("feedbackState", item)


class GoldenFixtureStaleProviderEnrichedDegradedTests(unittest.TestCase):
    """Test the _fixture_stale_provider_enriched_degraded golden fixture."""

    def test_stale_warning_appears(self) -> None:
        index = _fixture_stale_provider_enriched_degraded()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("stale"))
        self.assertIsNotNone(report)
        assert report is not None
        self.assertTrue(report["staleEvidenceWarnings"])
        self.assertIn("stale", report["staleEvidenceWarnings"][0])

    def test_enrichment_in_inferences_only_not_facts(self) -> None:
        index = _fixture_stale_provider_enriched_degraded()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("stale"))
        self.assertIsNotNone(report)
        assert report is not None
        # Specific review enrichment summary appears in inferences
        inference_statements = [i["statement"] for i in report["inferences"]]
        self.assertIn(
            "High ingress latency detected; consider scaling the gateway.",
            inference_statements,
            "Enrichment summary must appear in inferences",
        )
        # It must NOT appear in facts
        fact_statements = [f["statement"] for f in report["facts"]]
        self.assertNotIn(
            "High ingress latency detected; consider scaling the gateway.",
            fact_statements,
            "Enrichment summary must NOT appear in facts",
        )

    def test_enrichment_inference_has_review_enrichment_basis(self) -> None:
        index = _fixture_stale_provider_enriched_degraded()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("stale"))
        self.assertIsNotNone(report)
        assert report is not None
        enrichment_inferences = [
            i for i in report["inferences"]
            if "review-enrichment" in str(i.get("basis", []))
        ]
        self.assertTrue(enrichment_inferences)


class GoldenFixtureDeterministicOnlyNoCommandTests(unittest.TestCase):
    """Test the _fixture_deterministic_only_no_command golden fixture."""

    def test_worklist_command_is_null(self) -> None:
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertTrue(worklist["items"])
        for item in worklist["items"]:
            # Deterministic checks have method, not command; command must be null
            self.assertIsNone(item.get("command"))

    def test_worklist_items_have_rank_title_workstream(self) -> None:
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        for item in worklist["items"]:
            self.assertIn("rank", item)
            self.assertIn("title", item)
            self.assertIn("workstream", item)

    def test_worklist_counts_zero_completed(self) -> None:
        index = _fixture_deterministic_only_no_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertEqual(worklist["completedItems"], 0)
        self.assertEqual(worklist["blockedItems"], 0)


class GoldenFixtureQueueWithCommandTests(unittest.TestCase):
    """Test the _fixture_queue_with_command golden fixture."""

    def test_queue_item_command_is_populated(self) -> None:
        index = _fixture_queue_with_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # Find queue item by exact expected candidate ID "candidate-logs"
        queue_items = [i for i in worklist["items"] if str(i.get("id", "")) == "candidate-logs"]
        self.assertTrue(queue_items)
        for item in queue_items:
            self.assertIsNotNone(item.get("command"))

    def test_queue_item_has_all_required_metadata(self) -> None:
        index = _fixture_queue_with_command()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        queue_items = [i for i in worklist["items"] if str(i.get("id", "")) == "candidate-logs"]
        self.assertTrue(queue_items)
        for item in queue_items:
            self.assertIn("command", item)
            self.assertIn("targetCluster", item)
            self.assertIn("targetContext", item)
            self.assertIn("reason", item)
            self.assertIn("expectedEvidence", item)
            self.assertIn("safetyNote", item)
            self.assertIn("approvalState", item)
            self.assertIn("executionState", item)
            self.assertIn("feedbackState", item)
            self.assertIn("sourceArtifactRefs", item)
            self.assertTrue(item["sourceArtifactRefs"])


# =============================================================================
# Content Quality Tests (Phase 3 - Deterministic Quality Fixtures)
# =============================================================================


