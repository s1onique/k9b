"""Regression tests for live-lab Python dependency coverage.

The live OTel lab workflow installs a deliberately small Python environment.
These tests ensure Python modules imported by the live-lab/P4c path are either
stdlib/local modules or explicitly installed by the live-lab workflow.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github/workflows/k9b-otel-demo-live-lab.yml"

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


def _load_workflow() -> dict[str, Any]:
    data = yaml.safe_load(WORKFLOW.read_text())
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


def _live_lab_pip_install_run_blocks() -> list[str]:
    workflow = _load_workflow()
    return [
        step.get("run", "")
        for step in _all_steps(workflow)
        if step.get("name") == "Install Python dependencies"
        and isinstance(step.get("run"), str)
    ]


def _workflow_installed_packages() -> set[str]:
    packages: set[str] = set()

    for run in _live_lab_pip_install_run_blocks():
        # Normalize shell line continuations before processing.
        normalized = run.replace("\\\n", " ")
        for line in normalized.splitlines():
            if "pip install" not in line:
                continue

            _, _, args = line.partition("pip install")

            for token in re.split(r"\s+", args.strip()):
                if not token or token.startswith("-"):
                    continue
                if token in {"--upgrade", "install"}:
                    continue

                # Normalize simple package specs:
                # "PyYAML==6.0.2" -> "pyyaml"
                # "requests>=2" -> "requests"
                name = re.split(r"[<>=!~\[]", token, maxsplit=1)[0]
                if name and not name.startswith("."):
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
    installed = _workflow_installed_packages()
    assert installed, "live-lab workflow must install Python dependencies explicitly"

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
