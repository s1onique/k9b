"""Tests for promotion.py artifact reading integration.

These tests verify that collect_promoted_next_check_payloads() correctly:
- Collects promotions for the target run
- Filters out promotions for other runs
- Skips malformed artifacts silently (log_failures=False)
- Filters by purpose
- Extracts payload fields correctly
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.deterministic_next_check_promotion import (
    collect_promoted_next_check_payloads,
)


class TestCollectPromotedNextCheckPayloads:
    """Tests for collect_promoted_next_check_payloads function."""

    def test_collects_promotions_for_target_run(
        self, tmp_path: Path
    ) -> None:
        """Should collect promotions only for the target run."""
        runs_dir = tmp_path
        external_dir = runs_dir / "external-analysis"
        external_dir.mkdir(parents=True)

        # Write promotion for target run
        target_artifact = ExternalAnalysisArtifact(
            tool_name="promoter",
            run_id="run-target",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
            payload={
                "runId": "run-target",
                "description": "Target run promotion",
            },
        )
        target_path = external_dir / "run-target-next-check-promotion-0.json"
        target_path.write_text(json.dumps(target_artifact.to_dict()), encoding="utf-8")

        result = collect_promoted_next_check_payloads(runs_dir, "run-target")

        assert len(result) == 1
        entry, _ = result[0]
        assert entry["description"] == "Target run promotion"

    def test_filters_out_other_run_promotions(
        self, tmp_path: Path
    ) -> None:
        """Should filter out promotions for runs other than the target."""
        runs_dir = tmp_path
        external_dir = runs_dir / "external-analysis"
        external_dir.mkdir(parents=True)

        # Write promotion for other run
        other_artifact = ExternalAnalysisArtifact(
            tool_name="promoter",
            run_id="run-other",
            cluster_label="staging",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
            payload={
                "runId": "run-other",
                "description": "Other run promotion",
            },
        )
        other_path = external_dir / "run-other-next-check-promotion-0.json"
        other_path.write_text(json.dumps(other_artifact.to_dict()), encoding="utf-8")

        # Write promotion for target run
        target_artifact = ExternalAnalysisArtifact(
            tool_name="promoter",
            run_id="run-target",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
            payload={
                "runId": "run-target",
                "description": "Target run promotion",
            },
        )
        target_path = external_dir / "run-target-next-check-promotion-0.json"
        target_path.write_text(json.dumps(target_artifact.to_dict()), encoding="utf-8")

        result = collect_promoted_next_check_payloads(runs_dir, "run-target")

        # Should only have the target run promotion
        assert len(result) == 1
        entry, _ = result[0]
        assert entry["runId"] == "run-target"

    def test_skips_malformed_artifacts_silently(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should skip malformed artifacts silently (no logging for broad scan path)."""
        runs_dir = tmp_path
        external_dir = runs_dir / "external-analysis"
        external_dir.mkdir(parents=True)

        # Write valid promotion for target run
        target_artifact = ExternalAnalysisArtifact(
            tool_name="promoter",
            run_id="run-skip-test",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
            payload={
                "runId": "run-skip-test",
                "description": "Valid promotion",
            },
        )
        target_path = external_dir / "run-skip-test-next-check-promotion-0.json"
        target_path.write_text(json.dumps(target_artifact.to_dict()), encoding="utf-8")

        # Write malformed artifact
        bad_path = external_dir / "run-skip-test-next-check-promotion-1.json"
        bad_path.write_text("{ malformed json", encoding="utf-8")

        # Capture warnings from the reader module
        with caplog.at_level(logging.WARNING):
            result = collect_promoted_next_check_payloads(runs_dir, "run-skip-test")

        # Should still get the valid promotion
        assert len(result) == 1
        entry, _ = result[0]
        assert entry["description"] == "Valid promotion"
        # Malformed was skipped silently (no warning logged because promotion.py uses log_failures=False)
        assert len(caplog.records) == 0

    def test_skips_artifacts_with_wrong_purpose(
        self, tmp_path: Path
    ) -> None:
        """Should skip artifacts that don't have NEXT_CHECK_PROMOTION purpose."""
        runs_dir = tmp_path
        external_dir = runs_dir / "external-analysis"
        external_dir.mkdir(parents=True)

        # Write artifact with wrong purpose
        wrong_purpose = ExternalAnalysisArtifact(
            tool_name="promoter",
            run_id="run-wrong-purpose",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.AUTO_DRILLDOWN,  # Wrong purpose
            payload={
                "runId": "run-wrong-purpose",
                "description": "Wrong purpose",
            },
        )
        wrong_path = external_dir / "run-wrong-purpose-next-check-promotion-0.json"
        wrong_path.write_text(json.dumps(wrong_purpose.to_dict()), encoding="utf-8")

        result = collect_promoted_next_check_payloads(runs_dir, "run-wrong-purpose")

        assert result == []

    def test_returns_empty_for_nonexistent_directory(self, tmp_path: Path) -> None:
        """Should return empty list when external-analysis directory doesn't exist."""
        runs_dir = tmp_path
        # No external-analysis directory

        result = collect_promoted_next_check_payloads(runs_dir, "run-nonexistent")

        assert result == []

    def test_extracts_all_payload_fields(self, tmp_path: Path) -> None:
        """Should extract all payload fields correctly."""
        runs_dir = tmp_path
        external_dir = runs_dir / "external-analysis"
        external_dir.mkdir(parents=True)

        # Write promotion with all fields
        full_artifact = ExternalAnalysisArtifact(
            tool_name="promoter",
            run_id="run-full",
            cluster_label="prod",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
            payload={
                "runId": "run-full",
                "description": "Full test promotion",
                "method": "kubectl describe",
                "evidenceNeeded": ["evidence1", "evidence2"],
                "workstream": "incident",
                "urgency": "high",
                "whyNow": "Because reasons",
                "topProblem": "High CPU",
                "priorityScore": 85,
                "clusterLabel": "prod",
                "targetContext": "default",
                "candidateId": "abc123",
                "promotionIndex": 0,
            },
        )
        full_path = external_dir / "run-full-next-check-promotion-0.json"
        full_path.write_text(json.dumps(full_artifact.to_dict()), encoding="utf-8")

        result = collect_promoted_next_check_payloads(runs_dir, "run-full")

        assert len(result) == 1
        entry, _ = result[0]
        assert entry["description"] == "Full test promotion"
        assert entry["method"] == "kubectl describe"
        assert entry["evidenceNeeded"] == ["evidence1", "evidence2"]
        assert entry["workstream"] == "incident"
        assert entry["urgency"] == "high"
        assert entry["whyNow"] == "Because reasons"
        assert entry["topProblem"] == "High CPU"
        assert entry["priorityScore"] == 85
        assert entry["clusterLabel"] == "prod"
        assert entry["targetContext"] == "default"
        assert entry["candidateId"] == "abc123"
        assert entry["promotionIndex"] == 0
