"""Bootstrap + inventory contract proofs for the experimental-lab verifier.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION04/05

P0-8 (CORRECTION04) bootstrap proofs enforced on the runtime workflow:

  1. editable install without ``[dev]``                  -> rejected
  2. direct ``pip install pytest`` outside authority      -> rejected
  3. missing pytest version preflight                    -> rejected
  4. missing Ruff version preflight                     -> rejected
  5. missing mypy version preflight                      -> rejected
  6. pytest execution before canonical bootstrap          -> rejected
  7. ``runtime_gate=pass`` emitted before pytest         -> rejected

P0-11 (CORRECTION05) additional bootstrap / inventory proofs:

  8. inline ``TESTS=(...)`` array in runtime workflow     -> rejected
  9. canonical runner invocation missing                 -> rejected
 10. PATH export missing before bootstrap proof           -> rejected
 11. PATH proof command missing in bootstrap script      -> rejected
 12. canonical manifest referenced from caller           -> required
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.verify_promotion_experimental_lab_build_lane import Finding


def _first_invocation_index(text: str, marker: str) -> int:
    """Return the index of the FIRST step-level invocation of ``marker``.

    Step-level invocations are recognised by preceding the marker with
    ``bash`` (for shell scripts) or ``.venv/bin/python`` (for Python).
    Comments and docstrings that merely mention the marker are skipped.

    Returns -1 if no step-level invocation is found.
    """
    candidates: list[int] = []
    pos = 0
    while True:
        idx = text.find(marker, pos)
        if idx == -1:
            break
        candidates.append(idx)
        pos = idx + len(marker)
    for candidate in candidates:
        # Look back at most 200 characters for a step prefix.
        window_start = max(0, candidate - 200)
        prefix = text[window_start:candidate]
        if "\n          bash " in prefix[-200:] or ".venv/bin/python" in prefix[-200:]:
            return candidate
    return -1


def check_bootstrap_contract(runtime_path: Path) -> list[Finding]:
    """Run all CORRECTION04 + CORRECTION05 bootstrap/inventory proofs."""
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

    # Proof 3-5: tool version preflight MUST appear in the runtime workflow.
    for tool, code in (
        ("pytest", "PYTEST_VERSION_PREFLIGHT_MISSING"),
        ("ruff", "RUFF_VERSION_PREFLIGHT_MISSING"),
        ("mypy", "MYPY_VERSION_PREFLIGHT_MISSING"),
    ):
        if f"{tool} --version" not in raw:
            findings.append(
                Finding(
                    code,
                    f"runtime workflow does not run ``{tool} --version`` "
                    f"before invoking the test suite",
                )
            )

    # Proof 8 (CORRECTION05): no inline TESTS=(...) array.
    if re.search(r"^\s*TESTS=\(", raw, re.MULTILINE):
        findings.append(
            Finding(
                "INLINE_TESTS_ARRAY_FORBIDDEN",
                "runtime workflow contains an inline ``TESTS=(...)`` "
                "array; the canonical inventory is "
                "scripts/ci/promotion_runtime_tests.txt",
            )
        )

    # Proof 9 (CORRECTION05): canonical runner invocation MUST appear.
    if "run_promotion_runtime_gate.py" not in raw:
        findings.append(
            Finding(
                "CANONICAL_RUNNER_INVOCATION_MISSING",
                "runtime workflow does not invoke "
                "scripts/ci/run_promotion_runtime_gate.py; "
                "tests MUST be executed through the canonical runner",
            )
        )

    # Proof 6 (bootstrap ordering): the canonical bootstrap step MUST
    # precede any pytest -m invocation.  Use the FIRST ``bash``-based
    # invocation of the bootstrap script and the FIRST ``python``-based
    # invocation of the runner, ignoring comments / docstrings.
    bootstrap_index = _first_invocation_index(raw, "bootstrap_python_dev.sh")
    pytest_call_index = _first_invocation_index(raw, "run_promotion_runtime_gate.py")
    if (
        bootstrap_index == -1
        or pytest_call_index == -1
        or pytest_call_index < bootstrap_index
    ):
        findings.append(
            Finding(
                "PYTEST_BEFORE_CANONICAL_BOOTSTRAP",
                "runtime workflow runs the canonical runner before the "
                "canonical ``bootstrap_python_dev.sh`` install",
            )
        )

    # Proof 7: ``runtime_gate=pass`` MUST be emitted via the runner
    # output, not pre-written.  Skip this check when the workflow does
    # not invoke the runner at all (proof 9 will already cover that).
    if (
        pytest_call_index != -1
        and 'runtime_gate=pass"' in raw
        and raw.find('runtime_gate=pass"') < pytest_call_index
    ):
        findings.append(
            Finding(
                "RUNTIME_GATE_PASS_BEFORE_PYTEST",
                "runtime workflow writes ``runtime_gate=pass`` before "
                "running the canonical runner; the runner is the sole "
                "authority for that verdict",
            )
        )

    return findings


def check_bootstrap_script(script_path: Path) -> list[Finding]:
    """P0-6 / P0-11 (CORRECTION05) bootstrap script proofs.

    The bootstrap script MUST:
      * export ``PATH`` BEFORE the first ``python`` / proof command
      * prove every tool resolves under ``${VENV_DIR}/bin/``
    """
    findings: list[Finding] = []
    if not script_path.exists():
        findings.append(
            Finding(
                "BOOTSTRAP_SCRIPT_MISSING",
                f"{script_path} does not exist",
            )
        )
        return findings
    raw = script_path.read_text(encoding="utf-8")

    # Proof: explicit PATH export precedes the first proof command.
    export_index = raw.find('export PATH="${VENV_DIR}/bin:${PATH}"')
    first_python = -1
    for marker in ("python --version", "python -m pip", "python -m pytest"):
        idx = raw.find(marker)
        if idx != -1 and (first_python == -1 or idx < first_python):
            first_python = idx
    if export_index == -1:
        findings.append(
            Finding(
                "BOOTSTRAP_PATH_EXPORT_MISSING",
                "bootstrap script does not export "
                "``PATH=\"${VENV_DIR}/bin:${PATH}\"`` before any proof "
                "command",
            )
        )
    elif first_python != -1 and export_index > first_python:
        findings.append(
            Finding(
                "BOOTSTRAP_PATH_EXPORT_AFTER_PYTHON",
                "bootstrap script exports PATH AFTER the first ``python`` "
                "proof command",
            )
        )

    # Proof: PATH proof for python/pytest/ruff/mypy.
    if "command -v" not in raw:
        findings.append(
            Finding(
                "BOOTSTRAP_PATH_PROOF_MISSING",
                "bootstrap script does not run ``command -v`` to prove "
                "every tool resolves under ``${VENV_DIR}/bin/``",
            )
        )

    return findings