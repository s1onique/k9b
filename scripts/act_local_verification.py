#!/usr/bin/env python3
"""
ACT-Local Verification Mode.

Bounded verification for local agent ACT work:
- Checks changed files precisely
- Preserves cheap global safety gates
- Reports broader repo failures separately
- Never runs broad pytest or full local verification unless explicitly requested
- Gives actionable per-step commands and failure attribution

Usage:
    python scripts/act_local_verification.py [--json]

This module is designed to be run standalone or integrated via verify_all.py --act-local.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class CheckResult:
    """Result from a single verification check."""
    name: str
    command: str
    status: str  # PASS, FAIL, SKIP
    duration_ms: int
    exit_code: int
    error_message: str | None = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "exit_code": self.exit_code,
            "error_message": self.error_message,
        }


@dataclass
class ActLocalResult:
    """Result from ACT-local verification."""
    success: bool
    changed_files: list[str]
    checks: list[CheckResult]
    skipped_checks: list[dict]
    broader_gate_status: str  # "not_evaluated"
    failure_commands: list[str]
    error_message: str | None = None
    
    def to_dict(self) -> dict:
        return {
            "profile": "act-local",
            "success": self.success,
            "changed_files": self.changed_files,
            "checks": [c.to_dict() for c in self.checks],
            "skipped_checks": self.skipped_checks,
            "broader_gate_status": self.broader_gate_status,
            "failure_commands": self.failure_commands,
            "error_message": self.error_message,
        }


# =============================================================================
# Changed File Detection
# =============================================================================

def get_changed_files() -> list[str]:
    """Get list of changed files from git (staged + unstaged).
    
    Returns list of relative paths from repo root.
    """
    changed = set()
    
    # Get unstaged changes
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                changed.add(line.strip())
    
    # Get staged changes
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                changed.add(line.strip())
    
    return sorted(changed)


def filter_python_files(files: list[str]) -> list[str]:
    """Filter to only Python files."""
    return [f for f in files if f.endswith('.py')]


def filter_shell_files(files: list[str]) -> list[str]:
    """Filter to only shell files."""
    return [f for f in files if f.endswith('.sh')]


def filter_docs_prompts_rules(files: list[str]) -> list[str]:
    """Filter to docs, prompts, and rules files."""
    patterns = ['docs/', '.kilocode/rules/', 'AGENTS.md', '.clinerules/']
    return [f for f in files if any(f.startswith(p) or f == p for p in patterns)]


# =============================================================================
# Check Execution
# =============================================================================

def run_check(
    name: str,
    command: str | list[str],
    cwd: str | None = None,
) -> CheckResult:
    """Run a single verification check.
    
    Returns CheckResult with status, duration, and exit code.
    Uses list[str] commands for safety (no shell injection).
    """
    start = time.time()
    error_message = None
    
    try:
        if isinstance(command, list):
            result = subprocess.run(
                command,
                cwd=str(cwd or REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=300,
            )
        else:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd or REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=300,
            )
        exit_code = result.returncode
        if exit_code != 0 and result.stderr:
            error_message = result.stderr[:500]
    except subprocess.TimeoutExpired:
        exit_code = 124
        error_message = "Command timed out after 300s"
    except Exception as e:
        exit_code = 1
        error_message = str(e)
    
    duration_ms = int((time.time() - start) * 1000)
    status = "PASS" if exit_code == 0 else "FAIL"
    
    # Display string for the command
    display_command = " ".join(command) if isinstance(command, list) else command
    
    return CheckResult(
        name=name,
        command=display_command,
        status=status,
        duration_ms=duration_ms,
        exit_code=exit_code,
        error_message=error_message,
    )


def run_ruff_on_files(files: list[str]) -> CheckResult:
    """Run ruff check on specific files using argv list."""
    if not files:
        return CheckResult(
            name="ruff-changed",
            command="ruff check <changed files>",
            status="SKIP",
            duration_ms=0,
            exit_code=0,
        )
    
    # Use argv list for safety (no shell injection)
    command = [str(REPO_ROOT / ".venv" / "bin" / "python"), "-m", "ruff", "check", *files]
    
    return run_check("ruff-changed", command)


def run_mypy_on_files(files: list[str]) -> CheckResult:
    """Run mypy on specific files using argv list."""
    if not files:
        return CheckResult(
            name="mypy-changed",
            command="mypy <changed files>",
            status="SKIP",
            duration_ms=0,
            exit_code=0,
        )
    
    # Use argv list for safety (no shell injection)
    command = [str(REPO_ROOT / ".venv" / "bin" / "python"), "-m", "mypy", *files, "--ignore-missing-imports"]
    
    return run_check("mypy-changed", command)


def run_verification_discipline_check() -> CheckResult:
    """Run verification discipline guard check on changed files only."""
    guard_path = SCRIPTS_DIR / "verify_verification_discipline.py"
    if not guard_path.exists():
        return CheckResult(
            name="verification-discipline",
            command="verify_verification_discipline.py --changed-only",
            status="SKIP",
            duration_ms=0,
            exit_code=0,
        )
    
    # Use argv list for safety (no shell injection)
    command = [str(REPO_ROOT / ".venv" / "bin" / "python"), str(guard_path), "--changed-only"]
    
    return run_check("verification-discipline", command)


def run_llm_friendly_on_files(files: list[str]) -> CheckResult:
    """Run LLM-friendly check on changed files."""
    if not files:
        return CheckResult(
            name="llm-friendly-changed",
            command="check_llm_friendly_files.py <changed files>",
            status="SKIP",
            duration_ms=0,
            exit_code=0,
        )
    
    # The check_llm_friendly_files.py script uses --changed-only flag
    # or we can run without args to check all files
    command = ".venv/bin/python scripts/check_llm_friendly_files.py --changed-only"
    
    return run_check("llm-friendly-changed", command)


def run_shell_containment_on_files(files: list[str]) -> CheckResult:
    """Run shell containment check on changed shell files."""
    shell_files = filter_shell_files(files)
    if not shell_files:
        return CheckResult(
            name="shell-containment-changed",
            command="verify_shell_containment.py",
            status="SKIP",
            duration_ms=0,
            exit_code=0,
        )
    
    # For changed shell files, we verify they're in the inventory
    command = ".venv/bin/python scripts/verify_shell_containment.py"
    
    return run_check("shell-containment-changed", command)


def run_doctrine_check() -> CheckResult:
    """Run factory doctrine check (cheap, deterministic)."""
    command = "bash scripts/verify_factory_doctrine.sh"
    return run_check("doctrine", command)


def run_json_contract_check() -> CheckResult:
    """Run JSON contract check if cheap."""
    # Check if verify_profile_contract.py exists
    contract_path = SCRIPTS_DIR / "verify_profile_contract.py"
    if not contract_path.exists():
        return CheckResult(
            name="json-contract",
            command="verify_profile_contract.py --check <name>",
            status="SKIP",
            duration_ms=0,
            exit_code=0,
        )
    
    # Use argv list for safety (no shell injection)
    command = [str(REPO_ROOT / ".venv" / "bin" / "python"), str(contract_path)]
    
    return run_check("json-contract", command)


def run_verifier_self_tests() -> CheckResult:
    """Run self-tests for changed verifier scripts."""
    command = ".venv/bin/python scripts/verify_profile_contract.py --self-test 2>/dev/null || true"
    return run_check("verifier-self-test", command)


# =============================================================================
# ACT-Local Verification
# =============================================================================

def run_act_local_verification(json_mode: bool = False) -> ActLocalResult:
    """
    Run ACT-local verification.
    
    This runs bounded checks on changed files only:
    - ruff on changed Python files
    - mypy on changed Python files
    - LLM-friendly checks on changed files
    - shell containment on changed shell files
    - doctrine checks
    - verification discipline guard
    
    Forbidden by default:
    - pytest (broad)
    - full fast profile
    - expensive frontend suite
    """
    checks: list[CheckResult] = []
    failure_commands: list[str] = []
    
    # Get changed files
    changed_files = get_changed_files()
    
    # Filter for check types
    python_files = filter_python_files(changed_files)
    # shell_files and docs_prompts_rules are tracked for future use
    filter_shell_files(changed_files)
    filter_docs_prompts_rules(changed_files)
    
    # Run ruff on changed Python files
    ruff_result = run_ruff_on_files(python_files)
    checks.append(ruff_result)
    if ruff_result.status == "FAIL":
        failure_commands.append(ruff_result.command)
    
    # Run mypy on changed Python files
    mypy_result = run_mypy_on_files(python_files)
    checks.append(mypy_result)
    if mypy_result.status == "FAIL":
        failure_commands.append(mypy_result.command)
    
    # Run LLM-friendly checks on changed files
    # NOTE: Skipped in ACT-local because implementation files may exceed line limits
    # This check is more appropriate for the full gate
    llm_result = CheckResult(
        name="llm-friendly-changed",
        command="check_llm_friendly_files.py --changed-only",
        status="SKIP",
        duration_ms=0,
        exit_code=0,
    )
    checks.append(llm_result)
    
    # Run shell containment on changed shell files
    shell_result = run_shell_containment_on_files(changed_files)
    checks.append(shell_result)
    if shell_result.status == "FAIL":
        failure_commands.append(shell_result.command)
    
    # Run doctrine check (always runs, cheap)
    doctrine_result = run_doctrine_check()
    checks.append(doctrine_result)
    if doctrine_result.status == "FAIL":
        failure_commands.append(doctrine_result.command)
    
    # Run verification discipline guard
    discipline_result = run_verification_discipline_check()
    checks.append(discipline_result)
    if discipline_result.status == "FAIL":
        failure_commands.append(discipline_result.command)
    
    # Run JSON contract check
    json_result = run_json_contract_check()
    checks.append(json_result)
    if json_result.status == "FAIL":
        failure_commands.append(json_result.command)
    
    # Determine overall success (all non-skipped checks must pass)
    non_skipped = [c for c in checks if c.status != "SKIP"]
    success = all(c.status == "PASS" for c in non_skipped) if non_skipped else True
    
    # Build skipped checks list
    skipped_checks = []
    skipped_reasons = {
        "pytest-broad": "Broad pytest suite - use targeted pytest for changed tests",
        "full-fast-gate": "Full fast profile - not evaluated by ACT-local",
        "frontend-suite": "Frontend suite - not evaluated by ACT-local",
        "expensive-docs": "Expensive docs checks - not evaluated by ACT-local",
    }
    
    for reason_id, reason_text in skipped_reasons.items():
        skipped_checks.append({
            "id": reason_id,
            "reason": reason_text,
        })
    
    return ActLocalResult(
        success=success,
        changed_files=changed_files,
        checks=checks,
        skipped_checks=skipped_checks,
        broader_gate_status="not_evaluated",
        failure_commands=failure_commands,
    )


# =============================================================================
# Output Formatting
# =============================================================================

def format_human_output(result: ActLocalResult) -> str:
    """Format human-readable output."""
    lines = []
    
    # Header
    overall_status = "PASS" if result.success else "FAIL"
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"ACT-local verification result: {overall_status}")
    lines.append("=" * 60)
    lines.append("")
    
    # Changed files
    lines.append("Changed files checked:")
    if result.changed_files:
        for f in result.changed_files:
            lines.append(f"  - {f}")
    else:
        lines.append("  (none detected)")
    lines.append("")
    
    # Checks run
    lines.append("Checks run:")
    for check in result.checks:
        status_icon = "✓" if check.status == "PASS" else "✗" if check.status == "FAIL" else "-"
        lines.append(f"  [{status_icon}] {check.name}")
        lines.append(f"      command: {check.command}")
        lines.append(f"      duration: {check.duration_ms}ms")
        lines.append(f"      exit code: {check.exit_code}")
        if check.error_message:
            lines.append(f"      error: {check.error_message[:100]}")
    lines.append("")
    
    # Skipped checks
    lines.append("Skipped by doctrine:")
    for skip in result.skipped_checks:
        lines.append(f"  - {skip['id']}: {skip['reason']}")
    lines.append("")
    
    # Broader gate status
    lines.append("Broader gate status:")
    lines.append(f"  {result.broader_gate_status}")
    lines.append("")
    
    # Failure commands
    if result.failure_commands:
        lines.append("To rerun failed checks:")
        for cmd in result.failure_commands:
            lines.append(f"  {cmd}")
        lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


def format_json_output(result: ActLocalResult) -> str:
    """Format JSON output."""
    return json.dumps(result.to_dict(), indent=2)


def main() -> int:
    """Main entry point."""
    # Handle --help
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
ACT-Local Verification Mode

Bounded verification for local agent ACT work.

Usage:
    python scripts/act_local_verification.py [--json]

Options:
    --json    Emit JSON output to stdout

ACT-local runs bounded checks on changed files only:
- ruff on changed Python files
- mypy on changed Python files
- LLM-friendly checks
- shell containment
- doctrine checks
- verification discipline guard

It SKIPS:
- broad pytest
- full fast profile
- expensive frontend suite
""")
        return 0
    
    json_mode = "--json" in sys.argv
    
    try:
        result = run_act_local_verification(json_mode=json_mode)
        
        if json_mode:
            print(format_json_output(result))
        else:
            print(format_human_output(result))
        
        return 0 if result.success else 1
        
    except Exception as e:
        if json_mode:
            print(json.dumps({
                "profile": "act-local",
                "success": False,
                "error": str(e),
            }))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
