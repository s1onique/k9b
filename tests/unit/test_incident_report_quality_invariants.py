"""Unit tests for incident report claim type quality invariants.

These tests verify the quality gates documented in:
- docs/data-model/incident-report-quality.md
- DOC-CLAIM-0054: Every claim is classified into one of five types
- DOC-CLAIM-0055: Observed claims never contain root-cause/causal language
- DOC-CLAIM-0056: Hypothesis claims must have non-empty basis
- DOC-CLAIM-0057: Unknown claims must have whyMissing explanation
- DOC-CLAIM-0063: Signal/finding/hypothesis/confidence/action remain separated
"""

from __future__ import annotations

import unittest
import unittest.mock

from k8s_diag_agent.ui.api_incident_report import _build_incident_report_payload
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.ui_index_sample import sample_ui_index

# Forbidden causal patterns per DOC-CLAIM-0055
FORBIDDEN_CAUSAL_PATTERNS = [
    "root cause",
    "caused by",
    "because of",
    "is the cause",
    "the cause of",
    "directly caused",
    "responsible for",
]


class TestClaimTypeTaxonomy(unittest.TestCase):
    """Tests for DOC-CLAIM-0054: Claim type taxonomy enforcement.

    Every claim in the incident report must be classified into one of five types:
    - observed
    - derived
    - hypothesis (via 'inferences' field)
    - unknown
    - recommendation
    """

    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_all_claims_have_valid_claim_type(self) -> None:
        """Test that all claims in the report have a valid claimType."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        valid_types = {"observed", "derived", "hypothesis", "unknown", "recommendation"}

        # Check facts (observed claims)
        for fact in payload["facts"]:
            self.assertIn(
                fact.get("claimType"),
                valid_types,
                f"Invalid claimType in facts: {fact.get('claimType')}",
            )

        # Check derived claims
        for derived in payload["derived"]:
            self.assertIn(
                derived.get("claimType"),
                valid_types,
                f"Invalid claimType in derived: {derived.get('claimType')}",
            )

        # Check inferences (hypothesis claims)
        for inference in payload["inferences"]:
            self.assertIn(
                inference.get("claimType"),
                valid_types,
                f"Invalid claimType in inferences: {inference.get('claimType')}",
            )

        # Check recommendations
        for rec in payload["recommendations"]:
            self.assertIn(
                rec.get("claimType"),
                valid_types,
                f"Invalid claimType in recommendations: {rec.get('claimType')}",
            )

        # Check unknowns
        for unknown in payload["unknowns"]:
            self.assertIn(
                unknown.get("claimType"),
                valid_types,
                f"Invalid claimType in unknowns: {unknown.get('claimType')}",
            )

    def test_observed_claims_in_facts_field(self) -> None:
        """Test that observed claims appear in facts field."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        # Facts should have claimType='observed'
        for fact in payload["facts"]:
            self.assertEqual(
                fact.get("claimType"),
                "observed",
                f"Expected 'observed' in facts, got: {fact.get('claimType')}",
            )

    def test_derived_claims_in_derived_field(self) -> None:
        """Test that derived claims appear in derived field."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        # Derived claims should have claimType='derived'
        for derived in payload["derived"]:
            self.assertEqual(
                derived.get("claimType"),
                "derived",
                f"Expected 'derived' in derived, got: {derived.get('claimType')}",
            )

    def test_hypothesis_claims_in_inferences_field(self) -> None:
        """Test that hypothesis claims appear in inferences field."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        # Inferences should have claimType='hypothesis'
        for inference in payload["inferences"]:
            self.assertEqual(
                inference.get("claimType"),
                "hypothesis",
                f"Expected 'hypothesis' in inferences, got: {inference.get('claimType')}",
            )

    def test_recommendation_claims_in_recommendations_field(self) -> None:
        """Test that recommendation claims appear in recommendations field."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        # Recommendations should have claimType='recommendation'
        for rec in payload["recommendations"]:
            self.assertEqual(
                rec.get("claimType"),
                "recommendation",
                f"Expected 'recommendation', got: {rec.get('claimType')}",
            )

    def test_unknown_claims_in_unknowns_field(self) -> None:
        """Test that unknown claims appear in unknowns field."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        # Unknowns should have claimType='unknown'
        for unknown in payload["unknowns"]:
            self.assertEqual(
                unknown.get("claimType"),
                "unknown",
                f"Expected 'unknown', got: {unknown.get('claimType')}",
            )


class TestObservedNoCausalLanguage(unittest.TestCase):
    """Tests for DOC-CLAIM-0055: Observed claims never contain root-cause/causal language.

    Invariant: observed claims (facts) must NOT contain causal/root-cause language.
    This prevents overconfident causal claims in deterministic facts.
    """

    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_observed_claims_no_forbidden_causal_patterns(self) -> None:
        """Test that observed claims don't contain forbidden causal patterns."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        for fact in payload["facts"]:
            statement = fact.get("statement", "").lower()
            for pattern in FORBIDDEN_CAUSAL_PATTERNS:
                self.assertNotIn(
                    pattern,
                    statement,
                    f"Found forbidden causal pattern '{pattern}' in observed claim: {fact.get('statement')}",
                )

    def test_observed_claims_have_source_refs(self) -> None:
        """Test that observed claims have sourceArtifactRefs for provenance."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        for fact in payload["facts"]:
            self.assertIn(
                "sourceArtifactRefs",
                fact,
                f"Observed claim missing sourceArtifactRefs: {fact.get('statement')}",
            )


class TestHypothesisHasBasis(unittest.TestCase):
    """Tests for DOC-CLAIM-0056: Hypothesis claims must have non-empty basis.

    Invariant: hypothesis claims must have a non-empty 'basis' field to use
    root-cause language. This ensures inferences are explicitly labeled and backed.
    """

    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_hypothesis_claims_have_basis(self) -> None:
        """Test that hypothesis claims have non-empty basis."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        for inference in payload["inferences"]:
            self.assertIn(
                "basis",
                inference,
                f"Hypothesis claim missing 'basis': {inference.get('statement')}",
            )
            basis = inference.get("basis")
            self.assertIsInstance(
                basis,
                list,
                f"basis should be a list, got: {type(basis)}",
            )
            self.assertGreater(
                len(basis),
                0,
                f"Hypothesis claim has empty basis: {inference.get('statement')}",
            )

    def test_hypothesis_claims_have_confidence(self) -> None:
        """Test that hypothesis claims have confidence level."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        for inference in payload["inferences"]:
            self.assertIn(
                "confidence",
                inference,
                f"Hypothesis claim missing 'confidence': {inference.get('statement')}",
            )
            confidence = inference.get("confidence")
            self.assertIn(
                confidence,
                ["high", "medium", "low", "unknown"],
                f"Invalid confidence value: {confidence}",
            )


class TestUnknownHasWhyMissing(unittest.TestCase):
    """Tests for DOC-CLAIM-0057: Unknown claims must have whyMissing explanation.

    Invariant: unknown claims must have a 'whyMissing' explanation field.
    Missing evidence must be surfaced, not omitted or invented.
    """

    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_unknown_claims_have_why_missing(self) -> None:
        """Test that unknown claims have whyMissing explanation."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        for unknown in payload["unknowns"]:
            self.assertIn(
                "whyMissing",
                unknown,
                f"Unknown claim missing 'whyMissing': {unknown.get('statement')}",
            )
            why_missing = unknown.get("whyMissing")
            self.assertIsInstance(
                why_missing,
                str,
                f"whyMissing should be a string, got: {type(why_missing)}",
            )
            self.assertGreater(
                len(why_missing),
                0,
                f"whyMissing is empty: {unknown.get('statement')}",
            )

    def test_unknown_claims_explain_missing_evidence(self) -> None:
        """Test that whyMissing explains what evidence is missing."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        for unknown in payload["unknowns"]:
            why_missing = unknown.get("whyMissing", "")
            # whyMissing should contain meaningful explanation
            self.assertGreater(
                len(why_missing),
                5,
                f"whyMissing too short to be meaningful: '{why_missing}'",
            )


class TestSignalFindingHypothesisSeparation(unittest.TestCase):
    """Tests for DOC-CLAIM-0063: Signal/finding/hypothesis/confidence/action separation.

    Invariant: observed signal, derived symptom/finding, hypothesis, confidence,
    and recommended action must remain separate fields. The system must not
    collapse them into one opaque conclusion.
    """

    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_payload_has_separate_fields(self) -> None:
        """Test that payload has all required separate fields."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        # Required separate fields
        required_fields = [
            "facts",       # observed signals
            "derived",     # derived findings
            "inferences",  # hypotheses
            "recommendations",  # recommended actions
            "unknowns",    # unknown/missing evidence
            "confidence",  # overall confidence
        ]

        for field in required_fields:
            self.assertIn(
                field,
                payload,
                f"Payload missing required field: {field}",
            )

    def test_confidence_not_collapsed_with_conclusion(self) -> None:
        """Test that confidence is a separate field, not embedded in conclusions."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        # Confidence should be a top-level field with simple value
        self.assertIn("confidence", payload)
        confidence = payload["confidence"]
        self.assertIsInstance(
            confidence,
            str,
            f"Confidence should be a simple string, got: {type(confidence)}",
        )
        self.assertIn(
            confidence,
            ["high", "medium", "low", "unknown"],
            f"Invalid confidence value: {confidence}",
        )

    def test_claim_types_not_mixed(self) -> None:
        """Test that different claim types are not mixed into single fields."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        # Each field should only contain its specific claim type
        for fact in payload["facts"]:
            self.assertEqual(fact.get("claimType"), "observed")

        for derived in payload["derived"]:
            self.assertEqual(derived.get("claimType"), "derived")

        for inference in payload["inferences"]:
            self.assertEqual(inference.get("claimType"), "hypothesis")

        for rec in payload["recommendations"]:
            self.assertEqual(rec.get("claimType"), "recommendation")

        for unknown in payload["unknowns"]:
            self.assertEqual(unknown.get("claimType"), "unknown")

    def test_each_claim_has_distinct_structure(self) -> None:
        """Test that each claim type has its expected field structure."""
        payload = _build_incident_report_payload(self.context, None)
        self.assertIsNotNone(payload)
        assert payload is not None

        # Observed claims: statement, sourceArtifactRefs, confidence
        for fact in payload["facts"]:
            self.assertIn("statement", fact)
            self.assertIn("sourceArtifactRefs", fact)
            self.assertIn("confidence", fact)

        # Derived claims: statement, sourceFields, sourceArtifactRefs, confidence
        for derived in payload["derived"]:
            self.assertIn("statement", derived)
            self.assertIn("confidence", derived)

        # Hypothesis claims: statement, basis, confidence, sourceArtifactRefs
        for inference in payload["inferences"]:
            self.assertIn("statement", inference)
            self.assertIn("basis", inference)
            self.assertIn("confidence", inference)

        # Recommendation claims: statement, safetyLevel, sourceArtifactRefs
        for rec in payload["recommendations"]:
            self.assertIn("statement", rec)
            self.assertIn("safetyLevel", rec)

        # Unknown claims: statement, whyMissing, sourceArtifactRefs
        for unknown in payload["unknowns"]:
            self.assertIn("statement", unknown)
            self.assertIn("whyMissing", unknown)


if __name__ == "__main__":
    unittest.main()