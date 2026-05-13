"""Regression tests for "in-cluster" sanitization in review enrichment serialization.

These tests verify that internal context markers like "in-cluster" and "in_cluster"
do not leak into review enrichment operator-facing fields.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from k8s_diag_agent.ui.api_review_enrichment import (
    _is_safe_cluster_label,
    _sanitize_command_list,
    _sanitize_text_field,
    _serialize_review_enrichment,
)
from k8s_diag_agent.ui.model import ReviewEnrichmentView

# =============================================================================
# Tests for _is_safe_cluster_label
# =============================================================================


class TestIsSafeClusterLabel(unittest.TestCase):
    """Tests for _is_safe_cluster_label helper function."""

    def test_in_cluster_returns_false(self) -> None:
        """'in-cluster' is flagged as unsafe."""
        self.assertFalse(_is_safe_cluster_label("in-cluster"))

    def test_in_cluster_underscore_returns_false(self) -> None:
        """'in_cluster' is flagged as unsafe."""
        self.assertFalse(_is_safe_cluster_label("in_cluster"))

    def test_real_cluster_returns_true(self) -> None:
        """Real cluster names are flagged as safe."""
        self.assertTrue(_is_safe_cluster_label("prod-cluster"))
        self.assertTrue(_is_safe_cluster_label("staging-cluster"))
        self.assertTrue(_is_safe_cluster_label("rc-runity-test-msk1-c02"))

    def test_none_returns_true(self) -> None:
        """None returns True (no marker to filter)."""
        self.assertTrue(_is_safe_cluster_label(None))


# =============================================================================
# Tests for _sanitize_text_field
# =============================================================================


class TestSanitizeTextField(unittest.TestCase):
    """Tests for _sanitize_text_field helper function."""

    def test_in_cluster_in_text_replaced(self) -> None:
        """'in-cluster' in text is replaced with safe fallback."""
        result = _sanitize_text_field("in-cluster is in a degraded state")
        self.assertEqual(result, "the cluster is in a degraded state")

    def test_in_cluster_underscore_in_text_replaced(self) -> None:
        """'in_cluster' in text is replaced with safe fallback."""
        result = _sanitize_text_field("in_cluster needs attention")
        self.assertEqual(result, "the cluster needs attention")

    def test_real_cluster_in_text_preserved(self) -> None:
        """Real cluster names in text are preserved."""
        result = _sanitize_text_field("prod-cluster is degraded")
        self.assertEqual(result, "prod-cluster is degraded")

    def test_none_input_returns_none(self) -> None:
        """None input returns None."""
        result = _sanitize_text_field(None)
        self.assertIsNone(result)

    def test_empty_string_input_returns_empty(self) -> None:
        """Empty string input returns empty string."""
        result = _sanitize_text_field("")
        self.assertEqual(result, "")


# =============================================================================
# Tests for _sanitize_command_list
# =============================================================================


class TestSanitizeCommandList(unittest.TestCase):
    """Tests for _sanitize_command_list helper function."""

    def test_command_with_in_cluster_context_removed(self) -> None:
        """kubectl commands with --context in-cluster are sanitized."""
        commands = (
            "kubectl get pods --context in-cluster",
            "kubectl describe event --context in-cluster",
        )
        result = _sanitize_command_list(commands)
        self.assertEqual(len(result), 2)
        for cmd in result:
            self.assertNotIn("--context", cmd)
            self.assertNotIn("in-cluster", cmd)

    def test_command_with_in_cluster_equals_removed(self) -> None:
        """kubectl commands with --context=in-cluster are sanitized."""
        commands = (
            "kubectl get crd --context=in-cluster",
        )
        result = _sanitize_command_list(commands)
        self.assertEqual(len(result), 1)
        self.assertNotIn("--context", result[0])
        self.assertNotIn("in-cluster", result[0])

    def test_command_with_real_context_preserved(self) -> None:
        """kubectl commands with real --context are preserved."""
        commands = (
            "kubectl get pods --context prod-cluster",
        )
        result = _sanitize_command_list(commands)
        self.assertEqual(len(result), 1)
        self.assertIn("--context prod-cluster", result[0])

    def test_empty_tuple_returns_empty_list(self) -> None:
        """Empty tuple returns empty list."""
        result = _sanitize_command_list(())
        self.assertEqual(result, [])


# =============================================================================
# Tests for _serialize_review_enrichment with in-cluster data
# =============================================================================


class TestSerializeReviewEnrichmentSanitization(unittest.TestCase):
    """Tests that _serialize_review_enrichment sanitizes operator-facing fields."""

    def _make_review_enrichment_view(
        self,
        summary: str | None = None,
        next_checks: tuple[str, ...] = (),
        triage_order: tuple[str, ...] = (),
        top_concerns: tuple[str, ...] = (),
        evidence_gaps: tuple[str, ...] = (),
        focus_notes: tuple[str, ...] = (),
    ) -> ReviewEnrichmentView:
        """Create a ReviewEnrichmentView with test data."""
        return MagicMock(
            spec=ReviewEnrichmentView,
            status="success",
            provider="llamacpp",
            timestamp="2026-01-01T00:00:00Z",
            summary=summary,
            triage_order=triage_order,
            top_concerns=top_concerns,
            evidence_gaps=evidence_gaps,
            next_checks=next_checks,
            focus_notes=focus_notes,
            alertmanager_evidence_references=(),
            artifact_path="test-artifact.json",
            error_summary=None,
            skip_reason=None,
        )

    def test_summary_with_in_cluster_sanitized(self) -> None:
        """Summary containing 'in-cluster' is sanitized."""
        view = self._make_review_enrichment_view(
            summary="in-cluster is in a degraded state"
        )
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        self.assertNotIn("in-cluster", result["summary"])
        self.assertIn("the cluster", result["summary"])

    def test_summary_with_in_cluster_underscore_sanitized(self) -> None:
        """Summary containing 'in_cluster' is sanitized."""
        view = self._make_review_enrichment_view(
            summary="in_cluster needs attention"
        )
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        self.assertNotIn("in_cluster", result["summary"])

    def test_triage_order_with_in_cluster_sanitized(self) -> None:
        """TriageOrder containing 'in-cluster' is sanitized."""
        view = self._make_review_enrichment_view(
            triage_order=("in-cluster", "prod-cluster")
        )
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["triageOrder"]), 1)
        self.assertEqual(result["triageOrder"][0], "prod-cluster")

    def test_next_checks_with_in_cluster_context_removed(self) -> None:
        """nextChecks with --context in-cluster are sanitized."""
        view = self._make_review_enrichment_view(
            next_checks=(
                "kubectl get pods --context in-cluster",
                "kubectl describe event --context in-cluster",
                "kubectl get pods --context prod-cluster",
            )
        )
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        # All 3 commands are preserved, but internal contexts are removed
        self.assertEqual(len(result["nextChecks"]), 3)
        for cmd in result["nextChecks"]:
            self.assertNotIn("--context in-cluster", cmd)
            self.assertNotIn("--context=in-cluster", cmd)
        # Only the real context is preserved
        self.assertIn("prod-cluster", result["nextChecks"][2])

    def test_next_checks_with_in_cluster_equals_format_removed(self) -> None:
        """nextChecks with --context=in-cluster are sanitized."""
        view = self._make_review_enrichment_view(
            next_checks=(
                "kubectl get crd --context=in-cluster",
            )
        )
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        # Command is preserved but internal context is removed
        self.assertEqual(len(result["nextChecks"]), 1)
        self.assertNotIn("--context", result["nextChecks"][0])
        self.assertIn("kubectl get crd", result["nextChecks"][0])

    def test_top_concerns_with_in_cluster_sanitized(self) -> None:
        """topConcerns containing 'in-cluster' are sanitized."""
        view = self._make_review_enrichment_view(
            top_concerns=(
                "High latency in in-cluster",
                "Memory pressure in prod-cluster",
            )
        )
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["topConcerns"]), 2)
        # in-cluster reference should be replaced
        self.assertNotIn("in-cluster", result["topConcerns"][0])
        self.assertIn("the cluster", result["topConcerns"][0])
        # prod-cluster should be preserved
        self.assertIn("prod-cluster", result["topConcerns"][1])

    def test_real_summary_preserved(self) -> None:
        """Real cluster names in summary are preserved."""
        view = self._make_review_enrichment_view(
            summary="prod-eu-1 is in a degraded state"
        )
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        self.assertEqual(result["summary"], "prod-eu-1 is in a degraded state")

    def test_real_context_in_next_checks_preserved(self) -> None:
        """Real --context values in nextChecks are preserved."""
        view = self._make_review_enrichment_view(
            next_checks=(
                "kubectl get pods --context prod-cluster",
                "kubectl get crd --context=staging-cluster",
            )
        )
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["nextChecks"]), 2)
        self.assertIn("prod-cluster", result["nextChecks"][0])
        self.assertIn("staging-cluster", result["nextChecks"][1])

    def test_none_view_returns_none(self) -> None:
        """None input returns None."""
        result = _serialize_review_enrichment(None)
        self.assertIsNone(result)

    def test_text_field_command_context_removed(self) -> None:
        """Text fields with kubectl --context in-cluster are sanitized."""
        view = self._make_review_enrichment_view(
            top_concerns=("Run kubectl get pods --context in-cluster",),
            focus_notes=("Check kubectl describe event --context=in-cluster",),
        )
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        # Check entire payload for any leaked markers
        payload_str = str(result)
        self.assertNotIn("in-cluster", payload_str)
        self.assertNotIn("in_cluster", payload_str)
        self.assertNotIn("--context in-cluster", payload_str)
        self.assertNotIn("--context=in-cluster", payload_str)

    def test_error_summary_with_in_cluster_sanitized(self) -> None:
        """errorSummary containing 'in-cluster' is sanitized."""
        view = self._make_review_enrichment_view()
        view.error_summary = "Failed to connect to in-cluster"
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        self.assertNotIn("in-cluster", result["errorSummary"])
        self.assertIn("the cluster", result["errorSummary"])

    def test_skip_reason_with_in_cluster_sanitized(self) -> None:
        """skipReason containing 'in-cluster' is sanitized."""
        view = self._make_review_enrichment_view()
        view.skip_reason = "Skipped in-cluster check"
        result = _serialize_review_enrichment(view)
        self.assertIsNotNone(result)
        self.assertNotIn("in-cluster", result["skipReason"])


if __name__ == "__main__":
    unittest.main()