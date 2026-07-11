#!/usr/bin/env python3
"""ACT-Local runtime-log structured check.

Verifies that the scheduler runtime log fixtures conform to the JSONL-only
contract. This gate catches unstructured log emissions that cause UI warning
count mismatches.

The gate:
1. Checks that required fixtures exist and are tracked by git
2. Verifies the known-bad fixture FAILS (has raw unstructured lines)
3. Verifies the structured fixture PASSES (all JSONL format)

This prevents locally-passing gates that rely on untracked fixtures.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path

from act_local_checks import _is_git_tracked
from act_local_contract import CheckResult

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent


def run_runtime_structured_logs_check() -> CheckResult:
    """Run the runtime structured logs gate (JSONL-only contract)."""
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