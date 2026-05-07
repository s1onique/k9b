"""Tests for provider alias de-anonymization in health/ui.py index generation.

These tests verify that write_health_ui_index() and related serializers
produce operator-facing content WITHOUT leaked provider aliases.

The leak paths being tested:
- $.reviewEnrichment.triageOrder[]
- $.reviewEnrichment.topConcerns[]
- $.reviewEnrichment.nextChecks[]
- $.reviewEnrichment.focusNotes[]
- $.nextCheckPlan.candidates[].description
- $.nextCheckPlan.candidates[].targetCluster
- $.nextCheckPlan.candidates[].targetContext
- $.nextCheckPlan.candidates[].commandPreview
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.health.ui import _serialize_review_enrichment, write_health_ui_index
from k8s_diag_agent.health.ui_planner_queue import (
    _find_review_enrichment_artifact_for_alias,
    _serialize_next_check_plan,
)
from k8s_diag_agent.security.deanonymization import assert_no_provider_aliases


class TestSerializeReviewEnrichmentDeanonymization:
    """Tests for _serialize_review_enrichment() de-anonymization at index boundary."""

    def test_serialize_review_enrichment_deanonymizes_triage_order(self, tmp_path: Path) -> None:
        """Triage order should contain real names, not aliases."""
        alias_mapping = {
            "cluster-a": "prod-cluster",
            "cluster-b": "stage-cluster",
            "namespace-f": "kube-system",
            "name-a": "nginx-deployment",
        }

        artifact = ExternalAnalysisArtifact(
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            status=ExternalAnalysisStatus.SUCCESS,
            tool_name="k8sgpt",
            provider="k8sgpt",
            run_id="test-run",
            run_label="Test Run",
            cluster_label="test",
            timestamp=datetime.now(UTC),
            payload={
                "triage_order": ["cluster-a", "cluster-b"],
                "top_concerns": ["High latency in cluster-a", "Memory pressure in cluster-b"],
                "focus_notes": ["Investigate cluster-a and namespace-f"],
                "next_checks": ["kubectl get pods -n namespace-f"],
                "summary": "Review of cluster-a and cluster-b",
            },
            alias_mapping=alias_mapping,
        )

        result = _serialize_review_enrichment((artifact,), tmp_path, "test-run")

        assert result is not None
        triage_order = cast(list[str], result["triageOrder"])
        top_concerns = cast(list[str], result["topConcerns"])
        focus_notes = cast(list[str], result["focusNotes"])
        next_checks = cast(list[str], result["nextChecks"])

        # Verify real names appear
        assert "prod-cluster" in triage_order
        assert "stage-cluster" in triage_order
        assert any("prod-cluster" in concern for concern in top_concerns)
        assert any("stage-cluster" in concern for concern in top_concerns)
        assert any("prod-cluster" in note for note in focus_notes)
        assert any("kube-system" in check for check in next_checks)

        # Verify aliases do NOT appear in operator-facing fields
        assert "cluster-a" not in triage_order
        assert "cluster-b" not in triage_order
        assert not any("cluster-a" in concern for concern in top_concerns)
        if focus_notes:
            assert "namespace-f" not in focus_notes[0]
        assert not any("namespace-f" in note for note in focus_notes)

        # Assert no aliases leak in the result dict - uses internal assert helper
        assert_no_provider_aliases(result)


class TestNextCheckPlanDeanonymization:
    """Tests for _serialize_next_check_plan() de-anonymization at index boundary."""

    def test_serialize_next_check_plan_deanonymizes_candidates(self, tmp_path: Path) -> None:
        """Next-check plan candidates should contain real names, not aliases."""
        alias_mapping = {
            "cluster-a": "prod-cluster",
            "cluster-b": "stage-cluster",
            "namespace-f": "monitoring",
            "name-a": "prometheus",
        }

        # Create a review enrichment artifact with alias_mapping for fallback
        review_artifact = ExternalAnalysisArtifact(
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            status=ExternalAnalysisStatus.SUCCESS,
            tool_name="k8sgpt",
            provider="k8sgpt",
            run_id="test-run",
            run_label="Test Run",
            cluster_label="test",
            timestamp=datetime.now(UTC),
            payload={},
            alias_mapping=alias_mapping,
        )

        # Create next-check plan artifact (without its own alias_mapping)
        plan_artifact = ExternalAnalysisArtifact(
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            status=ExternalAnalysisStatus.SUCCESS,
            tool_name="k8sgpt",
            provider="k8sgpt",
            run_id="test-run",
            run_label="Test Run",
            cluster_label="test",
            timestamp=datetime.now(UTC),
            payload={
                "candidates": [
                    {
                        "candidateId": "check-1",
                        "description": "Check pod status in cluster-a",
                        "targetCluster": "cluster-a",
                        "targetContext": "cluster-b",
                        "commandPreview": "kubectl get pods --context cluster-a",
                    },
                    {
                        "candidateId": "check-2",
                        "description": "Investigate namespace-f in cluster-b",
                        "targetCluster": "cluster-b",
                        "targetContext": "cluster-a",
                        "commandPreview": "kubectl get pods -n namespace-f --context cluster-b",
                    },
                ]
            },
        )

        artifacts = [review_artifact, plan_artifact]
        result = _serialize_next_check_plan(artifacts, tmp_path, "test-run")

        assert result is not None
        candidates = cast(list[dict[str, object]], result["candidates"])

        # Verify de-anonymized values appear
        assert any("prod-cluster" in str(c.get("description", "")) for c in candidates)
        assert any("monitoring" in str(c.get("description", "")) for c in candidates)

        # Verify aliases do NOT appear
        assert not any("cluster-a" in str(c.get("description", "")) for c in candidates)
        assert not any("cluster-b" in str(c.get("targetCluster", "")) for c in candidates)
        assert not any("namespace-f" in str(c.get("description", "")) for c in candidates)

        # Assert no aliases leak
        assert_no_provider_aliases(result)


class TestFindReviewEnrichmentForAlias:
    """Tests for _find_review_enrichment_artifact_for_alias() helper."""

    def test_finds_review_enrichment_artifact(self, tmp_path: Path) -> None:
        """Should find the review enrichment artifact from the sequence."""
        artifact = ExternalAnalysisArtifact(
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            status=ExternalAnalysisStatus.SUCCESS,
            tool_name="k8sgpt",
            provider="k8sgpt",
            run_id="test-run",
            run_label="Test Run",
            cluster_label="test",
            timestamp=datetime.now(UTC),
            payload={},
            alias_mapping={"cluster-a": "prod-cluster"},
        )

        other_artifact = ExternalAnalysisArtifact(
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            status=ExternalAnalysisStatus.SUCCESS,
            tool_name="k8sgpt",
            provider="k8sgpt",
            run_id="test-run",
            run_label="Test Run",
            cluster_label="test",
            timestamp=datetime.now(UTC),
            payload={},
        )

        result = _find_review_enrichment_artifact_for_alias(
            [other_artifact, artifact], "test-run"
        )

        assert result is not None
        assert result.purpose == ExternalAnalysisPurpose.REVIEW_ENRICHMENT
        assert result.alias_mapping == {"cluster-a": "prod-cluster"}


class TestWriteHealthUiIndexDeanonymization:
    """Integration tests for write_health_ui_index() alias de-anonymization."""

    def test_write_health_ui_index_removes_aliases_from_review_enrichment(
        self, tmp_path: Path
    ) -> None:
        """write_health_ui_index should not write aliases to the index file."""
        alias_mapping = {
            "cluster-a": "prod-cluster",
            "cluster-b": "stage-cluster",
            "namespace-f": "monitoring",
            "name-a": "app-deployment",
        }

        artifact = ExternalAnalysisArtifact(
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            status=ExternalAnalysisStatus.SUCCESS,
            tool_name="k8sgpt",
            provider="k8sgpt",
            run_id="test-run",
            run_label="Test Run",
            cluster_label="test",
            timestamp=datetime.now(UTC),
            payload={
                "triage_order": ["cluster-a", "cluster-b"],
                "top_concerns": [
                    "High latency in cluster-a",
                    "Check cluster-b for memory issues",
                ],
                "focus_notes": ["Focus on cluster-a namespace-f"],
                "next_checks": [
                    "kubectl logs -n namespace-f deploy/name-a"
                ],
                "summary": "Review results for cluster-a",
            },
            alias_mapping=alias_mapping,
        )

        output_dir = tmp_path / "health"
        output_dir.mkdir(parents=True)
        (output_dir / "reviews").mkdir()
        (output_dir / "external-analysis").mkdir()
        (output_dir / "proposals").mkdir()

        index_path = write_health_ui_index(
            output_dir=output_dir,
            run_id="test-run",
            run_label="Test Run",
            collector_version="1.0.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
            external_analysis=[artifact],
        )

        assert index_path.exists()

        index_data = json.loads(index_path.read_text(encoding="utf-8"))

        # Check reviewEnrichment entry - use the helper for full verification
        review_enrichment = index_data.get("run", {}).get("review_enrichment")
        if review_enrichment and isinstance(review_enrichment, dict):
            # The assert_no_provider_aliases helper will catch any alias leaks
            assert_no_provider_aliases(review_enrichment)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
