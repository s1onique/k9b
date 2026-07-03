"""Toolchain contract tests for GitHub workflow verification."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def find_step_by_name(workflow: dict[str, object], step_name: str) -> dict[str, object] | None:
    """Find a step by name in a workflow dict."""
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            if step.get("name") == step_name:
                return step  # type: ignore[no-any-return]
    return None


def test_toolchain_python_executable_contract(
    verbose: bool = False,
    emit_diagnostics: bool = True,
) -> tuple[int, int]:
    """Test that toolchain consumers use python-executable, not python-location.

    This prevents regressions where consumers mistakenly use the bin directory
    instead of the Python executable path.
    """
    passed = 0
    failed = 0

    # Workflows that should use python-executable for venv setup
    EXPECTED_EXECUTABLE = {
        "k9b-otel-demo-live-lab.yml": "Prepare live lab Python venv",
    }

    for workflow_name, step_name in EXPECTED_EXECUTABLE.items():
        wf_path = WORKFLOWS_DIR / workflow_name
        if not wf_path.exists():
            failed += 1
            if emit_diagnostics:
                print(f"  FAIL: {workflow_name} not found")
            continue

        try:
            with open(wf_path, encoding="utf-8") as f:
                workflow = yaml.safe_load(f)
        except Exception as e:
            failed += 1
            if emit_diagnostics:
                print(f"  FAIL: {workflow_name} parse error: {e}")
            continue

        step = find_step_by_name(workflow, step_name)
        if step is None:
            failed += 1
            if emit_diagnostics:
                print(f"  FAIL: {workflow_name} step '{step_name}' not found")
            continue

        env = step.get("env", {})
        python_env = env.get("K9B_LIVE_LAB_PYTHON", "")

        if "python-executable" in python_env:
            passed += 1
            if verbose:
                print(f"  PASS: {workflow_name}/{step_name} uses python-executable")
        else:
            failed += 1
            if emit_diagnostics:
                print(f"  FAIL: {workflow_name}/{step_name} K9B_LIVE_LAB_PYTHON={python_env!r}, expected python-executable")

    return passed, failed


def test_toolchain_action_outputs_contract(
    verbose: bool = False,
    emit_diagnostics: bool = True,
) -> tuple[int, int]:
    """Test that toolchain action outputs have correct contracts.

    - python-location should be bin directory (legacy)
    - python-executable should end with /python3
    - python-root should reference python-root step output
    """
    passed = 0
    failed = 0

    action_path = REPO_ROOT / ".github" / "actions" / "k9b-live-lab-toolchain" / "action.yml"
    if not action_path.exists():
        failed += 1
        if emit_diagnostics:
            print(f"  FAIL: action.yml not found at {action_path}")
        return passed, failed

    try:
        with open(action_path, encoding="utf-8") as f:
            action = yaml.safe_load(f)
    except Exception as e:
        failed += 1
        if emit_diagnostics:
            print(f"  FAIL: action.yml parse error: {e}")
        return passed, failed

    outputs = action.get("outputs", {})

    # Test python-location is legacy bin dir
    python_loc = outputs.get("python-location", {})
    python_loc_value = python_loc.get("value", "") if isinstance(python_loc, dict) else ""
    if "python-bin-dir" in python_loc_value and "python3" not in python_loc_value:
        passed += 1
        if verbose:
            print("  PASS: python-location is legacy bin dir")
    else:
        failed += 1
        if emit_diagnostics:
            print(f"  FAIL: python-location value={python_loc_value!r}, expected python-bin-dir without python3")

    # Test python-executable ends with /python3
    python_exec = outputs.get("python-executable", {})
    python_exec_value = python_exec.get("value", "") if isinstance(python_exec, dict) else ""
    if python_exec_value.endswith("/python3"):
        passed += 1
        if verbose:
            print("  PASS: python-executable ends with /python3")
    else:
        failed += 1
        if emit_diagnostics:
            print(f"  FAIL: python-executable value={python_exec_value!r}, expected to end with /python3")

    # Test python-root references python-root step output
    python_root = outputs.get("python-root", {})
    python_root_value = python_root.get("value", "") if isinstance(python_root, dict) else ""
    if "python-root" in python_root_value:
        passed += 1
        if verbose:
            print("  PASS: python-root references step output")
    else:
        failed += 1
        if emit_diagnostics:
            print(f"  FAIL: python-root value={python_root_value!r}, expected to reference step output")

    return passed, failed


def run_toolchain_contract_tests(
    verbose: bool = False,
    emit_summary: bool = True,
    emit_diagnostics: bool = True,
) -> bool:
    """Run toolchain contract tests and report results.

    Returns True if all tests pass, False otherwise.
    """
    all_passed = True

    # Run workflow consumer tests
    p, f = test_toolchain_python_executable_contract(
        verbose=verbose,
        emit_diagnostics=emit_diagnostics,
    )
    if f > 0:
        all_passed = False
    if emit_summary:
        print(f"Toolchain consumer tests: {p} passed, {f} failed")

    # Run action output contract tests
    p, f = test_toolchain_action_outputs_contract(
        verbose=verbose,
        emit_diagnostics=emit_diagnostics,
    )
    if f > 0:
        all_passed = False
    if emit_summary:
        print(f"Toolchain action output tests: {p} passed, {f} failed")

    return all_passed
