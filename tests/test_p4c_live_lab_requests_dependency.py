"""Regression tests for P4c live lab requests dependency.

These tests ensure the P4c diagnosis verifier does not have hidden
dependencies on the `requests` package that would cause ImportError
in live-lab environments where `requests` is not installed.

Related issue: OTel live lab P4c failure due to "No module named 'requests'"
"""

from __future__ import annotations

from pathlib import Path


def test_p4c_verifier_does_not_import_requests() -> None:
    """Ensure P4c diagnosis verifier has no hidden requests dependency.

    This test prevents regression of the live-lab P4c failure where
    the diagnosis loop triggered an ImportError: "No module named 'requests'".

    The P4c verifier path should not depend on the `requests` package,
    which may not be installed in live-lab runner environments.
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
        assert "import requests" not in source, (
            f"{filepath} should not import 'requests' - "
            "use urllib.request from stdlib instead"
        )
        assert "from requests" not in source, (
            f"{filepath} should not import from 'requests' - "
            "use urllib.request from stdlib instead"
        )


def test_live_lab_workflow_installs_requests() -> None:
    """Ensure live lab workflow installs requests package.

    The live-lab Python installation was recently redesigned so dependency
    preparation is delegated through scripts/ci/ensure_live_lab_venv.sh.
    This test verifies that `requests` is installed via the venv script path.

    The venv script reads requirements from requirements-live-lab.txt which
    contains the `requests` package.
    """
    import yaml

    workflow_path = Path(__file__).parent.parent / ".github/workflows/k9b-otel-demo-live-lab.yml"
    workflow = yaml.safe_load(workflow_path.read_text())

    # Find the "Prepare live lab Python venv" step that invokes the venv script
    venv_prepare_step = None
    for job_name, job in workflow.get("jobs", {}).items():
        for step in job.get("steps", []):
            if step.get("name") == "Prepare live lab Python venv":
                venv_prepare_step = step
                break
        if venv_prepare_step:
            break

    assert venv_prepare_step is not None, (
        "Workflow should have 'Prepare live lab Python venv' step"
    )

    run_block = venv_prepare_step.get("run", "")
    assert "ensure_live_lab_venv.sh" in run_block, (
        "Prepare live lab Python venv step should invoke ensure_live_lab_venv.sh"
    )

    # Verify requirements-live-lab.txt contains requests
    requirements_path = Path(__file__).parent.parent / "requirements-live-lab.txt"
    requirements_content = requirements_path.read_text()
    assert "requests" in requirements_content, (
        "requirements-live-lab.txt should include 'requests' package"
    )
