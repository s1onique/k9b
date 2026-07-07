"""Golden/contract tests for Alertmanager source promotion review packet.

Tests that the promotion review packet schema is stable and conforms to the canonical wire schema
k9b.alertmanager_source.promotion_review.v1.

Run with: python -m pytest tests/unit/test_alertmanager_packet_contracts_promotion.py -v
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.external_analysis.alertmanager_source_promotion_review import (
    AlertmanagerSourcePromotionReview,
    PromotionRisk,
    TrackedSourceSpec,
)


class TestAlertmanagerSourcePromotionReviewContract(unittest.TestCase):
    """Contract tests for AlertmanagerSourcePromotionReview canonical schema."""

    def test_schema_version_matches_canonical(self) -> None:
        """Schema version must be k9b.alertmanager_source.promotion_review.v1."""
        from k8s_diag_agent.external_analysis.alertmanager_source_promotion_review import SCHEMA_VERSION

        self.assertEqual(SCHEMA_VERSION, "k9b.alertmanager_source.promotion_review.v1")

    def test_promotion_review_to_dict_has_required_top_level_keys(self) -> None:
        """Promotion review must have all required top-level keys."""
        packet = AlertmanagerSourcePromotionReview(
            source_id="test-source",
            promotable=True,
        )
        result = packet.to_dict()

        # Required top-level keys
        required_keys = {
            "schema_version",
            "artifact_id",
            "generated_at",
            "source_id",
            "promotable",
            "will_create",
            "aliases",
            "risks",
            "redactions",
        }
        self.assertEqual(set(result.keys()), required_keys)

    def test_promotion_review_schema_version_in_output(self) -> None:
        """Schema version must appear in output dict."""
        packet = AlertmanagerSourcePromotionReview(
            source_id="test-source",
            promotable=True,
        )
        result = packet.to_dict()

        self.assertEqual(result["schema_version"], "k9b.alertmanager_source.promotion_review.v1")

    def test_promotion_review_tracked_source_spec_keys(self) -> None:
        """TrackedSourceSpec must have stable key names."""
        spec = TrackedSourceSpec(
            endpoint_url="http://alertmanager:9093",
            identity_hash="hash123",
            cluster="prod",
            namespace="monitoring",
            name="alertmanager",
        )
        result = spec.to_dict()

        # Stable key names
        expected_keys = {"endpoint_url", "identity_hash", "cluster", "namespace", "name"}
        self.assertEqual(set(result.keys()), expected_keys)

    def test_promotion_review_promotion_risk_keys(self) -> None:
        """PromotionRisk must have stable key names."""
        risk = PromotionRisk(
            risk_id="duplicate_tracking",
            severity="warning",
            description="Endpoint already tracked",
            mitigation="Consider disabling existing source",
        )
        result = risk.to_dict()

        # Stable key names
        expected_keys = {"risk_id", "severity", "description", "mitigation"}
        self.assertEqual(set(result.keys()), expected_keys)

    def test_promotion_review_source_id_with_special_chars(self) -> None:
        """Source IDs with slash/URL-encoded chars must be preserved."""
        packet = AlertmanagerSourcePromotionReview(
            source_id="source/with/slash/and%20space",
            promotable=True,
        )
        result = packet.to_dict()

        self.assertEqual(result["source_id"], "source/with/slash/and%20space")

    def test_promotion_review_promotable_false(self) -> None:
        """Promotable false should be preserved."""
        packet = AlertmanagerSourcePromotionReview(
            source_id="test-source",
            promotable=False,
        )
        result = packet.to_dict()

        self.assertFalse(result["promotable"])

    def test_promotion_review_risks_list(self) -> None:
        """Risks must be a list, even when empty."""
        packet = AlertmanagerSourcePromotionReview(
            source_id="test",
            promotable=True,
            risks=(
                PromotionRisk(
                    risk_id="info_risk",
                    severity="info",
                    description="No issues found",
                ),
            ),
        )
        result = packet.to_dict()

        self.assertIsInstance(result["risks"], list)
        self.assertEqual(len(result["risks"]), 1)

    def test_promotion_review_redactions_policy(self) -> None:
        """Redactions must specify policy constants."""
        packet = AlertmanagerSourcePromotionReview(
            source_id="test",
            promotable=True,
        )
        result = packet.to_dict()

        self.assertIn("redactions", result)
        redactions = result["redactions"]
        self.assertEqual(redactions["alertmanager_config"], "sha256_only")
        self.assertEqual(redactions["annotations"], "secret_like_values_redacted")
        self.assertEqual(redactions["tokens"], "redacted")


class TestAlertmanagerSourcePromotionReviewRedaction(unittest.TestCase):
    """Redaction tests proving raw Alertmanager config is not emitted."""

    def test_will_create_does_not_contain_raw_config(self) -> None:
        """TrackedSourceSpec must not contain raw config data."""
        spec = TrackedSourceSpec(
            endpoint_url="http://alertmanager:9093",
            identity_hash="hash123",  # Only hash allowed
            cluster="prod",
            namespace="monitoring",
            name="alertmanager",
        )
        result = spec.to_dict()

        # Must not contain raw config keys
        forbidden_keys = {"config", "config_original", "raw_config"}
        for key in forbidden_keys:
            self.assertNotIn(key, result)

        # Only identity_hash is allowed
        self.assertIn("identity_hash", result)
        self.assertEqual(result["identity_hash"], "hash123")

    def test_redactions_prevent_raw_config_exposure(self) -> None:
        """Redactions must prevent raw config exposure."""
        packet = AlertmanagerSourcePromotionReview(
            source_id="test",
            promotable=True,
        )
        result = packet.to_dict()

        redactions = result["redactions"]
        # Config redaction must be sha256_only
        self.assertEqual(redactions["alertmanager_config"], "sha256_only")

    def test_no_config_fields_in_packet(self) -> None:
        """Promotion review packet must not have config-related fields."""
        packet = AlertmanagerSourcePromotionReview(
            source_id="test",
            promotable=True,
        )
        result = packet.to_dict()

        # Should not contain config fields
        for key in result.keys():
            self.assertNotIn("config", key.lower())


if __name__ == "__main__":
    unittest.main()
