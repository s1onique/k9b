"""ACT-Local check implementations for golden case verification.

This module is separated from act_local_checks.py to keep files under
the LLM-friendly 500-line limit.
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

from act_local_contract import CheckResult

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent


def _run_check(name: str, command: list[str], cwd: str | None = None) -> CheckResult:
    """Run a single verification check."""
    import shlex
    
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


def _run_golden_case_production_adapter(case_dir: Path, output_dir: Path) -> tuple[Path | None, str | None]:
    """Run one-pass production loop adapter."""
    production_adapter_path = SCRIPTS_DIR / "run_golden_case_via_one_pass_diagnosis_loop.py"
    if not production_adapter_path.exists():
        return None, "one-pass production loop adapter not found"
    
    production_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(production_adapter_path),
        "--case-dir", str(case_dir),
        "--output-dir", str(output_dir),
    ]
    
    result = subprocess.run(
        production_cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    
    if result.returncode != 0:
        return None, f"adapter failed: {result.stderr[:500]}"
    
    diagnosis_path = output_dir / "diagnosis.json"
    if not diagnosis_path.exists():
        return None, "diagnosis output not found"
    
    return diagnosis_path, None


def run_golden_case_check() -> CheckResult:
    """Run golden case one-pass production-loop diagnosis verification."""
    verifier_path = SCRIPTS_DIR / "verify_diagnosis_golden_case.py"
    if not verifier_path.exists():
        return CheckResult(
            name="golden-case-verify",
            command="verify_diagnosis_golden_case.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: verify_diagnosis_golden_case.py not found",
        )
    
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
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_dir = Path(tmp_dir) / "diagnosis-output"
        diagnosis_path, error = _run_golden_case_production_adapter(case_dir, output_dir)
        
        if error:
            return CheckResult(
                name="golden-case-verify",
                command="run_golden_case_via_one_pass_diagnosis_loop.py",
                status="FAIL",
                duration_ms=0,
                exit_code=1,
                error_message=error,
            )
        
        verify_cmd = [
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            str(verifier_path),
            "--expected", str(expected_path),
            "--diagnosis", str(diagnosis_path),
            "--case-dir", str(case_dir),
        ]
        
        return _run_check("golden-case-verify", verify_cmd)


def run_provenance_golden_case_check() -> CheckResult:
    """Run provenance verification for the golden case."""
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
    
    verify_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(verifier_path),
        "--case-dir", str(case_dir),
    ]
    
    return _run_check("provenance-golden-case", verify_cmd)


def run_golden_case_privacy_check() -> CheckResult:
    """Run privacy verification for diagnosis golden-case fixtures."""
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
    
    verify_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(verifier_path),
        str(case_dir),
    ]
    
    return _run_check("golden-case-privacy", verify_cmd)
