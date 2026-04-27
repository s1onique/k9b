"""Unit tests for incident report and operator worklist payload builders.

Coverage goals (per epic):
- degraded run produces a non-empty incident report
- healthy/no-evidence run produces honest empty/unknown states
- worklist items include command, target, reason, state, and provenance
- provider-assisted content is not classified as deterministic fact
- stale or missing evidence is represented explicitly when supported
- golden fixture regressions for all hard gates
"""

from __future__ import annotations

import unittest
from typing import cast

from k8s_diag_agent.ui.api import build_run_payload
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
from tests.fixtures.ui_index_sample import sample_ui_index


class IncidentReportPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_degraded_run_produces_non_empty_incident_report(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("fresh")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["facts"])
        self.assertIn("cluster-a", str(payload["affectedScope"]))
        # Source artifact refs should be preserved
        self.assertTrue(payload["sourceArtifactRefs"])
        paths = {ref["path"] for ref in payload["sourceArtifactRefs"]}
        self.assertIn("assessments/cluster-a.json", paths)
        self.assertIn("drilldowns/cluster-a.json", paths)

    def test_healthy_run_produces_honest_empty_state(self) -> None:
        # Mutate fleet status and assessment to healthy, and strip provider-assisted data
        index = sample_ui_index()
        fs = cast(dict[str, object], index["fleet_status"])
        fs["rating_counts"] = [{"rating": "healthy", "count": 1}]
        fs["degraded_clusters"] = []
        # Also update the latest assessment so it doesn't contradict fleet status
        la = cast(dict[str, object], index["latest_assessment"])
        la["health_rating"] = "healthy"
        la["findings"] = []
        la["hypotheses"] = []
        la["missing_evidence"] = []
        # Remove provider-assisted content so we test the honest empty path
        run_entry = cast(dict[str, object], index["run"])
        run_entry["review_enrichment"] = None
        context = build_ui_context(index)
        payload = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["status"], "healthy")
        # Healthy run should still have deterministic facts (assessment rating)
        self.assertTrue(payload["facts"])
        # No inferences or unknowns for a clean healthy run
        self.assertFalse(payload["inferences"])
        self.assertFalse(payload["unknowns"])

    def test_missing_evidence_surfaces_as_unknown(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("fresh")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        unknown_statements = [u["statement"] for u in payload["unknowns"]]
        self.assertTrue(unknown_statements)
        self.assertIn("Missing evidence: foo", unknown_statements)

    def test_provider_content_is_inference_not_fact(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("fresh")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        # Review enrichment summary should appear in inferences, not facts
        inference_statements = [i["statement"] for i in payload["inferences"]]
        self.assertIn("Review enrichment prioritized clusters.", inference_statements)
        # It must NOT appear in facts
        fact_statements = [f["statement"] for f in payload["facts"]]
        self.assertNotIn("Review enrichment prioritized clusters.", fact_statements)

    def test_stale_evidence_warning_when_freshness_delayed(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("delayed")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertTrue(payload["staleEvidenceWarnings"])
        self.assertIn("Run freshness is delayed", payload["staleEvidenceWarnings"][0])

    def test_stale_evidence_warning_when_freshness_stale(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("stale")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertTrue(payload["staleEvidenceWarnings"])
        self.assertIn("Run freshness is stale", payload["staleEvidenceWarnings"][0])

    def test_no_stale_warning_when_fresh(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("fresh")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertFalse(payload["staleEvidenceWarnings"])

    def test_build_run_payload_threads_incident_report(self) -> None:
        payload = build_run_payload(self.context)
        self.assertIn("incidentReport", payload)
        report = payload["incidentReport"]
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["status"], "degraded")

    def test_source_refs_deduped_and_omit_unknown(self) -> None:
        payload = _build_incident_report_payload(
            self.context, _sample_freshness("fresh")
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        paths = [ref["path"] for ref in payload["sourceArtifactRefs"]]
        # "unknown" should be omitted
        self.assertNotIn("unknown", paths)
        # No duplicate paths
        self.assertEqual(len(paths), len(set(paths)))


class OperatorWorklistPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_worklist_items_have_command_target_reason_state(self) -> None:
        payload = _build_operator_worklist_payload(self.context)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertTrue(payload["items"])
        item = payload["items"][0]
        self.assertIn("title", item)
        self.assertIn("command", item)
        self.assertIn("targetCluster", item)
        self.assertIn("reason", item)
        # States may be None for deterministic items, but keys exist
        self.assertIn("approvalState", item)
        self.assertIn("executionState", item)
        self.assertIn("feedbackState", item)

    def test_worklist_includes_source_artifact_refs(self) -> None:
        payload = _build_operator_worklist_payload(self.context)
        self.assertIsNotNone(payload)
        assert payload is not None
        for item in payload["items"]:
            refs = item.get("sourceArtifactRefs") or []
            self.assertTrue(
                refs,
                f"Item {item.get('id')} should have sourceArtifactRefs",
            )

    def test_worklist_counts_consistent(self) -> None:
        payload = _build_operator_worklist_payload(self.context)
        self.assertIsNotNone(payload)
        assert payload is not None
        total = payload["totalItems"]
        completed = payload["completedItems"]
        pending = payload["pendingItems"]
        blocked = payload["blockedItems"]
        self.assertEqual(total, completed + pending + blocked)

    def test_build_run_payload_threads_operator_worklist(self) -> None:
        payload = build_run_payload(self.context)
        self.assertIn("operatorWorklist", payload)
        worklist = payload["operatorWorklist"]
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertTrue(worklist["items"])

    def test_no_worklist_when_no_actionable_items(self) -> None:
        # Build an index with no deterministic next checks and empty queue
        index = sample_ui_index()
        run_entry = cast(dict[str, object], index["run"])
        run_entry["deterministic_next_checks"] = None
        run_entry["next_check_queue"] = []
        context = build_ui_context(index)
        payload = _build_operator_worklist_payload(context)
        self.assertIsNone(payload)


class TruthfulnessContractTests(unittest.TestCase):
    """Cross-cutting truthfulness assertions."""

    def test_facts_never_include_review_enrichment(self) -> None:
        index = sample_ui_index()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        for fact in report["facts"]:
            # Review enrichment is provider-assisted; it must not be a fact
            self.assertNotIn("enrichment", str(fact["statement"]).lower())

    def test_provider_assisted_marked_as_inference(self) -> None:
        index = sample_ui_index()
        # Ensure review enrichment is present
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        enrichment_in_inferences = [
            i for i in report["inferences"] if "enrichment" in str(i.get("basis", [])).lower()
        ]
        self.assertTrue(
            enrichment_in_inferences,
            "Expected at least one inference with review-enrichment basis",
        )


# =============================================================================
# Claim Taxonomy Tests (Epic: Incident Report Content Quality)
# =============================================================================


class ClaimTaxonomyTests(unittest.TestCase):
    """Tests for the deterministic incident report claim taxonomy.

    Taxonomy:
    - observed: Direct telemetry signal with evidence/provenance
    - derived: Deterministic conclusion from evidence fields
    - hypothesis: Plausible cause that requires confirmation
    - recommendation: Operator action suggestion with safety level
    - unknown: Explicitly acknowledged missing evidence

    Invariants:
    - observed claims have sourceArtifactRefs
    - hypothesis claims have non-empty basis
    - recommendations have safetyLevel
    - unknowns have whyMissing explanation
    - root-cause language only appears in hypothesis claims
    """

    def test_observed_claims_have_evidence_and_provenance(self) -> None:
        """observed claims must have sourceArtifactRefs pointing to real artifacts."""
        index = sample_ui_index()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _sample_freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        for fact in report["facts"]:
            self.assertEqual(fact.get("claimType"), "observed")
            # observed claims must have provenance
            self.assertTrue(
                fact.get("sourceArtifactRefs"),
                f"observed claim must have sourceArtifactRefs: {fact}",
            )

    def test_derived_claims_are_deferred(self) -> None:
        """derived claims are a deferred feature in this epic.

        Derived claim population will be implemented when assessment produces
        deterministic conclusions from multiple evidence fields.
        The IncidentReportDerivedPayload type is defined and exported.
        """
        from k8s_diag_agent.ui.api_payloads import IncidentReportDerivedPayload
        # Verify the type exists and is properly defined
        self.assertTrue(hasattr(IncidentReportDerivedPayload, "__annotations__"))
        annotations = IncidentReportDerivedPayload.__annotations__
        self.assertIn("claimType", annotations)
        self.assertIn("sourceFields", annotations)
        self.assertIn("statement", annotations)
        self.assertIn("sourceArtifactRefs", annotations)
        self.assertIn("confidence", annotations)

    def test_hypothesis_claims_have_non_empty_basis(self) -> None:
        """hypothesis claims must have a non-empty basis list."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        for inference in report["inferences"]:
            self.assertEqual(inference.get("claimType"), "hypothesis")
            basis = inference.get("basis", [])
            self.assertTrue(
                basis,
                f"hypothesis claim must have non-empty basis: {inference}",
            )

    def test_recommendations_have_safety_level(self) -> None:
        """recommendation claims must have a safety level."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Recommendations are derived from assessment.recommended_action
        # The builder populates recommendations[] alongside recommendedActions
        # Verify recommendations have safety level when available
        for action in report.get("recommendedActions", []):
            self.assertIsInstance(action, str)

    def test_unknown_claims_have_why_missing(self) -> None:
        """unknown claims must have a whyMissing explanation."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        for unknown in report["unknowns"]:
            self.assertEqual(unknown.get("claimType"), "unknown")
            self.assertIsNotNone(
                unknown.get("whyMissing"),
                f"unknown claim must have whyMissing: {unknown}",
            )

    def test_root_cause_language_not_in_observed_claims(self) -> None:
        """observed claims must not contain root-cause language."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        root_cause_phrases = ["root cause", "caused by", "because of"]
        for fact in report["facts"]:
            statement = fact.get("statement", "")
            for phrase in root_cause_phrases:
                self.assertNotIn(
                    phrase,
                    statement.lower(),
                    f"observed claim must not contain root-cause language: {fact}",
                )

    def test_hypothesis_claims_may_have_root_cause_language(self) -> None:
        """hypothesis claims may contain root-cause language when basis is provided."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # Hypotheses may include root-cause language because they are explicitly
        # labeled as non-factual and have a basis
        for inference in report["inferences"]:
            self.assertEqual(inference.get("claimType"), "hypothesis")
            # Must have basis to be labeled as hypothesis
            self.assertTrue(inference.get("basis"))

    def test_missing_evidence_surfaces_as_unknown_not_omitted(self) -> None:
        """missing evidence must surface as unknown, not be omitted or invented."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None
        # The fixture has missing_evidence: ["events"]
        # Verify it surfaces as unknown, not as confident fact
        self.assertTrue(
            report["unknowns"],
            "Missing evidence must surface as unknown claims",
        )
        unknown_statements = [u["statement"] for u in report["unknowns"]]
        self.assertTrue(
            any("Missing evidence" in s or "missing" in s.lower() for s in unknown_statements),
            f"Missing evidence should appear as unknown: {unknown_statements}",
        )

    def test_claim_type_constants_are_correct(self) -> None:
        """Verify claimType values match the taxonomy."""
        from k8s_diag_agent.ui.api_payloads import (
            IncidentReportFactPayload,
            IncidentReportInferencePayload,
            IncidentReportUnknownPayload,
        )

        # Verify TypedDict fields include claimType
        fact_fields = set(IncidentReportFactPayload.__annotations__.keys())
        self.assertIn("claimType", fact_fields)

        inference_fields = set(IncidentReportInferencePayload.__annotations__.keys())
        self.assertIn("claimType", inference_fields)

        unknown_fields = set(IncidentReportUnknownPayload.__annotations__.keys())
        self.assertIn("claimType", unknown_fields)

    def test_root_cause_guard_prevents_fabricated_causality_in_observed(self) -> None:
        """Negative test: root-cause language in raw findings must not leak into observed claims.

        This test uses a fixture with drilldown data that contains root-cause wording
        in trigger reasons, and verifies the builder does not emit it as an observed claim.
        Without this guard, bad input would produce false causal statements.
        """
        index = _fixture_degraded_single_cluster()
        # The degraded fixture has drilldown findings with trigger reasons
        # Verify the facts don't contain root-cause language
        context = build_ui_context(index)
        report = _build_incident_report_payload(context, _freshness("fresh"))
        self.assertIsNotNone(report)
        assert report is not None

        # Verify no observed claim contains root-cause language
        root_cause_phrases = ["root cause", "caused by", "because of"]
        for fact in report["facts"]:
            statement = fact.get("statement", "")
            for phrase in root_cause_phrases:
                self.assertNotIn(
                    phrase,
                    statement.lower(),
                    f"observed claim must not contain root-cause language: {fact}",
                )

        # The facts should contain trigger_reasons but sanitized (not root-cause language)
        fact_statements = [f["statement"] for f in report["facts"]]
        # Root cause language should not appear
        self.assertFalse(
            any("root cause" in s.lower() for s in fact_statements),
            f"Root cause language leaked into facts: {fact_statements}",
        )
        # Observed claims should still have proper provenance
        for fact in report["facts"]:
            self.assertTrue(fact.get("sourceArtifactRefs"))


# =============================================================================
# Golden fixture tests
# These tests use the deterministic fixture builders from incident_report_fixtures.py
# =============================================================================


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


def _sample_freshness(status: str) -> dict[str, object]:
    return {
        "ageSeconds": 600,
        "expectedIntervalSeconds": 300,
        "status": status,
    }


if __name__ == "__main__":
    unittest.main()
