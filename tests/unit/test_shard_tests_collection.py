"""Tests for collection command builder and test_collection integration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestCollectionCommandBuilder:
    """Tests for collection command building with allowlist integration."""

    def test_empty_allowlist_produces_no_ignore_flags(self) -> None:
        import test_collection

        original = test_collection.ALLOWED_COLLECTION_EXCLUSIONS
        test_collection.ALLOWED_COLLECTION_EXCLUSIONS = set()

        try:
            cmd = test_collection.build_collection_command()
            assert "--ignore" not in cmd, f"Empty allowlist should not produce --ignore: {cmd}"
            assert "tests/" in cmd
        finally:
            test_collection.ALLOWED_COLLECTION_EXCLUSIONS = original

    def test_allowlist_produces_ignore_flags(self) -> None:
        import test_collection

        original = test_collection.ALLOWED_COLLECTION_EXCLUSIONS
        test_collection.ALLOWED_COLLECTION_EXCLUSIONS = {
            "tests/unit/test_foo.py",
            "tests/unit/test_bar.py",
        }

        try:
            cmd = test_collection.build_collection_command()
            assert "--ignore" in cmd, f"Non-empty allowlist should produce --ignore: {cmd}"
            assert "tests/unit/test_foo.py" in cmd
            assert "tests/unit/test_bar.py" in cmd
        finally:
            test_collection.ALLOWED_COLLECTION_EXCLUSIONS = original

    def test_ignore_flags_are_separate_arguments(self) -> None:
        import test_collection

        original = test_collection.ALLOWED_COLLECTION_EXCLUSIONS
        test_collection.ALLOWED_COLLECTION_EXCLUSIONS = {"tests/excluded.py"}

        try:
            cmd = test_collection.build_collection_command()
            ignore_idx = cmd.index("--ignore")
            assert cmd[ignore_idx + 1] == "tests/excluded.py"
        finally:
            test_collection.ALLOWED_COLLECTION_EXCLUSIONS = original

    def test_extra_args_appended(self) -> None:
        import test_collection

        cmd = test_collection.build_collection_command(extra_args=["--verbose", "-x"])
        assert "--verbose" in cmd
        assert "-x" in cmd
        assert cmd.index("--verbose") < cmd.index("tests/")
        assert cmd.index("-x") < cmd.index("tests/")

    def test_include_allowed_ignores_false_skips_ignores(self) -> None:
        import test_collection

        original = test_collection.ALLOWED_COLLECTION_EXCLUSIONS
        test_collection.ALLOWED_COLLECTION_EXCLUSIONS = {"tests/excluded.py"}

        try:
            cmd = test_collection.build_collection_command(include_allowed_ignores=False)
            assert "--ignore" not in cmd, f"include_allowed_ignores_false should skip --ignore: {cmd}"
        finally:
            test_collection.ALLOWED_COLLECTION_EXCLUSIONS = original


class TestCollectTestNodeidsLenient:
    """Tests for lenient collection behavior when pytest has partial errors."""

    def test_returns_zero_when_nodeids_collected_with_errors(self) -> None:
        """Collection returns success (rc=0) when nodeids are collected despite pytest errors.
        
        This is the key fix: pytest may return rc=2 due to import errors in some files,
        but if we successfully collected nodeids from other files, we should treat it
        as success and proceed with sharding.
        """
        import test_collection
        
        # Mock subprocess.run to simulate pytest returning rc=2 but with nodeids
        mock_result = MagicMock()
        mock_result.returncode = 2  # pytest error due to import issues
        mock_result.stdout = "tests/unit/test_foo.py::test_one\ntests/unit/test_foo.py::test_two\n"
        mock_result.stderr = "ERROR collecting tests/test_bar.py - ImportError"
        
        with patch("subprocess.run", return_value=mock_result):
            result = test_collection.collect_test_nodeids()
        
        # Should return success because we got nodeids
        assert result.returncode == 0
        assert result.raw_returncode == 2  # Raw rc preserved for diagnostics
        assert len(result.nodeids) == 2
        assert "tests/unit/test_foo.py::test_one" in result.nodeids
        # Properties should work
        assert result.usable_for_sharding is True
        assert result.had_collection_errors is True

    def test_returns_nonzero_when_no_nodeids_collected(self) -> None:
        """Collection returns pytest's rc when no nodeids are collected."""
        import test_collection
        
        # Mock subprocess.run to simulate pytest returning rc=1 with no nodeids
        mock_result = MagicMock()
        mock_result.returncode = 1  # pytest fatal error
        mock_result.stdout = ""  # no nodeids
        mock_result.stderr = "FATAL: no tests found"
        
        with patch("subprocess.run", return_value=mock_result):
            result = test_collection.collect_test_nodeids()
        
        # Should return the actual returncode since no nodeids were collected
        assert result.returncode == 1
        assert result.raw_returncode == 1
        assert len(result.nodeids) == 0
        assert result.usable_for_sharding is False
        assert result.had_collection_errors is True
