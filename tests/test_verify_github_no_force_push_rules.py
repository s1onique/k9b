#!/usr/bin/env python3
"""Tests for verify_github_no_force_push_rules module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from verify_github_no_force_push_rules import (
    GitHubVerificationResult,
    ProtectionCheck,
    format_results,
    get_github_token,
    get_repo_info,
)


class TestProtectionCheck:
    def test_protection_check_passed(self) -> None:
        check = ProtectionCheck(name="test_check", passed=True, message="Check passed", details={"key": "value"})
        assert check.passed is True
        assert check.name == "test_check"
        assert check.message == "Check passed"

    def test_protection_check_failed(self) -> None:
        check = ProtectionCheck(name="test_check", passed=False, message="Check failed")
        assert check.passed is False

    def test_protection_check_unknown(self) -> None:
        check = ProtectionCheck(name="test_check", passed=None, message="Cannot verify")
        assert check.passed is None

    def test_to_dict(self) -> None:
        check = ProtectionCheck(name="test", passed=True, message="OK", details={"count": 5})
        d = check.to_dict()
        assert d["name"] == "test"
        assert d["passed"] is True
        assert d["details"]["count"] == 5


class TestGitHubVerificationResult:
    def test_result_passed(self) -> None:
        checks = [
            ProtectionCheck(name="check1", passed=True, message="OK"),
            ProtectionCheck(name="check2", passed=True, message="OK"),
        ]
        result = GitHubVerificationResult(success=True, branch="main", can_verify=True, checks=checks)
        assert result.success is True
        assert result.branch == "main"
        assert len(result.checks) == 2

    def test_result_failed(self) -> None:
        checks = [
            ProtectionCheck(name="check1", passed=True, message="OK"),
            ProtectionCheck(name="check2", passed=False, message="Failed"),
        ]
        result = GitHubVerificationResult(success=False, branch="main", can_verify=True, checks=checks)
        assert result.success is False

    def test_result_cannot_verify(self) -> None:
        result = GitHubVerificationResult(success=False, branch="main", can_verify=False, error_message="Cannot determine repository")
        assert result.can_verify is False

    def test_to_dict(self) -> None:
        checks = [ProtectionCheck(name="check1", passed=True, message="OK")]
        result = GitHubVerificationResult(success=True, branch="main", can_verify=True, checks=checks)
        d = result.to_dict()
        assert d["success"] is True
        assert d["branch"] == "main"
        assert len(d["checks"]) == 1


class TestGetGitHubToken:
    def test_token_from_github_token(self) -> None:
        import os
        old_val = os.environ.get("GITHUB_TOKEN")
        try:
            os.environ["GITHUB_TOKEN"] = "test-token-123"
            token = get_github_token()
            assert token == "test-token-123"
        finally:
            if old_val is not None:
                os.environ["GITHUB_TOKEN"] = old_val
            elif "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]

    def test_token_from_gh_token(self) -> None:
        import os
        old_gh = os.environ.get("GH_TOKEN")
        old_github = os.environ.get("GITHUB_TOKEN")
        try:
            if "GH_TOKEN" in os.environ:
                del os.environ["GH_TOKEN"]
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]
            os.environ["GH_TOKEN"] = "fallback-token"
            token = get_github_token()
            assert token == "fallback-token"
        finally:
            if old_gh is not None:
                os.environ["GH_TOKEN"] = old_gh
            elif "GH_TOKEN" in os.environ:
                del os.environ["GH_TOKEN"]
            if old_github is not None:
                os.environ["GITHUB_TOKEN"] = old_github
            elif "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]

    def test_token_none(self) -> None:
        import os
        old_gh = os.environ.get("GH_TOKEN")
        old_github = os.environ.get("GITHUB_TOKEN")
        try:
            if "GH_TOKEN" in os.environ:
                del os.environ["GH_TOKEN"]
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]
            token = get_github_token()
            assert token is None
        finally:
            if old_gh is not None:
                os.environ["GH_TOKEN"] = old_gh
            if old_github is not None:
                os.environ["GITHUB_TOKEN"] = old_github


class TestGetRepoInfo:
    def test_repo_info_from_environment(self) -> None:
        import os
        old_val = os.environ.get("GITHUB_REPOSITORY")
        try:
            os.environ["GITHUB_REPOSITORY"] = "owner/test-repo"
            owner, repo = get_repo_info()
            assert owner == "owner"
            assert repo == "test-repo"
        finally:
            if old_val is not None:
                os.environ["GITHUB_REPOSITORY"] = old_val
            elif "GITHUB_REPOSITORY" in os.environ:
                del os.environ["GITHUB_REPOSITORY"]


class TestFormatResults:
    def test_format_json(self) -> None:
        import json
        checks = [ProtectionCheck(name="check1", passed=True, message="OK")]
        result = GitHubVerificationResult(success=True, branch="main", can_verify=True, checks=checks)
        output = format_results(result, json_output=True)
        data = json.loads(output)
        assert data["success"] is True

    def test_format_human(self) -> None:
        checks = [
            ProtectionCheck(name="check1", passed=True, message="OK"),
            ProtectionCheck(name="check2", passed=False, message="Failed"),
        ]
        result = GitHubVerificationResult(success=False, branch="main", can_verify=True, checks=checks)
        output = format_results(result, json_output=False)
        assert "FAIL" in output
        assert "main" in output

    def test_format_cannot_verify(self) -> None:
        result = GitHubVerificationResult(success=False, branch="main", can_verify=False, error_message="Cannot determine repository")
        output = format_results(result, json_output=False)
        assert "Cannot verify" in output
        assert "Cannot determine repository" in output


class TestGitHubApiSimulation:
    def test_protection_check_result_aggregation(self) -> None:
        checks = [
            ProtectionCheck(name="force_push", passed=True, message="Disabled"),
            ProtectionCheck(name="deletion", passed=True, message="Disabled"),
            ProtectionCheck(name="admins", passed=False, message="Not enforced"),
        ]
        result = GitHubVerificationResult(success=False, branch="main", can_verify=True, checks=checks)
        assert result.success is False
        failed = [c for c in result.checks if c.passed is False]
        assert len(failed) == 1
        assert failed[0].name == "admins"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
