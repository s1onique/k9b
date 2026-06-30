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

    The live-lab runner installs a minimal set of Python packages.
    This test verifies that `requests` is explicitly listed in the
    "Install Python dependencies" step's run block.
    """
    import yaml

    workflow_path = Path(__file__).parent.parent / ".github/workflows/k9b-otel-demo-live-lab.yml"
    workflow = yaml.safe_load(workflow_path.read_text())

    # Find the "Install Python dependencies" step
    install_step = None
    for job_name, job in workflow.get("jobs", {}).items():
        for step in job.get("steps", []):
            if step.get("name") == "Install Python dependencies":
                install_step = step
                break
        if install_step:
            break

    assert install_step is not None, (
        "Workflow should have 'Install Python dependencies' step"
    )

    run_block = install_step.get("run", "")
    assert "pip install" in run_block, (
        "Install step should contain 'pip install' command"
    )
    assert "requests" in run_block, (
        "Install step should install 'requests' package"
    )
