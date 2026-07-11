#!/usr/bin/env python3
"""ACT-Local frontend vitest check.

Runs targeted frontend API client and component tests with mocked fetch.
HARD FAILURE if tests missing (ACT requires these tests).

Hermeticity contract: this check MUST NOT silently fetch the newest
Vitest via ``npx``. It invokes the project's pinned Vitest from
``frontend/node_modules/.bin/vitest`` when present, and otherwise
fails closed with a clear "frontend deps not installed" message.
``npx`` is forbidden because it triggers an implicit npm install of
the latest Vitest, which can break with the repository's pinned
config (e.g., Vitest 4.1.10 cannot resolve ``vitest/config``).
"""

from __future__ import annotations

from pathlib import Path

from act_local_checks import run_check
from act_local_contract import CheckResult

REPO_ROOT = Path(__file__).parent.parent


def run_frontend_one_pass_diagnosis_check() -> CheckResult:
    """Run frontend one-pass diagnosis UI check."""
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

    # Pinned local binary preferred over ``npx`` to keep the test hermetic.
    # ``npx`` will silently fetch the latest Vitest when the local binary
    # is missing, which is forbidden by the verification discipline.
    local_vitest = REPO_ROOT / "frontend" / "node_modules" / ".bin" / "vitest"
    if not local_vitest.exists():
        return CheckResult(
            name="frontend-one-pass-diagnosis",
            command="frontend/node_modules/.bin/vitest run ...",
            status="FAIL",
            duration_ms=0,
            exit_code=127,
            error_message=(
                "CRITICAL: frontend/node_modules/.bin/vitest not found. "
                "Run `cd frontend && npm ci` to install pinned dependencies. "
                "Refusing to fall back to `npx vitest` because npx silently "
                "fetches the latest Vitest which can break the repository's "
                "pinned config."
            ),
        )

    check_cmd = [
        str(local_vitest), "run",
        "src/api/incidentOnePassDiagnosis.test.ts",
        "src/api/incidentOnePassDiagnosisValidation.test.ts",
        "src/components/IncidentOnePassDiagnosisPanel.test.tsx",
    ]

    return run_check("frontend-one-pass-diagnosis", check_cmd, cwd=str(REPO_ROOT / "frontend"))