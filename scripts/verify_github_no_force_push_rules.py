#!/usr/bin/env python3
"""GitHub branch protection/ruleset verifier for no-force-push policy."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent


@dataclass
class ProtectionCheck:
    """Result of a single protection check."""
    name: str
    passed: bool | None
    message: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "message": self.message, "details": self.details}


@dataclass
class GitHubVerificationResult:
    """Result from GitHub protection verification."""
    success: bool
    branch: str
    can_verify: bool
    checks: list[ProtectionCheck] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success, "branch": self.branch, "can_verify": self.can_verify,
            "checks": [{"name": c.name, "passed": c.passed, "message": c.message} for c in self.checks],
            "error_message": self.error_message,
        }


def get_github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def get_repo_info() -> tuple[str, str] | None:
    env_repo = os.environ.get("GITHUB_REPOSITORY", "")
    if env_repo:
        parts = env_repo.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
    try:
        import subprocess
        result = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, cwd=str(REPO_ROOT))
        if result.returncode == 0:
            url = result.stdout.strip()
            if "github.com" in url:
                if url.startswith("git@"):
                    repo_path = url.split(":")[1].rstrip(".git")
                    owner, repo = repo_path.split("/")
                    return owner, repo
                elif url.startswith("https://"):
                    parts = url.rstrip("/").split("/")
                    if len(parts) >= 2:
                        return parts[-2], parts[-1].rstrip(".git")
    except Exception:
        pass
    return None


def make_github_request(endpoint: str, token: str | None = None) -> dict[str, Any] | None:
    """Make a request to GitHub API. Returns JSON response or None on error."""
    url = f"https://api.github.com{endpoint}"
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "k9b-no-force-push-verifier"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            data: dict[str, Any] = json.loads(response.read().decode())
            return data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"HTTP error: {e.code} {e.reason}", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"URL error: {e.reason}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}", file=sys.stderr)
    except TimeoutError:
        print("Request timed out", file=sys.stderr)
    return None


def check_branch_protection(owner: str, repo: str, branch: str, token: str | None = None) -> GitHubVerificationResult:
    """Check branch protection settings for a specific branch.
    
    GitHub REST API uses:
    - allow_force_pushes.enabled: false means force push is blocked
    - allow_deletions.enabled: false means branch deletion is blocked
    """
    protection_data = make_github_request(f"/repos/{owner}/{repo}/branches/{branch}/protection", token=token)
    checks: list[ProtectionCheck] = []

    if protection_data is None:
        branch_data = make_github_request(f"/repos/{owner}/{repo}/branches/{branch}", token=token)
        if branch_data is None:
            return GitHubVerificationResult(False, branch, False, error_message=f"Cannot verify branch {branch}")
        return GitHubVerificationResult(False, branch, True, [ProtectionCheck("protection_enabled", False, "Branch protection not enabled")])

    # GitHub API field is allow_force_pushes (not allow_force_pushs)
    fpush = protection_data.get("allow_force_pushes", {})
    fpush_enabled = fpush.get("enabled", True) if isinstance(fpush, dict) else True
    checks.append(ProtectionCheck("force_pushs_disabled", not fpush_enabled, "Force pushes disabled" if not fpush_enabled else "Force pushes ENABLED (dangerous!)"))
    
    del_data = protection_data.get("allow_deletions", {})
    del_enabled = del_data.get("enabled", True) if isinstance(del_data, dict) else True
    checks.append(ProtectionCheck("deletion_disabled", not del_enabled, "Branch deletion disabled" if not del_enabled else "Branch deletion ENABLED"))
    
    strict = protection_data.get("required_status_checks", {}).get("strict", False)
    checks.append(ProtectionCheck("required_status_checks", strict, "Required status checks enabled" if strict else "Required status checks not enforced"))
    
    admin_en = protection_data.get("enforce_admins", {}).get("enabled", False)
    checks.append(ProtectionCheck("admin_enforcement", admin_en, "Admin enforcement enabled" if admin_en else "Admin enforcement not enabled"))
    
    # branch_locked is informational only - stronger than no-force-push, makes branch read-only
    locked = protection_data.get("lock", {}).get("enabled", False)
    checks.append(ProtectionCheck("branch_locked_info", True, "Branch lock status noted" if locked else "Branch not locked (normal)" if not locked else "N/A"))
    
    # Core enforcement: force push and deletion must be disabled
    core_passed = all(c.passed for c in checks[:4] if c.passed is not None)
    return GitHubVerificationResult(core_passed, branch, True, checks)


def check_branch_rules(owner: str, repo: str, branch: str, token: str | None = None) -> GitHubVerificationResult | None:
    """Check rules for a specific branch using GET /repos/{owner}/{repo}/rules/branches/{branch}.
    
    GitHub API returns active rules applying to the branch directly.
    Key rule types:
    - deletion: blocks branch deletion
    - non_fast_forward: blocks non-fast-forward updates (force push equivalent)
    """
    rules_data = make_github_request(f"/repos/{owner}/{repo}/rules/branches/{branch}", token=token)
    if rules_data is None:
        return None  # API may not be available
    
    checks: list[ProtectionCheck] = []
    has_deletion = False
    has_non_fast_forward = False
    
    # rules_data is a list of rules
    for rule in rules_data:
        rule_type = rule.get("type", "")
        if rule_type == "deletion":
            has_deletion = True
        if rule_type == "non_fast_forward":
            has_non_fast_forward = True
    
    checks.append(ProtectionCheck("branch_rule_deletion", has_deletion, "Branch deletion rule active" if has_deletion else "No deletion rule blocking branch deletion"))
    checks.append(ProtectionCheck("branch_rule_non_fast_forward", has_non_fast_forward, "Non-fast-forward rule active" if has_non_fast_forward else "No rule blocking non-fast-forward"))
    
    return GitHubVerificationResult(all(c.passed for c in checks if c.passed is not None), branch, True, checks)


def run_verification(branch: str = "main", ci_mode: bool = False) -> GitHubVerificationResult:
    """Run GitHub protection verification."""
    token = get_github_token()
    repo_info = get_repo_info()
    if repo_info is None:
        return GitHubVerificationResult(False, branch, False, error_message="Cannot determine repository. Set GITHUB_REPOSITORY or configure git remote.")
    owner, repo = repo_info
    result = check_branch_protection(owner, repo, branch, token)
    
    # Also check branch rules (GitHub's recommended API for rules)
    branch_rules_result = check_branch_rules(owner, repo, branch, token)
    if branch_rules_result:
        result.checks.extend(branch_rules_result.checks)
        result.success = all(c.passed for c in result.checks if c.passed is not None)
    
    if ci_mode and not result.can_verify:
        result.success = False
    return result


def run_self_test() -> tuple[bool, list[str]]:
    """Run self-test validation with mock data."""
    print("=== GitHub No-Force-Push Rules Self-Test ===\n")
    errors: list[str] = []
    try:
        from verify_github_no_force_push_rules import ProtectionCheck, get_github_token, get_repo_info  # noqa: F401
        print("[PASS] Module imports successfully")
    except ImportError as e:
        errors.append(f"Module import failed: {e}")
    info = get_repo_info()
    if info:
        print(f"[PASS] Repo info detected: {info[0]}/{info[1]}")
    else:
        print("[INFO] Repo info not available (expected outside git repo)")
    if get_github_token():
        print("[PASS] GitHub token available")
    else:
        print("[INFO] GitHub token not set (CI mode will be limited)")
    check = ProtectionCheck(name="test", passed=True, message="Test", details={"key": "value"})
    if not (check.passed and check.to_dict()["details"]["key"] == "value"):
        errors.append("ProtectionCheck test failed")
    print("[INFO] Testing offline behavior...")
    result = run_verification(branch="main", ci_mode=False)
    if not result.can_verify:
        print(f"[PASS] Offline mode handled gracefully: {result.error_message}")
    else:
        print("[INFO] GitHub API accessible (running against real repo)")
    print(f"\nSelf-test result: {'PASS' if not errors else 'FAIL'}")
    return not errors, errors


def format_results(result: GitHubVerificationResult, json_output: bool = False, verbose: bool = False) -> str:
    """Format verification results for output."""
    if json_output:
        return json.dumps(result.to_dict(), indent=2)
    lines = ["=== GitHub No-Force-Push Rules Verification ===\n", f"Branch: {result.branch}", f"Can verify: {result.can_verify}"]
    if not result.can_verify:
        lines.append(f"\nCannot verify: {result.error_message}")
        return "\n".join(lines)
    lines.append(f"Overall: {'PASS' if result.success else 'FAIL'}")
    lines.append("\nProtection checks:")
    for check in result.checks:
        status = "?" if check.passed is None else ("✓" if check.passed else "✗")
        lines.append(f"  [{status}] {check.name}: {check.message}")
        if verbose and not check.passed:
            lines.append(f"      Details: {check.details}")
    return "\n".join(lines)


def main() -> int:
    """Entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Verify GitHub branch protection rules for no-force-push policy")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--self-test", action="store_true", help="Run self-test validation")
    parser.add_argument("--ci", action="store_true", help="CI mode - fail if cannot verify")
    parser.add_argument("--branch", default="main", help="Branch to verify (default: main)")
    args = parser.parse_args()
    if args.self_test:
        success, errors = run_self_test()
        print("\nSELF-TEST: PASSED" if success else "\nSELF-TEST: FAILED")
        for error in errors:
            print(f"  - {error}")
        return 0 if success else 1
    result = run_verification(branch=args.branch, ci_mode=args.ci)
    print(format_results(result, json_output=args.json, verbose=args.verbose))
    if not result.can_verify and args.ci:
        print("\nNote: Cannot verify in CI mode without credentials.", file=sys.stderr)
        return 2
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
