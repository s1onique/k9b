"""Tests for artifact_id field in HealthReviewArtifact.

Design:
- artifact_id is None for legacy artifacts (deserialized from files without it)
- artifact_id is auto-generated for NEW reviews created via build_health_review()
- artifact_id is preserved when deserializing artifacts that already have it
- Direct HealthReviewArtifact() construction does NOT auto-generate artifact_id
  (use build_health_review() for new reviews)
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.health.review_feedback import (
    DrilldownSelection,
    HealthReviewArtifact,
    build_health_review,
)


def _minimal_drilldown() -> DrilldownSelection:
    """Create a minimal DrilldownSelection for testing."""
    return DrilldownSelection(
        label="cluster-a",
        context="cluster-a",
        reasons=("warning_event_threshold",),
        warning_event_count=10,
        non_running_pod_count=2,
        severity=4,
        missing_evidence=(),
    )


class TestReviewArtifactIdFactoryFunction(unittest.TestCase):
    """Tests for artifact_id in reviews generated via factory function."""

    def test_build_health_review_includes_artifact_id(self) -> None:
        """build_health_review should create reviews with artifact_id."""
        review = build_health_review(
            run_id="run-1",
            assessments=[],
            drilldowns=[],
            warning_threshold=5,
        )
        assert review.artifact_id is not None
        self.assertIsInstance(review.artifact_id, str)
        self.assertGreater(len(review.artifact_id), 0)

    def test_build_health_review_artifact_id_uuid_format(self) -> None:
        """Generated artifact_id should be UUID-like format."""
        review = build_health_review(
            run_id="run-1",
            assessments=[],
            drilldowns=[],
        )
        aid = review.artifact_id
        assert aid is not None
        parts = aid.split("-")
        self.assertEqual(len(parts), 5)
        self.assertEqual(len(parts[0]), 8)
        self.assertEqual(len(parts[1]), 4)
        self.assertEqual(len(parts[2]), 4)
        self.assertEqual(len(parts[3]), 4)
        self.assertEqual(len(parts[4]), 12)

    def test_build_health_review_includes_artifact_id_not_empty(self) -> None:
        """artifact_id should not be empty string."""
        review = build_health_review(
            run_id="run-1",
            assessments=[],
            drilldowns=[],
            warning_threshold=5,
        )
        assert review.artifact_id is not None
        self.assertGreater(len(review.artifact_id), 0)

    def test_build_health_review_artifact_ids_unique(self) -> None:
        """Each generated review should have a unique artifact_id."""
        reviews = [
            build_health_review(run_id=f"run-{i}", assessments=[], drilldowns=[])
            for i in range(10)
        ]
        ids = {r.artifact_id for r in reviews}
        self.assertEqual(len(ids), len(reviews), "All artifact_ids should be unique")


class TestReviewArtifactIdSerialization(unittest.TestCase):
    """Tests for artifact_id serialization/deserialization."""

    def test_to_dict_includes_artifact_id_when_present(self) -> None:
        """to_dict should serialize artifact_id when present."""
        review = HealthReviewArtifact(
            run_id="run-1",
            timestamp=datetime.now(UTC),
            selected_drilldowns=(),
            quality_summary=(),
            failure_modes=(),
            proposed_improvements=(),
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        result = review.to_dict()
        self.assertIn("artifact_id", result)
        self.assertEqual(result["artifact_id"], "0192a1b8-3c4e-5678-abcd-1234567890ab")

    def test_from_dict_preserves_artifact_id(self) -> None:
        """from_dict should parse and preserve artifact_id."""
        raw = {
            "run_id": "run-1",
            "timestamp": datetime.now(UTC).isoformat(),
            "review_version": "health-review:v1",
            "selected_drilldowns": [],
            "quality_summary": [],
            "failure_modes": [],
            "proposed_improvements": [],
            "artifact_id": "0192a1b8-3c4e-5678-abcd-1234567890ab",
        }
        review = HealthReviewArtifact.from_dict(raw)
        self.assertEqual(review.artifact_id, "0192a1b8-3c4e-5678-abcd-1234567890ab")

    def test_from_dict_missing_artifact_id_returns_none(self) -> None:
        """Legacy artifacts without artifact_id should deserialize with None."""
        raw = {
            "run_id": "run-1",
            "timestamp": datetime.now(UTC).isoformat(),
            "review_version": "health-review:v1",
            "selected_drilldowns": [],
            "quality_summary": [],
            "failure_modes": [],
            "proposed_improvements": [],
            # No artifact_id field
        }
        review = HealthReviewArtifact.from_dict(raw)
        self.assertIsNone(review.artifact_id)

    def test_roundtrip_preserves_artifact_id(self) -> None:
        """Roundtrip serialization should preserve artifact_id."""
        original = HealthReviewArtifact(
            run_id="run-1",
            timestamp=datetime.now(UTC),
            selected_drilldowns=(),
            quality_summary=(),
            failure_modes=(),
            proposed_improvements=(),
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        serialized = original.to_dict()
        restored = HealthReviewArtifact.from_dict(serialized)
        self.assertEqual(restored.artifact_id, original.artifact_id)

    def test_legacy_review_to_dict_excludes_artifact_id(self) -> None:
        """Legacy reviews (without artifact_id) should not include it in to_dict."""
        raw = {
            "run_id": "run-1",
            "timestamp": datetime.now(UTC).isoformat(),
            "review_version": "health-review:v1",
            "selected_drilldowns": [],
            "quality_summary": [],
            "failure_modes": [],
            "proposed_improvements": [],
            # No artifact_id field
        }
        review = HealthReviewArtifact.from_dict(raw)
        # artifact_id should be None for legacy reviews
        self.assertIsNone(review.artifact_id)
        # to_dict should NOT include artifact_id when it's None
        result = review.to_dict()
        self.assertNotIn("artifact_id", result)


class TestReviewArtifactIdSeparation(unittest.TestCase):
    """Tests ensuring artifact_id stays distinct from other identifiers."""

    def test_artifact_id_distinct_from_run_id(self) -> None:
        """artifact_id must remain distinct from run_id."""
        review = HealthReviewArtifact(
            run_id="run-1",
            timestamp=datetime.now(UTC),
            selected_drilldowns=(),
            quality_summary=(),
            failure_modes=(),
            proposed_improvements=(),
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        self.assertNotEqual(review.artifact_id, review.run_id)

    def test_explicit_artifact_id_preserved(self) -> None:
        """Explicit artifact_id should be preserved (not overwritten)."""
        explicit_id = "0192a1b8-3c4e-5678-abcd-1234567890ab"
        review = HealthReviewArtifact(
            run_id="run-1",
            timestamp=datetime.now(UTC),
            selected_drilldowns=(),
            quality_summary=(),
            failure_modes=(),
            proposed_improvements=(),
            artifact_id=explicit_id,
        )
        self.assertEqual(review.artifact_id, explicit_id)
        result = review.to_dict()
        self.assertEqual(result["artifact_id"], explicit_id)

    def test_direct_construction_without_artifact_id(self) -> None:
        """Direct construction without artifact_id should leave it as None."""
        review = HealthReviewArtifact(
            run_id="run-1",
            timestamp=datetime.now(UTC),
            selected_drilldowns=(),
            quality_summary=(),
            failure_modes=(),
            proposed_improvements=(),
        )
        self.assertIsNone(review.artifact_id)


class TestReviewArtifactIdWithDrilldowns(unittest.TestCase):
    """Tests for artifact_id with drilldown content."""

    def test_review_with_drilldowns_includes_artifact_id(self) -> None:
        """Review with drilldowns should have artifact_id."""
        from unittest.mock import MagicMock

        # Create a mock drilldown artifact
        drilldown = MagicMock()
        drilldown.context = "cluster-a"
        drilldown.label = "cluster-a"
        drilldown.trigger_reasons = ("warning_event_threshold",)
        drilldown.missing_evidence = ()
        drilldown.warning_events = []
        drilldown.non_running_pods = []

        review = build_health_review(
            run_id="run-1",
            assessments=[],
            drilldowns=[drilldown],
            warning_threshold=5,
        )
        assert review.artifact_id is not None
        self.assertIsNotNone(review.artifact_id)
        self.assertGreater(len(review.artifact_id), 0)

    def test_review_selected_drilldowns_preserved_with_artifact_id(self) -> None:
        """Selected drilldowns should be preserved alongside artifact_id."""
        selection = _minimal_drilldown()
        review = HealthReviewArtifact(
            run_id="run-1",
            timestamp=datetime.now(UTC),
            selected_drilldowns=(selection,),
            quality_summary=(),
            failure_modes=(),
            proposed_improvements=(),
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        self.assertEqual(len(review.selected_drilldowns), 1)
        self.assertEqual(review.selected_drilldowns[0].label, "cluster-a")
        self.assertEqual(review.artifact_id, "0192a1b8-3c4e-5678-abcd-1234567890ab")


if __name__ == "__main__":
    unittest.main()
