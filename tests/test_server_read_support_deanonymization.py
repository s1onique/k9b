"""Tests for server_read_support.py provider alias de-anonymization.

These tests verify that _find_review_enrichment() and _find_next_check_plan()
return de-anonymized operator-facing values, NOT provider aliases.

Backend de-anonymization is complete:
- ExternalAnalysisArtifact stores alias_mapping
- LlamaCppAdapter persists all alias categories
- review enrichment payload is de-anonymized at UI/API boundary
- next-check/worklist candidates are de-anonymized at UI/API boundary
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from k8s_diag_agent.ui.server_read_support import (
    _build_run_artifact_index,
    _find_next_check_plan,
    _find_review_enrichment,
)


class TestReviewEnrichmentDeanonymization:
    """Tests for _find_review_enrichment() de-anonymization."""

    def test_review_enrichment_returns_deanonymized_triage_order(self, tmp_path: Path) -> None:
        """Triage order should contain real cluster names, not aliases."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact with aliases that get de-anonymized
        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "provider": "k8sgpt",
                "timestamp": "2024-01-01T00:00:00Z",
                "payload": {
                    # Simulating provider response with anonymized input
                    "triage_order": ["cluster-a", "cluster-b"],
                    "top_concerns": ["High latency in cluster-a", "Memory pressure in cluster-b"],
                    "summary": "Review results based on anonymized drilldown data",
                },
                # Backend alias_mapping for de-anonymization
                "alias_mapping": {
                    "cluster-a": "cluster1",
                    "cluster-b": "cluster2",
                    "namespace-f": "kube-system",
                },
            }),
            encoding="utf-8",
        )

        result = _find_review_enrichment(ea_dir, "run-test")

        assert result is not None
        assert isinstance(result, dict)
        triage_order = cast(list[str], result["triageOrder"])
        assert isinstance(triage_order, list)
        # Verify de-anonymized values appear
        assert "cluster1" in triage_order
        assert "cluster2" in triage_order
        # Verify aliases do NOT appear in operator-facing fields
        assert "cluster-a" not in triage_order
        assert "cluster-b" not in triage_order

    def test_review_enrichment_deanonymizes_top_concerns(self, tmp_path: Path) -> None:
        """Top concerns text should contain real cluster names after de-anonymization."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "payload": {
                    "triage_order": ["cluster-a", "cluster-b"],
                    "top_concerns": [
                        "Ingress latency affecting cluster-a user traffic",
                        "Storage delays in cluster-b namespace",
                    ],
                },
                "alias_mapping": {
                    "cluster-a": "prod-cluster",
                    "cluster-b": "stage-cluster",
                },
            }),
            encoding="utf-8",
        )

        result = _find_review_enrichment(ea_dir, "run-test")

        assert result is not None
        concerns = result["topConcerns"]
        # Verify real cluster names appear
        assert any("prod-cluster" in concern for concern in concerns)
        assert any("stage-cluster" in concern for concern in concerns)
        # Verify aliases do NOT appear in concerns
        assert not any("cluster-a" in concern for concern in concerns)
        assert not any("cluster-b" in concern for concern in concerns)

    def test_review_enrichment_deanonymizes_focus_notes(self, tmp_path: Path) -> None:
        """Focus notes should contain real cluster names after de-anonymization."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "payload": {
                    "triage_order": ["cluster-a"],
                    "focus_notes": ["Prioritize cluster-a for investigation"],
                },
                "alias_mapping": {
                    "cluster-a": "primary-prod",
                },
            }),
            encoding="utf-8",
        )

        result = _find_review_enrichment(ea_dir, "run-test")

        assert result is not None
        notes = result["focusNotes"]
        # Verify real cluster name appears
        assert any("primary-prod" in note for note in notes)
        # Verify alias does NOT appear
        assert not any("cluster-a" in note for note in notes)

    def test_review_enrichment_preserves_alias_mapping_for_audit(self, tmp_path: Path) -> None:
        """provider_alias_mapping field should be preserved for audit/debug."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        alias_mapping = {
            "cluster-a": "cluster1",
            "cluster-b": "cluster2",
            "namespace-f": "kube-system",
        }

        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "payload": {
                    "triage_order": ["cluster1", "cluster2"],
                },
                "alias_mapping": alias_mapping,
            }),
            encoding="utf-8",
        )

        result = _find_review_enrichment(ea_dir, "run-test")

        assert result is not None
        assert isinstance(result, dict)
        # Verify alias_mapping is preserved for audit/debug
        assert "provider_alias_mapping" in result
        assert result["provider_alias_mapping"] == alias_mapping
        # But it should NOT appear in operator-facing triageOrder
        triage_order = cast(list[str], result["triageOrder"])
        assert isinstance(triage_order, list)
        assert "cluster-a" not in triage_order

    def test_review_enrichment_handles_missing_alias_mapping(self, tmp_path: Path) -> None:
        """Should handle artifacts without alias_mapping gracefully."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "payload": {
                    "triage_order": ["existing-cluster"],
                    "top_concerns": ["Some concern"],
                },
                # No alias_mapping - backward compatibility
            }),
            encoding="utf-8",
        )

        result = _find_review_enrichment(ea_dir, "run-test")

        assert result is not None
        triage_order = cast(list[str], result["triageOrder"])
        assert "existing-cluster" in triage_order
        # provider_alias_mapping should not be present when no alias_mapping
        assert "provider_alias_mapping" not in result


class TestNextCheckPlanDeanonymization:
    """Tests for _find_next_check_plan() de-anonymization."""

    def test_next_check_plan_deanonymizes_candidate_commands(self, tmp_path: Path) -> None:
        """commandPreview should contain real context/namespace, not aliases."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-next-check-plan.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "status": "success",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "test-candidate-1",
                            "description": "Collect logs from cluster-a control plane",
                            "targetCluster": "cluster-a",
                            "commandPreview": "kubectl logs --context cluster-a -n namespace-f",
                            "safeToAutomate": True,
                            "requiresOperatorApproval": False,
                        },
                    ],
                },
                "alias_mapping": {
                    "cluster-a": "primary-prod",
                    "namespace-f": "kube-system",
                },
            }),
            encoding="utf-8",
        )

        result = _find_next_check_plan(ea_dir, "run-test")

        assert result is not None
        assert result["candidateCount"] == 1

        candidates = cast(list[dict[str, object]], result["candidates"])
        candidate = candidates[0]
        command_preview = cast(str, candidate["commandPreview"])
        # Verify de-anonymized values appear in command
        assert "primary-prod" in command_preview
        assert "kube-system" in command_preview
        # Verify aliases do NOT appear in command
        assert "cluster-a" not in command_preview
        assert "namespace-f" not in command_preview

    def test_next_check_plan_deanonymizes_target_context(self, tmp_path: Path) -> None:
        """targetContext should contain real cluster name, not alias."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-next-check-plan.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "status": "success",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "test-candidate-2",
                            "description": "Check node health",
                            "targetCluster": "cluster-b",
                            "targetContext": "cluster-b · nodes",
                            "commandPreview": "kubectl get nodes --context cluster-b",
                            "safeToAutomate": False,
                            "requiresOperatorApproval": True,
                        },
                    ],
                },
                "alias_mapping": {
                    "cluster-b": "stage-cluster",
                },
            }),
            encoding="utf-8",
        )

        result = _find_next_check_plan(ea_dir, "run-test")

        assert result is not None
        candidates = cast(list[dict[str, object]], result["candidates"])
        candidate = candidates[0]
        target_context = cast(str, candidate["targetContext"])
        command_preview = cast(str, candidate["commandPreview"])
        # Verify de-anonymized values appear
        assert "stage-cluster" in target_context
        assert "stage-cluster" in command_preview
        # Verify alias does NOT appear
        assert "cluster-b" not in target_context

    def test_next_check_plan_falls_back_to_review_alias_mapping(self, tmp_path: Path) -> None:
        """Should use review-enrichment alias_mapping when plan has none."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create review-enrichment with alias_mapping (fallback source)
        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "payload": {
                    "triage_order": ["cluster-x"],
                },
                "alias_mapping": {
                    "cluster-x": "real-cluster-name",
                },
            }),
            encoding="utf-8",
        )

        # Create plan WITHOUT alias_mapping (should fall back to review)
        (ea_dir / "run-test-next-check-plan.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "status": "success",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "fallback-test",
                            "description": "Test fallback de-anonymization",
                            "targetCluster": "cluster-x",
                            "commandPreview": "kubectl get pods --context cluster-x",
                            "safeToAutomate": True,
                            "requiresOperatorApproval": False,
                        },
                    ],
                },
                # No alias_mapping - should use review fallback
            }),
            encoding="utf-8",
        )

        result = _find_next_check_plan(ea_dir, "run-test")

        assert result is not None
        candidates = cast(list[dict[str, object]], result["candidates"])
        candidate = candidates[0]
        command_preview = cast(str, candidate["commandPreview"])
        # Verify fallback de-anonymization worked
        assert "real-cluster-name" in command_preview
        # Verify alias does NOT appear
        assert "cluster-x" not in command_preview

    def test_next_check_plan_handles_multiple_aliases(self, tmp_path: Path) -> None:
        """Should correctly de-anonymize when multiple alias types are present."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-next-check-plan.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "status": "success",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "multi-alias-1",
                            "description": "Check pods in cluster-a namespace",
                            "targetCluster": "cluster-a",
                            "commandPreview": "kubectl get pods -n namespace-f --context cluster-a",
                            "safeToAutomate": True,
                            "requiresOperatorApproval": False,
                        },
                    ],
                },
                "alias_mapping": {
                    "cluster-a": "prod-east",
                    "cluster-b": "prod-west",
                    "namespace-f": "production",
                    "node-a": "prod-east-node-1",
                },
            }),
            encoding="utf-8",
        )

        result = _find_next_check_plan(ea_dir, "run-test")

        assert result is not None
        candidates = cast(list[dict[str, object]], result["candidates"])
        candidate = candidates[0]
        command_preview = cast(str, candidate["commandPreview"])
        # Verify all de-anonymized values appear
        assert "prod-east" in command_preview
        assert "production" in command_preview
        # Verify NO aliases appear
        assert "cluster-a" not in command_preview
        assert "cluster-b" not in command_preview
        assert "namespace-f" not in command_preview


class TestDeanonymizationEdgeCases:
    """Edge case tests for de-anonymization."""

    def test_empty_alias_mapping_noop(self, tmp_path: Path) -> None:
        """Empty alias_mapping should result in no changes."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "payload": {
                    "triage_order": ["original-cluster"],
                },
                "alias_mapping": {},
            }),
            encoding="utf-8",
        )

        result = _find_review_enrichment(ea_dir, "run-test")

        assert result is not None
        triage_order = cast(list[str], result["triageOrder"])
        assert "original-cluster" in triage_order
        # No provider_alias_mapping when mapping is empty
        assert "provider_alias_mapping" not in result

    def test_partial_alias_coverage(self, tmp_path: Path) -> None:
        """Should de-anonymize available aliases, leave others unchanged."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "payload": {
                    "triage_order": ["cluster-a", "already-real"],
                    "top_concerns": ["Issue in cluster-a", "Issue in already-real"],
                },
                "alias_mapping": {
                    "cluster-a": "mapped-cluster",
                    # cluster-b not in payload, so no mapping needed
                },
            }),
            encoding="utf-8",
        )

        result = _find_review_enrichment(ea_dir, "run-test")

        assert result is not None
        triage_order = cast(list[str], result["triageOrder"])
        # cluster-a should be de-anonymized
        assert "mapped-cluster" in triage_order
        assert "cluster-a" not in triage_order
        # already-real should remain unchanged
        assert "already-real" in triage_order

    def test_uses_artifact_index_for_efficient_lookup(self, tmp_path: Path) -> None:
        """Should use artifact_index for O(1) lookup and still de-anonymize."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create artifacts
        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "payload": {
                    "triage_order": ["cluster-a", "cluster-b"],
                },
                "alias_mapping": {
                    "cluster-a": "real-prod",
                    "cluster-b": "real-stage",
                },
            }),
            encoding="utf-8",
        )

        # Build index first
        index = _build_run_artifact_index(ea_dir, "run-test")

        # Use index for lookup - should still de-anonymize
        result = _find_review_enrichment(ea_dir, "run-test", index)

        assert result is not None
        triage_order = cast(list[str], result["triageOrder"])
        # Verify de-anonymized values
        assert "real-prod" in triage_order
        assert "real-stage" in triage_order
        # Verify aliases not present
        assert "cluster-a" not in triage_order
        assert "cluster-b" not in triage_order
