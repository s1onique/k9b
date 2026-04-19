"""Tests for external analysis utils module.

Tests cover:
- artifact_matches_run utility function
- Edge cases in artifact path matching
- Error handling for various input scenarios
"""

import unittest

from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisArtifact
from k8s_diag_agent.external_analysis.utils import artifact_matches_run


class TestArtifactMatchesRun(unittest.TestCase):
    """Tests for artifact_matches_run function."""

    def test_returns_true_when_run_id_exact_match(self) -> None:
        """Test that exact run_id match returns True."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-123",
            cluster_label="cluster-a",
        )

        result = artifact_matches_run(artifact, "run-123")

        self.assertTrue(result)

    def test_returns_false_when_run_id_no_match(self) -> None:
        """Test that non-matching run_id returns False."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-456",
            cluster_label="cluster-a",
        )

        result = artifact_matches_run(artifact, "run-123")

        self.assertFalse(result)

    def test_returns_true_when_artifact_path_starts_with_run_id_dash(self) -> None:
        """Test that path with run_id as prefix returns True."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/some/path/run-123-analysis-output.json",
        )

        result = artifact_matches_run(artifact, "run-123")

        self.assertTrue(result)

    def test_returns_false_when_artifact_path_does_not_start_with_run_id(self) -> None:
        """Test that path without matching prefix returns False."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/some/path/other-run-123-analysis.json",
        )

        result = artifact_matches_run(artifact, "run-123")

        self.assertFalse(result)

    def test_returns_false_when_artifact_path_is_none(self) -> None:
        """Test that None artifact_path returns False."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path=None,
        )

        result = artifact_matches_run(artifact, "run-123")

        self.assertFalse(result)

    def test_returns_true_when_run_id_match_takes_precedence(self) -> None:
        """Test that run_id match is checked first."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-123",
            cluster_label="cluster-a",
            artifact_path="/other/path/run-456-extra.json",
        )

        # Even though artifact_path suggests run-456, run_id match should win
        result = artifact_matches_run(artifact, "run-123")

        self.assertTrue(result)

    def test_uses_only_filename_for_path_matching(self) -> None:
        """Test that only the filename portion is used for path matching."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/very/nested/path/run-789-results.json",
        )

        result = artifact_matches_run(artifact, "run-789")

        self.assertTrue(result)

    def test_path_prefix_must_include_dash_after_run_id(self) -> None:
        """Test that path prefix must include dash separator."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/path/run-12345-extra.json",
        )

        # "run-123" is a prefix of "run-12345" but not a complete run_id match
        # Requires "run-123-" not just "run-123"
        result = artifact_matches_run(artifact, "run-123")

        self.assertFalse(result)

    def test_exact_filename_match_with_dash_suffix(self) -> None:
        """Test that exact run_id followed by dash in filename works."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-other",
            cluster_label="cluster-a",
            artifact_path="/path/run-abc--results.json",
        )

        # Filename is "run-abc--results.json", starts with "run-abc-"
        result = artifact_matches_run(artifact, "run-abc")

        self.assertTrue(result)


class TestArtifactMatchesRunEdgeCases(unittest.TestCase):
    """Tests for edge cases in artifact_matches_run function."""

    def test_empty_run_id_string(self) -> None:
        """Test behavior with empty run_id.

        When run_id is empty, the path prefix becomes just "-".
        Since the filename doesn't start with "-", it returns False.
        """
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="some-run",
            cluster_label="cluster-a",
            artifact_path="/path/run-suffix.json",
        )

        result = artifact_matches_run(artifact, "")

        # Empty run_id creates prefix "-", filename doesn't start with "-"
        self.assertFalse(result)

    def test_artifact_path_with_special_characters(self) -> None:
        """Test path matching with special characters in filename."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/path/run-special-analysis-results.json",
        )

        result = artifact_matches_run(artifact, "run-special")

        self.assertTrue(result)

    def test_artifact_path_with_underscore_instead_of_dash(self) -> None:
        """Test that underscore is not a valid separator - dash is required."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/path/run_underscore_extra.json",
        )

        # Underscore does not satisfy the dash requirement
        result = artifact_matches_run(artifact, "run_underscore")

        self.assertFalse(result)

    def test_artifact_path_with_spaces(self) -> None:
        """Test path matching with spaces in filename."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/path/run spaces-extra.json",
        )

        result = artifact_matches_run(artifact, "run spaces")

        self.assertTrue(result)

    def test_artifact_path_with_unicode(self) -> None:
        """Test path matching with unicode characters."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/path/run-тест-results.json",
        )

        result = artifact_matches_run(artifact, "run-тест")

        self.assertTrue(result)

    def test_very_long_run_id(self) -> None:
        """Test with a very long run_id."""
        long_run_id = "run-" + "a" * 500
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-short",
            cluster_label="cluster-a",
            artifact_path=f"/path/{long_run_id}-extra.json",
        )

        result = artifact_matches_run(artifact, long_run_id)

        self.assertTrue(result)

    def test_artifact_path_only_filename_without_dash_suffix(self) -> None:
        """Test with artifact path that is just a filename without dash suffix."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",  # Different from artifact_path name
            cluster_label="cluster-a",
            artifact_path="run-xyz",
        )

        # Path("run-xyz").name returns "run-xyz" which doesn't start with "run-xyz-"
        result = artifact_matches_run(artifact, "run-xyz")

        self.assertFalse(result)

    def test_artifact_path_with_run_id_match(self) -> None:
        """Test with artifact path whose filename matches target run_id."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/some/path/run-match-extra.json",
        )

        result = artifact_matches_run(artifact, "run-match")

        self.assertTrue(result)

    def test_path_with_multiple_dashes(self) -> None:
        """Test path matching when run_id appears multiple times."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-other",
            cluster_label="cluster-a",
            artifact_path="/path/run-abc-run-abc-results.json",
        )

        # Should match because filename starts with "run-abc-"
        result = artifact_matches_run(artifact, "run-abc")

        self.assertTrue(result)

    def test_path_without_dash_suffix(self) -> None:
        """Test path matching without dash suffix - should fail."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-other",
            cluster_label="cluster-a",
            artifact_path="/path/run-noext.json",
        )

        result = artifact_matches_run(artifact, "run-noext")

        self.assertFalse(result)

    def test_path_with_only_extension(self) -> None:
        """Test path matching where filename is just the prefix with dash."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-other",
            cluster_label="cluster-a",
            artifact_path="/path/run-only-.json",
        )

        result = artifact_matches_run(artifact, "run-only")

        self.assertTrue(result)

    def test_path_with_dash_in_middle(self) -> None:
        """Test path matching where run_id has a dash in the middle."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-other",
            cluster_label="cluster-a",
            artifact_path="/path/run-mid-dash-extra.json",
        )

        result = artifact_matches_run(artifact, "run-mid-dash")

        self.assertTrue(result)


class TestArtifactMatchesRunErrorHandling(unittest.TestCase):
    """Tests for error handling in artifact_matches_run function."""

    def test_handles_empty_artifact_path_string(self) -> None:
        """Test that empty string artifact_path is handled gracefully."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="",
        )

        # Empty string path - Path("").name returns ""
        # "".startswith("run-123-") is False
        result = artifact_matches_run(artifact, "run-123")

        self.assertFalse(result)

    def test_handles_whitespace_only_path(self) -> None:
        """Test that whitespace-only artifact_path is handled."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="   ",
        )

        # Path("   ").name returns "   "
        # "   ".startswith("run-123-") is False
        result = artifact_matches_run(artifact, "run-123")

        self.assertFalse(result)

    def test_handles_path_with_leading_slash(self) -> None:
        """Test path with leading slash."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/leading/slash/run-test-extra.json",
        )

        result = artifact_matches_run(artifact, "run-test")

        self.assertTrue(result)

    def test_handles_path_with_windows_style_separator(self) -> None:
        """Test path with Windows-style separators (on non-Windows).

        On macOS/Linux, Path doesn't parse Windows paths correctly,
        so the whole string becomes the filename.
        """
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="C:\\Users\\test\\run-win-extra.json",
        )

        # On macOS/Linux, the entire string becomes the filename
        # It starts with "C:\", not "run-win-"
        result = artifact_matches_run(artifact, "run-win")

        self.assertFalse(result)

    def test_handles_windows_path_where_only_run_id_matches(self) -> None:
        """Test Windows path where only the run_id matches (not the path)."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-win",  # Matches the target
            cluster_label="cluster-a",
            artifact_path="C:\\Users\\test\\other-name.json",
        )

        # run_id matches directly
        result = artifact_matches_run(artifact, "run-win")

        self.assertTrue(result)

    def test_run_id_matching_is_case_sensitive(self) -> None:
        """Test that run_id matching is case-sensitive."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="RUN-UPPER",
            cluster_label="cluster-a",
        )

        # Case-sensitive comparison
        result_lower = artifact_matches_run(artifact, "run-upper")
        result_upper = artifact_matches_run(artifact, "RUN-UPPER")

        self.assertFalse(result_lower)
        self.assertTrue(result_upper)

    def test_path_matching_is_case_sensitive(self) -> None:
        """Test that path-based matching is case-sensitive."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="/path/RUN-CAPS-extra.json",
        )

        result_lower = artifact_matches_run(artifact, "run-caps")
        result_upper = artifact_matches_run(artifact, "RUN-CAPS")

        self.assertFalse(result_lower)
        self.assertTrue(result_upper)

    def test_artifact_with_run_id_match_not_path(self) -> None:
        """Test artifact where run_id matches even though path doesn't."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-abc",
            cluster_label="cluster-a",
            artifact_path="/some/other/run-xyz.json",
        )

        result = artifact_matches_run(artifact, "run-abc")

        # run_id matches directly, so True
        self.assertTrue(result)

    def test_artifact_with_nonexistent_path(self) -> None:
        """Test artifact with path to a file that doesn't exist on disk."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-other",
            cluster_label="cluster-a",
            artifact_path="/nonexistent/path/run-test-extra.json",
        )

        # Function doesn't check if file exists, only parses the string
        result = artifact_matches_run(artifact, "run-test")

        self.assertTrue(result)

    def test_path_with_double_slash(self) -> None:
        """Test path with double slashes."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-different",
            cluster_label="cluster-a",
            artifact_path="//leading//double//slashes//run-dbl-extra.json",
        )

        result = artifact_matches_run(artifact, "run-dbl")

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
