#!/usr/bin/env python3
"""ACT-Local core check implementations.

Provides the most-used check functions: linting, mypy, JSON contract,
workflow verification, doctrine, shell containment, LLM-friendly,
verification discipline, no-new-allowlist, and gate-summary parser.

Heavy or topic-specific checks live in dedicated modules:
- ``act_local_runtime_checks`` (structured logs, small provider helpers)
- ``act_local_incident_api_checks`` (one-pass diagnosis wiring)
- ``act_local_frontend_checks`` (frontend vitest)

All commands use list[str] for safety (no shell=True).
"""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path

from act_local_contract import CheckResult

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent


def _is_git_tracked(path: Path) -> bool:
    """Check if a path is tracked by git using ls-files --error-unmatch."""
    try:
        rel_path = path.relative_to(REPO_ROOT)
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(rel_path)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def run_no_new_llm_allowlist_check() -> CheckResult:
    """Run the no-new-allowlist gate before LLM-friendly check.

    CRITICAL: If the verifier is missing, this is a FAIL (not SKIP).
    The no-new-allowlist policy is mandatory debt containment.
    """
    verifier_path = SCRIPTS_DIR / "verify_no_new_llm_allowlist.py"
    if not verifier_path.exists():
        return CheckResult(
            name="no-new-llm-allowlist",
            command="verify_no_new_llm_allowlist.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: scripts/verify_no_new_llm_allowlist.py not found - no-new-allowlist policy enforcement is missing",
        )

    command = [str(REPO_ROOT / ".venv" / "bin" / "python"), str(verifier_path)]
    return run_check("no-new-llm-allowlist", command)


def run_check(
    name: str,
    command: list[str],
    cwd: str | None = None,
) -> CheckResult:
    """Run a single verification check.

    Returns CheckResult with status, duration, and exit code.
    Uses list[str] commands for safety (no shell injection).
    """
    start = time.time()
    error_message = None

    try:
        result = subprocess.run(
            command,
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

    display_command = shlex.join(command)

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

    command = [str(REPO_ROOT / ".venv" / "bin" / "python"), str(guard_path), "--changed-only"]
    return run_check("verification-discipline", command)


def run_llm_friendly_on_files(files: list[str]) -> CheckResult:
    """Run LLM-friendly check on changed files."""
    checker_path = SCRIPTS_DIR / "check_llm_friendly_files.py"
    if not checker_path.exists():
        return CheckResult(
            name="llm-friendly-changed",
            command="check_llm_friendly_files.py --changed-only",
            status="SKIP",
            duration_ms=0,
            exit_code=0,
        )

    command = [str(REPO_ROOT / ".venv" / "bin" / "python"), str(checker_path), "--changed-only"]
    return run_check("llm-friendly-changed", command)


def run_shell_containment_on_files(files: list[str]) -> CheckResult:
    """Run shell containment check on changed shell files."""
    from act_local_changed_files import filter_shell_files

    shell_files = filter_shell_files(files)
    if not shell_files:
        return CheckResult(
            name="shell-containment-changed",
            command="verify_shell_containment.py",
            status="SKIP",
            duration_ms=0,
            exit_code=0,
        )

    verifier_path = SCRIPTS_DIR / "verify_shell_containment.py"
    if not verifier_path.exists():
        return CheckResult(
            name="shell-containment-changed",
            command="verify_shell_containment.py",
            status="SKIP",
            duration_ms=0,
            exit_code=0,
        )

    command = [str(REPO_ROOT / ".venv" / "bin" / "python"), str(verifier_path)]
    return run_check("shell-containment-changed", command)


def run_doctrine_check() -> CheckResult:
    """Run factory doctrine check (cheap, deterministic)."""
    doctrine_path = SCRIPTS_DIR / "verify_factory_doctrine.sh"

    command = ["bash", str(doctrine_path)]
    return run_check("doctrine", command)


def run_json_contract_check() -> CheckResult:
    """Run JSON contract check if cheap."""
    contract_path = SCRIPTS_DIR / "verify_profile_contract.py"
    if not contract_path.exists():
        return CheckResult(
            name="json-contract",
            command="verify_profile_contract.py --check <name>",
            status="SKIP",
            duration_ms=0,
            exit_code=0,
        )

    command = [str(REPO_ROOT / ".venv" / "bin" / "python"), str(contract_path)]
    return run_check("json-contract", command)


def run_gate_summary_parser_check(artifact_path: Path | None = None) -> CheckResult:
    """Run the canonical gate-summary-parser against the gate-summary artifact.

    This check is part of the canonical ACT-local close-check by default.
    When ``verify_all.py`` is invoked via ``--skip-gate-summary`` (typically
    from inside ``populate_gate_summary.py``), this check is omitted to break
    the populate -> verify -> populate circular dependency.

    Args:
        artifact_path: Override path to the gate-summary artifact. When
            ``None``, the production location ``.factory/gate-summary.json``
            is used. Tests pass a ``tmp_path`` so they never rename or
            delete the real tracked artifact.
    """
    artifact = (
        artifact_path
        if artifact_path is not None
        else REPO_ROOT / ".factory" / "gate-summary.json"
    )
    if not artifact.exists():
        return CheckResult(
            name="gate-summary-parser",
            command=(
                f"python scripts/factory/parse_gate_summary.py --target "
                f"{artifact} --quiet"
            ),
            status="FAIL",
            duration_ms=0,
            exit_code=2,
            error_message=(
                f"CRITICAL: gate-summary artifact not found at {artifact}. "
                "Run scripts/factory/populate_gate_summary.py first."
            ),
        )
    parser_path = SCRIPTS_DIR / "factory" / "parse_gate_summary.py"
    command = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(parser_path),
        "--target",
        str(artifact),
        "--quiet",
    ]
    return run_check("gate-summary-parser", command)


def run_workflow_check() -> CheckResult:
    """Run GitHub workflow YAML and shell syntax verifier on all workflows.

    Always runs because workflow validity depends on all workflows (duplicate name detection).
    """
    verifier_path = SCRIPTS_DIR / "verify_github_workflows.py"
    if not verifier_path.exists():
        return CheckResult(
            name="workflow-verify",
            command="verify_github_workflows.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: verify_github_workflows.py not found",
        )

    command = [str(REPO_ROOT / ".venv" / "bin" / "python"), str(verifier_path)]
    return run_check("workflow-verify", command)