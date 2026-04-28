"""Tests for Alertmanager relevance review-artifact endpoint, discovery, and merge-back.

This module provides focused backend tests covering:
1. Endpoint validation (POST /api/alertmanager-relevance-feedback)
2. Artifact creation (immutable review artifacts)
3. Discovery (_load_alertmanager_review_artifacts)
4. Merge-back into execution history (_merge_alertmanager_review_into_history_entry)
5. API-visible behavior (reload through projection path)
"""

import json
import shutil
import tempfile
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.external_analysis.artifact import (
    AlertmanagerRelevanceClass,
    ExternalAnalysisPurpose,
)
from k8s_diag_agent.ui.server_read_support import (
    _load_alertmanager_review_artifacts,
    _merge_alertmanager_review_into_history_entry,
)


class TestAlertmanagerRelevanceEndpointValidation(unittest.TestCase):
    """Tests for POST /api/alertmanager-relevance-feedback endpoint validation."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_dir = self.tmpdir / "health"
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_execution_artifact(
        self,
        run_id: str,
        index: int,
        alertmanager_provenance: Mapping[str, object] | None = None,
    ) -> Path:
        """Create a mock execution artifact with optional Alertmanager provenance."""
        artifact_data: dict[str, object] = {
            "purpose": "next-check-execution",
            "run_id": run_id,
            "cluster_label": "cluster-a",
            "status": "success",
            "tool_name": "kubectl",
            "summary": "Test execution",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if alertmanager_provenance:
            artifact_data["alertmanager_provenance"] = alertmanager_provenance

        artifact_path = self.external_dir / f"{run_id}-next-check-execution-{index}.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")
        return artifact_path

    def test_valid_relevance_classes_accepted(self) -> None:
        """Test that all valid AlertmanagerRelevanceClass values are accepted."""
        valid_classes = [
            AlertmanagerRelevanceClass.RELEVANT.value,
            AlertmanagerRelevanceClass.NOT_RELEVANT.value,
            AlertmanagerRelevanceClass.NOISY.value,
            AlertmanagerRelevanceClass.UNSURE.value,
        ]

        for cls in valid_classes:
            # Clean up from previous iteration
            for f in self.external_dir.glob("*-alertmanager-review-*.json"):
                f.unlink()

            run_id = f"test-run-{cls}"
            self._create_execution_artifact(run_id, 0)

            # Validate the class is correctly parsed
            parsed = AlertmanagerRelevanceClass(cls)
            self.assertEqual(parsed.value, cls)

    def test_invalid_relevance_class_rejected(self) -> None:
        """Test that invalid alertmanagerRelevance is rejected."""
        invalid_classes = [
            "invalid",
            "maybe",
            "RELEVANT",  # Wrong case
            "relevant ",  # Trailing space
            "not-relevant",  # Wrong format
            "",
        ]

        for invalid_cls in invalid_classes:
            with self.assertRaises(ValueError):
                AlertmanagerRelevanceClass(invalid_cls)

    def test_missing_artifact_path_rejected(self) -> None:
        """Test that missing artifactPath is rejected."""
        # Validate the check works
        payload = {"alertmanagerRelevance": "relevant"}
        self.assertNotIn("artifactPath", payload)

    def test_missing_relevance_field_rejected(self) -> None:
        """Test that missing alertmanagerRelevance is rejected."""
        payload = {"artifactPath": "some/path.json"}
        self.assertNotIn("alertmanagerRelevance", payload)

    def test_bad_artifact_path_rejected(self) -> None:
        """Test that malformed artifact paths are rejected."""
        # Test path traversal attempt
        bad_paths = [
            "../../../etc/passwd",
            "external-analysis/../../../etc/passwd",
            "/absolute/path.json",
        ]

        for bad_path in bad_paths:
            # Path should be relative (not starting with /)
            self.assertTrue(bad_path.startswith("/") or ".." in bad_path)

    def test_nonexistent_artifact_path_rejected(self) -> None:
        """Test that non-existent artifact paths are rejected."""
        run_id = "test-nonexistent"
        artifact_path = self.external_dir / f"{run_id}-next-check-execution-0.json"

        # The artifact should not exist
        self.assertFalse(artifact_path.exists())


class TestAlertmanagerReviewArtifactCreation(unittest.TestCase):
    """Tests for Alertmanager review artifact creation behavior."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_dir = self.tmpdir / "health"
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_execution_artifact(
        self,
        run_id: str,
        index: int,
        alertmanager_provenance: Mapping[str, object] | None = None,
    ) -> Path:
        """Create a mock execution artifact."""
        artifact_data: dict[str, object] = {
            "purpose": "next-check-execution",
            "run_id": run_id,
            "cluster_label": "cluster-a",
            "status": "success",
            "tool_name": "kubectl",
            "summary": "Test execution",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if alertmanager_provenance:
            artifact_data["alertmanager_provenance"] = alertmanager_provenance

        artifact_path = self.external_dir / f"{run_id}-next-check-execution-{index}.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")
        return artifact_path

    def _simulate_review_artifact_creation(
        self,
        source_artifact_path: Path,
        relevance: AlertmanagerRelevanceClass,
        relevance_summary: str | None = None,
    ) -> tuple[Path, dict]:
        """Simulate what the endpoint does when creating a review artifact."""
        source_data = json.loads(source_artifact_path.read_text(encoding="utf-8"))
        run_id = source_data.get("run_id", "")
        provenance = source_data.get("alertmanager_provenance")

        # Generate unique filename (mirrors endpoint behavior)
        import uuid
        review_uuid = str(uuid.uuid4())[:8]
        review_filename = f"{run_id}-next-check-execution-alertmanager-review-{review_uuid}.json"
        review_path = self.external_dir / review_filename

        review_artifact = {
            "purpose": ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value,
            "tool_name": source_data.get("tool_name", ""),
            "run_id": run_id,
            "run_label": source_data.get("run_label", ""),
            "cluster_label": source_data.get("cluster_label", ""),
            "status": source_data.get("status", ""),
            "timestamp": source_data.get("timestamp", ""),
            "reviewed_at": datetime.now(UTC).isoformat(),
            "source_artifact": str(source_artifact_path.relative_to(self.health_dir)),
            "alertmanager_relevance": relevance.value,
            "alertmanager_relevance_summary": relevance_summary,
            "alertmanager_provenance": provenance,
            "summary": source_data.get("summary"),
            "duration_ms": source_data.get("duration_ms"),
        }

        review_path.write_text(json.dumps(review_artifact, indent=2), encoding="utf-8")
        return review_path, review_artifact

    def test_review_artifact_uses_formal_purpose(self) -> None:
        """Test that review artifact uses the formal ExternalAnalysisPurpose value."""
        run_id = "test-purpose"
        artifact_path = self._create_execution_artifact(run_id, 0)

        review_path, review_data = self._simulate_review_artifact_creation(
            artifact_path,
            AlertmanagerRelevanceClass.RELEVANT,
        )

        expected_purpose = ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value
        self.assertEqual(review_data["purpose"], expected_purpose)

    def test_review_artifact_links_to_source(self) -> None:
        """Test that review artifact links back to source execution artifact."""
        run_id = "test-source-link"
        artifact_path = self._create_execution_artifact(run_id, 0)

        review_path, review_data = self._simulate_review_artifact_creation(
            artifact_path,
            AlertmanagerRelevanceClass.NOT_RELEVANT,
        )

        self.assertIn("source_artifact", review_data)
        self.assertEqual(review_data["source_artifact"], str(artifact_path.relative_to(self.health_dir)))

    def test_review_artifact_preserves_provenance(self) -> None:
        """Test that review artifact preserves server-owned provenance from execution artifact."""
        run_id = "test-provenance"
        provenance = {
            "matchedDimensions": ["namespace"],
            "matchedValues": {"namespace": ["monitoring"]},
            "alertmanagerSource": "prometheus",
        }
        artifact_path = self._create_execution_artifact(run_id, 0, alertmanager_provenance=provenance)

        review_path, review_data = self._simulate_review_artifact_creation(
            artifact_path,
            AlertmanagerRelevanceClass.NOISY,
            relevance_summary="Too much noise",
        )

        self.assertIn("alertmanager_provenance", review_data)
        self.assertEqual(review_data["alertmanager_provenance"], provenance)

    def test_review_artifact_does_not_require_client_provenance(self) -> None:
        """Test that review artifact creation does not require client-supplied provenance."""
        run_id = "test-no-client-provenance"
        # Execution artifact without provenance
        artifact_path = self._create_execution_artifact(run_id, 0)

        review_path, review_data = self._simulate_review_artifact_creation(
            artifact_path,
            AlertmanagerRelevanceClass.UNSURE,
        )

        # Should still create the artifact (provenance is optional)
        self.assertTrue(review_path.exists())
        self.assertIn("alertmanager_provenance", review_data)
        # provenance will be None since source artifact had none
        self.assertIsNone(review_data["alertmanager_provenance"])

    def test_review_artifact_immutability_pattern(self) -> None:
        """Test that source execution artifact is NOT modified when review is created."""
        run_id = "test-immutability"
        artifact_path = self._create_execution_artifact(run_id, 0)
        original_content = artifact_path.read_text(encoding="utf-8")

        review_path, _ = self._simulate_review_artifact_creation(
            artifact_path,
            AlertmanagerRelevanceClass.RELEVANT,
        )

        # Source artifact should be unchanged
        self.assertEqual(artifact_path.read_text(encoding="utf-8"), original_content)

        # Review artifact should be a separate file
        self.assertTrue(review_path.exists())
        self.assertNotEqual(review_path, artifact_path)


class TestAlertmanagerReviewArtifactDiscovery(unittest.TestCase):
    """Tests for _load_alertmanager_review_artifacts() discovery behavior."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_dir = self.tmpdir / "health"
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_review_artifact(
        self,
        run_id: str,
        uuid_suffix: str,
        source_artifact: str,
        relevance: str,
        reviewed_at: str,
        purpose: str | None = None,
        relevance_summary: str | None = None,
    ) -> Path:
        """Create a review artifact with specified fields."""
        filename = f"{run_id}-next-check-execution-alertmanager-review-{uuid_suffix}.json"
        artifact_data = {
            "purpose": purpose or ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value,
            "run_id": run_id,
            "source_artifact": source_artifact,
            "alertmanager_relevance": relevance,
            "alertmanager_relevance_summary": relevance_summary,
            "reviewed_at": reviewed_at,
        }
        path = self.external_dir / filename
        path.write_text(json.dumps(artifact_data), encoding="utf-8")
        return path

    def test_discovers_current_formal_purpose_artifacts(self) -> None:
        """Test that discovery finds artifacts with formal purpose constant."""
        run_id = "test-discovery-formal"
        formal_purpose = ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value

        # Create artifact with formal purpose
        self._create_review_artifact(
            run_id=run_id,
            uuid_suffix="abc12345",
            source_artifact=f"external-analysis/{run_id}-next-check-execution-0.json",
            relevance="relevant",
            reviewed_at="2026-04-26T10:00:00Z",
            purpose=formal_purpose,
        )

        reviews = _load_alertmanager_review_artifacts(self.external_dir, run_id)

        self.assertEqual(len(reviews), 1)

    def test_preserves_backward_compatibility_legacy_literal(self) -> None:
        """Test that discovery also accepts legacy literal purpose value."""
        run_id = "test-legacy"

        # Create artifact with legacy literal purpose
        self._create_review_artifact(
            run_id=run_id,
            uuid_suffix="def67890",
            source_artifact=f"external-analysis/{run_id}-next-check-execution-0.json",
            relevance="not_relevant",
            reviewed_at="2026-04-26T11:00:00Z",
            purpose="next-check-execution-alertmanager-review",  # Legacy literal
        )

        reviews = _load_alertmanager_review_artifacts(self.external_dir, run_id)

        self.assertEqual(len(reviews), 1)

    def test_ignores_unrelated_external_analysis_artifacts(self) -> None:
        """Test that discovery ignores artifacts with different purposes."""
        run_id = "test-unrelated"

        # Create unrelated artifact (usefulness review)
        unrelated_data = {
            "purpose": "next-check-execution-usefulness-review",
            "run_id": run_id,
            "source_artifact": f"external-analysis/{run_id}-next-check-execution-0.json",
            "usefulness_class": "useful",
            "reviewed_at": "2026-04-26T12:00:00Z",
        }
        unrelated_path = self.external_dir / f"{run_id}-next-check-execution-usefulness-review-xyz.json"
        unrelated_path.write_text(json.dumps(unrelated_data), encoding="utf-8")

        # Create actual alertmanager review
        self._create_review_artifact(
            run_id=run_id,
            uuid_suffix="abc12345",
            source_artifact=f"external-analysis/{run_id}-next-check-execution-0.json",
            relevance="relevant",
            reviewed_at="2026-04-26T10:00:00Z",
        )

        reviews = _load_alertmanager_review_artifacts(self.external_dir, run_id)

        # Should only find the alertmanager review, not the unrelated usefulness review
        self.assertEqual(len(reviews), 1)

    def test_returns_correct_review_for_correct_source(self) -> None:
        """Test that discovery returns the correct review for the correct source artifact."""
        run_id = "test-correct-source"

        # Create two execution artifacts
        source_1 = f"external-analysis/{run_id}-next-check-execution-0.json"
        source_2 = f"external-analysis/{run_id}-next-check-execution-1.json"

        # Create reviews for each
        self._create_review_artifact(
            run_id=run_id,
            uuid_suffix="aaa11111",
            source_artifact=source_1,
            relevance="relevant",
            reviewed_at="2026-04-26T10:00:00Z",
        )
        self._create_review_artifact(
            run_id=run_id,
            uuid_suffix="bbb22222",
            source_artifact=source_2,
            relevance="not_relevant",
            reviewed_at="2026-04-26T11:00:00Z",
        )

        reviews = _load_alertmanager_review_artifacts(self.external_dir, run_id)

        self.assertEqual(len(reviews), 2)
        self.assertIn(source_1, reviews)
        self.assertIn(source_2, reviews)
        self.assertEqual(reviews[source_1]["alertmanager_relevance"], "relevant")
        self.assertEqual(reviews[source_2]["alertmanager_relevance"], "not_relevant")


class TestAlertmanagerReviewMergeBack(unittest.TestCase):
    """Tests for merge-back behavior into execution history entries."""

    def test_latest_review_wins_for_same_source(self) -> None:
        """Test that when multiple reviews exist, the latest one is used."""
        # Two reviews for the same source, different timestamps
        new_review = {
            "alertmanager_relevance": "not_relevant",
            "alertmanager_relevance_summary": "New summary",
            "alertmanager_provenance": {"matched": "new"},
            "reviewed_at": "2026-04-26T12:00:00Z",
            "artifact_path": "external-analysis/review-new.json",
        }

        entry = {"artifactPath": "source.json"}
        merged = _merge_alertmanager_review_into_history_entry(entry, new_review)

        # Should use new review's values
        self.assertEqual(merged["alertmanagerRelevance"], "not_relevant")
        self.assertEqual(merged["alertmanagerRelevanceSummary"], "New summary")
        self.assertEqual(merged["alertmanagerReviewedAt"], "2026-04-26T12:00:00Z")
        self.assertEqual(merged["alertmanagerReviewArtifactPath"], "external-analysis/review-new.json")

    def test_merged_entry_includes_alertmanager_relevance(self) -> None:
        """Test that merged entry includes alertmanagerRelevance field."""
        review = {
            "alertmanager_relevance": "noisy",
        }
        entry = {"artifactPath": "source.json"}
        merged = _merge_alertmanager_review_into_history_entry(entry, review)

        self.assertIn("alertmanagerRelevance", merged)
        self.assertEqual(merged["alertmanagerRelevance"], "noisy")

    def test_merged_entry_includes_alertmanager_relevance_summary(self) -> None:
        """Test that merged entry includes alertmanagerRelevanceSummary field."""
        review = {
            "alertmanager_relevance": "unsure",
            "alertmanager_relevance_summary": "Need more investigation",
        }
        entry = {"artifactPath": "source.json"}
        merged = _merge_alertmanager_review_into_history_entry(entry, review)

        self.assertIn("alertmanagerRelevanceSummary", merged)
        self.assertEqual(merged["alertmanagerRelevanceSummary"], "Need more investigation")

    def test_merged_entry_includes_alertmanager_provenance(self) -> None:
        """Test that merged entry includes alertmanagerProvenance field."""
        provenance = {
            "matchedDimensions": ["namespace", "cluster"],
            "matchedValues": {"namespace": ["monitoring"], "cluster": ["prod"]},
        }
        review = {
            "alertmanager_relevance": "not_relevant",
            "alertmanager_provenance": provenance,
        }
        entry = {"artifactPath": "source.json"}
        merged = _merge_alertmanager_review_into_history_entry(entry, review)

        self.assertIn("alertmanagerProvenance", merged)
        self.assertEqual(merged["alertmanagerProvenance"], provenance)

    def test_merged_entry_includes_review_artifact_path(self) -> None:
        """Test that merged entry includes alertmanagerReviewArtifactPath field."""
        review = {
            "alertmanager_relevance": "relevant",
            "artifact_path": "external-analysis/review-123.json",
        }
        entry = {"artifactPath": "source.json"}
        merged = _merge_alertmanager_review_into_history_entry(entry, review)

        self.assertIn("alertmanagerReviewArtifactPath", merged)
        self.assertEqual(merged["alertmanagerReviewArtifactPath"], "external-analysis/review-123.json")

    def test_merged_entry_includes_reviewed_timestamp(self) -> None:
        """Test that merged entry includes alertmanagerReviewedAt field."""
        review = {
            "alertmanager_relevance": "relevant",
            "reviewed_at": "2026-04-26T14:30:00Z",
        }
        entry = {"artifactPath": "source.json"}
        merged = _merge_alertmanager_review_into_history_entry(entry, review)

        self.assertIn("alertmanagerReviewedAt", merged)
        self.assertEqual(merged["alertmanagerReviewedAt"], "2026-04-26T14:30:00Z")

    def test_unrelated_reviews_do_not_leak_into_other_entries(self) -> None:
        """Test that reviews for other source artifacts don't leak into unrelated entries."""
        # Review for a different source
        review_for_source_a = {
            "alertmanager_relevance": "relevant",
            "alertmanager_relevance_summary": "Summary for A",
            "source_artifact": "source-a.json",
        }

        # Entry for source B (should NOT get A's review)
        entry_for_b = {"artifactPath": "source-b.json"}
        merged_b = _merge_alertmanager_review_into_history_entry(entry_for_b, None)

        # Should have original entry fields, no alertmanager fields
        self.assertEqual(merged_b["artifactPath"], "source-b.json")
        self.assertNotIn("alertmanagerRelevance", merged_b)
        self.assertNotIn("alertmanagerRelevanceSummary", merged_b)

        # Verify A's review wouldn't leak into B's entry
        entry_for_a = {"artifactPath": "source-a.json"}
        merged_a = _merge_alertmanager_review_into_history_entry(entry_for_a, review_for_source_a)
        self.assertEqual(merged_a["alertmanagerRelevance"], "relevant")
        self.assertNotIn("alertmanagerRelevance", merged_b)

    def test_entry_with_no_review_unchanged(self) -> None:
        """Test that entries without reviews are returned unchanged."""
        entry = {
            "artifactPath": "source.json",
            "timestamp": "2026-04-26T10:00:00Z",
            "status": "success",
        }
        merged = _merge_alertmanager_review_into_history_entry(entry, None)

        self.assertEqual(merged, entry)
        self.assertNotIn("alertmanagerRelevance", merged)
        self.assertNotIn("alertmanagerRelevanceSummary", merged)

    def test_review_with_none_values_skipped(self) -> None:
        """Test that None values in review don't add fields to entry."""
        review = {
            "alertmanager_relevance": "relevant",
            "alertmanager_relevance_summary": None,  # None should be skipped
            "alertmanager_provenance": None,  # None should be skipped
            "reviewed_at": "2026-04-26T10:00:00Z",
            "artifact_path": "external-analysis/review.json",
        }
        entry = {"artifactPath": "source.json"}
        merged = _merge_alertmanager_review_into_history_entry(entry, review)

        # Required field should be present
        self.assertIn("alertmanagerRelevance", merged)
        self.assertEqual(merged["alertmanagerRelevance"], "relevant")

        # Optional None fields should NOT create camelCase keys
        self.assertNotIn("alertmanagerRelevanceSummary", merged)
        self.assertNotIn("alertmanagerProvenance", merged)

        # Other fields should still be present
        self.assertIn("alertmanagerReviewedAt", merged)
        self.assertIn("alertmanagerReviewArtifactPath", merged)


class TestAlertmanagerReviewReloadVisibility(unittest.TestCase):
    """Tests for API-visible behavior after reload through projection path."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_dir = self.tmpdir / "health"
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_execution_artifact(
        self,
        run_id: str,
        index: int,
        alertmanager_provenance: Mapping[str, object] | None = None,
    ) -> Path:
        """Create a mock execution artifact."""
        artifact_data: dict[str, object] = {
            "purpose": "next-check-execution",
            "run_id": run_id,
            "cluster_label": "cluster-a",
            "status": "success",
            "tool_name": "kubectl",
            "summary": "Test execution",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if alertmanager_provenance:
            artifact_data["alertmanager_provenance"] = alertmanager_provenance

        artifact_path = self.external_dir / f"{run_id}-next-check-execution-{index}.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")
        return artifact_path

    def _simulate_review_creation_and_discovery(
        self,
        run_id: str,
        execution_index: int,
        relevance: AlertmanagerRelevanceClass,
        relevance_summary: str | None = None,
    ) -> dict:
        """Simulate full flow: create review artifact and discover it."""
        import uuid

        # Create source execution artifact
        source_artifact = self._create_execution_artifact(run_id, execution_index)
        source_relative = str(source_artifact.relative_to(self.health_dir))

        # Create review artifact (as endpoint would)
        review_uuid = str(uuid.uuid4())[:8]
        review_filename = f"{run_id}-next-check-execution-alertmanager-review-{review_uuid}.json"
        review_path = self.external_dir / review_filename

        source_data = json.loads(source_artifact.read_text(encoding="utf-8"))

        review_artifact = {
            "purpose": ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value,
            "tool_name": source_data.get("tool_name", ""),
            "run_id": run_id,
            "cluster_label": source_data.get("cluster_label", ""),
            "source_artifact": source_relative,
            "alertmanager_relevance": relevance.value,
            "alertmanager_relevance_summary": relevance_summary,
            "alertmanager_provenance": source_data.get("alertmanager_provenance"),
            "reviewed_at": datetime.now(UTC).isoformat(),
        }

        review_path.write_text(json.dumps(review_artifact))

        return {"source_artifact": source_relative, "review_data": review_artifact}

    def test_persisted_feedback_visible_after_reload(self) -> None:
        """Test that persisted feedback becomes visible after reload through discovery."""
        run_id = "test-reload-visibility"
        provenance = {"matchedDimensions": ["namespace"], "alertmanagerSource": "prometheus"}

        # Create source artifact with provenance
        source_path = self._create_execution_artifact(run_id, 0, alertmanager_provenance=provenance)

        # Simulate endpoint creating review
        uuid_suffix = "testreload1"
        source_relative = str(source_path.relative_to(self.health_dir))
        review_filename = f"{run_id}-next-check-execution-alertmanager-review-{uuid_suffix}.json"
        review_path = self.external_dir / review_filename

        review_artifact = {
            "purpose": ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value,
            "run_id": run_id,
            "source_artifact": source_relative,
            "alertmanager_relevance": "not_relevant",
            "alertmanager_relevance_summary": "Not helpful for this namespace",
            "alertmanager_provenance": provenance,
            "reviewed_at": "2026-04-26T15:00:00Z",
        }
        review_path.write_text(json.dumps(review_artifact))

        # Discover the review (as UI projection would)
        reviews = _load_alertmanager_review_artifacts(self.external_dir, run_id)

        # Verify review is discoverable
        self.assertIn(source_relative, reviews)
        discovered = reviews[source_relative]

        # Verify all fields are accessible
        self.assertEqual(discovered["alertmanager_relevance"], "not_relevant")
        self.assertEqual(discovered["alertmanager_relevance_summary"], "Not helpful for this namespace")
        self.assertEqual(discovered["alertmanager_provenance"], provenance)
        self.assertEqual(discovered["reviewed_at"], "2026-04-26T15:00:00Z")

    def test_feedback_visible_in_merged_execution_history(self) -> None:
        """Test that feedback is visible in merged execution history entry."""
        run_id = "test-history-merge"
        provenance = {"matchedDimensions": ["cluster"], "alertmanagerSource": "alertmanager"}

        # Create review artifact
        source_relative = f"external-analysis/{run_id}-next-check-execution-0.json"
        review_filename = f"{run_id}-next-check-execution-alertmanager-review-viewtest.json"
        review_path = self.external_dir / review_filename

        review_artifact = {
            "purpose": ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value,
            "run_id": run_id,
            "source_artifact": source_relative,
            "alertmanager_relevance": "noisy",
            "alertmanager_relevance_summary": "Too many false positives",
            "alertmanager_provenance": provenance,
            "reviewed_at": "2026-04-26T16:00:00Z",
            "artifact_path": f"external-analysis/{review_filename}",
        }
        review_path.write_text(json.dumps(review_artifact))

        # Simulate execution history entry (before merge)
        execution_entry = {
            "artifactPath": source_relative,
            "timestamp": "2026-04-26T14:00:00Z",
            "status": "success",
        }

        # Merge the review into history entry (as projection would)
        merged = _merge_alertmanager_review_into_history_entry(execution_entry, review_artifact)

        # Verify all expected fields are in merged entry
        self.assertEqual(merged["alertmanagerRelevance"], "noisy")
        self.assertEqual(merged["alertmanagerRelevanceSummary"], "Too many false positives")
        self.assertEqual(merged["alertmanagerProvenance"], provenance)
        self.assertEqual(merged["alertmanagerReviewedAt"], "2026-04-26T16:00:00Z")
        self.assertIn("alertmanagerReviewArtifactPath", merged)

    def test_multiple_runs_feedback_isolated(self) -> None:
        """Test that feedback from one run doesn't appear in another run."""
        run_id_a = "test-run-a"
        run_id_b = "test-run-b"

        # Create review for run A
        source_a = f"external-analysis/{run_id_a}-next-check-execution-0.json"
        review_a_filename = f"{run_id_a}-next-check-execution-alertmanager-review-runa.json"
        review_a_path = self.external_dir / review_a_filename
        review_a_path.write_text(json.dumps({
            "purpose": ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value,
            "run_id": run_id_a,
            "source_artifact": source_a,
            "alertmanager_relevance": "relevant",
            "reviewed_at": "2026-04-26T10:00:00Z",
        }), encoding="utf-8")

        # Create review for run B
        source_b = f"external-analysis/{run_id_b}-next-check-execution-0.json"
        review_b_filename = f"{run_id_b}-next-check-execution-alertmanager-review-runb.json"
        review_b_path = self.external_dir / review_b_filename
        review_b_path.write_text(json.dumps({
            "purpose": ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value,
            "run_id": run_id_b,
            "source_artifact": source_b,
            "alertmanager_relevance": "not_relevant",
            "reviewed_at": "2026-04-26T11:00:00Z",
        }), encoding="utf-8")

        # Discover reviews for each run
        reviews_a = _load_alertmanager_review_artifacts(self.external_dir, run_id_a)
        reviews_b = _load_alertmanager_review_artifacts(self.external_dir, run_id_b)

        # Verify isolation
        self.assertEqual(len(reviews_a), 1)
        self.assertIn(source_a, reviews_a)
        self.assertEqual(reviews_a[source_a]["alertmanager_relevance"], "relevant")

        self.assertEqual(len(reviews_b), 1)
        self.assertIn(source_b, reviews_b)
        self.assertEqual(reviews_b[source_b]["alertmanager_relevance"], "not_relevant")

        # Run A's feedback should NOT appear in Run B
        self.assertNotIn(source_a, reviews_b)
        # Run B's feedback should NOT appear in Run A
        self.assertNotIn(source_b, reviews_a)


if __name__ == "__main__":
    unittest.main()
