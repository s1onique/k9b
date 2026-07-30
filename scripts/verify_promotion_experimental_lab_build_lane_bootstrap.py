"""Bootstrap contract proofs for the experimental-lab build lane verifier.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION04

P0-8 (CORRECTION04) bootstrap proofs enforced on the runtime workflow:

  1. editable install without ``[dev]``                  -> rejected
  2. direct ``pip install pytest`` outside authority      -> rejected
  3. missing pytest version preflight                    -> rejected
  4. missing Ruff version preflight                     -> rejected
  5. missing mypy version preflight                      -> rejected
  6. pytest execution before canonical bootstrap          -> rejected
  7. ``runtime_gate=pass`` emitted before pytest         -> rejected
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.verify_promotion_experimental_lab_build_lane import Finding


def check_bootstrap_contract(runtime_path: Path) -> list[Finding]:
    """Run all CORRECTION04 bootstrap proofs against the runtime workflow."""
    findings: list[Finding] = []
    if not runtime_path.exists():
        findings.append(
            Finding(
                "RUNTIME_WORKFLOW_MISSING",
                f"{runtime_path} does not exist",
            )
        )
        return findings
    raw = runtime_path.read_text(encoding="utf-8")

    # Proof 1: editable install without ``[dev]`` is rejected.
    if re.search(r"pip install -e\s+\.", raw) and ".[dev]" not in raw:
        findings.append(
            Finding(
                "EDITABLE_INSTALL_WITHOUT_DEV",
                "runtime workflow installs ``-e .`` without ``.[dev]``; "
                "use ``-e ``.[dev]```` or invoke "
                "scripts/ci/bootstrap_python_dev.sh",
            )
        )

    # Proof 2: ``pip install pytest`` (or any standalone tooling install)
    # outside the canonical bootstrap is rejected.
    bad_pip_install = re.findall(
        r"pip install\s+[^\n]*\b(pytest|ruff|mypy)\b",
        raw,
    )
    if bad_pip_install:
        findings.append(
            Finding(
                "DIRECT_PIP_INSTALL_TEST_TOOL",
                "runtime workflow installs pytest/ruff/mypy via direct "
                "``pip install``; use scripts/ci/bootstrap_python_dev.sh "
                "(canonical ``.[dev]`` install) instead",
            )
        )

    # Proof 3: pytest --version MUST appear in the runtime workflow.
    if "pytest --version" not in raw:
        findings.append(
            Finding(
                "PYTEST_VERSION_PREFLIGHT_MISSING",
                "runtime workflow does not run ``pytest --version`` "
                "before invoking the test suite",
            )
        )
    # Proof 4: Ruff --version MUST appear.
    if "ruff --version" not in raw:
        findings.append(
            Finding(
                "RUFF_VERSION_PREFLIGHT_MISSING",
                "runtime workflow does not run ``ruff --version`` "
                "before linting changed Python",
            )
        )
    # Proof 5: mypy --version MUST appear.
    if "mypy --version" not in raw:
        findings.append(
            Finding(
                "MYPY_VERSION_PREFLIGHT_MISSING",
                "runtime workflow does not run ``mypy --version`` "
                "before type-checking changed Python",
            )
        )

    # Proof 6: pytest -m pytest MUST NOT be invoked before the canonical
    # bootstrap step.  The bootstrap step must precede any pytest -m call.
    bootstrap_index = raw.find("bootstrap_python_dev.sh")
    pytest_call_index = raw.find("-m pytest")
    if (
        bootstrap_index == -1
        or pytest_call_index == -1
        or pytest_call_index < bootstrap_index
    ):
        findings.append(
            Finding(
                "PYTEST_BEFORE_CANONICAL_BOOTSTRAP",
                "runtime workflow runs pytest before the canonical "
                "``bootstrap_python_dev.sh`` install",
            )
        )

    # Proof 7: ``runtime_gate=pass`` MUST NOT appear before the pytest
    # step that emits it.
    gate_emit_index = raw.find('runtime_gate=pass"')
    pytest_emit_index = raw.find("-m pytest")
    if gate_emit_index != -1 and (
        pytest_emit_index == -1 or gate_emit_index < pytest_emit_index
    ):
        findings.append(
            Finding(
                "RUNTIME_GATE_PASS_BEFORE_PYTEST",
                "runtime workflow writes ``runtime_gate=pass`` before "
                "running pytest; emit it only after pytest returns zero",
            )
        )

    return findings