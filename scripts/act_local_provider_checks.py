"""ACT-Local check implementations for provider-related checks.

This module is separated from act_local_checks.py to keep files under
the LLM-friendly 500-line limit.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from act_local_contract import CheckResult

REPO_ROOT = Path(__file__).parent.parent


def run_provider_artifact_verifier_check() -> CheckResult:
    """Run provider artifact verifier tests.

    Verifies fail-closed behavior for LLM diagnosis artifacts:
    - Secret detection (API keys, tokens, credentials)
    - Internal network pattern detection
    - Blocked field content detection (mutation commands)
    HARD FAILURE if verifier tests missing.
    """
    test_path = REPO_ROOT / "tests" / "test_provider_artifact_verifier.py"
    if not test_path.exists():
        return CheckResult(
            name="provider-artifact-verifier",
            command="pytest tests/test_provider_artifact_verifier.py",
            status="FAIL",
            duration_ms=0,
            exit_code=1,
            error_message="CRITICAL: tests/test_provider_artifact_verifier.py not found - provider artifact verifier is missing",
        )
    
    check_cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        "-m", "pytest",
        str(test_path),
        "-v",
    ]
    
    return _run_check("provider-artifact-verifier", check_cmd)


def _run_check(name: str, command: list[str]) -> CheckResult:
    """Run a single verification check.
    
    Returns CheckResult with status, duration, and exit code.
    """
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
