"""Tests for server_read_support.py security hardening.

These tests verify the security hardening for run_id validation
in the server_read_support module functions.
"""

from __future__ import annotations

import json
from pathlib import Path

from k8s_diag_agent.ui.server_read_support import (
    _build_clusters_and_drilldown_availability,
    _build_drilldown_availability_from_review,
    _build_execution_history,
    _build_llm_stats_for_run,
    _build_run_artifact_index,
    _count_run_artifacts,
    _find_next_check_plan,
    _find_review_enrichment,
    _load_alertmanager_review_artifacts,
    _load_proposals_for_run,
    _scan_external_analysis,
)


class TestLoadAlertmanagerReviewArtifacts:
    """Tests for _load_alertmanager_review_artifacts() security hardening."""

    def test_valid_run_id_finds_artifacts(self, tmp_path: Path) -> None:
        """Valid run_id should find alertmanager review artifacts."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create alertmanager review artifact
        (ea_dir / "run-test-next-check-execution-alertmanager-review-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution-alertmanager-review",
                "source_artifact": "run-test-001.json",
                "reviewed_at": "2024-01-01T00:00:00Z",
                "alertmanager_relevance": "relevant",
            }),
            encoding="utf-8",
        )

        # Valid run_id should find artifacts
        reviews = _load_alertmanager_review_artifacts(ea_dir, "run-test")
        assert len(reviews) == 1

    def test_traversal_run_id_returns_empty_dict(self, tmp_path: Path) -> None:
        """Traversal run_id should return empty dict, not raise."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Traversal should return empty result
        reviews = _load_alertmanager_review_artifacts(ea_dir, "../etc")
        assert reviews == {}

    def test_glob_metachar_run_id_returns_empty_dict(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return empty dict."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Glob metacharacter should be rejected
        reviews = _load_alertmanager_review_artifacts(ea_dir, "run*")
        assert reviews == {}

    def test_empty_run_id_returns_empty_dict(self, tmp_path: Path) -> None:
        """Empty run_id should return empty dict."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        reviews = _load_alertmanager_review_artifacts(ea_dir, "")
        assert reviews == {}

    def test_prefix_collision_prevented(self, tmp_path: Path) -> None:
        """Verify run_id prefix collision is prevented."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create exact prefix artifact
        (ea_dir / "run-test-next-check-execution-alertmanager-review-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution-alertmanager-review",
                "source_artifact": "run-test-001.json",
                "reviewed_at": "2024-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )
        # Create extended prefix artifact (should NOT match)
        (ea_dir / "run-test-extra-next-check-execution-alertmanager-review-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution-alertmanager-review",
                "source_artifact": "run-test-extra-001.json",
                "reviewed_at": "2024-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )

        # Only exact prefix should match
        reviews = _load_alertmanager_review_artifacts(ea_dir, "run-test")
        assert len(reviews) == 1
        assert "run-test-001.json" in reviews


class TestCountRunArtifacts:
    """Tests for _count_run_artifacts() security hardening."""

    def test_valid_run_id_counts_artifacts(self, tmp_path: Path) -> None:
        """Valid run_id should count artifacts."""
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Create artifacts
        (artifacts_dir / "run-test-001.json").write_text("{}", encoding="utf-8")
        (artifacts_dir / "run-test-002.json").write_text("{}", encoding="utf-8")

        count = _count_run_artifacts(artifacts_dir, "run-test")
        assert count == 2

    def test_traversal_run_id_returns_zero(self, tmp_path: Path) -> None:
        """Traversal run_id should return 0, not raise."""
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        count = _count_run_artifacts(artifacts_dir, "../etc")
        assert count == 0

    def test_glob_metachar_run_id_returns_zero(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return 0."""
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        count = _count_run_artifacts(artifacts_dir, "run*")
        assert count == 0

    def test_empty_dir_returns_zero(self, tmp_path: Path) -> None:
        """Empty directory returns 0."""
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        count = _count_run_artifacts(artifacts_dir, "run-test")
        assert count == 0


class TestLoadProposalsForRun:
    """Tests for _load_proposals_for_run() security hardening."""

    def test_valid_run_id_loads_proposals(self, tmp_path: Path) -> None:
        """Valid run_id should load proposals."""
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        # Create proposal
        (proposals_dir / "run-test-001.json").write_text(
            json.dumps({"status": "pending", "type": "proposal"}),
            encoding="utf-8",
        )

        proposals, count = _load_proposals_for_run(proposals_dir, "run-test")
        assert count == 1
        assert proposals[0]["type"] == "proposal"

    def test_traversal_run_id_returns_empty(self, tmp_path: Path) -> None:
        """Traversal run_id should return empty list, not raise."""
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        proposals, count = _load_proposals_for_run(proposals_dir, "../etc")
        assert proposals == []
        assert count == 0

    def test_glob_metachar_run_id_returns_empty(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return empty list."""
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        proposals, count = _load_proposals_for_run(proposals_dir, "run*")
        assert proposals == []
        assert count == 0


class TestScanExternalAnalysis:
    """Tests for _scan_external_analysis() security hardening."""

    def test_valid_run_id_scans_artifacts(self, tmp_path: Path) -> None:
        """Valid run_id should scan external analysis artifacts."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact
        (ea_dir / "run-test-001.json").write_text(
            json.dumps({
                "status": "success",
                "tool_name": "test-tool",
                "run_id": "run-test",
            }),
            encoding="utf-8",
        )

        result = _scan_external_analysis(ea_dir, "run-test")
        assert result["count"] == 1
        assert len(result["artifacts"]) == 1

    def test_traversal_run_id_returns_empty(self, tmp_path: Path) -> None:
        """Traversal run_id should return empty result, not raise."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        result = _scan_external_analysis(ea_dir, "../etc")
        assert result["count"] == 0
        assert result["artifacts"] == []

    def test_glob_metachar_run_id_returns_empty(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return empty result."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        result = _scan_external_analysis(ea_dir, "run*")
        assert result["count"] == 0
        assert result["artifacts"] == []

    def test_non_existent_dir_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent directory returns empty result."""
        ea_dir = tmp_path / "external-analysis"

        result = _scan_external_analysis(ea_dir, "run-test")
        assert result["count"] == 0
        assert result["artifacts"] == []


class TestBuildClustersAndDrilldownAvailability:
    """Tests for _build_clusters_and_drilldown_availability() security hardening."""

    def test_valid_run_id_builds_clusters(self, tmp_path: Path) -> None:
        """Valid run_id should build clusters from review data."""
        review_data = {
            "selected_drilldowns": [
                {"label": "prod", "context": "production"},
            ],
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Create drilldowns directory with artifact
        drilldowns_dir = tmp_path / "health" / "drilldowns"
        drilldowns_dir.mkdir(parents=True, exist_ok=True)
        (drilldowns_dir / "run-test-prod-diagnostic.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00Z"}),
            encoding="utf-8",
        )

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            "run-test", review_data, tmp_path
        )
        assert len(clusters) == 1
        assert clusters[0]["label"] == "prod"

    def test_traversal_run_id_returns_empty_clusters(self, tmp_path: Path) -> None:
        """Traversal run_id should return empty clusters, not raise."""
        review_data = {
            "selected_drilldowns": [
                {"label": "prod", "context": "production"},
            ],
            "timestamp": "2024-01-01T00:00:00Z",
        }

        drilldowns_dir = tmp_path / "health" / "drilldowns"
        drilldowns_dir.mkdir(parents=True, exist_ok=True)

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            "../etc", review_data, tmp_path
        )
        assert clusters == []
        assert drilldown_availability["available"] == 0
        assert drilldown_availability["missing"] == 1

    def test_glob_metachar_run_id_returns_empty_clusters(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return empty clusters."""
        review_data = {
            "selected_drilldowns": [
                {"label": "prod", "context": "production"},
            ],
            "timestamp": "2024-01-01T00:00:00Z",
        }

        drilldowns_dir = tmp_path / "health" / "drilldowns"
        drilldowns_dir.mkdir(parents=True, exist_ok=True)

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            "run*", review_data, tmp_path
        )
        assert clusters == []
        assert drilldown_availability["available"] == 0


class TestBuildDrilldownAvailabilityFromReview:
    """Tests for _build_drilldown_availability_from_review() security hardening."""

    def test_valid_run_id_builds_availability(self, tmp_path: Path) -> None:
        """Valid run_id should build drilldown availability."""
        review_data = {
            "selected_drilldowns": [
                {"label": "prod", "context": "production"},
            ],
            "timestamp": "2024-01-01T00:00:00Z",
        }

        drilldowns_dir = tmp_path / "drilldowns"
        drilldowns_dir.mkdir(parents=True, exist_ok=True)
        (drilldowns_dir / "run-test-prod-diagnostic.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00Z"}),
            encoding="utf-8",
        )

        result = _build_drilldown_availability_from_review(
            review_data, drilldowns_dir, "run-test"
        )
        assert result["available"] == 1
        assert result["missing"] == 0

    def test_traversal_run_id_returns_empty(self, tmp_path: Path) -> None:
        """Traversal run_id should return empty result, not raise."""
        review_data = {
            "selected_drilldowns": [
                {"label": "prod", "context": "production"},
            ],
            "timestamp": "2024-01-01T00:00:00Z",
        }

        drilldowns_dir = tmp_path / "drilldowns"
        drilldowns_dir.mkdir(parents=True, exist_ok=True)

        result = _build_drilldown_availability_from_review(
            review_data, drilldowns_dir, "../etc"
        )
        assert result["available"] == 0
        assert result["missing"] == 1

    def test_glob_metachar_run_id_returns_empty(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return empty result."""
        review_data = {
            "selected_drilldowns": [
                {"label": "prod", "context": "production"},
            ],
            "timestamp": "2024-01-01T00:00:00Z",
        }

        drilldowns_dir = tmp_path / "drilldowns"
        drilldowns_dir.mkdir(parents=True, exist_ok=True)

        result = _build_drilldown_availability_from_review(
            review_data, drilldowns_dir, "run*"
        )
        assert result["available"] == 0

    def test_label_traversal_rejected(self, tmp_path: Path) -> None:
        """Label with traversal pattern should be handled safely."""
        review_data = {
            "selected_drilldowns": [
                {"label": "../etc", "context": "production"},
            ],
            "timestamp": "2024-01-01T00:00:00Z",
        }

        drilldowns_dir = tmp_path / "drilldowns"
        drilldowns_dir.mkdir(parents=True, exist_ok=True)

        result = _build_drilldown_availability_from_review(
            review_data, drilldowns_dir, "run-test"
        )
        # Should not crash, label should be rejected
        assert result["available"] == 0


class TestBuildRunArtifactIndex:
    """Tests for _build_run_artifact_index() security hardening."""

    def test_valid_run_id_builds_index(self, tmp_path: Path) -> None:
        """Valid run_id should build artifact index."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({"purpose": "review-enrichment"}),
            encoding="utf-8",
        )
        (ea_dir / "run-test-next-check-plan.json").write_text(
            json.dumps({"purpose": "next-check-planning"}),
            encoding="utf-8",
        )

        index = _build_run_artifact_index(ea_dir, "run-test")
        assert index.artifacts_considered == 2
        assert len(index.review_enrichment) == 1
        assert len(index.next_check_plan) == 1

    def test_traversal_run_id_returns_empty_index(self, tmp_path: Path) -> None:
        """Traversal run_id should return empty index, not raise."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        index = _build_run_artifact_index(ea_dir, "../etc")
        assert index.artifacts_considered == 0
        assert index.source == "file_scan"

    def test_glob_metachar_run_id_returns_empty_index(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return empty index."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        index = _build_run_artifact_index(ea_dir, "run*")
        assert index.artifacts_considered == 0


class TestFindReviewEnrichment:
    """Tests for _find_review_enrichment() security hardening (fallback path)."""

    def test_valid_run_id_finds_enrichment(self, tmp_path: Path) -> None:
        """Valid run_id should find review enrichment artifact."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "provider": "test-provider",
            }),
            encoding="utf-8",
        )

        result = _find_review_enrichment(ea_dir, "run-test")
        assert result is not None
        assert result["status"] == "success"

    def test_traversal_run_id_returns_none(self, tmp_path: Path) -> None:
        """Traversal run_id should return None, not raise."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        result = _find_review_enrichment(ea_dir, "../etc")
        assert result is None

    def test_glob_metachar_run_id_returns_none(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return None."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        result = _find_review_enrichment(ea_dir, "run*")
        assert result is None


class TestFindNextCheckPlan:
    """Tests for _find_next_check_plan() security hardening (fallback path)."""

    def test_valid_run_id_finds_plan(self, tmp_path: Path) -> None:
        """Valid run_id should find next-check plan artifact."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-next-check-plan.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "status": "success",
                "payload": {"summary": "test"},
            }),
            encoding="utf-8",
        )

        result = _find_next_check_plan(ea_dir, "run-test")
        assert result is not None
        assert result["status"] == "success"

    def test_traversal_run_id_returns_none(self, tmp_path: Path) -> None:
        """Traversal run_id should return None, not raise."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        result = _find_next_check_plan(ea_dir, "../etc")
        assert result is None

    def test_glob_metachar_run_id_returns_none(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return None."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        result = _find_next_check_plan(ea_dir, "run*")
        assert result is None


class TestBuildExecutionHistory:
    """Tests for _build_execution_history() security hardening (fallback path)."""

    def test_valid_run_id_builds_history(self, tmp_path: Path) -> None:
        """Valid run_id should build execution history."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-next-check-execution-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "timestamp": "2024-01-01T00:00:00Z",
                "payload": {},
            }),
            encoding="utf-8",
        )

        history, telemetry = _build_execution_history(ea_dir, "run-test")
        assert len(history) == 1
        assert telemetry["execution_history_source"] == "file_scan"

    def test_traversal_run_id_returns_empty_history(self, tmp_path: Path) -> None:
        """Traversal run_id should return empty history, not raise."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        history, telemetry = _build_execution_history(ea_dir, "../etc")
        assert history == []
        assert telemetry["execution_history_source"] == "file_scan"

    def test_glob_metachar_run_id_returns_empty_history(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return empty history."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        history, telemetry = _build_execution_history(ea_dir, "run*")
        assert history == []


class TestBuildLlmStatsForRun:
    """Tests for _build_llm_stats_for_run() security hardening (fallback path)."""

    def test_valid_run_id_builds_stats(self, tmp_path: Path) -> None:
        """Valid run_id should build LLM stats."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        (ea_dir / "run-test-001.json").write_text(
            json.dumps({
                "status": "success",
                "tool_name": "test-tool",
                "duration_ms": 100,
            }),
            encoding="utf-8",
        )

        stats = _build_llm_stats_for_run(ea_dir, "run-test")
        assert stats["totalCalls"] == 1
        assert stats["successfulCalls"] == 1

    def test_traversal_run_id_returns_empty_stats(self, tmp_path: Path) -> None:
        """Traversal run_id should return empty stats, not raise."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        stats = _build_llm_stats_for_run(ea_dir, "../etc")
        assert stats["totalCalls"] == 0
        assert stats["successfulCalls"] == 0

    def test_glob_metachar_run_id_returns_empty_stats(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return empty stats."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        stats = _build_llm_stats_for_run(ea_dir, "run*")
        assert stats["totalCalls"] == 0
