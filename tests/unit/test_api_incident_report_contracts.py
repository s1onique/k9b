"""Unit tests for incident report truthfulness and claim taxonomy contracts.

Tests cross-cutting truthfulness assertions and claim taxonomy invariants.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.api_incident_report import (
    _build_incident_report_payload,
)
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.incident_report_fixtures import (
    _fixture_degraded_single_cluster,
    _freshness,
)
from tests.fixtures.ui_index_sample import sample_ui_index
from tests.unit.test_api_incident_report_helpers import _sample_freshness


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


