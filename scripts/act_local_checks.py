#!/usr/bin/env python3
"""ACT-Local check implementations.

Provides individual check functions that run verification tools on changed files.
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


def run_runtime_structured_logs_check() -> CheckResult:
    """Run the runtime structured logs gate (JSONL-only contract).
    
    Verifies that the scheduler runtime log fixtures conform to the JSONL-only
    contract. This gate catches unstructured log emissions that cause UI warning
    count mismatches.
    
    The gate:
    1. Checks that required fixtures exist and are tracked by git
    2. Verifies the known-bad fixture FAILS (has raw unstructured lines)
    3. Verifies the structured fixture PASSES (all JSONL format)
    
    This prevents locally-passing gates that rely on untracked fixtures.
    """
    verifier_path = SCRIPTS_DIR / "verify_runtime_structured_logs.py"
    if not verifier_path.exists():
        return CheckResult(
            name="runtime-structured-logs",
            command="verify_runtime_structured_logs.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: scripts/verify_runtime_structured_logs.py not found",
        )
    
    # Required fixtures for the runtime log contract
    required_fixtures = [
        REPO_ROOT / "tests" / "fixtures" / "runtime_logs_mixed.log",
        REPO_ROOT / "tests" / "fixtures" / "runtime_logs_structured.log",
        REPO_ROOT / "tests" / "fixtures" / "runtime_logs_valid.log",
    ]
    
    # Check all fixtures exist and are tracked
    for fixture in required_fixtures:
        if not fixture.exists():
            return CheckResult(
                name="runtime-structured-logs",
                command=f"fixture existence check: {fixture.name}",
                status="FAIL",
                duration_ms=0,
                exit_code=1,
                error_message=f"Required runtime log fixture missing: {fixture}",
            )
        
        if not _is_git_tracked(fixture):
            return CheckResult(
                name="runtime-structured-logs",
                command=f"git ls-files --error-unmatch {fixture.name}",
                status="FAIL",
                duration_ms=0,
                exit_code=1,
                error_message=f"Required runtime log fixture is not tracked by git: {fixture}",
            )
    
    # Run the verifier on the fixtures
    command = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(verifier_path),
        str(required_fixtures[0]),  # mixed fixture
        str(required_fixtures[1]),  # structured fixture
        str(required_fixtures[2]),  # valid fixture
    ]
    
    start = time.time()
    error_message = None
    status = "PASS"
    
    try:
        result = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = result.stdout + result.stderr
        
        # Verify the expected pattern: mixed fixture FAILs, others PASS
        # Output uses relative paths, so check for file basename patterns
        bad_fail = "runtime_logs_mixed.log" in output and "FAIL:" in output
        structured_pass = "runtime_logs_structured.log" in output and "PASS:" in output
        valid_pass = "runtime_logs_valid.log" in output and "PASS:" in output
        
        if not bad_fail:
            status = "FAIL"
            error_message = "Expected mixed fixture to FAIL but it didn't"
        elif not structured_pass:
            status = "FAIL"
            error_message = "Expected structured fixture to PASS but it didn't"
        elif not valid_pass:
            status = "FAIL"
            error_message = "Expected valid fixture to PASS but it didn't"
        
        exit_code = 0 if status == "PASS" else 1
        
    except subprocess.TimeoutExpired:
        exit_code = 124
        status = "FAIL"
        error_message = "Command timed out after 300s"
    except Exception as e:
        exit_code = 1
        status = "FAIL"
        error_message = str(e)
    
    duration_ms = int((time.time() - start) * 1000)
    display_command = shlex.join(command)
    
    return CheckResult(
        name="runtime-structured-logs",
        command=display_command,
        status=status,
        duration_ms=duration_ms,
        exit_code=exit_code,
        error_message=error_message,
    )


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


def run_incident_api_one_pass_diagnosis_check() -> CheckResult:
    """Run incident API/service one-pass diagnosis wiring verification.

    Exercises incident diagnosis service seam with golden case, verifies wiring to production one-pass loop.
    HARD FAILURE if script missing (ACT requires this check).
    """
    check_script_path = SCRIPTS_DIR / "run_incident_api_one_pass_diagnosis_check.py"
    if not check_script_path.exists():
        return CheckResult(
            name="incident-api-one-pass-diagnosis",
            command="run_incident_api_one_pass_diagnosis_check.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: run_incident_api_one_pass_diagnosis_check.py not found - ACT requires this check",
        )
    
    case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
    if not case_dir.exists():
        return CheckResult(
            name="incident-api-one-pass-diagnosis",
            command="golden case bundle",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message=f"Golden case bundle not found: {case_dir}",
        )
    
    check_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(check_script_path),
    ]
    
    return run_check("incident-api-one-pass-diagnosis", check_cmd)


def run_incident_api_route_one_pass_diagnosis_check() -> CheckResult:
    """Run incident API route one-pass diagnosis wiring verification.

    Exercises HTTP API route, verifies route wires to run_incident_one_pass_diagnosis().
    HARD FAILURE if script missing (ACT requires this check).
    """
    check_script_path = SCRIPTS_DIR / "run_incident_api_route_one_pass_diagnosis_check.py"
    if not check_script_path.exists():
        return CheckResult(
            name="incident-api-route-one-pass-diagnosis",
            command="run_incident_api_route_one_pass_diagnosis_check.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: run_incident_api_route_one_pass_diagnosis_check.py not found - ACT requires this check",
        )
    
    case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
    if not case_dir.exists():
        return CheckResult(
            name="incident-api-route-one-pass-diagnosis",
            command="golden case bundle",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message=f"Golden case bundle not found: {case_dir}",
        )
    
    check_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(check_script_path),
    ]
    
    return run_check("incident-api-route-one-pass-diagnosis", check_cmd)


def run_frontend_one_pass_diagnosis_check() -> CheckResult:
    """Run frontend one-pass diagnosis UI check.

    Runs targeted frontend API client and component tests with mocked fetch.
    HARD FAILURE if tests missing (ACT requires these tests).
    """
    api_test_path = REPO_ROOT / "frontend" / "src" / "api" / "incidentOnePassDiagnosis.test.ts"
    component_test_path = REPO_ROOT / "frontend" / "src" / "components" / "IncidentOnePassDiagnosisPanel.test.tsx"
    
    if not api_test_path.exists():
        return CheckResult(
            name="frontend-one-pass-diagnosis",
            command="vitest --run frontend/src/api/incidentOnePassDiagnosis.test.ts",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: frontend/src/api/incidentOnePassDiagnosis.test.ts not found - ACT requires API client tests",
        )
    
    if not component_test_path.exists():
        return CheckResult(
            name="frontend-one-pass-diagnosis",
            command="vitest --run frontend/src/components/IncidentOnePassDiagnosisPanel.test.tsx",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: frontend/src/components/IncidentOnePassDiagnosisPanel.test.tsx not found - ACT requires component tests",
        )
    
    check_cmd = [
        "npx", "vitest", "run",
        "src/api/incidentOnePassDiagnosis.test.ts",
        "src/api/incidentOnePassDiagnosisValidation.test.ts",
        "src/components/IncidentOnePassDiagnosisPanel.test.tsx",
    ]
    
    return run_check("frontend-one-pass-diagnosis", check_cmd, cwd=str(REPO_ROOT / "frontend"))
