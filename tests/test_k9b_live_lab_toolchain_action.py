"""Regression tests for k9b-live-lab-toolchain action Python tool-cache behavior.

These tests verify that the action:
1. Prints tool-cache diagnostics
2. Checks for local Python 3.13 tool cache before remote restore
3. Makes remote restore conditional on local cache miss
4. Still sets up Python 3.13
5. Does not change OTel live-lab workflow semantics
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Path to the toolchain action file
TOOLCHAIN_ACTION_FILE = Path(__file__).parent.parent / ".github/actions/k9b-live-lab-toolchain/action.yml"

# Path to the OTel live lab workflow
OTEL_LIVE_LAB_WORKFLOW = Path(__file__).parent.parent / ".github/workflows/k9b-otel-demo-live-lab.yml"


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


class TestToolchainActionToolCacheDiagnostics:
    """Test that the action prints tool-cache diagnostics."""

    def test_action_file_exists(self) -> None:
        """The toolchain action file should exist."""
        assert TOOLCHAIN_ACTION_FILE.exists(), (
            f"Toolchain action file not found at {TOOLCHAIN_ACTION_FILE}"
        )

    def test_diagnostics_step_prints_tool_cache_paths(self) -> None:
        """Action should have a step that prints tool-cache path diagnostics."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_names = _get_step_names(action)

        # Should have a diagnostics step
        diagnostics_steps = [name for name in step_names if "diagnostics" in name.lower() or "tool cache" in name.lower()]
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
            if "diagnostics" in step_name.lower() or ("tool cache" in step_name.lower() and "show" in step_name.lower()):
                run_text = step.get("run", "")
                # Should list directory contents
                assert "ls" in run_text or "find" in run_text, (
                    "Diagnostics should list tool cache contents"
                )
                return


class TestToolchainActionLocalCacheHitCheck:
    """Test that the action checks for local Python tool cache."""

    def test_has_local_cache_hit_check_step(self) -> None:
        """Action should have a step to check local Python tool cache."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_ids = _get_step_ids(action)

        # Should have a local cache hit check step
        local_cache_steps = [sid for sid in step_ids if "local" in sid.lower() and "cache" in sid.lower()]
        assert len(local_cache_steps) > 0, (
            f"Should have local cache hit check step, found ids: {step_ids}"
        )

    def test_local_cache_hit_step_has_correct_id(self) -> None:
        """Local cache hit check step should have id 'local-python-tool-cache'."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_ids = _get_step_ids(action)

        assert "local-python-tool-cache" in step_ids, (
            f"Should have id 'local-python-tool-cache', found ids: {step_ids}"
        )

    def test_local_cache_hit_check_uses_github_output(self) -> None:
        """Local cache hit check should set outputs via GITHUB_OUTPUT."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "local-python-tool-cache")

        assert step is not None, "local-python-tool-cache step not found"
        assert "GITHUB_OUTPUT" in step.get("run", ""), (
            "Local cache hit check should write to GITHUB_OUTPUT"
        )

    def test_local_cache_hit_check_sets_hit_output(self) -> None:
        """Local cache hit check should set 'hit' output."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "local-python-tool-cache")

        assert step is not None, "local-python-tool-cache step not found"
        run_text = step.get("run", "")
        assert "hit=" in run_text, (
            "Local cache hit check should set 'hit' output"
        )

    def test_local_cache_hit_check_looks_for_python_313(self) -> None:
        """Local cache hit check should look for Python 3.13."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "local-python-tool-cache")

        assert step is not None, "local-python-tool-cache step not found"
        run_text = step.get("run", "")
        assert "3.13" in run_text, (
            "Local cache hit check should look for Python 3.13"
        )


class TestToolchainActionRemoteRestoreConditional:
    """Test that remote restore is conditional on local cache miss."""

    def test_remote_restore_step_exists(self) -> None:
        """Action should still have a remote Python tool cache restore step."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_uses = [
            step.get("uses", "")
            for step in action.get("runs", {}).get("steps", [])
        ]

        restore_steps = [u for u in step_uses if "actions/cache/restore" in u]
        assert len(restore_steps) > 0, (
            "Should have actions/cache/restore step"
        )

    def test_remote_restore_is_conditional_on_local_miss(self) -> None:
        """Remote restore should only run when local cache misses."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)

        for step in action.get("runs", {}).get("steps", []):
            if "actions/cache/restore" in step.get("uses", ""):
                step_if = step.get("if", "")
                assert "local-python-tool-cache" in step_if, (
                    f"Remote restore should be conditional on local-python-tool-cache, "
                    f"found if: {step_if}"
                )
                assert "hit" in step_if, (
                    f"Remote restore should check 'hit' output, found if: {step_if}"
                )
                return

        assert False, "No actions/cache/restore step found"

    def test_remote_save_is_conditional(self) -> None:
        """Remote save should be conditional on local cache miss and no remote hit."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)

        for step in action.get("runs", {}).get("steps", []):
            if "actions/cache/save" in step.get("uses", ""):
                step_if = step.get("if", "")
                assert "local-python-tool-cache" in step_if, (
                    f"Remote save should be conditional on local-python-tool-cache, "
                    f"found if: {step_if}"
                )
                return

        # Save step is optional, so this is a soft check
        # assert False, "No actions/cache/save step found"


class TestToolchainActionSetupPython:
    """Test that Python setup still works correctly."""

    def test_has_setup_python_step(self) -> None:
        """Action should have actions/setup-python step."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step_uses = [
            step.get("uses", "")
            for step in action.get("runs", {}).get("steps", [])
        ]

        setup_python_steps = [u for u in step_uses if "actions/setup-python" in u]
        assert len(setup_python_steps) > 0, (
            "Should have actions/setup-python step"
        )

    def test_setup_python_uses_python_313(self) -> None:
        """Setup Python should use Python 3.13."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)

        for step in action.get("runs", {}).get("steps", []):
            if "actions/setup-python" in step.get("uses", ""):
                with_block = step.get("with", {})
                python_version = with_block.get("python-version", "")
                # Action accepts python-version via inputs and passes it through
                assert python_version == "${{ inputs.python-version }}", (
                    f"Setup Python should use inputs.python-version, found: {python_version}"
                )
                return

        assert False, "No actions/setup-python step found"


class TestToolchainActionWorkflowSemantics:
    """Test that OTel live-lab workflow semantics are unchanged."""

    def test_workflow_uses_toolchain_action(self) -> None:
        """OTel live lab workflow should use the toolchain action."""
        assert OTEL_LIVE_LAB_WORKFLOW.exists(), (
            f"OTel live lab workflow not found at {OTEL_LIVE_LAB_WORKFLOW}"
        )

        workflow = yaml.safe_load(OTEL_LIVE_LAB_WORKFLOW.read_text())

        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if "k9b-live-lab-toolchain" in uses:
                    return

        assert False, "Workflow should use k9b-live-lab-toolchain action"

    def test_workflow_passes_python_313_to_toolchain(self) -> None:
        """OTel live lab workflow should pass Python 3.13 to toolchain action."""
        workflow = yaml.safe_load(OTEL_LIVE_LAB_WORKFLOW.read_text())

        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if "k9b-live-lab-toolchain" in uses:
                    with_block = step.get("with", {})
                    python_version = with_block.get("python-version", "")
                    # Workflow uses env.PYTHON_VERSION which resolves to '3.13' (defined in workflow env)
                    assert python_version == "${{ env.PYTHON_VERSION }}", (
                        f"Workflow should pass python-version via env.PYTHON_VERSION to toolchain action, "
                        f"found: {python_version}"
                    )
                    return

        assert False, "Workflow should use k9b-live-lab-toolchain action"

    def test_workflow_defines_python_313_env(self) -> None:
        """Workflow should define PYTHON_VERSION env as '3.13'."""
        workflow = yaml.safe_load(OTEL_LIVE_LAB_WORKFLOW.read_text())
        env = workflow.get("env", {})
        python_version = env.get("PYTHON_VERSION", "")
        assert python_version == "3.13", (
            f"Workflow env should define PYTHON_VERSION: '3.13', found: {python_version}"
        )

    def test_workflow_still_creates_venv(self) -> None:
        """Workflow should still create virtual environment after toolchain setup."""
        workflow = yaml.safe_load(OTEL_LIVE_LAB_WORKFLOW.read_text())

        for job in workflow.get("jobs", {}).values():
            run_text = " ".join(
                step.get("run", "")
                for step in job.get("steps", [])
                if step.get("run")
            )

            if "k9b-live-lab-toolchain" in " ".join(
                step.get("uses", "")
                for step in job.get("steps", [])
            ):
                # After toolchain action, should create venv
                assert "python -m venv" in run_text, (
                    "Workflow should create virtual environment"
                )
                return

    def test_workflow_still_installs_pip_dependencies(self) -> None:
        """Workflow should still install pip dependencies."""
        workflow = yaml.safe_load(OTEL_LIVE_LAB_WORKFLOW.read_text())

        for job in workflow.get("jobs", {}).values():
            run_text = " ".join(
                step.get("run", "")
                for step in job.get("steps", [])
                if step.get("run")
            )

            if "k9b-live-lab-toolchain" in " ".join(
                step.get("uses", "")
                for step in job.get("steps", [])
            ):
                # After toolchain action, should install pip
                assert "pip install" in run_text or "pip" in run_text, (
                    "Workflow should install pip dependencies"
                )
                return


class TestToolchainActionStepOrder:
    """Test that steps are in the correct order."""

    def test_diagnostics_before_local_cache_check(self) -> None:
        """Tool cache diagnostics should come before local cache hit check."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        steps = action.get("runs", {}).get("steps", [])

        diagnostics_idx = None
        local_cache_idx = None

        for i, step in enumerate(steps):
            step_name = step.get("name", "")
            if "diagnostics" in step_name.lower():
                diagnostics_idx = i
            if step.get("id") == "local-python-tool-cache":
                local_cache_idx = i

        assert diagnostics_idx is not None, "No diagnostics step found"
        assert local_cache_idx is not None, "No local-python-tool-cache step found"
        assert diagnostics_idx < local_cache_idx, (
            f"Diagnostics ({diagnostics_idx}) should come before "
            f"local cache check ({local_cache_idx})"
        )

    def test_local_cache_check_before_remote_restore(self) -> None:
        """Local cache hit check should come before remote restore."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        steps = action.get("runs", {}).get("steps", [])

        local_cache_idx = None
        restore_idx = None

        for i, step in enumerate(steps):
            if step.get("id") == "local-python-tool-cache":
                local_cache_idx = i
            if "actions/cache/restore" in step.get("uses", ""):
                restore_idx = i

        assert local_cache_idx is not None, "No local-python-tool-cache step found"
        assert restore_idx is not None, "No restore step found"
        assert local_cache_idx < restore_idx, (
            f"Local cache check ({local_cache_idx}) should come before "
            f"remote restore ({restore_idx})"
        )

    def test_remote_restore_before_setup_python(self) -> None:
        """Remote restore (if it runs) should come before setup-python."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        steps = action.get("runs", {}).get("steps", [])

        restore_idx = None
        setup_python_idx = None

        for i, step in enumerate(steps):
            if "actions/cache/restore" in step.get("uses", ""):
                restore_idx = i
            if "actions/setup-python" in step.get("uses", ""):
                setup_python_idx = i

        assert setup_python_idx is not None, "No setup-python step found"
        # Restore is optional (conditional), so this is about ordering when it does run
        if restore_idx is not None:
            assert restore_idx < setup_python_idx, (
                f"Remote restore ({restore_idx}) should come before "
                f"setup-python ({setup_python_idx})"
            )
