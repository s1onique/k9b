"""Tests for collection command builder and test_collection integration."""
from __future__ import annotations


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
            assert "--ignore" not in cmd, f"include_allowed_ignores=False should skip --ignore: {cmd}"
        finally:
            test_collection.ALLOWED_COLLECTION_EXCLUSIONS = original
