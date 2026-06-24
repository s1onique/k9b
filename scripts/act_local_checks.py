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


def run_no_new_llm_allowlist_check() -> CheckResult:
    """Run the no-new-allowlist gate before LLM-friendly check.
    
    This gate runs BEFORE the normal LLM-friendly check to reject
    allowlist growth before the normal gate can accept it.
    
    CRITICAL: If the verifier is missing, this is a FAIL (not SKIP).
    The no-new-allowlist policy is mandatory debt containment.
    """
    verifier_path = SCRIPTS_DIR / "verify_no_new_llm_allowlist.py"
    if not verifier_path.exists():
        # FAIL closed: missing verifier is a policy violation
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
    
    # Display string for the command
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
    # Check if checker supports --changed-only
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
    
    # For changed shell files, we verify they're in the inventory
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

    This check always runs because workflow validity depends on all workflows
    (duplicate name detection requires seeing the full set). It's fast (~1s).
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


def run_golden_case_check() -> CheckResult:
    """Run golden case one-pass production-loop diagnosis verification.

    This check:
    - Runs the production one-pass diagnosis loop adapter on the pod-failure golden case
    - Uses golden-case fake handlers for read-only check execution
    - Uses deterministic LLM provider for diagnosis
    - Verifies the diagnosis output against expected.json
    - Ensures correct category, root cause, and no forbidden conclusions

    This is a fast, deterministic check that uses checked-in fixtures.

    The one-pass production loop exercises:
    - incident_case_file (build)
    - incident_llm_diagnosis (with injected deterministic provider)
    - incident_diagnosis_loop_orchestrator (one-pass)
    - incident_read_only_check_runner (with injected fake handlers)

    Note: The standalone fixture harness (run_golden_case_diagnosis_via_production_loop.py)
    is preserved for focused tests. The new runner exercises the production loop machinery
    more completely.
    """
    # Check if golden case verifier exists
    verifier_path = SCRIPTS_DIR / "verify_diagnosis_golden_case.py"

    # Check if one-pass production loop adapter exists
    production_adapter_path = SCRIPTS_DIR / "run_golden_case_via_one_pass_diagnosis_loop.py"

    if not verifier_path.exists():
        return CheckResult(
            name="golden-case-verify",
            command="verify_diagnosis_golden_case.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: verify_diagnosis_golden_case.py not found",
        )

    if not production_adapter_path.exists():
        return CheckResult(
            name="golden-case-verify",
            command="run_golden_case_via_one_pass_diagnosis_loop.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: one-pass production loop adapter not found - golden case must exercise production path",
        )

    # Define golden case paths
    case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
    expected_path = case_dir / "expected.json"

    if not case_dir.exists():
        return CheckResult(
            name="golden-case-verify",
            command="golden case bundle",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message=f"Golden case bundle not found: {case_dir}",
        )

    if not expected_path.exists():
        return CheckResult(
            name="golden-case-verify",
            command="expected.json",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message=f"Expected.json not found: {expected_path}",
        )

    # Create temp output directory
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_dir = Path(tmp_dir) / "diagnosis-output"

        # Run one-pass production loop adapter (exercises real production path)
        production_cmd = [
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            str(production_adapter_path),
            "--case-dir", str(case_dir),
            "--output-dir", str(output_dir),
        ]

        production_result = subprocess.run(
            production_cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if production_result.returncode != 0:
            return CheckResult(
                name="golden-case-verify",
                command=shlex.join(production_cmd),
                status="FAIL",
                duration_ms=0,
                exit_code=production_result.returncode,
                error_message=f"One-pass production loop adapter failed: {production_result.stderr[:500]}",
            )

        # Verify diagnosis output
        diagnosis_path = output_dir / "diagnosis.json"
        if not diagnosis_path.exists():
            return CheckResult(
                name="golden-case-verify",
                command="diagnosis.json",
                status="FAIL",
                duration_ms=0,
                exit_code=1,
                error_message="Diagnosis output not found",
            )

        verify_cmd = [
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            str(verifier_path),
            "--expected", str(expected_path),
            "--diagnosis", str(diagnosis_path),
            "--case-dir", str(case_dir),
        ]

        return run_check("golden-case-verify", verify_cmd)


def run_provenance_golden_case_check() -> CheckResult:
    """Run provenance verification for the golden case.

    This check:
    - Verifies source_kind is live_sanitized_artifact (not representative_fixture)
    - Verifies provenance.artifacts_hash is non-null
    - Verifies provenance.github_artifact_digest is present
    - Verifies real_live_artifact_required_for_promotion is false
    - Verifies required evidence files exist
    - Verifies sanitizer findings show success
    - Verifies provenance data is not placeholder/mock data

    PASS-as-not-yet-promoted behavior: When source_kind is representative_fixture, this check
    passes (exit 0) because the case is intentionally not yet promoted.
    This allows ACT-local to pass before real promotion occurs.

    This is a fast, offline check that does not contact GitHub.
    """
    # Check if provenance verifier exists
    verifier_path = SCRIPTS_DIR / "verify_provenance_golden_case.py"

    if not verifier_path.exists():
        return CheckResult(
            name="provenance-golden-case",
            command="verify_provenance_golden_case.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: verify_provenance_golden_case.py not found",
        )

    # Define golden case path
    case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"

    if not case_dir.exists():
        return CheckResult(
            name="provenance-golden-case",
            command="golden case bundle",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message=f"Golden case bundle not found: {case_dir}",
        )

    # Run provenance verification
    verify_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(verifier_path),
        "--case-dir", str(case_dir),
    ]

    return run_check("provenance-golden-case", verify_cmd)


def run_golden_case_privacy_check() -> CheckResult:
    """Run privacy verification for diagnosis golden-case fixtures.

    This check:
    - Scans golden-case fixture directories for leaked internal topology
    - Detects RFC1918 private IPs (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
    - Detects internal K8s node names (k3s-worker-*, k3s-master-*)
    - Detects internal namespace names (k9b-cnpg-lab-[0-9]+)
    - Detects internal domains (*.spbnix.local, registry.spbnix.com)
    - Detects raw artifact paths (lab-artifacts/live)
    - Allows intended placeholders: <PRIVATE_IP>, <K8S_NODE>, etc.
    - Reports file, line number, pattern class, and bounded excerpt on failure

    This is a fail-closed check that prevents accidental commits of private topology.
    Missing verifier is a HARD FAILURE (not SKIP) because privacy is mandatory.

    This is a fast, offline check that does not contact external services.
    """
    # Check if privacy verifier exists - HARD FAIL if missing (privacy is mandatory)
    verifier_path = SCRIPTS_DIR / "verify_diagnosis_golden_case_privacy.py"

    if not verifier_path.exists():
        return CheckResult(
            name="golden-case-privacy",
            command="verify_diagnosis_golden_case_privacy.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: verify_diagnosis_golden_case_privacy.py not found - privacy gate is missing",
        )

    # Define golden case path
    case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"

    if not case_dir.exists():
        return CheckResult(
            name="golden-case-privacy",
            command="golden case bundle",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message=f"Golden case bundle not found: {case_dir}",
        )

    # Run privacy verification
    verify_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(verifier_path),
        str(case_dir),
    ]

    return run_check("golden-case-privacy", verify_cmd)


def run_incident_api_one_pass_diagnosis_check() -> CheckResult:
    """Run incident API/service one-pass diagnosis wiring verification.

    This check:
    - Exercises the incident diagnosis service seam with the pod-failure golden case
    - Uses fake stores, fake providers, and fake read-only handlers
    - Verifies the golden case passes through the service/API path
    - Proves the same one-pass loop is invoked as the golden-case proof
    - Verifies read-only fake handlers are invoked
    - Verifies missing providers/handlers fail closed
    - Verifies mutation proposals fail closed

    This is a fast, deterministic check that uses checked-in fixtures.
    It exercises the new service function (incident_diagnosis_service.py)
    and proves it wires correctly to the production one-pass loop.

    Missing script is a HARD FAILURE because the ACT requires this check.
    """
    # Check if the API/service one-pass diagnosis check script exists
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

    # Define golden case path
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

    # Run the incident API one-pass diagnosis check
    check_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(check_script_path),
    ]

    return run_check("incident-api-one-pass-diagnosis", check_cmd)
