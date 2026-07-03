#!/usr/bin/env python3
"""GitHub workflow YAML and embedded-shell verifier."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
METADATA_ONLY_KEYS = frozenset({
    "name", "id", "if", "unless", "env", "with", "continue-on-error",
    "timeout-minutes", "shell", "working-directory", "condition", "outputs",
})
NON_BASH_SHELLS = frozenset({"pwsh", "powershell", "python", "cmd", "shell"})
PATH_LIKE_PATTERNS = [
    r"^\./", r"^\.\./", r"^[a-zA-Z]:[/\\]", r"\.yml$", r"\.yaml$",
    r"\.yml/", r"\.yaml/",
]


class WorkflowError:
    def __init__(
        self,
        workflow_path: Path,
        job_id: str | None = None,
        step_index: int | None = None,
        step_name: str | None = None,
        error_type: str = "ERROR",
        message: str = "",
    ) -> None:
        self.workflow_path = workflow_path
        self.job_id = job_id
        self.step_index = step_index
        self.step_name = step_name
        self.error_type = error_type
        self.message = message

    def __str__(self) -> str:
        parts = [f"{self.error_type} in {self.workflow_path}"]
        for attr in ("job_id", "step_index", "step_name"):
            val = getattr(self, attr)
            if val is not None:
                parts.append(f"{attr.replace('_', ' ')} '{val}'" if isinstance(val, str) else f"{attr}[{val}]")
        parts.append(f": {self.message}")
        return " | ".join(parts)


class WorkflowVerifier:
    def __init__(self, workflows_dir: Path) -> None:
        self.workflows_dir = workflows_dir
        self.errors: list[WorkflowError] = []
        self.warnings: list[WorkflowError] = []
        self._workflow_names: dict[str, Path] = {}
        self._skipped_shells: list[tuple[WorkflowError, str]] = []

    def verify_all(self) -> bool:
        self.errors = []
        self.warnings = []
        self._workflow_names = {}
        self._skipped_shells = []
        if not self.workflows_dir.exists():
            self.errors.append(WorkflowError(self.workflows_dir, "ERROR", message=f"Directory not found: {self.workflows_dir}"))
            return False
        workflow_files = sorted(self.workflows_dir.glob("*.yml")) + sorted(self.workflows_dir.glob("*.yaml"))
        if not workflow_files:
            self.warnings.append(WorkflowError(self.workflows_dir, "WARNING", message="No workflow files found"))
            return True
        for workflow_file in workflow_files:
            self._verify_workflow(workflow_file)
        return len(self.errors) == 0

    def _verify_workflow(self, workflow_path: Path) -> None:
        try:
            with open(workflow_path, encoding="utf-8") as f:
                workflow = yaml.safe_load(f)
        except yaml.YAMLError as e:
            self.errors.append(WorkflowError(workflow_path, error_type="YAML_ERROR", message=f"YAML parse error: {e}"))
            return
        if workflow is None:
            self.errors.append(WorkflowError(workflow_path, error_type="YAML_ERROR", message="Empty workflow file"))
            return
        if "name" not in workflow:
            self.errors.append(WorkflowError(workflow_path, error_type="MISSING_NAME", message="Missing top-level 'name' field"))
        else:
            self._verify_workflow_name(workflow_path, workflow["name"])
        if "on" not in workflow and True not in workflow:
            self.errors.append(WorkflowError(workflow_path, error_type="MISSING_ON", message="Missing top-level 'on' trigger field"))
        if "jobs" not in workflow:
            self.errors.append(WorkflowError(workflow_path, error_type="MISSING_JOBS", message="Missing top-level 'jobs' field"))
        else:
            self._verify_jobs(workflow_path, workflow.get("jobs", {}))

    def _verify_workflow_name(self, workflow_path: Path, name: object) -> None:
        if not isinstance(name, str) or not name.strip():
            self.errors.append(WorkflowError(workflow_path, error_type="INVALID_NAME", message=f"Empty or non-string workflow name: {name!r}"))
            return
        for pattern in PATH_LIKE_PATTERNS:
            if re.search(pattern, name, re.IGNORECASE):
                self.errors.append(WorkflowError(workflow_path, error_type="PATH_LIKE_NAME", message=f"Workflow name looks like a file path: {name!r}"))
                return
        normalized_name = name.strip().lower()
        if normalized_name in self._workflow_names:
            self.errors.append(WorkflowError(workflow_path, error_type="DUPLICATE_NAME", message=f"Duplicate workflow name: {name!r} (also used in {self._workflow_names[normalized_name]})"))
        else:
            self._workflow_names[normalized_name] = workflow_path

    def _verify_jobs(self, workflow_path: Path, jobs: object) -> None:
        if not isinstance(jobs, dict):
            self.errors.append(WorkflowError(workflow_path, error_type="INVALID_JOBS", message=f"'jobs' must be a dict, got {type(jobs).__name__}"))
            return
        for job_id, job in jobs.items():
            self._verify_job(workflow_path, job_id, job)

    def _verify_job(self, workflow_path: Path, job_id: str, job: object) -> None:
        if not isinstance(job, dict):
            self.errors.append(WorkflowError(workflow_path, job_id=job_id, error_type="INVALID_JOB", message=f"Job '{job_id}' must be a dict"))
            return
        has_runs_on = "runs-on" in job
        has_uses = "uses" in job
        if not has_runs_on and not has_uses:
            self.errors.append(WorkflowError(workflow_path, job_id=job_id, error_type="MISSING_RUNS_ON", message=f"Job '{job_id}' missing both 'runs-on' and 'uses'"))
        if "steps" in job:
            self._verify_steps(workflow_path, job_id, job["steps"])

    def _verify_steps(self, workflow_path: Path, job_id: str, steps: object) -> None:
        if not isinstance(steps, list):
            self.errors.append(WorkflowError(workflow_path, job_id=job_id, error_type="INVALID_STEPS", message=f"Steps must be a list, got {type(steps).__name__}"))
            return
        for step_idx, step in enumerate(steps):
            self._verify_step(workflow_path, job_id, step_idx, step)

    def _verify_step(self, workflow_path: Path, job_id: str, step_idx: int, step: object) -> None:
        if not isinstance(step, dict):
            self.errors.append(WorkflowError(workflow_path, job_id=job_id, step_index=step_idx, step_name=step.get("name") if isinstance(step, dict) else None, error_type="INVALID_STEP", message="Step must be a dict"))
            return
        step_name = step.get("name", "")
        has_run = "run" in step
        has_uses = "uses" in step
        actual_keys = set(step.keys()) - METADATA_ONLY_KEYS
        if not has_run and not has_uses:
            msg = "Step has neither 'run' nor 'uses' and no other keys" if not actual_keys else f"Step has no 'run' or 'uses' (has: {sorted(actual_keys)})"
            self.errors.append(WorkflowError(workflow_path, job_id=job_id, step_index=step_idx, step_name=step_name, error_type="EMPTY_STEP" if not actual_keys else "NO_EXECUTION_PRIMITIVE", message=msg))
        elif has_run and has_uses:
            self.errors.append(WorkflowError(workflow_path, job_id=job_id, step_index=step_idx, step_name=step_name, error_type="BOTH_RUN_AND_USES", message="Step cannot have both 'run' and 'uses'"))
        if has_run:
            self._verify_run_block(workflow_path, job_id, step_idx, step_name, step)

    def _verify_run_block(self, workflow_path: Path, job_id: str, step_idx: int, step_name: str, step: dict) -> None:
        run_value = step["run"]
        if not isinstance(run_value, str):
            return
        shell = step.get("shell", "").lower()
        if shell in NON_BASH_SHELLS:
            detail = f"{workflow_path}: step[{step_idx}] ({step_name}) uses shell={shell}"
            self._skipped_shells.append((WorkflowError(workflow_path, job_id=job_id, step_index=step_idx, step_name=step_name, error_type="SKIPPED_SHELL_CHECK", message=f"Skipping bash -n for shell: {shell}"), detail))
            return
        script_path = Path(tempfile.mktemp(suffix=".sh", prefix="workflow_sh_"))
        script_path.write_text(run_value + "\n")
        try:
            result = subprocess.run(["bash", "-n", str(script_path)], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                self.errors.append(WorkflowError(workflow_path, job_id=job_id, step_index=step_idx, step_name=step_name, error_type="SHELL_SYNTAX_ERROR", message=f"Shell syntax error: {result.stderr.strip()}"))
        except subprocess.TimeoutExpired:
            self.errors.append(WorkflowError(workflow_path, job_id=job_id, step_index=step_idx, step_name=step_name, error_type="SHELL_CHECK_TIMEOUT", message="bash -n timed out after 10s"))
        except Exception as e:
            self.errors.append(WorkflowError(workflow_path, job_id=job_id, step_index=step_idx, step_name=step_name, error_type="SHELL_CHECK_ERROR", message=f"bash -n check failed: {e}"))
        finally:
            if script_path.exists():
                script_path.unlink()

    def get_skipped_shells_report(self) -> str:
        if not self._skipped_shells:
            return ""
        return "\nSkipped shell checks (explicit non-bash shells):\n" + "\n".join(f"  - {detail}" for _, detail in self._skipped_shells) + "\n"


def verify_workflows(workflows_dir: Path | None = None, verbose: bool = False) -> bool:
    if workflows_dir is None:
        workflows_dir = WORKFLOWS_DIR
    verifier = WorkflowVerifier(workflows_dir)
    ok = verifier.verify_all()
    if verbose and verifier._skipped_shells:
        print(verifier.get_skipped_shells_report())
    for error in verifier.errors:
        print(str(error), file=sys.stderr)
    for warning in verifier.warnings:
        print(str(warning), file=sys.stderr)
    return ok


def run_toolchain_contract_tests(verbose: bool = False, emit_summary: bool = True, emit_diagnostics: bool = True) -> bool:
    """Run toolchain contract tests and report results.

    Returns True if all tests pass, False otherwise.
    """
    all_passed = True

    # Run workflow consumer tests
    p, f = test_toolchain_python_executable_contract(verbose=verbose, emit_diagnostics=emit_diagnostics)
    if f > 0:
        all_passed = False
    if emit_summary:
        print(f"Toolchain consumer tests: {p} passed, {f} failed")

    # Run action output contract tests
    p, f = test_toolchain_action_outputs_contract(verbose=verbose, emit_diagnostics=emit_diagnostics)
    if f > 0:
        all_passed = False
    if emit_summary:
        print(f"Toolchain action output tests: {p} passed, {f} failed")

    return all_passed


def find_step_by_name(workflow: dict, step_name: str) -> dict | None:
    """Find a step by name in a workflow dict."""
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            if step.get("name") == step_name:
                return step  # type: ignore[return-value]
    return None


def test_toolchain_python_executable_contract(verbose: bool = False, emit_diagnostics: bool = True) -> tuple[int, int]:
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


def test_toolchain_action_outputs_contract(verbose: bool = False, emit_diagnostics: bool = True) -> tuple[int, int]:
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


def run_self_test(verbose: bool = False) -> bool:
    """Run self-test against fixture workflows."""
    import tempfile

    # Fixture specs: (filename, yaml_content)
    FIXTURES: list[tuple[str, str]] = [
        ("valid_workflow.yml", "name: Valid Test Workflow\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - name: Checkout\n        uses: actions/checkout@v4\n      - name: Run test\n        run: echo \"test\"\n"),
        ("no_name.yml", "on:\n  push:\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo test\n"),
        ("empty_name.yml", 'name: ""\non:\n  push:\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo test\n'),
        ("path_like_name.yml", "name: .github/workflows/test.yml\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo test\n"),
        ("dup_a.yml", "name: Duplicate Name Test\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo test\n"),
        ("dup_b.yml", "name: Duplicate Name Test\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo test\n"),
        ("no_on.yml", "name: No Trigger\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo test\n"),
        ("no_jobs.yml", "name: No Jobs\non:\n  push:\n"),
        ("no_runs_on.yml", "name: No Runs-On\non: push\njobs:\n  build:\n    steps:\n      - run: echo test\n"),
        ("no_exec_step.yml", "name: No Exec Step\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - name: Just metadata\n        env:\n          FOO: bar\n"),
        ("both_run_and_uses.yml", "name: Both Run and Uses\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - name: Invalid step\n        run: echo test\n        uses: actions/checkout@v4\n"),
        ("bad_indent.yml", "name: Bad Indentation\non: push\njobs:\n  build:\n  runs-on: ubuntu-latest\n    steps:\n      - run: echo test\n"),
        ("missing_fi.yml", "name: Missing Fi\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - name: Test missing fi\n        run: |\n          if [ -z \"$FOO\" ]; then\n            echo \"FOO is empty\"\n          # Missing fi\n"),
        ("valid_nested_if.yml", "\n".join([
            "name: Valid Nested If",
            "on: push",
            "jobs:",
            "  build:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - name: Test nested if",
            "        run: |",
            '          if [ -z "$FOO" ]; then',
            '            echo "FOO is empty"',
            '            if [ -z "$BAR" ]; then',
            '              echo "BAR is also empty"',
            "            else",
            '              echo "BAR is set"',
            "            fi",
            "          else",
            '            echo "FOO is set"',
            "          fi",
        ])),
        ("pwsh_shell.yml", "name: Pwsh Shell\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - name: Run PowerShell\n        shell: pwsh\n        run: |\n          $foo = \"bar\"\n          Write-Host $foo\n"),
        ("python_shell.yml", "name: Python Shell\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - name: Run Python\n        shell: python\n        run: |\n          import sys\n          print(sys.version)\n"),
    ]

    with tempfile.TemporaryDirectory(prefix="workflow_verify_") as tmp_dir:
        fixtures_dir = Path(tmp_dir)
        for fname, content in FIXTURES:
            (fixtures_dir / fname).write_text(content)

        verifier = WorkflowVerifier(fixtures_dir)
        verifier.verify_all()

        if verifier._skipped_shells:
            print("\nSkipped shell checks:")
            for _, detail in verifier._skipped_shells:
                print(f"  - {detail}")

        passed = 0
        failed = 0
        EXPECTED_ERRORS = {
            "no_name.yml": {"MISSING_NAME"},
            "empty_name.yml": {"INVALID_NAME"},
            "path_like_name.yml": {"PATH_LIKE_NAME"},
            "dup_b.yml": {"DUPLICATE_NAME"},
            "no_on.yml": {"MISSING_ON"},
            "no_jobs.yml": {"MISSING_JOBS"},
            "no_runs_on.yml": {"MISSING_RUNS_ON"},
            "no_exec_step.yml": {"EMPTY_STEP"},
            "both_run_and_uses.yml": {"BOTH_RUN_AND_USES"},
            "bad_indent.yml": {"YAML_ERROR"},
            "missing_fi.yml": {"SHELL_SYNTAX_ERROR"},
        }
        VALID = {"valid_workflow.yml", "valid_nested_if.yml", "pwsh_shell.yml", "python_shell.yml"}

        # Workflow name assertions for specific files in the repo
        # Maps filename -> expected top-level name
        NAME_ASSERTIONS: dict[str, str] = {}

        # Populate name assertions from repo workflows if available
        repo_workflows_dir = REPO_ROOT / ".github" / "workflows"
        if repo_workflows_dir.exists():
            repo_cnpg_lab = repo_workflows_dir / "k9b-cnpg-incident-lab.yml"
            if repo_cnpg_lab.exists():
                NAME_ASSERTIONS["k9b-cnpg-incident-lab.yml"] = "K3s CNPG Incident Lab"

        for fname, expected in EXPECTED_ERRORS.items():
            wf_errors = {e.error_type for e in verifier.errors if e.workflow_path.name == fname}
            # Allow MISSING_ON as extra error type
            if wf_errors >= expected:
                passed += 1
                if verbose:
                    print(f"  PASS: {fname}")
            else:
                failed += 1
                print(f"  FAIL: {fname} - expected >= {expected}, got {wf_errors}")

        valid_errors = [e for e in verifier.errors if e.workflow_path.name in VALID]
        if valid_errors:
            failed += 1
            print(f"  FAIL: Valid workflows have errors: {[e.error_type for e in valid_errors]}")
        else:
            passed += 1
            if verbose:
                print("  PASS: valid_workflow.yml, valid_nested_if.yml, pwsh_shell.yml, python_shell.yml")

        skipped_count = len(verifier._skipped_shells)
        if skipped_count == 2:
            passed += 1
            if verbose:
                print("  PASS: Skipped 2 non-bash shell checks (pwsh, python)")
        else:
            failed += 1
            print(f"  FAIL: Expected 2 skipped shell checks, got {skipped_count}")

        # Verify specific workflow name assertions
        # Build reverse map: filename -> actual name (from repo scan)
        repo_name_map: dict[str, Path] = {}
        for wf_path in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
            try:
                with open(wf_path, encoding="utf-8") as f:
                    wf_data = yaml.safe_load(f)
                if wf_data and isinstance(wf_data, dict) and "name" in wf_data:
                    repo_name_map[wf_path.name] = wf_data["name"]
            except Exception:
                pass

        for fname, expected_name in NAME_ASSERTIONS.items():
            actual_name = repo_name_map.get(fname)
            if actual_name == expected_name:
                passed += 1
                if verbose:
                    print(f"  PASS: {fname} has top-level name == {expected_name!r}")
            else:
                failed += 1
                print(f"  FAIL: {fname} has name == {actual_name!r}, expected {expected_name!r}")

        print(f"\nSelf-test results: {passed} passed, {failed} failed")
        return failed == 0


def main() -> int:
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Verify GitHub workflow files.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--fixtures-dir", type=Path)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return 0 if run_self_test(verbose=args.verbose) else 1

    workflows_dir = args.fixtures_dir or (args.repo_root / ".github" / "workflows")
    verifier = WorkflowVerifier(workflows_dir)
    ok = verifier.verify_all()

    error_list = [{"workflow": str(e.workflow_path.relative_to(workflows_dir)), "job": e.job_id, "step_index": e.step_index, "step_name": e.step_name, "error_type": e.error_type, "message": e.message} for e in verifier.errors]
    skipped_list = [{"workflow": str(e.workflow_path.relative_to(workflows_dir)), "step_index": e.step_index, "step_name": e.step_name, "shell": e.message.split("shell=")[-1] if "shell=" in e.message else "unknown"} for e, _ in verifier._skipped_shells]

    # Run toolchain contract tests
    # Suppress verbose diagnostics under JSON mode to keep machine-readable output clean
    toolchain_ok = run_toolchain_contract_tests(verbose=args.verbose and not args.json, emit_summary=not args.json, emit_diagnostics=not args.json)
    if not toolchain_ok:
        ok = False

    if args.json:
        print(json.dumps({"success": ok, "workflows_dir": str(workflows_dir), "errors": error_list, "skipped_shell_checks": skipped_list}, indent=2))
    else:
        if verifier.errors:
            print(f"Found {len(verifier.errors)} error(s):", file=sys.stderr)
            for error in verifier.errors:
                print(f"  {error}", file=sys.stderr)
        if verifier._skipped_shells:
            print(verifier.get_skipped_shells_report())
        print(f"\nWorkflow verification: {'PASS' if ok else 'FAIL'}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
