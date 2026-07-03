"""Regression tests for k9b-live-lab-toolchain action Python tool-cache wiring.

These tests verify that the action:
1. Prints tool-cache diagnostics
2. Wires Python, kubectl, and Helm from local runner tool cache
3. Validates the toolchain after wiring
4. Exports outputs for workflow consumption
5. Does not change lab semantics (venv creation, pip install still happen in workflow)
"""

from __future__ import annotations

from tests.helpers.k9b_live_lab_toolchain_action_helpers import (
    TOOLCHAIN_ACTION_FILE,
    _get_step_by_id,
    _get_step_ids,
    _get_step_names,
    _load_action_yaml,
)


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
