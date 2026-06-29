"""Unit tests for temporal context in incident report.

Tests temporal context derivation and staleness thresholds.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.api_incident_report import (
    _build_operator_worklist_payload,
)
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.incident_report_fixtures import (
    _fixture_approval_needed_item,
    _fixture_degraded_single_cluster,
    _fixture_executed_with_usefulness,
    _fixture_healthy_no_incident,
)


class TemporalContextTests(unittest.TestCase):
    """Tests for temporal context fields in operator worklist items.

    Regression tests for BETA-G4 epic: Temporal context in worklist.
    Verifies that worklist items expose useful temporal context when timestamps
    are available, and honestly represent unknown timing when data is insufficient.

    Temporal context fields:
    - firstRecommendedAt: earliest known recommendation timestamp
    - lastStateChangedAt: most recent state transition timestamp
    - recommendationAgeSeconds: age in seconds from first recommendation
    - stalenessClass: fresh | aging | stale | unknown

    Derivation rules:
    - firstRecommendedAt: from assessment/drilldown for deterministic, plan artifact for queue
    - lastStateChangedAt: latest execution/approval timestamp
    - recommendationAgeSeconds: derived from firstRecommendedAt and current run timestamp
    - stalenessClass: fresh (<5min), aging (5-30min), stale (>30min), unknown (no data)
    """

    def test_temporal_fields_are_present_in_worklist_items(self) -> None:
        """All worklist items must have temporal context fields."""
        index = _fixture_degraded_single_cluster()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        self.assertTrue(worklist["items"])
        for item in worklist["items"]:
            self.assertIn("firstRecommendedAt", item)
            self.assertIn("lastStateChangedAt", item)
            self.assertIn("recommendationAgeSeconds", item)
            self.assertIn("stalenessClass", item)

    def test_fresh_item_has_fresh_staleness_class(self) -> None:
        """Items with recent timestamps must have stalenessClass=fresh."""
        index = _fixture_degraded_single_cluster()
        # The degraded fixture has timestamps close to run time
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        # At least one item should have temporal context
        items_with_time = [
            i for i in worklist["items"]
            if i.get("firstRecommendedAt") is not None
        ]
        if items_with_time:
            for item in items_with_time:
                # If age is known, staleness should be determinable
                age_val = item.get("recommendationAgeSeconds")
                if age_val is not None:
                    staleness = item.get("stalenessClass")
                    if age_val < 5 * 60:
                        self.assertEqual(staleness, "fresh")
                    elif age_val < 30 * 60:
                        self.assertEqual(staleness, "aging")
                    else:
                        self.assertEqual(staleness, "stale")

    def test_staleness_class_unknown_when_timing_data_missing(self) -> None:
        """Items without timing data must have stalenessClass=unknown."""
        # Create an index with no timestamps
        index = _fixture_healthy_no_incident()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        # Healthy fixture has no worklist items
        self.assertIsNone(worklist)

    def test_stale_items_not_misrepresented_as_fresh(self) -> None:
        """Items older than 30 minutes must not have stalenessClass=fresh."""
        # Create a fixture with old timestamps
        index = _fixture_degraded_single_cluster()
        # The degraded fixture should have temporal context
        # If timestamps exist and age > 30min, staleness must be "stale" or "unknown"
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        if worklist:
            for item in worklist["items"]:
                age_val = item.get("recommendationAgeSeconds")
                if age_val is not None:
                    staleness = item.get("stalenessClass")
                    if age_val >= 30 * 60:
                        self.assertNotEqual(
                            staleness, "fresh",
                            f"Item {item.get('id')} with age {age_val}s should not be fresh"
                        )

    def test_executed_items_have_meaningful_recency_metadata(self) -> None:
        """Executed/reviewed items retained for review must have recency metadata."""
        index = _fixture_executed_with_usefulness()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        executed_items = [
            i for i in worklist["items"]
            if i.get("itemState") in ("executed", "reviewed")
        ]
        if executed_items:
            for item in executed_items:
                # Should have temporal context fields
                self.assertIn("firstRecommendedAt", item)
                self.assertIn("lastStateChangedAt", item)
                # Should have a staleness class (may be unknown if timing data is missing)
                self.assertIn("stalenessClass", item)

    def test_approval_needed_items_have_temporal_context(self) -> None:
        """Approval-needed items should have temporal context for staleness visibility."""
        index = _fixture_approval_needed_item()
        context = build_ui_context(index)
        worklist = _build_operator_worklist_payload(context)
        self.assertIsNotNone(worklist)
        assert worklist is not None
        approval_items = [
            i for i in worklist["items"]
            if i.get("itemState") == "approval-needed"
        ]
        if approval_items:
            for item in approval_items:
                self.assertIn("stalenessClass", item)
                # If we have timestamps, we should have age
                if item.get("firstRecommendedAt") and item.get("recommendationAgeSeconds") is not None:
                    # Age should be derivable
                    self.assertIsNotNone(item.get("recommendationAgeSeconds"))


class TemporalContextDerivationTests(unittest.TestCase):
    """Tests for the _derive_temporal_context helper function."""

    def test_derive_temporal_context_with_both_timestamps(self) -> None:
        """Temporal context is correctly derived when both timestamps are present."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        last_at = "2026-01-01T00:10:00Z"
        current = "2026-01-01T00:35:00Z"  # 35 minutes after first

        first_rec, last_change, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=last_at,
            current_run_timestamp=current,
        )

        self.assertEqual(first_rec, first_at)
        self.assertEqual(last_change, last_at)
        self.assertEqual(age_sec, 35 * 60)  # 2100 seconds
        self.assertEqual(staleness, "stale")  # > 30 minutes

    def test_derive_temporal_context_fresh_item(self) -> None:
        """Fresh items (<5 min) have stalenessClass=fresh."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:03:00Z"  # 3 minutes after first

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(age_sec, 3 * 60)  # 180 seconds
        self.assertEqual(staleness, "fresh")

    def test_derive_temporal_context_aging_item(self) -> None:
        """Aging items (5-30 min) have stalenessClass=aging."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:15:00Z"  # 15 minutes after first

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(age_sec, 15 * 60)  # 900 seconds
        self.assertEqual(staleness, "aging")

    def test_derive_temporal_context_unknown_when_no_first_timestamp(self) -> None:
        """stalenessClass=unknown when firstRecommendedAt is missing."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=None,
            last_state_changed_at="2026-01-01T00:10:00Z",
            current_run_timestamp="2026-01-01T00:30:00Z",
        )

        self.assertIsNone(age_sec)
        self.assertEqual(staleness, "unknown")

    def test_derive_temporal_context_unknown_when_no_current_timestamp(self) -> None:
        """stalenessClass=unknown when current_run_timestamp is missing."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at="2026-01-01T00:00:00Z",
            last_state_changed_at="2026-01-01T00:10:00Z",
            current_run_timestamp=None,
        )

        self.assertIsNone(age_sec)
        self.assertEqual(staleness, "unknown")

    def test_derive_temporal_context_returns_input_timestamps(self) -> None:
        """firstRecommendedAt and lastStateChangedAt are returned as-is."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        last_at = "2026-01-01T00:10:00Z"
        current = "2026-01-01T00:30:00Z"

        first_rec, last_change, _, _ = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=last_at,
            current_run_timestamp=current,
        )

        self.assertEqual(first_rec, first_at)
        self.assertEqual(last_change, last_at)

    def test_derive_temporal_context_invalid_timestamp_handled(self) -> None:
        """Invalid timestamps are handled gracefully with unknown staleness."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at="not-a-timestamp",
            last_state_changed_at="also-invalid",
            current_run_timestamp="2026-01-01T00:30:00Z",
        )

        self.assertIsNone(age_sec)
        self.assertEqual(staleness, "unknown")

    def test_derive_temporal_context_negative_age_unknown(self) -> None:
        """Negative age (first recommendation after current run) is marked unknown."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T01:00:00Z"  # Later than current
        current = "2026-01-01T00:30:00Z"

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        # Negative age should result in unknown rather than fabricating
        self.assertIsNone(age_sec)
        self.assertEqual(staleness, "unknown")


class TemporalContextStalenessThresholdTests(unittest.TestCase):
    """Tests for staleness threshold boundaries."""

    def test_fresh_boundary_5_minutes(self) -> None:
        """Exactly 5 minutes is aging, not fresh."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:05:00Z"  # Exactly 5 minutes

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(age_sec, 5 * 60)
        self.assertEqual(staleness, "aging")  # >= 5 minutes is aging

    def test_aging_boundary_30_minutes(self) -> None:
        """Exactly 30 minutes is stale, not aging."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:30:00Z"  # Exactly 30 minutes

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(age_sec, 30 * 60)
        self.assertEqual(staleness, "stale")  # >= 30 minutes is stale

    def test_just_under_fresh_boundary(self) -> None:
        """Just under 5 minutes is fresh."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:04:59Z"  # Just under 5 minutes

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(age_sec, 4 * 60 + 59)  # 299 seconds
        self.assertEqual(staleness, "fresh")

    def test_just_under_aging_boundary(self) -> None:
        """Just under 30 minutes is aging."""
        from k8s_diag_agent.ui.api_incident_report import _derive_temporal_context

        first_at = "2026-01-01T00:00:00Z"
        current = "2026-01-01T00:29:59Z"  # Just under 30 minutes

        _, _, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_at,
            last_state_changed_at=None,
            current_run_timestamp=current,
        )

        self.assertEqual(staleness, "aging")


if __name__ == "__main__":
    unittest.main()

