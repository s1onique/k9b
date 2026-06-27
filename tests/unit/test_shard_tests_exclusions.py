"""Tests for exclusion policy and hard-coded ignore regression guard."""
from __future__ import annotations

from pathlib import Path


class TestRegressionGuard:
    """Tests for the hard-coded ignore regression guard."""

    def test_no_hard_coded_ignores_in_shard_tests(self) -> None:
        """Verify shard_tests.py has no hard-coded --ignore=tests/... literals."""
        import test_collection

        shard_tests_path = Path(__file__).parent.parent.parent / "scripts" / "shard_tests.py"
        violations = test_collection.check_for_hard_coded_ignores(shard_tests_path)

        assert len(violations) == 0, (
            "Found hard-coded --ignore=tests/... in shard_tests.py:\n"
            + "\n".join(violations)
        )

    def test_no_hard_coded_ignores_in_verify_test_exclusions(self) -> None:
        """Verify verify_test_exclusions.py has no hard-coded --ignore=tests/... literals."""
        import test_collection

        verify_path = Path(__file__).parent.parent.parent / "scripts" / "verify_test_exclusions.py"
        violations = test_collection.check_for_hard_coded_ignores(verify_path)

        assert len(violations) == 0, (
            "Found hard-coded --ignore=tests/... in verify_test_exclusions.py:\n"
            + "\n".join(violations)
        )

    def test_no_hard_coded_ignores_in_test_collection(self) -> None:
        """Verify test_collection.py itself has no hard-coded --ignore=tests/... literals."""
        import test_collection

        collection_path = Path(__file__).parent.parent.parent / "scripts" / "test_collection.py"
        violations = test_collection.check_for_hard_coded_ignores(collection_path)

        assert len(violations) == 0, (
            "Found hard-coded --ignore=tests/... in test_collection.py:\n"
            + "\n".join(violations)
        )

    def test_allowlist_exclusions_match_expected_state(self) -> None:
        """Verify ALLOWED_COLLECTION_EXCLUSIONS matches documented policy."""
        import test_collection

        # Current state: no exclusions
        assert len(test_collection.ALLOWED_COLLECTION_EXCLUSIONS) == 0, (
            "ALLOWED_COLLECTION_EXCLUSIONS should be empty when no files are broken"
        )

    def test_verify_no_hard_coded_ignores_passes(self) -> None:
        """Verify the full regression guard check passes."""
        import test_collection

        passed, violations = test_collection.verify_no_hard_coded_ignores()

        assert passed, (
            "Regression guard failed:\n"
            + "".join(violations)
        )

    def test_ast_guard_catches_multiline_ignore_pattern(self, tmp_path: Path) -> None:
        import test_collection

        # Create a temporary file with the stale multiline pattern
        test_file = tmp_path / "test_stale.py"
        stale_code = '''
import subprocess
import sys

def bad_function():
    result = subprocess.run([
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "--ignore=tests/test_rollout_classifier_extended.py",
        "tests/",
    ])
    return result
'''
        test_file.write_text(stale_code)

        violations = test_collection.check_for_hard_coded_ignores(test_file)

        assert len(violations) == 1, f"AST guard should catch multiline --ignore pattern. Got: {violations}"
        assert "test_rollout_classifier_extended.py" in violations[0]

    def test_ast_guard_cannot_catch_split_argument_ignore_pattern(self, tmp_path: Path) -> None:
        """Split-argument patterns are an explicit non-goal (documented in test_exclusions.md)."""
        import test_collection

        test_file = tmp_path / "test_split.py"
        # This is split into two separate strings - AST guard cannot catch this
        split_code = '''
import subprocess
import sys

def bad_function():
    result = subprocess.run([
        sys.executable,
        "-m",
        "pytest",
        "--ignore",
        "tests/foo.py",
        "tests/",
    ])
    return result
'''
        test_file.write_text(split_code)

        violations = test_collection.check_for_hard_coded_ignores(test_file)

        # AST guard cannot detect split-argument patterns
        # This is a known limitation - the guard catches --ignore=tests/... in one string
        assert len(violations) == 0, f"AST guard should NOT catch split-argument pattern: {violations}"

    def test_ast_guard_ignores_code_mention(self, tmp_path: Path) -> None:
        """Verify AST-based guard only catches actual command strings, not code mentions."""
        import test_collection

        test_file = tmp_path / "test_mentions.py"
        # This is valid code that mentions ignore but doesn't use it
        code = 'example = "--ignore=tests/foo.py"\n'
        test_file.write_text(code)

        violations = test_collection.check_for_hard_coded_ignores(test_file)

        # This should be caught since it's a string constant with the pattern
        # The guard is intentionally conservative
        assert len(violations) == 1, f"AST guard should catch string constants. Got: {violations}"
