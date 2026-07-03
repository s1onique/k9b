"""Regression tests for live lab workflow dependency contracts.

These tests verify that workflows:
1. Use the toolchain action for tool wiring
2. Use ensure_live_lab_venv.sh for venv preparation
3. Do not use actions/cache for .venv
4. Have the redesigned venv preparation steps
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.helpers.k9b_live_lab_toolchain_action_helpers import (
    CNPG_LIVE_LAB_WORKFLOW,
    OTEL_LIVE_LAB_WORKFLOW,
    REQUIREMENTS_LIVE_LAB,
)


class TestWorkflowRequirementsFile:
    """Test that requirements-live-lab.txt exists and is valid."""

    def test_requirements_file_exists(self) -> None:
        """requirements-live-lab.txt should exist."""
        assert REQUIREMENTS_LIVE_LAB.exists(), (
            f"requirements-live-lab.txt not found at {REQUIREMENTS_LIVE_LAB}"
        )

    def test_requirements_file_has_dependencies(self) -> None:
        """requirements-live-lab.txt should have required dependencies."""
        content = REQUIREMENTS_LIVE_LAB.read_text()

        assert "pytest" in content, (
            "requirements-live-lab.txt should include pytest"
        )
        assert "pyyaml" in content, (
            "requirements-live-lab.txt should include pyyaml"
        )
        assert "requests" in content, (
            "requirements-live-lab.txt should include requests"
        )
        assert "ijson" in content, (
            "requirements-live-lab.txt should include ijson"
        )


class TestWorkflowVenvCaching:
    """Test that workflows use deterministic local venv preparation (no remote cache)."""

    def test_otel_workflow_uses_ensure_venv_script(self) -> None:
        """OTel live lab workflow should use ensure_live_lab_venv.sh script."""
        workflow_text = OTEL_LIVE_LAB_WORKFLOW.read_text()
        assert "scripts/ci/ensure_live_lab_venv.sh" in workflow_text, (
            "OTel workflow should use scripts/ci/ensure_live_lab_venv.sh for venv preparation"
        )

    def test_otel_workflow_no_venv_cache_restore(self) -> None:
        """OTel live lab workflow should NOT use actions/cache/restore for .venv."""
        _assert_no_venv_cache_steps(OTEL_LIVE_LAB_WORKFLOW)

    def test_otel_workflow_no_venv_cache_save(self) -> None:
        """OTel live lab workflow should NOT use actions/cache/save for .venv."""
        _assert_no_venv_cache_steps(OTEL_LIVE_LAB_WORKFLOW)

    def test_otel_workflow_prepares_live_lab_python_venv(self) -> None:
        """OTel live lab workflow should use redesigned venv preparation steps.

        The live-lab Python installation was recently redesigned so dependency
        preparation is delegated through scripts/ci/ensure_live_lab_venv.sh.
        The workflow should have:
        - 'Prepare live lab Python venv' step that invokes ensure_live_lab_venv.sh
        - 'Verify live lab Python dependencies' step that proves imports are available
        """
        workflow = yaml.safe_load(OTEL_LIVE_LAB_WORKFLOW.read_text())
        jobs = workflow.get("jobs", {})
        if "live-k3s-lab" not in jobs:
            assert False, "OTel workflow should have live-k3s-lab job"

        live_job = jobs["live-k3s-lab"]
        step_names = [step.get("name", "") for step in live_job.get("steps", [])]

        # Check for redesigned venv preparation steps
        assert "Prepare live lab Python venv" in step_names, (
            "OTel workflow should have 'Prepare live lab Python venv' step"
        )
        assert "Verify live lab Python dependencies" in step_names, (
            "OTel workflow should have 'Verify live lab Python dependencies' step"
        )

        # Verify the prepare step invokes ensure_live_lab_venv.sh
        for step in live_job.get("steps", []):
            if step.get("name") == "Prepare live lab Python venv":
                run_block = step.get("run", "")
                assert "ensure_live_lab_venv.sh" in run_block, (
                    "Prepare live lab Python venv step should invoke ensure_live_lab_venv.sh"
                )
                return

        assert False, "Prepare live lab Python venv step not found"

    def test_otel_workflow_supports_prebaked_venv(self) -> None:
        """OTel live lab workflow should support pre-baked venv via env var."""
        workflow_text = OTEL_LIVE_LAB_WORKFLOW.read_text()
        assert "K9B_LIVE_LAB_PREBAKED_VENV" in workflow_text, (
            "OTel workflow should reference K9B_LIVE_LAB_PREBAKED_VENV for pre-baked venv support"
        )

    def test_cnpg_workflow_uses_ensure_venv_script(self) -> None:
        """CNPG live lab workflow should use ensure_live_lab_venv.sh script."""
        workflow_text = CNPG_LIVE_LAB_WORKFLOW.read_text()
        assert "scripts/ci/ensure_live_lab_venv.sh" in workflow_text, (
            "CNPG workflow should use scripts/ci/ensure_live_lab_venv.sh for venv preparation"
        )

    def test_cnpg_workflow_no_venv_cache_restore(self) -> None:
        """CNPG live lab workflow should NOT use actions/cache/restore for .venv."""
        _assert_no_venv_cache_steps(CNPG_LIVE_LAB_WORKFLOW)

    def test_cnpg_workflow_no_venv_cache_save(self) -> None:
        """CNPG live lab workflow should NOT use actions/cache/save for .venv."""
        _assert_no_venv_cache_steps(CNPG_LIVE_LAB_WORKFLOW)


def _assert_no_venv_cache_steps(workflow_path: Path) -> None:
    """Assert workflow does not use actions/cache for .venv directory."""
    workflow = yaml.safe_load(workflow_path.read_text())

    for job_name, job in workflow.get("jobs", {}).items():
        for step in job.get("steps", []):
            uses = step.get("uses", "")
            with_block = step.get("with", {})
            path = str(with_block.get("path", ""))

            assert not (
                uses.startswith("actions/cache/restore")
                and path == ".venv"
            ), f"{workflow_path}: job {job_name} restores .venv via actions/cache"

            assert not (
                uses.startswith("actions/cache/save")
                and path == ".venv"
            ), f"{workflow_path}: job {job_name} saves .venv via actions/cache"


class TestWorkflowToolchainActionUsage:
    """Test that workflows use the updated toolchain action."""

    def test_otel_workflow_uses_toolchain_action(self) -> None:
        """OTel live lab workflow should use the toolchain action."""
        workflow = yaml.safe_load(OTEL_LIVE_LAB_WORKFLOW.read_text())

        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if "k9b-live-lab-toolchain" in uses:
                    return

        assert False, "OTel workflow should use k9b-live-lab-toolchain action"

    def test_cnpg_workflow_uses_toolchain_action(self) -> None:
        """CNPG incident lab live workflow should use the toolchain action."""
        workflow = yaml.safe_load(CNPG_LIVE_LAB_WORKFLOW.read_text())

        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if "k9b-live-lab-toolchain" in uses:
                    return

        assert False, "CNPG workflow should use k9b-live-lab-toolchain action"

    def test_workflows_no_longer_use_setup_actions(self) -> None:
        """Live lab workflows should NOT use setup actions directly in toolchain section."""
        for workflow_path in [OTEL_LIVE_LAB_WORKFLOW, CNPG_LIVE_LAB_WORKFLOW]:
            workflow = yaml.safe_load(workflow_path.read_text())

            # Track if we are in the sanitize section (last section of workflow)
            # Sanitize section needs setup-python for artifact processing
            jobs = workflow.get("jobs", {})
            sanitize_section_started = False

            for job_name, job in jobs.items():
                steps = job.get("steps", [])
                for step in steps:
                    uses = step.get("uses", "")
                    step_name = step.get("name", "")

                    # Skip the toolchain action itself
                    if "k9b-live-lab-toolchain" in uses:
                        continue

                    # Detect sanitize section (steps with "sanitize" in name)
                    if "sanitize" in step_name.lower():
                        sanitize_section_started = True

                    # Allow setup-python in sanitize section (needs fresh Python env)
                    if "actions/setup-python" in uses and sanitize_section_started:
                        continue

                    # Check for setup actions in toolchain/setup section
                    if "actions/setup-python" in uses:
                        assert False, (
                            f"{workflow_path.name} should NOT use actions/setup-python "
                            "(use toolchain action instead, except for sanitize section)"
                        )
                    if "azure/setup-kubectl" in uses:
                        assert False, (
                            f"{workflow_path.name} should NOT use azure/setup-kubectl "
                            "(use toolchain action instead)"
                        )
                    if "azure/setup-helm" in uses:
                        assert False, (
                            f"{workflow_path.name} should NOT use azure/setup-helm "
                            "(use toolchain action instead)"
                        )
