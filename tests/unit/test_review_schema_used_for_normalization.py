"""Tests for used_for alias normalization in review_schema.

Verifies that pluralized variants like 'top_concerns' are normalized
to canonical values like 'top_concern' before validation.
"""

import unittest

from k8s_diag_agent.external_analysis.review_schema import (
    ReviewEnrichmentPayload,
    ReviewEnrichmentPayloadError,
    _normalize_used_for,
)


class NormalizeUsedForTests(unittest.TestCase):
    """Tests for _normalize_used_for() alias normalization."""

    def test_plurals_are_normalized(self) -> None:
        """Test that pluralized variants are normalized to canonical values."""
        # top_concerns -> top_concern
        self.assertEqual(_normalize_used_for("top_concerns"), "top_concern")
        # next_checks -> next_check
        self.assertEqual(_normalize_used_for("next_checks"), "next_check")
        # focus_notes -> focus_note
        self.assertEqual(_normalize_used_for("focus_notes"), "focus_note")

    def test_canonical_values_pass_through(self) -> None:
        """Test that canonical values pass through unchanged."""
        self.assertEqual(_normalize_used_for("top_concern"), "top_concern")
        self.assertEqual(_normalize_used_for("next_check"), "next_check")
        self.assertEqual(_normalize_used_for("summary"), "summary")
        self.assertEqual(_normalize_used_for("triage_order"), "triage_order")
        self.assertEqual(_normalize_used_for("focus_note"), "focus_note")

    def test_unknown_invalid_values_returned_unchanged(self) -> None:
        """Test that unknown invalid values are returned unchanged for downstream rejection."""
        # These should pass through so the dataclass validator can reject them
        self.assertEqual(_normalize_used_for("unknown_value"), "unknown_value")
        self.assertEqual(_normalize_used_for("invalid"), "invalid")
        self.assertEqual(_normalize_used_for(""), "")


class AlertmanagerEvidenceReferenceAliasNormalizationTests(unittest.TestCase):
    """Tests for AlertmanagerEvidenceReference with aliased used_for values."""

    def test_pluralized_used_for_accepted(self) -> None:
        """Test that pluralized used_for values are normalized and accepted."""
        from k8s_diag_agent.external_analysis.review_schema import (
            AlertmanagerEvidenceReference,
        )

        # These should not raise - alias normalization handles them
        ref = AlertmanagerEvidenceReference(
            cluster="test-cluster",
            matched_dimensions=("alertname",),
            reason="Test reason",
            used_for="top_concerns",  # Should be normalized to "top_concern"
        )
        self.assertEqual(ref.used_for, "top_concern")

    def test_next_checks_normalized(self) -> None:
        """Test that 'next_checks' is normalized to 'next_check'."""
        from k8s_diag_agent.external_analysis.review_schema import (
            AlertmanagerEvidenceReference,
        )

        ref = AlertmanagerEvidenceReference(
            cluster="test-cluster",
            matched_dimensions=("namespace",),
            reason="Test reason",
            used_for="next_checks",  # Should be normalized
        )
        self.assertEqual(ref.used_for, "next_check")

    def test_focus_notes_normalized(self) -> None:
        """Test that 'focus_notes' is normalized to 'focus_note'."""
        from k8s_diag_agent.external_analysis.review_schema import (
            AlertmanagerEvidenceReference,
        )

        ref = AlertmanagerEvidenceReference(
            cluster="test-cluster",
            matched_dimensions=("severity",),
            reason="Test reason",
            used_for="focus_notes",  # Should be normalized
        )
        self.assertEqual(ref.used_for, "focus_note")

    def test_canonical_values_still_work(self) -> None:
        """Test that canonical used_for values still work."""
        from k8s_diag_agent.external_analysis.review_schema import (
            AlertmanagerEvidenceReference,
        )

        for canonical in ("top_concern", "next_check", "summary", "triage_order", "focus_note"):
            ref = AlertmanagerEvidenceReference(
                cluster="test-cluster",
                matched_dimensions=("alertname",),
                reason="Test reason",
                used_for=canonical,
            )
            self.assertEqual(ref.used_for, canonical)

    def test_unknown_invalid_values_still_rejected(self) -> None:
        """Test that unknown invalid values still raise validation error."""
        from k8s_diag_agent.external_analysis.review_schema import (
            AlertmanagerEvidenceReference,
        )

        with self.assertRaises(ReviewEnrichmentPayloadError) as ctx:
            AlertmanagerEvidenceReference(
                cluster="test-cluster",
                matched_dimensions=("alertname",),
                reason="Test reason",
                used_for="invalid_value",
            )
        self.assertIn("invalid_value", str(ctx.exception))
        self.assertIn("must be one of", str(ctx.exception))


class ReviewEnrichmentPayloadFromDictTests(unittest.TestCase):
    """Tests for ReviewEnrichmentPayload.from_dict() with aliased used_for values."""

    def test_from_dict_normalizes_plurals_in_refs(self) -> None:
        """Test that from_dict normalizes pluralized used_for in alertmanager refs."""
        raw = {
            "summary": "Test summary",
            "alertmanagerEvidenceReferences": [
                {
                    "cluster": "cluster-a",
                    "matchedDimensions": ["alertname"],
                    "reason": "Fires on restart",
                    "usedFor": "top_concerns",  # Plural - should be normalized
                },
                {
                    "cluster": "cluster-b",
                    "matchedDimensions": ["namespace"],
                    "reason": "Indicates pressure",
                    "usedFor": "next_checks",  # Plural - should be normalized
                },
                {
                    "cluster": "cluster-c",
                    "matchedDimensions": ["severity"],
                    "reason": "Focus area",
                    "usedFor": "focus_notes",  # Plural - should be normalized
                },
            ],
        }

        payload = ReviewEnrichmentPayload.from_dict(raw)

        self.assertEqual(len(payload.alertmanager_evidence_references), 3)
        self.assertEqual(payload.alertmanager_evidence_references[0].used_for, "top_concern")
        self.assertEqual(payload.alertmanager_evidence_references[1].used_for, "next_check")
        self.assertEqual(payload.alertmanager_evidence_references[2].used_for, "focus_note")

    def test_to_dict_preserves_canonical_values(self) -> None:
        """Test that to_dict preserves canonical stored values."""
        raw = {
            "summary": "Test",
            "alertmanagerEvidenceReferences": [
                {
                    "cluster": "cluster-a",
                    "matchedDimensions": ["alertname"],
                    "reason": "Reason",
                    "usedFor": "top_concerns",  # Will be normalized
                },
            ],
        }

        payload = ReviewEnrichmentPayload.from_dict(raw)
        output = payload.to_dict()

        # Stored value should be canonical, not the alias
        self.assertEqual(
            output["alertmanagerEvidenceReferences"][0]["usedFor"],
            "top_concern",
        )


class SystemInstructionsComplianceTests(unittest.TestCase):
    """Tests verifying provider instructions list exact usedFor literals."""

    def test_instructions_list_exact_literals(self) -> None:
        """Test that _REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS explicitly lists exact literals."""
        from k8s_diag_agent.llm.llamacpp_provider import (
            _REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS,
        )

        instructions = _REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS

        # Should list exact canonical values
        self.assertIn("top_concern", instructions)
        self.assertIn("next_check", instructions)
        self.assertIn("summary", instructions)
        self.assertIn("triage_order", instructions)
        self.assertIn("focus_note", instructions)

    def test_instructions_warn_against_plurals(self) -> None:
        """Test that instructions explicitly warn against plural forms."""
        from k8s_diag_agent.llm.llamacpp_provider import (
            _REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS,
        )

        instructions = _REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS

        # Should explicitly warn against plural forms
        self.assertIn("top_concerns", instructions)
        self.assertIn("next_checks", instructions)
        self.assertIn("focus_notes", instructions)
        self.assertIn("Do NOT use plural forms", instructions)

    def test_instructions_warn_against_field_name_derivation(self) -> None:
        """Test that instructions warn against deriving usedFor from field names."""
        from k8s_diag_agent.llm.llamacpp_provider import (
            _REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS,
        )

        instructions = _REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS

        # Should warn against deriving from field names
        self.assertIn("topConcerns", instructions)
        self.assertIn("nextChecks", instructions)
        self.assertIn("focusNotes", instructions)
        self.assertIn("Do NOT derive usedFor from field names", instructions)


if __name__ == "__main__":
    unittest.main()
