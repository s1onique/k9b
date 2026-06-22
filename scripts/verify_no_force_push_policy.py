#!/usr/bin/env python3
"""Offline policy verifier for no-force-push doctrine."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

REQUIRED_DOCTRINE_TERMS = [
    "git push --force",
    "--force-with-lease",
    "force",
    "protected",
    "history rewrite",
    "revert",
    "emergency",
]

REQUIRED_FILES = [
    "docs/doctrine/no-force-push.md",
    "docs/policy/no-force-push-protected-refs.json",
    "scripts/git_no_force_push_guard.py",
    "scripts/install_git_no_force_push_hook.py",
]


@dataclass
class PolicyCheck:
    name: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class PolicyVerificationResult:
    success: bool
    checks: list[PolicyCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def check_doctrine_file_exists() -> PolicyCheck:
    path = REPO_ROOT / "docs/doctrine/no-force-push.md"
    exists = path.exists()
    return PolicyCheck(
        name="doctrine_file_exists",
        passed=exists,
        message=f"Doctrine file {'exists' if exists else 'MISSING'}: {path}",
        details={"path": str(path)},
    )


def check_doctrine_content() -> PolicyCheck:
    path = REPO_ROOT / "docs/doctrine/no-force-push.md"
    if not path.exists():
        return PolicyCheck(name="doctrine_content", passed=False, message="Doctrine file missing")
    try:
        content = path.read_text().lower()
        missing = [t for t in REQUIRED_DOCTRINE_TERMS if t.lower() not in content]
        passed = len(missing) == 0
        return PolicyCheck(
            name="doctrine_content",
            passed=passed,
            message="Doctrine contains all required terms" if passed else f"Missing terms: {missing}",
            details={"missing_terms": missing},
        )
    except OSError as e:
        return PolicyCheck(name="doctrine_content", passed=False, message=f"Failed to read doctrine: {e}")


def check_doctrine_manifest() -> PolicyCheck:
    manifest_path = REPO_ROOT / "docs/doctrine/manifest.yaml"
    if not manifest_path.exists():
        return PolicyCheck(name="doctrine_manifest", passed=False, message="Manifest file missing")
    try:
        content = manifest_path.read_text()
        has_entry = "id: no-force-push" in content
        has_file = "file: docs/doctrine/no-force-push.md" in content
        passed = has_entry and has_file
        return PolicyCheck(
            name="doctrine_manifest",
            passed=passed,
            message="Doctrine registered in manifest" if passed else f"Manifest incomplete: entry={has_entry}, file={has_file}",
            details={"has_entry": has_entry, "has_file": has_file},
        )
    except OSError as e:
        return PolicyCheck(name="doctrine_manifest", passed=False, message=f"Failed to read manifest: {e}")


def check_agent_rules_reference() -> PolicyCheck:
    rules_path = REPO_ROOT / ".kilocode/rules/40-tool-use.md"
    if not rules_path.exists():
        return PolicyCheck(name="agent_rules_reference", passed=False, message="Agent rules file missing")
    try:
        content = rules_path.read_text()
        has_slug = "no-force-push" in content
        has_path = "docs/doctrine/no-force-push.md" in content
        passed = has_slug and has_path
        return PolicyCheck(
            name="agent_rules_reference",
            passed=passed,
            message="Agent rules reference doctrine" if passed else f"Agent rules incomplete: slug={has_slug}, path={has_path}",
            details={"has_slug": has_slug, "has_path": has_path},
        )
    except OSError as e:
        return PolicyCheck(name="agent_rules_reference", passed=False, message=f"Failed to read agent rules: {e}")


def check_required_files() -> PolicyCheck:
    missing = [p for p in REQUIRED_FILES if not (REPO_ROOT / p).exists()]
    passed = len(missing) == 0
    return PolicyCheck(
        name="required_files",
        passed=passed,
        message="All required files present" if passed else f"Missing files: {missing}",
        details={"missing": missing},
    )


def check_guard_script() -> PolicyCheck:
    try:
        import git_no_force_push_guard
        assert hasattr(git_no_force_push_guard, "check_push")
        assert hasattr(git_no_force_push_guard, "check_command_line_args")
        assert hasattr(git_no_force_push_guard, "parse_pre_push_stdin")
        assert hasattr(git_no_force_push_guard, "GuardResult")
        return PolicyCheck(
            name="guard_script",
            passed=True,
            message="Guard script has required functions",
            details={"functions": ["check_push", "check_command_line_args", "parse_pre_push_stdin"]},
        )
    except ImportError as e:
        return PolicyCheck(name="guard_script", passed=False, message=f"Failed to import guard script: {e}")


def check_installer_script() -> PolicyCheck:
    installer_path = REPO_ROOT / "scripts/install_git_no_force_push_hook.py"
    if not installer_path.exists():
        return PolicyCheck(name="installer_script", passed=False, message="Installer script missing")
    try:
        import install_git_no_force_push_hook
        assert hasattr(install_git_no_force_push_hook, "install_hook")
        assert hasattr(install_git_no_force_push_hook, "uninstall_hook")
        assert hasattr(install_git_no_force_push_hook, "check_hook_status")
        return PolicyCheck(
            name="installer_script",
            passed=True,
            message="Installer script has required functions",
            details={"functions": ["install_hook", "uninstall_hook", "check_hook_status"]},
        )
    except ImportError as e:
        return PolicyCheck(name="installer_script", passed=False, message=f"Failed to import installer script: {e}")


def check_protected_refs_config() -> PolicyCheck:
    config_path = REPO_ROOT / "docs/policy/no-force-push-protected-refs.json"
    if not config_path.exists():
        return PolicyCheck(name="protected_refs_config", passed=False, message="Protected refs config missing")
    try:
        with open(config_path) as f:
            config = json.load(f)
        has_refs = "protected_refs" in config
        has_flags = "banned_force_flags" in config
        passed = has_refs and has_flags
        return PolicyCheck(
            name="protected_refs_config",
            passed=passed,
            message="Protected refs config valid" if passed else f"Config incomplete: refs={has_refs}, flags={has_flags}",
            details={"has_refs": has_refs, "has_flags": has_flags},
        )
    except (json.JSONDecodeError, OSError) as e:
        return PolicyCheck(name="protected_refs_config", passed=False, message=f"Failed to read config: {e}")


def run_guard_self_test() -> PolicyCheck:
    import io
    try:
        from git_no_force_push_guard import check_push
        errors = []
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
        passed = len(errors) == 0
        return PolicyCheck(
            name="guard_self_test",
            passed=passed,
            message="Guard self-test passed" if passed else f"Self-test failed: {errors}",
            details={"errors": errors},
        )
    except ImportError as e:
        return PolicyCheck(name="guard_self_test", passed=False, message=f"Failed to import guard: {e}")


def run_verification() -> PolicyVerificationResult:
    checks = [
        check_doctrine_file_exists(),
        check_doctrine_content(),
        check_doctrine_manifest(),
        check_agent_rules_reference(),
        check_required_files(),
        check_guard_script(),
        check_installer_script(),
        check_protected_refs_config(),
        run_guard_self_test(),
    ]
    errors = [c.message for c in checks if not c.passed]
    return PolicyVerificationResult(success=len(errors) == 0, checks=checks, errors=errors)


def run_self_test() -> tuple[bool, list[str]]:
    print("=== No-Force-Push Policy Self-Test ===\n")
    result = run_verification()
    print(f"Policy checks run: {len(result.checks)}")
    print(f"Passed: {sum(1 for c in result.checks if c.passed)}")
    print(f"Failed: {sum(1 for c in result.checks if not c.passed)}")
    print()
    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"  [{status}] {check.name}: {check.message}")
    print()
    return result.success, result.errors


def format_results(result: PolicyVerificationResult, json_output: bool = False) -> str:
    if json_output:
        return json.dumps({"success": result.success, "checks": [{"name": c.name, "passed": c.passed} for c in result.checks]}, indent=2)
    lines = ["=== No-Force-Push Policy Verification ===\n", f"Overall: {'PASS' if result.success else 'FAIL'}"]
    for check in result.checks:
        status = "✓" if check.passed else "✗"
        lines.append(f"  [{status}] {check.name}: {check.message}")
    return "\n".join(lines)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Verify no-force-push policy implementation")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--self-test", action="store_true", help="Run self-test validation")
    args = parser.parse_args()
    if args.self_test:
        success, errors = run_self_test()
        print("\nSELF-TEST: PASSED" if success else "\nSELF-TEST: FAILED")
        for error in errors:
            print(f"  - {error}")
        return 0 if success else 1
    result = run_verification()
    print(format_results(result, json_output=args.json))
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
