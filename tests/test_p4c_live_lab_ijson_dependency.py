"""Regression tests for P4c live lab ijson dependency.

These tests ensure the P4c diagnosis verifier does not have hidden
dependencies on the `ijson` package that would cause ImportError
in live-lab environments where `ijson` is not installed.

Related issue: OTel live lab P4c failure due to "No module named 'ijson'"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml


def test_p4c_verifier_does_not_import_ijson() -> None:
    """Ensure P4c diagnosis verifier does not import ijson directly.

    The P4c verifier path should use standard library json or a compatible
    library that is guaranteed to be available. This test prevents regression
    of hidden ijson dependencies that would cause ImportError in live-lab
    runner environments.
    """
    # List of files in the P4c diagnosis verifier path
    p4c_files = [
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

    repo_root = Path(__file__).parent.parent

    for filepath in p4c_files:
        full_path = repo_root / filepath
        if not full_path.exists():
            # Skip non-existent files (may be optional modules)
            continue

        source = full_path.read_text()
        assert "import ijson" not in source, (
            f"{filepath} should not import 'ijson' - "
            "use json from stdlib instead"
        )
        assert "from ijson" not in source, (
            f"{filepath} should not import from 'ijson' - "
            "use json from stdlib instead"
        )


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github/workflows/k9b-otel-demo-live-lab.yml"


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


def test_live_lab_workflow_installs_ijson() -> None:
    """Ensure live lab workflow installs ijson package.

    The live-lab runner installs a minimal set of Python packages.
    This test verifies that `ijson` is explicitly listed in the
    "Install Python dependencies" step's run block.

    P4c diagnosis imports ijson, so the live-lab workflow must install ijson
    to avoid ImportError during the diagnosis phase.
    """
    workflow = _load_workflow()

    install_steps = [
        step
        for step in _all_steps(workflow)
        if step.get("name") == "Install Python dependencies"
    ]

    assert install_steps, "live-lab workflow must have an Install Python dependencies step"

    run_blocks = [
        step.get("run", "")
        for step in install_steps
        if isinstance(step.get("run"), str)
    ]

    assert any("pip install" in run and "ijson" in run for run in run_blocks), (
        "P4c diagnosis imports ijson, so the live-lab workflow must install ijson"
    )
