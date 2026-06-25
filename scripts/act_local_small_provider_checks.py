"""ACT-Local check implementations for small-provider runtime invocation."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from act_local_contract import CheckResult

REPO_ROOT = Path(__file__).parent.parent


def run_small_provider_smoke_check() -> CheckResult:
    """Run small-provider smoke test."""
    smoke_script = REPO_ROOT / "scripts" / "run_small_provider_smoke.py"
    if not smoke_script.exists():
        return CheckResult(
            name="small-provider-smoke",
            command=f"python {smoke_script}",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message=f"CRITICAL: {smoke_script} not found",
        )
    
    output_dir = REPO_ROOT / "provider-smoke" / "small-provider"
    check_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(smoke_script),
        "--output", str(output_dir),
    ]
    
    return _run_check("small-provider-smoke", check_cmd)


def run_small_provider_artifact_verifier_check() -> CheckResult:
    """Run provider artifact verifier on small-provider smoke artifacts."""
    artifact_dir = REPO_ROOT / "provider-smoke" / "small-provider"
    verifier_script = REPO_ROOT / "scripts" / "verify_diagnosis_provider_artifacts.py"
    
    if not verifier_script.exists():
        return CheckResult(
            name="small-provider-artifact-verifier",
            command=f"python {verifier_script}",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message=f"CRITICAL: {verifier_script} not found",
        )
    
    check_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(verifier_script),
        "--input", str(artifact_dir),
        "--directory",
    ]
    
    return _run_check("small-provider-artifact-verifier", check_cmd)


def _run_check(name: str, command: list[str]) -> CheckResult:
    """Run a single verification check."""
    import shlex
    
    start = time.time()
    error_message = None
    
    try:
        result = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
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
