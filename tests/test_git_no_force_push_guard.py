#!/usr/bin/env python3
"""Tests for git_no_force_push_guard module."""

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from git_no_force_push_guard import (
    GuardResult,
    check_command_line_args,
    check_push,
    check_stdin_updates,
    is_protected_ref,
    parse_pre_push_stdin,
)


class TestIsProtectedRef:
    def test_exact_match_main(self) -> None:
        protected_refs = ["refs/heads/main", "refs/heads/master"]
        assert is_protected_ref("refs/heads/main", protected_refs) is True

    def test_exact_match_master(self) -> None:
        protected_refs = ["refs/heads/main", "refs/heads/master"]
        assert is_protected_ref("refs/heads/master", protected_refs) is True

    def test_wildcard_release(self) -> None:
        protected_refs = ["refs/heads/release/"]
        assert is_protected_ref("refs/heads/release/v1.0", protected_refs) is True
        assert is_protected_ref("refs/heads/release/2.0.0", protected_refs) is True

    def test_wildcard_deploy(self) -> None:
        protected_refs = ["refs/heads/deploy/"]
        assert is_protected_ref("refs/heads/deploy/prod", protected_refs) is True

    def test_feature_not_protected(self) -> None:
        protected_refs = ["refs/heads/main", "refs/heads/release/"]
        assert is_protected_ref("refs/heads/feature/my-feature", protected_refs) is False
        assert is_protected_ref("refs/heads/feature/test", protected_refs) is False

    def test_develop_not_protected(self) -> None:
        protected_refs = ["refs/heads/main"]
        assert is_protected_ref("refs/heads/develop", protected_refs) is False


class TestCheckCommandLineArgs:
    def test_empty_args_allowed(self) -> None:
        result = check_command_line_args([])
        assert result is None

    def test_force_flag_blocked(self) -> None:
        result = check_command_line_args(["--force"])
        assert result is not None
        assert result.allowed is False
        assert "--force" in result.reason

    def test_f_flag_blocked(self) -> None:
        result = check_command_line_args(["-f"])
        assert result is not None
        assert result.allowed is False
        assert "-f" in result.reason

    def test_force_with_lease_blocked(self) -> None:
        result = check_command_line_args(["--force-with-lease"])
        assert result is not None
        assert result.allowed is False
        assert "--force-with-lease" in result.reason

    def test_force_if_includes_blocked(self) -> None:
        result = check_command_line_args(["--force-if-includes"])
        assert result is not None
        assert result.allowed is False

    def test_mirror_blocked(self) -> None:
        result = check_command_line_args(["--mirror"])
        assert result is not None
        assert result.allowed is False
        assert "--mirror" in result.reason

    def test_delete_blocked(self) -> None:
        result = check_command_line_args(["--delete"])
        assert result is not None
        assert result.allowed is False

    def test_force_refspec_blocked(self) -> None:
        result = check_command_line_args(["origin", "+main"])
        assert result is not None
        assert result.allowed is False

    def test_normal_push_allowed(self) -> None:
        result = check_command_line_args(["origin", "main"])
        assert result is None

    def test_multiple_flags_one_blocked(self) -> None:
        result = check_command_line_args(["--force-with-lease", "origin", "main"])
        assert result is not None
        assert result.allowed is False


class TestParsePrePushStdin:
    def test_empty_stdin(self) -> None:
        result = parse_pre_push_stdin(io.StringIO(""))
        assert result == []

    def test_single_line(self) -> None:
        stdin = io.StringIO("refs/heads/main abc123 refs/heads/main def456\n")
        result = parse_pre_push_stdin(stdin)
        assert len(result) == 1
        assert result[0] == ("refs/heads/main", "abc123", "refs/heads/main", "def456")

    def test_multiple_lines(self) -> None:
        stdin = io.StringIO("refs/heads/main abc refs/heads/main def\nrefs/heads/feature/test ghi refs/heads/feature/test jkl\n")
        result = parse_pre_push_stdin(stdin)
        assert len(result) == 2

    def test_whitespace_only_ignored(self) -> None:
        stdin = io.StringIO("   \n\nrefs/heads/main abc refs/heads/main def\n   \n")
        result = parse_pre_push_stdin(stdin)
        assert len(result) == 1


class TestCheckStdinUpdates:
    def test_feature_branch_allowed(self) -> None:
        refs = [("refs/heads/feature/test", "abc123", "refs/heads/feature/test", "def456")]
        result = check_stdin_updates(refs, ["refs/heads/main"])
        assert result is None

    def test_deletion_blocked(self) -> None:
        refs = [("refs/heads/main", "0" * 40, "refs/heads/main", "abc123")]
        result = check_stdin_updates(refs, ["refs/heads/main"], skip_sha_checks=False)
        assert result is not None
        assert result.allowed is False
        assert "deletion" in result.reason.lower()

    def test_main_update_with_sha_checks(self) -> None:
        refs = [("refs/heads/main", "abc123", "refs/heads/main", "def456")]
        result = check_stdin_updates(refs, ["refs/heads/main"], skip_sha_checks=True)
        assert result is not None
        assert result.allowed is False
        assert "fail_closed" in result.details.get("note", "")


class TestCheckPush:
    def test_normal_feature_push_allowed(self) -> None:
        stdin = io.StringIO("refs/heads/feature/test refs/heads/feature/test refs/heads/feature/test refs/heads/feature/test\n")
        result = check_push(args=[], stdin=stdin)
        assert result.allowed is True

    def test_force_flag_blocked(self) -> None:
        result = check_push(args=["--force"], stdin=io.StringIO(""))
        assert result.allowed is False

    def test_f_flag_blocked(self) -> None:
        result = check_push(args=["-f"], stdin=io.StringIO(""))
        assert result.allowed is False

    def test_mirror_blocked(self) -> None:
        result = check_push(args=["--mirror"], stdin=io.StringIO(""))
        assert result.allowed is False

    def test_force_refspec_blocked(self) -> None:
        result = check_push(args=["origin", "+main"], stdin=io.StringIO(""))
        assert result.allowed is False

    def test_guard_result_to_dict(self) -> None:
        result = GuardResult(allowed=False, reason="Test reason", details={"key": "value"})
        d = result.to_dict()
        assert d["allowed"] is False
        assert d["reason"] == "Test reason"
        assert d["details"]["key"] == "value"


class TestGuardSelfTest:
    def test_self_test_cases(self) -> None:
        errors: list[str] = []
        stdin_content = "refs/heads/feature/test refs/heads/feature/test refs/heads/feature/test refs/heads/feature/test\n"
        result = check_push(args=[], stdin=io.StringIO(stdin_content))
        if not result.allowed:
            errors.append(f"Feature branch push should be allowed: {result.reason}")
        result = check_push(args=["--force"], stdin=io.StringIO(""))
        if result.allowed:
            errors.append("--force flag should be blocked")
        result = check_push(args=["-f"], stdin=io.StringIO(""))
        if result.allowed:
            errors.append("-f flag should be blocked")
        result = check_push(args=["--force-with-lease"], stdin=io.StringIO(""))
        if result.allowed:
            errors.append("--force-with-lease flag should be blocked")
        result = check_push(args=["--mirror"], stdin=io.StringIO(""))
        if result.allowed:
            errors.append("--mirror flag should be blocked")
        result = check_push(args=["origin", "+main"], stdin=io.StringIO(""))
        if result.allowed:
            errors.append("Force refspec +main should be blocked")
        assert len(errors) == 0, f"Self-test failures: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
