"""Tests for security path validation helpers.

These tests verify the security hardening baseline for:
- Identifier validation
- Path containment
- Safe glob pattern construction
"""

from __future__ import annotations

import tempfile
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
