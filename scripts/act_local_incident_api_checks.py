#!/usr/bin/env python3
"""ACT-Local incident API one-pass diagnosis checks.

Exercises the incident diagnosis service seam and HTTP API route with
the golden case bundle, verifying both wire to the production
``run_incident_one_pass_diagnosis`` loop.

HARD FAILURE if a script or golden case is missing (ACT requires both).
"""

from __future__ import annotations

from pathlib import Path

from act_local_checks import run_check
from act_local_contract import CheckResult

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent


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