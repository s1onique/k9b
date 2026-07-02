"""Regression tests for k9b-live-lab-toolchain action Python tool-cache wiring.

These tests verify that the action:
1. Prints tool-cache diagnostics
2. Wires Python, kubectl, and Helm from local runner tool cache
3. Validates the toolchain after wiring
4. Exports outputs for workflow consumption
5. Does not change lab semantics (venv creation, pip install still happen in workflow)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Path to the toolchain action file
TOOLCHAIN_ACTION_FILE = Path(__file__).parent.parent / ".github/actions/k9b-live-lab-toolchain/action.yml"

# Path to the OTel live lab workflow
OTEL_LIVE_LAB_WORKFLOW = Path(__file__).parent.parent / ".github/workflows/k9b-otel-demo-live-lab.yml"

# Path to the CNPG incident lab live workflow
CNPG_LIVE_LAB_WORKFLOW = Path(__file__).parent.parent / ".github/workflows/k9b-cnpg-incident-lab-live.yml"

# Path to the requirements file
REQUIREMENTS_LIVE_LAB = Path(__file__).parent.parent / "requirements-live-lab.txt"


def _load_action_yaml(path: Path) -> dict[str, Any]:
    """Load YAML from action file."""
    return yaml.safe_load(path.read_text())  # type: ignore[no-any-return]


def _get_step_ids(action: dict) -> list[str]:
    """Extract step IDs from action steps."""
    return [
        step.get("id", "")
        for step in action.get("runs", {}).get("steps", [])
        if step.get("id")
    ]


def _get_step_by_id(action: dict[str, Any], step_id: str) -> dict[str, Any] | None:
    """Get step by its id."""
    for step in action.get("runs", {}).get("steps", []):
        if step.get("id") == step_id:
            return step  # type: ignore[no-any-return]
    return None


def _get_step_names(action: dict) -> list[str]:
    """Extract step names from action steps."""
    return [
        step.get("name", "")
        for step in action.get("runs", {}).get("steps", [])
    ]


class TestToolchainActionFileExists:
    """Test that the action file exists and is valid YAML."""

    def test_action_file_exists(self) -> None:
        """The toolchain action file should exist."""
        assert TOOLCHAIN_ACTION_FILE.exists(), (
            f"Toolchain action file not found at {TOOLCHAIN_ACTION_FILE}"
        )

    def test_action_yaml_valid(self) -> None:
        """The toolchain action should be valid YAML."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        assert action is not None, "Action YAML should not be None"
        assert "runs" in action, "Action should have 'runs' key"
        assert "steps" in action["runs"], "Action should have 'steps' key"


class TestToolchainActionToolCacheDiagnostics:
    """Test that the action prints tool-cache diagnostics."""

    def test_diagnostics_step_prints_tool_cache_paths(self) -> None:
        """Action should have a step that prints tool-cache path diagnostics."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_names = _get_step_names(action)

        # Should have a diagnostics step
        diagnostics_steps = [
            name for name in step_names
            if "diagnostics" in name.lower() or "tool cache" in name.lower()
        ]
        assert len(diagnostics_steps) > 0, (
            "Should have a tool-cache diagnostics step"
        )

        # Find the diagnostics step
        for step in action.get("runs", {}).get("steps", []):
            step_name = step.get("name", "")
            if "diagnostics" in step_name.lower() or ("tool cache" in step_name.lower() and "show" in step_name.lower()):
                run_text = step.get("run", "")
                assert "RUNNER_TOOL_CACHE" in run_text, (
                    "Diagnostics should print RUNNER_TOOL_CACHE"
                )
                assert "runner.tool_cache" in run_text, (
                    "Diagnostics should print runner.tool_cache"
                )
                assert "AGENT_TOOLSDIRECTORY" in run_text, (
                    "Diagnostics should print AGENT_TOOLSDIRECTORY"
                )
                return

        assert False, "No diagnostics step found with expected env vars"

    def test_diagnostics_step_lists_tool_cache_contents(self) -> None:
        """Diagnostics step should list contents of tool cache."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)

        for step in action.get("runs", {}).get("steps", []):
            step_name = step.get("name", "")
            if "diagnostics" in step_name.lower():
                run_text = step.get("run", "")
                # Should list directory contents
                assert "ls" in run_text or "find" in run_text, (
                    "Diagnostics should list tool cache contents"
                )
                return


class TestToolchainActionWireTools:
    """Test that the action wires tools from local runner tool cache."""

    def test_has_wire_tools_step(self) -> None:
        """Action should have a wire-tools step."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_ids = _get_step_ids(action)

        wire_steps = [sid for sid in step_ids if "wire" in sid.lower()]
        assert len(wire_steps) > 0, (
            f"Should have wire-tools step, found ids: {step_ids}"
        )

    def test_wire_tools_step_has_correct_id(self) -> None:
        """Wire tools step should have id 'wire-tools'."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_ids = _get_step_ids(action)

        assert "wire-tools" in step_ids, (
            f"Should have id 'wire-tools', found ids: {step_ids}"
        )

    def test_wire_tools_wires_python(self) -> None:
        """Wire tools should look for Python in tool cache."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")
        assert "Python" in run_text or "python" in run_text, (
            "Wire tools should look for Python"
        )
        assert "3.13" in run_text, (
            "Wire tools should look for Python 3.13"
        )

    def test_wire_tools_wires_helm(self) -> None:
        """Wire tools should look for Helm in tool cache."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")
        assert "helm" in run_text.lower(), (
            "Wire tools should look for Helm"
        )

    def test_wire_tools_wires_kubectl(self) -> None:
        """Wire tools should look for kubectl in tool cache."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")
        assert "kubectl" in run_text.lower(), (
            "Wire tools should look for kubectl"
        )

    def test_wire_tools_sets_github_path(self) -> None:
        """Wire tools should append bin directories to GITHUB_PATH."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")
        assert "GITHUB_PATH" in run_text, (
            "Wire tools should append to GITHUB_PATH"
        )


class TestToolchainActionNoSetupActions:
    """Test that the action does NOT use setup actions (direct wiring)."""

    def test_no_setup_python_action(self) -> None:
        """Action should NOT use actions/setup-python (uses direct wiring instead)."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_uses = [
            step.get("uses", "")
            for step in action.get("runs", {}).get("steps", [])
        ]

        setup_python_steps = [u for u in step_uses if "actions/setup-python" in u]
        assert len(setup_python_steps) == 0, (
            "Action should NOT use actions/setup-python (uses direct wiring instead)"
        )

    def test_no_setup_kubectl_action(self) -> None:
        """Action should NOT use azure/setup-kubectl (uses direct wiring instead)."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_uses = [
            step.get("uses", "")
            for step in action.get("runs", {}).get("steps", [])
        ]

        setup_kubectl_steps = [u for u in step_uses if "setup-kubectl" in u]
        assert len(setup_kubectl_steps) == 0, (
            "Action should NOT use azure/setup-kubectl (uses direct wiring instead)"
        )

    def test_no_setup_helm_action(self) -> None:
        """Action should NOT use azure/setup-helm (uses direct wiring instead)."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_uses = [
            step.get("uses", "")
            for step in action.get("runs", {}).get("steps", [])
        ]

        setup_helm_steps = [u for u in step_uses if "setup-helm" in u]
        assert len(setup_helm_steps) == 0, (
            "Action should NOT use azure/setup-helm (uses direct wiring instead)"
        )


class TestToolchainActionOutputs:
    """Test that the action exports useful outputs."""

    def test_action_has_outputs(self) -> None:
        """Action should define outputs."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        outputs = action.get("outputs", {})

        assert len(outputs) > 0, (
            "Action should define outputs"
        )

    def test_action_outputs_python_location(self) -> None:
        """Action should export python-location output."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        outputs = action.get("outputs", {})

        assert "python-location" in outputs, (
            "Action should export python-location output"
        )

    def test_action_outputs_helm_location(self) -> None:
        """Action should export helm-location output."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        outputs = action.get("outputs", {})

        assert "helm-location" in outputs, (
            "Action should export helm-location output"
        )

    def test_action_outputs_kubectl_location(self) -> None:
        """Action should export kubectl-location output."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        outputs = action.get("outputs", {})

        assert "kubectl-location" in outputs, (
            "Action should export kubectl-location output"
        )


class TestToolchainActionValidation:
    """Test that the action validates the toolchain."""

    def test_has_validate_step(self) -> None:
        """Action should have a validation step."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_names = _get_step_names(action)

        validate_steps = [
            name for name in step_names
            if "validate" in name.lower() or "validation" in name.lower()
        ]
        assert len(validate_steps) > 0, (
            f"Should have a validation step, found step names: {step_names}"
        )

    def test_validate_step_checks_python(self) -> None:
        """Validation step should check Python."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)

        for step in action.get("runs", {}).get("steps", []):
            step_name = step.get("name", "")
            if "validate" in step_name.lower():
                run_text = step.get("run", "")
                assert "python" in run_text.lower(), (
                    "Validation step should check Python"
                )
                assert "version" in run_text, (
                    "Validation step should check Python version"
                )
                return

    def test_validate_step_checks_helm(self) -> None:
        """Validation step should check Helm."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)

        for step in action.get("runs", {}).get("steps", []):
            step_name = step.get("name", "")
            if "validate" in step_name.lower():
                run_text = step.get("run", "")
                assert "helm" in run_text.lower(), (
                    "Validation step should check Helm"
                )
                return

    def test_validate_step_checks_kubectl(self) -> None:
        """Validation step should check kubectl."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)

        for step in action.get("runs", {}).get("steps", []):
            step_name = step.get("name", "")
            if "validate" in step_name.lower():
                run_text = step.get("run", "")
                assert "kubectl" in run_text.lower(), (
                    "Validation step should check kubectl"
                )
                return


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
    """Test that workflows use .venv caching."""

    def test_otel_workflow_uses_venv_cache(self) -> None:
        """OTel live lab workflow should use .venv caching."""
        workflow = yaml.safe_load(OTEL_LIVE_LAB_WORKFLOW.read_text())

        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if "cache/restore" in uses:
                    path = step.get("with", {}).get("path", "")
                    if ".venv" in path:
                        return

        assert False, "OTel workflow should use actions/cache/restore for .venv"

    def test_otel_workflow_has_venv_validation(self) -> None:
        """OTel live lab workflow should validate cached .venv."""
        workflow = yaml.safe_load(OTEL_LIVE_LAB_WORKFLOW.read_text())

        # Check the live-k3s-lab job specifically (where venv validation happens)
        jobs = workflow.get("jobs", {})
        if "live-k3s-lab" not in jobs:
            assert False, "OTel workflow should have live-k3s-lab job"

        live_job = jobs["live-k3s-lab"]
        run_text = " ".join(
            step.get("run", "")
            for step in live_job.get("steps", [])
            if step.get("run")
        )

        # Should have validation step with importlib check
        assert "validate" in run_text.lower() or "importlib" in run_text, (
            "OTel workflow should validate cached .venv with importlib check"
        )

    def test_otel_workflow_supports_prebaked_venv(self) -> None:
        """OTel live lab workflow should support pre-baked venv via env var."""
        # Check raw workflow file for prebaked venv documentation (comment or env)
        workflow_text = OTEL_LIVE_LAB_WORKFLOW.read_text()
        assert "PREBAKED" in workflow_text or "prebaked" in workflow_text.lower(), (
            "OTel workflow should document pre-baked venv support in env section"
        )


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

            # Track if we're in the sanitize section (last section of workflow)
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


class TestToolchainActionInputs:
    """Test that the action accepts expected inputs."""

    def test_action_has_inputs(self) -> None:
        """Action should define inputs."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        inputs = action.get("inputs", {})

        assert len(inputs) > 0, (
            "Action should define inputs"
        )

    def test_action_accepts_python_version(self) -> None:
        """Action should accept python-version input."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        inputs = action.get("inputs", {})

        assert "python-version" in inputs, (
            "Action should accept python-version input"
        )

    def test_action_accepts_kubectl_version(self) -> None:
        """Action should accept kubectl-version input."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        inputs = action.get("inputs", {})

        assert "kubectl-version" in inputs, (
            "Action should accept kubectl-version input"
        )

    def test_action_accepts_helm_version(self) -> None:
        """Action should accept helm-version input."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        inputs = action.get("inputs", {})

        assert "helm-version" in inputs, (
            "Action should accept helm-version input"
        )
