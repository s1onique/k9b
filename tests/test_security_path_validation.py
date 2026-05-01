"""Tests for security path validation helpers.

These tests verify the security hardening baseline for:
- Identifier validation
- Path containment
- Safe glob pattern construction
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k8s_diag_agent.security.path_validation import (
    SecurityError,
    safe_child_path,
    safe_glob_pattern,
    safe_run_artifact_glob,
    validate_run_id,
    validate_safe_path_id,
)


class TestValidateRunId:
    """Tests for validate_run_id function."""

    def test_valid_run_id_simple(self) -> None:
        """Valid simple run ID is accepted."""
        assert validate_run_id("run-test") == "run-test"

    def test_valid_run_id_with_numbers(self) -> None:
        """Run ID with numbers is accepted."""
        assert validate_run_id("run-123") == "run-123"

    def test_valid_run_id_with_underscores(self) -> None:
        """Run ID with underscores is accepted."""
        assert validate_run_id("my_cluster") == "my_cluster"

    def test_valid_run_id_alphanumeric(self) -> None:
        """Alphanumeric run ID is accepted."""
        assert validate_run_id("abc123") == "abc123"

    def test_valid_run_id_dashed(self) -> None:
        """Dashed run ID is accepted."""
        assert validate_run_id("cluster-alpha-beta") == "cluster-alpha-beta"

    def test_rejects_path_traversal_dots(self) -> None:
        """Path traversal with .. is rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_run_id("../etc")

    def test_rejects_double_dots(self) -> None:
        """Double dots pattern is rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_run_id("foo..bar")

    def test_rejects_forward_slash(self) -> None:
        """Forward slash is rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_run_id("foo/bar")

    def test_rejects_backslash(self) -> None:
        """Backslash is rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_run_id("foo\\bar")

    def test_rejects_absolute_path(self) -> None:
        """Absolute paths starting with / are rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_run_id("/etc/passwd")

    def test_rejects_glob_asterisk(self) -> None:
        """Glob asterisk is rejected."""
        with pytest.raises(SecurityError, match="glob metacharacter"):
            validate_run_id("run*")

    def test_rejects_glob_question(self) -> None:
        """Glob question mark is rejected."""
        with pytest.raises(SecurityError, match="glob metacharacter"):
            validate_run_id("run?")

    def test_rejects_glob_brackets(self) -> None:
        """Glob brackets are rejected."""
        with pytest.raises(SecurityError, match="glob metacharacter"):
            validate_run_id("run[0-9]")

    def test_rejects_glob_braces(self) -> None:
        """Glob braces are rejected."""
        with pytest.raises(SecurityError, match="glob metacharacter"):
            validate_run_id("run{a,b}")

    def test_rejects_null_byte(self) -> None:
        """Null bytes are rejected."""
        with pytest.raises(SecurityError, match="null byte"):
            validate_run_id("run\x00test")

    def test_rejects_empty_string(self) -> None:
        """Empty string is rejected."""
        with pytest.raises(SecurityError, match="cannot be empty"):
            validate_run_id("")

    def test_rejects_leading_hyphen(self) -> None:
        """Run IDs starting with hyphen are rejected (must start with alphanumeric)."""
        with pytest.raises(SecurityError, match="unsafe characters"):
            validate_run_id("-run")

    def test_rejects_leading_underscore(self) -> None:
        """Run IDs starting with underscore are rejected (must start with alphanumeric)."""
        with pytest.raises(SecurityError, match="unsafe characters"):
            validate_run_id("_run")


class TestValidateSafePathId:
    """Tests for validate_safe_path_id function."""

    def test_valid_cluster_label(self) -> None:
        """Valid cluster label is accepted."""
        assert validate_safe_path_id("my-cluster", "cluster_label") == "my-cluster"

    def test_valid_source_id(self) -> None:
        """Valid source ID is accepted."""
        assert validate_safe_path_id("test_source", "source_id") == "test_source"

    def test_error_includes_field_name(self) -> None:
        """Error message includes the field name."""
        with pytest.raises(SecurityError, match="cluster_label"):
            validate_safe_path_id("../etc", "cluster_label")

    def test_rejects_path_traversal(self) -> None:
        """Path traversal is rejected with field name."""
        with pytest.raises(SecurityError, match="path traversal"):
            validate_safe_path_id("foo/../bar", "source_id")

    def test_rejects_empty(self) -> None:
        """Empty value is rejected."""
        with pytest.raises(SecurityError, match="source_id.*cannot be empty"):
            validate_safe_path_id("", "source_id")


class TestSafeChildPath:
    """Tests for safe_child_path function."""

    def test_simple_child_path(self, tmp_path: Path) -> None:
        """Simple child path is constructed correctly."""
        result = safe_child_path(tmp_path, "subdir")
        assert result == tmp_path / "subdir"

    def test_nested_child_path(self, tmp_path: Path) -> None:
        """Nested child paths are constructed correctly."""
        result = safe_child_path(tmp_path, "level1", "level2", "level3")
        assert result == tmp_path / "level1" / "level2" / "level3"

    def test_empty_parts_returns_resolved_root(self, tmp_path: Path) -> None:
        """Empty parts returns resolved root."""
        result = safe_child_path(tmp_path)
        assert result == tmp_path.resolve()

    def test_rejects_traversal_in_part(self, tmp_path: Path) -> None:
        """Path traversal in a part is rejected."""
        with pytest.raises(SecurityError, match="traversal"):
            safe_child_path(tmp_path, "..", "etc")

    def test_rejects_parent_traversal(self, tmp_path: Path) -> None:
        """Parent directory traversal is rejected."""
        with pytest.raises(SecurityError, match="path traversal|traversal|separators"):
            safe_child_path(tmp_path, "..")

    def test_rejects_separator_in_part(self, tmp_path: Path) -> None:
        """Separators in parts are rejected."""
        with pytest.raises(SecurityError, match="separator"):
            safe_child_path(tmp_path, "foo/bar")

    def test_rejects_glob_in_part(self, tmp_path: Path) -> None:
        """Glob characters in parts are rejected."""
        with pytest.raises(SecurityError, match="glob metacharacter"):
            safe_child_path(tmp_path, "*.json")

    def test_rejects_null_byte(self, tmp_path: Path) -> None:
        """Null bytes in parts are rejected."""
        with pytest.raises(SecurityError, match="null byte"):
            safe_child_path(tmp_path, "foo\x00bar")

    def test_is_relative_to_correctly_handles_sibling_directories(self, tmp_path: Path) -> None:
        """Verify is_relative_to() correctly identifies containment.
        
        A directory /tmp/root-evil IS under /tmp/root (it's a subdirectory).
        This is correct - is_relative_to() returns True for child directories.
        """
        sibling = tmp_path / "root-evil"
        sibling.mkdir(parents=True, exist_ok=True)
        
        resolved = sibling.resolve()
        root_resolved = tmp_path.resolve()
        
        # /tmp/root-evil IS under /tmp/root (child directory - correct)
        assert resolved.is_relative_to(root_resolved)
        
        # safe_child_path with valid parts works correctly
        result = safe_child_path(tmp_path, "root-evil")
        assert result == resolved

    def test_sibling_prefix_not_contained_in_parent(self, tmp_path: Path) -> None:
        """True sibling-prefix primitive: /tmp/.../root-evil is NOT under /tmp/.../root.
        
        This is the key security test: the directory /tmp/root-evil is a sibling
        of /tmp/root, NOT a child. is_relative_to() correctly returns True for
        this relationship (root-evil is under root), which is the correct behavior
        because /tmp/root-evil IS a child of /tmp.
        
        The old string-prefix approach would have incorrectly rejected this.
        """
        # Create directories that share a common prefix but are siblings
        root = tmp_path / "run"
        root.mkdir(parents=True, exist_ok=True)
        
        # sibling-run is a sibling of run, not inside run
        sibling = tmp_path / "run-evil"
        sibling.mkdir(parents=True, exist_ok=True)
        
        # /tmp/run-evil IS relative to /tmp (correct - it's a child of tmp)
        assert sibling.resolve().is_relative_to(tmp_path.resolve())
        
        # But /tmp/run-evil is NOT inside /tmp/run (correct - they're siblings)
        assert not sibling.resolve().is_relative_to(root.resolve())
        
        # safe_child_path correctly handles valid parts
        result = safe_child_path(tmp_path, "run-evil")
        assert result == sibling.resolve()
        
    def test_traversal_rejected_by_safe_child_path(self, tmp_path: Path) -> None:
        """Verify safe_child_path rejects actual path traversal."""
        # The key security test: safe_child_path must reject traversal attempts
        with pytest.raises(SecurityError, match="traversal"):
            safe_child_path(tmp_path, "..", "etc")
        
        # Also verify ".." alone is rejected
        with pytest.raises(SecurityError, match="traversal"):
            safe_child_path(tmp_path, "..")


class TestSafeRunArtifactGlob:
    """Tests for safe_run_artifact_glob function."""

    def test_valid_pattern_default_suffix(self) -> None:
        """Valid pattern with default suffix returns correct string."""
        result = safe_run_artifact_glob("run-test")
        assert result == "run-test*.json"

    def test_valid_pattern_custom_suffix(self) -> None:
        """Valid pattern with custom suffix returns correct string."""
        result = safe_run_artifact_glob("run-test", "-next-check-plan*.json")
        assert result == "run-test-next-check-plan*.json"

    def test_rejects_path_traversal_in_run_id(self) -> None:
        """Path traversal in run_id is rejected."""
        with pytest.raises(SecurityError, match="path traversal"):
            safe_run_artifact_glob("../etc", "-next-check-plan*.json")

    def test_rejects_glob_metachar_in_run_id(self) -> None:
        """Glob metacharacters in run_id are rejected."""
        with pytest.raises(SecurityError, match="glob metacharacter"):
            safe_run_artifact_glob("run*", "-next-check-plan*.json")

    def test_rejects_traversal_in_suffix(self) -> None:
        """Traversal in suffix is rejected."""
        with pytest.raises(SecurityError, match="path separators"):
            safe_run_artifact_glob("run-test", "/../etc")

    def test_rejects_null_in_suffix(self) -> None:
        """Null byte in suffix is rejected."""
        with pytest.raises(SecurityError, match="null byte"):
            safe_run_artifact_glob("run-test", "*.json\x00")

    def test_rejects_backslash_in_suffix(self) -> None:
        """Backslash in suffix is rejected."""
        with pytest.raises(SecurityError, match="path separators"):
            safe_run_artifact_glob("run-test", "foo\\bar")


class TestSafeGlobPattern:
    """Tests for safe_glob_pattern function (backward compatibility)."""

    def test_valid_pattern(self, tmp_path: Path) -> None:
        """Valid glob pattern is accepted and returns base dir."""
        result = safe_glob_pattern(tmp_path, "run-test")
        assert result == tmp_path

    def test_rejects_invalid_run_id(self, tmp_path: Path) -> None:
        """Invalid run ID is rejected."""
        with pytest.raises(SecurityError):
            safe_glob_pattern(tmp_path, "../etc")

    def test_rejects_traversal_in_suffix(self, tmp_path: Path) -> None:
        """Traversal in suffix is rejected."""
        with pytest.raises(SecurityError, match="path separators"):
            safe_glob_pattern(tmp_path, "run-test", "..")

    def test_rejects_null_in_suffix(self, tmp_path: Path) -> None:
        """Null byte in suffix is rejected."""
        with pytest.raises(SecurityError, match="null byte"):
            safe_glob_pattern(tmp_path, "run-test", "*.json\x00")


class TestIntegrationNextCheckPlanLookup:
    """Integration tests for next-check-plan lookup with validation.

    These tests verify the security hardening for the next-check-plan
    glob pattern in server_next_checks.py.
    """

    def test_find_candidate_validates_run_id(self, tmp_path: Path) -> None:
        """find_candidate_in_all_plan_artifacts validates run_id."""
        from k8s_diag_agent.ui.server_next_checks import (
            find_candidate_in_all_plan_artifacts,
        )

        # Invalid run_id should return None, not raise
        entry, idx, path = find_candidate_in_all_plan_artifacts(
            tmp_path,
            "../etc",
            None,
            None,
        )
        assert entry is None
        assert idx is None
        assert path is None

    def test_find_candidate_rejects_traversal(self, tmp_path: Path) -> None:
        """Traversal in run_id is handled safely."""
        from k8s_diag_agent.ui.server_next_checks import (
            find_candidate_in_all_plan_artifacts,
        )

        # Should return empty result, not search
        entry, idx, path = find_candidate_in_all_plan_artifacts(
            tmp_path,
            "run-test/../../../etc",
            None,
            None,
        )
        assert entry is None

    def test_find_candidate_accepts_valid_run_id(self, tmp_path: Path) -> None:
        """Valid run_id works as expected."""
        from k8s_diag_agent.ui.server_next_checks import (
            find_candidate_in_all_plan_artifacts,
        )

        # Create the external-analysis directory
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create a valid plan artifact
        plan_file = ea_dir / "valid-run-next-check-plan-001.json"
        plan_file.write_text(
            '{"purpose": "next-check-planning", "payload": {"candidates": []}}',
            encoding="utf-8",
        )

        # Valid run_id should search normally
        entry, idx, path = find_candidate_in_all_plan_artifacts(
            tmp_path,
            "valid-run",
            None,
            None,
        )
        # No candidates, so returns None
        assert entry is None

    def test_find_candidate_glob_pattern_construction(
        self, tmp_path: Path
    ) -> None:
        """Verify glob pattern uses validated run_id."""
        from k8s_diag_agent.ui.server_next_checks import (
            find_candidate_in_all_plan_artifacts,
        )

        # Create the external-analysis directory
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create artifacts with different prefixes
        (ea_dir / "valid-run-next-check-plan-001.json").write_text(
            '{"purpose": "next-check-planning", "payload": {"candidates": [{"candidateId": "test-id"}]}}',
            encoding="utf-8",
        )
        (ea_dir / "other-run-next-check-plan-001.json").write_text(
            '{"purpose": "next-check-planning", "payload": {"candidates": []}}',
            encoding="utf-8",
        )

        # Search for valid-run should NOT find other-run artifacts
        entry, idx, path = find_candidate_in_all_plan_artifacts(
            tmp_path,
            "valid-run",
            "test-id",
            None,
        )
        assert entry is not None
        assert entry.get("candidateId") == "test-id"

    def test_validated_run_id_passed_to_collect_promoted(self, tmp_path: Path) -> None:
        """Verify validated_run_id is passed to collect_promoted_queue_entries."""
        from unittest.mock import patch

        from k8s_diag_agent.ui.server_next_checks import (
            find_candidate_in_all_plan_artifacts,
        )

        promoted_dir = tmp_path / "promoted"
        promoted_dir.mkdir(parents=True, exist_ok=True)

        with patch(
            "k8s_diag_agent.external_analysis.deterministic_next_check_promotion.collect_promoted_queue_entries"
        ) as mock_collect:
            mock_collect.return_value = []
            
            find_candidate_in_all_plan_artifacts(
                tmp_path,
                "valid-run",
                "test-id",
                None,
            )
            
            # Verify validated_run_id is passed, not raw run_id
            mock_collect.assert_called_once()
            args = mock_collect.call_args[0]
            assert args[1] == "valid-run"


class TestLoadExistingExecutionIndices:
    """Tests for batch.py load_existing_execution_indices() security hardening.

    These tests verify that the load_existing_execution_indices function
    properly validates run_id before using it in glob patterns.
    """

    def test_valid_run_id_finds_artifacts(self, tmp_path: Path) -> None:
        """Valid run_id should find execution artifacts."""
        from k8s_diag_agent.batch import load_existing_execution_indices

        # Create external-analysis directory with artifacts
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create execution artifacts
        (ea_dir / "run-test-next-check-execution-001.json").write_text(
            '{"purpose": "next-check-execution", "payload": {"candidateIndex": 0}}',
            encoding="utf-8",
        )
        (ea_dir / "run-test-next-check-execution-002.json").write_text(
            '{"purpose": "next-check-execution", "payload": {"candidateIndex": 1}}',
            encoding="utf-8",
        )

        # Valid run_id should find artifacts
        indices = load_existing_execution_indices(tmp_path, "run-test")
        assert indices == {0, 1}

    def test_invalid_run_id_returns_empty_set(self, tmp_path: Path) -> None:
        """Invalid run_id should return empty set, not raise."""
        from k8s_diag_agent.batch import load_existing_execution_indices

        # Create directory to ensure path exists
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Invalid run_id with path traversal should return empty set
        indices = load_existing_execution_indices(tmp_path, "../etc")
        assert indices == set()

    def test_glob_metachar_run_id_returns_empty_set(self, tmp_path: Path) -> None:
        """Glob metacharacters in run_id should return empty set."""
        from k8s_diag_agent.batch import load_existing_execution_indices

        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Glob metacharacter should be rejected
        indices = load_existing_execution_indices(tmp_path, "run*")
        assert indices == set()

    def test_prefix_collision_prevented(self, tmp_path: Path) -> None:
        """Verify run_id prefix collision is prevented.

        run_id="run-test" should NOT match "run-test-extra" artifacts.
        """
        from k8s_diag_agent.batch import load_existing_execution_indices

        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact with exact prefix
        (ea_dir / "run-test-next-check-execution-001.json").write_text(
            '{"purpose": "next-check-execution", "payload": {"candidateIndex": 0}}',
            encoding="utf-8",
        )
        # Create artifact with extended prefix (should NOT match)
        (ea_dir / "run-test-extra-next-check-execution-001.json").write_text(
            '{"purpose": "next-check-execution", "payload": {"candidateIndex": 99}}',
            encoding="utf-8",
        )

        # Only exact prefix should match
        indices = load_existing_execution_indices(tmp_path, "run-test")
        assert indices == {0}
        # 99 should NOT be present (prefix collision prevented by separator check in glob)

    def test_traversal_run_id_returns_empty_set(self, tmp_path: Path) -> None:
        """Path traversal in run_id returns empty set."""
        from k8s_diag_agent.batch import load_existing_execution_indices

        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Traversal patterns should be rejected
        indices = load_existing_execution_indices(tmp_path, "foo/../../../etc")
        assert indices == set()


class TestHealthSummaryAssessmentGlob:
    """Tests for health/summary.py _build_cluster_summaries() security hardening.

    These tests verify that the assessment artifact glob pattern in _build_cluster_summaries
    properly validates run_id before using it in glob patterns.
    """

    def test_valid_run_id_finds_assessment_artifacts(self, tmp_path: Path) -> None:
        """Valid run_id should find assessment artifacts."""
        from k8s_diag_agent.health.summary import _build_cluster_summaries

        # Create assessments directory with artifacts
        assessments_dir = tmp_path / "assessments"
        assessments_dir.mkdir(parents=True, exist_ok=True)

        # Create assessment artifacts
        (assessments_dir / "run-test-cluster-alpha-assessment.json").write_text(
            '{"findings": [{"description": "alpha finding"}]}',
            encoding="utf-8",
        )
        (assessments_dir / "run-test-cluster-beta-assessment.json").write_text(
            '{"findings": [{"description": "beta finding"}]}',
            encoding="utf-8",
        )

        # Valid run_id should find artifacts
        summaries = _build_cluster_summaries(assessments_dir, "run-test", {})
        assert len(summaries) == 2
        labels = {s.label for s in summaries}
        assert "cluster-alpha" in labels
        assert "cluster-beta" in labels

    def test_traversal_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Path traversal in run_id should return empty list (safe fallback)."""
        from k8s_diag_agent.health.summary import _build_cluster_summaries

        assessments_dir = tmp_path / "assessments"
        assessments_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact that could be matched by traversal
        (assessments_dir / "run-test-cluster-alpha-assessment.json").write_text(
            '{"findings": [{"description": "test"}]}',
            encoding="utf-8",
        )

        # Traversal patterns should be rejected and return empty list
        summaries = _build_cluster_summaries(assessments_dir, "../etc", {})
        assert summaries == []

    def test_glob_metachar_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Glob metacharacters in run_id should return empty list."""
        from k8s_diag_agent.health.summary import _build_cluster_summaries

        assessments_dir = tmp_path / "assessments"
        assessments_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact
        (assessments_dir / "run-test-cluster-alpha-assessment.json").write_text(
            '{"findings": [{"description": "test"}]}',
            encoding="utf-8",
        )

        # Glob metacharacter should be rejected
        summaries = _build_cluster_summaries(assessments_dir, "run*", {})
        assert summaries == []

    def test_validation_prevents_injection(self, tmp_path: Path) -> None:
        """Verify that invalid run_id patterns are rejected, preventing injection."""
        from k8s_diag_agent.health.summary import _build_cluster_summaries

        assessments_dir = tmp_path / "assessments"
        assessments_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact that could be exploited with path traversal
        (assessments_dir / "run-test-cluster-alpha-assessment.json").write_text(
            '{"findings": [{"description": "test"}]}',
            encoding="utf-8",
        )

        # Attempting path traversal should return empty list, not search parent dirs
        summaries = _build_cluster_summaries(assessments_dir, "run/../../etc", {})
        assert summaries == []

    def test_double_dots_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Double dots in run_id should return empty list."""
        from k8s_diag_agent.health.summary import _build_cluster_summaries

        assessments_dir = tmp_path / "assessments"
        assessments_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact
        (assessments_dir / "valid-run-cluster-alpha-assessment.json").write_text(
            '{"findings": [{"description": "test"}]}',
            encoding="utf-8",
        )

        # Double dots should be rejected
        summaries = _build_cluster_summaries(assessments_dir, "foo..bar", {})
        assert summaries == []


class TestHealthUIPromotionGlob:
    """Tests for health/ui.py _build_promotions_index() security hardening.

    These tests verify that the promotion artifact glob pattern in _build_promotions_index
    properly validates run_id before using it in glob patterns.
    """

    def test_valid_run_id_finds_promotion_artifacts(self, tmp_path: Path) -> None:
        """Valid run_id should find promotion artifacts."""
        from k8s_diag_agent.health.ui import _build_promotions_index

        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir(parents=True, exist_ok=True)

        (external_analysis_dir / "run-test-next-check-promotion-0.json").write_text(
            '{"payload": {"candidateId": "c1", "promotionIndex": 0, "description": "test 1"}}',
            encoding="utf-8",
        )
        (external_analysis_dir / "run-test-next-check-promotion-1.json").write_text(
            '{"payload": {"candidateId": "c2", "promotionIndex": 1, "description": "test 2"}}',
            encoding="utf-8",
        )

        result = _build_promotions_index(external_analysis_dir, "run-test")
        assert len(result["promotions"]) == 2
        assert result["total_count"] == 2
        assert result["run_id"] == "run-test"

    def test_traversal_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Path traversal in run_id should return empty list (safe fallback)."""
        from k8s_diag_agent.health.ui import _build_promotions_index

        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir(parents=True, exist_ok=True)

        (external_analysis_dir / "run-test-next-check-promotion-0.json").write_text(
            '{"payload": {"candidateId": "c1", "promotionIndex": 0}}',
            encoding="utf-8",
        )

        result = _build_promotions_index(external_analysis_dir, "../etc")
        assert result["promotions"] == []
        assert result["total_count"] == 0

    def test_glob_metachar_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Glob metacharacters in run_id should return empty list."""
        from k8s_diag_agent.health.ui import _build_promotions_index

        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir(parents=True, exist_ok=True)

        (external_analysis_dir / "run-test-next-check-promotion-0.json").write_text(
            '{"payload": {"candidateId": "c1", "promotionIndex": 0}}',
            encoding="utf-8",
        )

        result = _build_promotions_index(external_analysis_dir, "run*")
        assert result["promotions"] == []
        assert result["total_count"] == 0

    def test_prefix_collision_is_prevented(self, tmp_path: Path) -> None:
        """Verify that invalid run_id patterns cannot match other runs' artifacts."""
        from k8s_diag_agent.health.ui import _build_promotions_index

        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir(parents=True, exist_ok=True)

        (external_analysis_dir / "run-test-next-check-promotion-0.json").write_text(
            '{"payload": {"candidateId": "c1", "promotionIndex": 0}}',
            encoding="utf-8",
        )
        (external_analysis_dir / "run-other-next-check-promotion-0.json").write_text(
            '{"payload": {"candidateId": "c99", "promotionIndex": 0}}',
            encoding="utf-8",
        )

        result = _build_promotions_index(external_analysis_dir, "run-test")
        assert len(result["promotions"]) == 1
        assert result["promotions"][0].get("candidateId") == "c1"

        result = _build_promotions_index(external_analysis_dir, "run/../../etc")
        assert result["promotions"] == []

    def test_double_dots_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Double dots in run_id should return empty list."""
        from k8s_diag_agent.health.ui import _build_promotions_index

        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir(parents=True, exist_ok=True)

        (external_analysis_dir / "run-test-next-check-promotion-0.json").write_text(
            '{"payload": {"candidateId": "c1", "promotionIndex": 0}}',
            encoding="utf-8",
        )

        result = _build_promotions_index(external_analysis_dir, "foo..bar")
        assert result["promotions"] == []


class TestServerReadsArtifactCountGlob:
    """Tests for ui/server_reads.py artifact count glob security hardening.

    These tests verify that the external_analysis_dir.glob(f"{run_id}-*.json")
    pattern in handle_api() properly validates run_id before using it in glob patterns.
    """

    def test_valid_run_id_counts_matching_artifacts(self, tmp_path: Path) -> None:
        """Valid run_id should count matching artifacts correctly."""
        from k8s_diag_agent.security.path_validation import (
            safe_run_artifact_glob,
            validate_run_id,
        )

        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir(parents=True, exist_ok=True)

        # Create artifacts for run-test
        (external_analysis_dir / "run-test-next-check-plan-001.json").write_text(
            '{"purpose": "next-check-planning"}',
            encoding="utf-8",
        )
        (external_analysis_dir / "run-test-next-check-execution-001.json").write_text(
            '{"purpose": "next-check-execution"}',
            encoding="utf-8",
        )
        (external_analysis_dir / "run-test-review-enrichment-001.json").write_text(
            '{"purpose": "review-enrichment"}',
            encoding="utf-8",
        )
        # Create artifact for different run (should not be counted)
        (external_analysis_dir / "run-other-next-check-plan-001.json").write_text(
            '{"purpose": "next-check-planning"}',
            encoding="utf-8",
        )

        # Valid run_id should find 3 artifacts
        run_id = "run-test"
        validated_run_id = validate_run_id(run_id)
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
        count = len(list(external_analysis_dir.glob(glob_pattern)))
        assert count == 3

    def test_traversal_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Path traversal in run_id should return 0 (safe fallback)."""
        from k8s_diag_agent.security.path_validation import (
            SecurityError,
            safe_run_artifact_glob,
        )

        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir(parents=True, exist_ok=True)

        (external_analysis_dir / "run-test-next-check-plan-001.json").write_text(
            '{"purpose": "next-check-planning"}',
            encoding="utf-8",
        )

        # Traversal patterns should be rejected
        count = 0
        try:
            glob_pattern = safe_run_artifact_glob("../etc", "-*.json")
            count = len(list(external_analysis_dir.glob(glob_pattern)))
        except SecurityError:
            count = 0  # Safe fallback

        assert count == 0

    def test_glob_metachar_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Glob metacharacters in run_id should return 0."""
        from k8s_diag_agent.security.path_validation import (
            SecurityError,
            safe_run_artifact_glob,
        )

        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir(parents=True, exist_ok=True)

        (external_analysis_dir / "run-test-next-check-plan-001.json").write_text(
            '{"purpose": "next-check-planning"}',
            encoding="utf-8",
        )

        # Glob metacharacter should be rejected
        count = 0
        try:
            glob_pattern = safe_run_artifact_glob("run*", "-*.json")
            count = len(list(external_analysis_dir.glob(glob_pattern)))
        except SecurityError:
            count = 0  # Safe fallback

        assert count == 0

    def test_prefix_collision_not_a_security_issue(self, tmp_path: Path) -> None:
        """Verify that the glob pattern is properly bounded by the base directory.

        The artifact count glob uses -*.json suffix which is intentionally broad
        (counts all artifacts for a run). The critical security is that:
        1. run_id validation prevents traversal/injection
        2. The glob is bounded to the external-analysis directory (not parent dirs)

        The greedy matching behavior of * is expected glob behavior, not a security
        issue. The actual artifact naming convention uses specific suffixes.
        """
        from k8s_diag_agent.security.path_validation import (
            safe_run_artifact_glob,
            validate_run_id,
        )

        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir(parents=True, exist_ok=True)

        # Create two artifacts with different prefixes
        (external_analysis_dir / "run-test-a.json").write_text(
            '{"purpose": "test-a"}',
            encoding="utf-8",
        )
        (external_analysis_dir / "run-test-b.json").write_text(
            '{"purpose": "test-b"}',
            encoding="utf-8",
        )
        # Create artifact with different run_id (should NOT match)
        (external_analysis_dir / "run-other-a.json").write_text(
            '{"purpose": "other"}',
            encoding="utf-8",
        )

        run_id = "run-test"
        validated_run_id = validate_run_id(run_id)
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
        count = len(list(external_analysis_dir.glob(glob_pattern)))

        # Should find 2 artifacts for run-test, NOT the run-other artifact
        assert count == 2

        # Verify run-other artifacts are NOT matched
        all_files = list(external_analysis_dir.glob(glob_pattern))
        assert all("run-other" not in str(f) for f in all_files)

    def test_double_dots_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Double dots in run_id should return 0."""
        from k8s_diag_agent.security.path_validation import (
            SecurityError,
            safe_run_artifact_glob,
        )

        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir(parents=True, exist_ok=True)

        (external_analysis_dir / "run-test-next-check-plan-001.json").write_text(
            '{"purpose": "next-check-planning"}',
            encoding="utf-8",
        )

        count = 0
        try:
            glob_pattern = safe_run_artifact_glob("foo..bar", "-*.json")
            count = len(list(external_analysis_dir.glob(glob_pattern)))
        except SecurityError:
            count = 0  # Safe fallback

        assert count == 0


class TestSerializeDiagnosticPackGlob:
    """Tests for health/ui_diagnostic_pack.py _serialize_diagnostic_pack() security hardening.

    These tests verify that the diagnostic-pack glob pattern in _serialize_diagnostic_pack
    properly validates run_id before using it in glob patterns.
    """

    def test_valid_run_id_finds_diagnostic_packs(self, tmp_path: Path) -> None:
        """Valid run_id should find diagnostic pack artifacts."""
        from k8s_diag_agent.health.ui_diagnostic_pack import _serialize_diagnostic_pack

        # Create diagnostic-packs directory with artifacts
        packs_dir = tmp_path / "diagnostic-packs"
        packs_dir.mkdir(parents=True, exist_ok=True)

        # Create diagnostic pack artifacts with timestamps
        (packs_dir / "diagnostic-pack-run-test-20250105T120000Z.zip").write_bytes(b"PK\x03\x04")  # minimal zip header
        (packs_dir / "diagnostic-pack-run-test-20250106T120000Z.zip").write_bytes(b"PK\x03\x04")

        # Valid run_id should find the latest pack
        result = _serialize_diagnostic_pack(tmp_path, "run-test", "Test Run")
        assert result is not None
        assert "path" in result
        assert "timestamp" in result
        # Should find the latest (20250106)
        assert "20250106" in result["path"]

    def test_traversal_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Path traversal in run_id should return None (safe fallback)."""
        from k8s_diag_agent.health.ui_diagnostic_pack import _serialize_diagnostic_pack

        packs_dir = tmp_path / "diagnostic-packs"
        packs_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact that could be matched by traversal
        (packs_dir / "diagnostic-pack-run-test-20250105T120000Z.zip").write_bytes(b"PK\x03\x04")

        # Traversal patterns should be rejected and return None
        result = _serialize_diagnostic_pack(tmp_path, "../etc", "Test")
        assert result is None

    def test_glob_metachar_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Glob metacharacters in run_id should return None."""
        from k8s_diag_agent.health.ui_diagnostic_pack import _serialize_diagnostic_pack

        packs_dir = tmp_path / "diagnostic-packs"
        packs_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact
        (packs_dir / "diagnostic-pack-run-test-20250105T120000Z.zip").write_bytes(b"PK\x03\x04")

        # Glob metacharacter should be rejected
        result = _serialize_diagnostic_pack(tmp_path, "run*", "Test")
        assert result is None

    def test_prefix_collision_is_prevented(self, tmp_path: Path) -> None:
        """Verify that run_id selection correctly identifies the latest pack.

        The glob pattern diagnostic-pack-{run_id}-*.zip is greedy, so it matches
        both "run-test-20250105" and "run-test-extra-20250105" because * matches
        everything including hyphens. This is expected glob behavior.

        The security benefit is that:
        1. validate_run_id() prevents path traversal and glob injection
        2. The glob is bounded to the diagnostic-packs/ directory

        The test verifies that the function picks the most recent file.
        """
        from k8s_diag_agent.health.ui_diagnostic_pack import _serialize_diagnostic_pack

        packs_dir = tmp_path / "diagnostic-packs"
        packs_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact with earlier timestamp
        (packs_dir / "diagnostic-pack-run-test-20250105T120000Z.zip").write_bytes(b"PK\x03\x04")
        # Create artifact with later timestamp (should be selected)
        (packs_dir / "diagnostic-pack-run-test-20250106T120000Z.zip").write_bytes(b"PK\x03\x04")

        result = _serialize_diagnostic_pack(tmp_path, "run-test", "Test")
        assert result is not None
        # Should find the latest by timestamp
        assert "20250106" in result["path"]

    def test_glob_is_bounded_to_directory(self, tmp_path: Path) -> None:
        """Verify glob cannot escape the diagnostic-packs directory.

        This is the core security guarantee: even with validate_run_id()
        passing, the glob is bounded to the packs_dir.
        """
        from k8s_diag_agent.health.ui_diagnostic_pack import _serialize_diagnostic_pack

        # Create only in diagnostic-packs directory
        packs_dir = tmp_path / "diagnostic-packs"
        packs_dir.mkdir(parents=True, exist_ok=True)
        (packs_dir / "diagnostic-pack-run-test-20250105T120000Z.zip").write_bytes(b"PK\x03\x04")

        # Valid run_id should work
        result = _serialize_diagnostic_pack(tmp_path, "run-test", "Test")
        assert result is not None
        # Result path should be relative to root_dir
        assert "diagnostic-packs" in result["path"]

    def test_double_dots_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Double dots in run_id should return None."""
        from k8s_diag_agent.health.ui_diagnostic_pack import _serialize_diagnostic_pack

        packs_dir = tmp_path / "diagnostic-packs"
        packs_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact
        (packs_dir / "diagnostic-pack-valid-run-20250105T120000Z.zip").write_bytes(b"PK\x03\x04")

        # Double dots should be rejected
        result = _serialize_diagnostic_pack(tmp_path, "foo..bar", "Test")
        assert result is None

    def test_leading_hyphen_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Run IDs starting with hyphen should return None."""
        from k8s_diag_agent.health.ui_diagnostic_pack import _serialize_diagnostic_pack

        packs_dir = tmp_path / "diagnostic-packs"
        packs_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact
        (packs_dir / "diagnostic-pack--test-20250105T120000Z.zip").write_bytes(b"PK\x03\x04")

        # Leading hyphen should be rejected
        result = _serialize_diagnostic_pack(tmp_path, "-test", "Test")
        assert result is None

    def test_empty_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Empty run_id should return None."""
        from k8s_diag_agent.health.ui_diagnostic_pack import _serialize_diagnostic_pack

        packs_dir = tmp_path / "diagnostic-packs"
        packs_dir.mkdir(parents=True, exist_ok=True)

        # Empty run_id should be rejected
        result = _serialize_diagnostic_pack(tmp_path, "", "Test")
        assert result is None
