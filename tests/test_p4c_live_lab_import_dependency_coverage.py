"""Regression tests for live-lab Python dependency coverage.

The live OTel lab workflow installs a deliberately small Python environment.
These tests ensure Python modules imported by the live-lab/P4c path are either
stdlib/local modules or explicitly installed by the live-lab workflow.

The live-lab Python installation was recently redesigned so dependency
preparation is delegated through scripts/ci/ensure_live_lab_venv.sh.
The dependency surface now includes:
- Workflow YAML files
- The ensure_live_lab_venv.sh script
- Requirements files referenced by the script
"""

from __future__ import annotations

import ast
import re
import shlex
import sys
from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
OTEL_WORKFLOW = REPO_ROOT / ".github/workflows/k9b-otel-demo-live-lab.yml"
CNPG_WORKFLOW = REPO_ROOT / ".github/workflows/k9b-cnpg-incident-lab-live.yml"
ENSURE_VENV_SCRIPT = REPO_ROOT / "scripts/ci/ensure_live_lab_venv.sh"
REQUIREMENTS_FILE = REPO_ROOT / "requirements-live-lab.txt"

LIVE_LAB_IMPORT_FILES = [
    Path("scripts/k9b_otel_demo_lab.py"),
    Path("scripts/k9b_otel_demo_lab_common.py"),
    Path("scripts/k9b_otel_demo_lab_k8s.py"),
    Path("scripts/k9b_otel_demo_lab_k8s_diagnosis.py"),
    Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_phase.py"),
    Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_runner.py"),
    Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_verify.py"),
    Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_match.py"),
    Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_contract.py"),
    Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_artifacts.py"),
    Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_render.py"),
    Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_trajectory.py"),
    Path("scripts/k9b_otel_demo_lab_k8s_verdicts.py"),
]

# Import-name -> pip package-name mismatches.
IMPORT_TO_DISTRIBUTION = {
    "yaml": "pyyaml",
}

# Repo-local top-level modules/packages used by live-lab scripts.
LOCAL_TOP_LEVEL_IMPORTS = {
    "scripts",
    "src",
    "k8s_diag_agent",
    "tests",
}

# Optional/dev-only modules that should not force live-lab workflow installs.
OPTIONAL_OR_TEST_ONLY_IMPORTS = {
    "pytest",
}


def _load_workflow(workflow_path: Path) -> dict[str, Any]:
    data = yaml.safe_load(workflow_path.read_text())
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _all_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)

    steps: list[dict[str, Any]] = []
    for job in jobs.values():
        assert isinstance(job, dict)
        job_steps = job.get("steps", [])
        assert isinstance(job_steps, list)
        steps.extend(step for step in job_steps if isinstance(step, dict))

    return steps


def _collect_dependency_surface() -> set[str]:
    """Collect all third-party packages from the complete dependency surface.

    The dependency surface includes:
    - Workflow YAML files (checking for script invocations)
    - The ensure_live_lab_venv.sh script
    - Requirements files referenced by the script

    Returns a set of normalized package names (lowercase, underscores replaced with hyphens).
    """
    packages: set[str] = set()

    # Step 1: Scan workflow files for ensure_live_lab_venv.sh invocations
    # and collect the script content for analysis
    script_texts: list[str] = []

    for workflow_path in [OTEL_WORKFLOW, CNPG_WORKFLOW]:
        if not workflow_path.exists():
            continue
        workflow = _load_workflow(workflow_path)
        for step in _all_steps(workflow):
            run_block = step.get("run", "")
            if "ensure_live_lab_venv.sh" in run_block:
                # Found invocation - collect the script text
                if ENSURE_VENV_SCRIPT.exists():
                    script_texts.append(ENSURE_VENV_SCRIPT.read_text())
                break

    # Step 2: Parse packages from script texts (pip install commands)
    for script_text in script_texts:
        for line in script_text.splitlines():
            # Look for pip install commands
            if "pip install" not in line:
                continue

            # Extract arguments after "pip install"
            _, _, args = line.partition("pip install")

            # Use shlex.split() for proper shell-like tokenization
            # This handles "-r <file>" correctly (consumes next token as argument)
            try:
                tokens = list(shlex.split(args.strip()))
            except ValueError:
                # Fall back to simple whitespace split if shlex fails
                tokens = args.strip().split()

            tokens_iter = iter(tokens)
            for token in tokens_iter:
                if token in {"-r", "--requirement"}:
                    # Consume next token as the requirements file path
                    req_path = next(tokens_iter, "")
                    req_file = REPO_ROOT / req_path
                    if req_file.exists():
                        for pkg in _parse_requirements_file(req_file):
                            packages.add(pkg)
                    continue

                if token.startswith("-r") and token != "-r":
                    # Handle "-r<file>" (no space)
                    req_file = REPO_ROOT / token[2:]
                    if req_file.exists():
                        for pkg in _parse_requirements_file(req_file):
                            packages.add(pkg)
                    continue

                if token.startswith("--requirement="):
                    # Handle "--requirement=<file>"
                    req_file = REPO_ROOT / token.split("=", 1)[1]
                    if req_file.exists():
                        for pkg in _parse_requirements_file(req_file):
                            packages.add(pkg)
                    continue

                if token.startswith("-"):
                    # Skip other options (--upgrade, -q, etc.)
                    continue

                # Normalize simple package specs:
                # "PyYAML==6.0.2" -> "pyyaml"
                # "requests>=2" -> "requests"
                name = re.split(r"[<>=!~\[]", token, maxsplit=1)[0]
                if name and not name.startswith("."):
                    packages.add(name.lower().replace("_", "-"))

    # Step 3: Also scan requirements file directly to catch any direct requirements
    if REQUIREMENTS_FILE.exists():
        for pkg in _parse_requirements_file(REQUIREMENTS_FILE):
            packages.add(pkg)

    return packages


def _parse_requirements_file(req_file: Path) -> set[str]:
    """Parse package names from a requirements file.

    Returns a set of normalized package names.
    """
    packages: set[str] = set()
    for line in req_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Parse package name (before version specifiers)
        name = re.split(r"[<>=!~\[]", line, maxsplit=1)[0]
        if name:
            packages.add(name.lower().replace("_", "-"))
    return packages


def _top_level_imports(path: Path) -> set[str]:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))

    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".", maxsplit=1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                imports.add(node.module.split(".", maxsplit=1)[0])

    return imports


def _is_stdlib(module_name: str) -> bool:
    return module_name in sys.stdlib_module_names or module_name in sys.builtin_module_names


def _is_local(module_name: str) -> bool:
    if module_name in LOCAL_TOP_LEVEL_IMPORTS:
        return True

    return (
        (REPO_ROOT / f"{module_name}.py").exists()
        or (REPO_ROOT / module_name / "__init__.py").exists()
        or (REPO_ROOT / "src" / module_name / "__init__.py").exists()
    )


def _required_distribution_for_import(module_name: str) -> str:
    return IMPORT_TO_DISTRIBUTION.get(module_name, module_name).lower().replace("_", "-")


def test_live_lab_workflow_installs_all_third_party_imports() -> None:
    """Verify live-lab workflow installs all third-party imports used by live-lab scripts.

    This test follows the redesigned dependency boundary:
    - Workflows invoke scripts/ci/ensure_live_lab_venv.sh
    - The script installs packages from requirements-live-lab.txt
    - All third-party imports in live-lab scripts must be covered by this surface
    """
    installed = _collect_dependency_surface()

    # Verify that the dependency surface is not empty (script was found and parsed)
    assert installed, (
        "live-lab dependency surface is empty - ensure_live_lab_venv.sh must be "
        "invoked from workflows and must install Python dependencies"
    )

    # Verify requests is included (key third-party dependency for live labs)
    assert "requests" in installed, (
        "live-lab dependency surface must include 'requests' package"
    )

    missing: dict[str, list[str]] = {}

    for relative_path in LIVE_LAB_IMPORT_FILES:
        path = REPO_ROOT / relative_path
        if not path.exists():
            continue

        for module_name in sorted(_top_level_imports(path)):
            if _is_stdlib(module_name):
                continue
            if _is_local(module_name):
                continue
            if module_name in OPTIONAL_OR_TEST_ONLY_IMPORTS:
                continue

            distribution = _required_distribution_for_import(module_name)
            if distribution not in installed:
                missing.setdefault(distribution, []).append(str(relative_path))

    assert not missing, (
        "live-lab workflow is missing pip-installed packages for imports: "
        + repr(missing)
    )
