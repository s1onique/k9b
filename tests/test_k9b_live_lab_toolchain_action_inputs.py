"""Regression tests for k9b-live-lab-toolchain action inputs.

These tests verify that the action:
1. Accepts python-version, kubectl-version, helm-version inputs
2. Accepts allow-tool-download input for offline/hermetic mode
3. Has pinned kubectl-version default (not 'latest')

See: .github/actions/k9b-live-lab-toolchain/action.yml
"""

from __future__ import annotations

from tests.helpers.k9b_live_lab_toolchain_action_helpers import (
    TOOLCHAIN_ACTION_FILE,
    _load_action_yaml,
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

    def test_action_accepts_allow_tool_download(self) -> None:
        """Action should accept allow-tool-download input."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        inputs = action.get("inputs", {})

        assert "allow-tool-download" in inputs, (
            "Action should accept allow-tool-download input"
        )

    def test_allow_tool_download_default_is_false(self) -> None:
        """allow-tool-download should default to false for hermetic mode."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        inputs = action.get("inputs", {})

        assert inputs.get("allow-tool-download", {}).get("default") == "false", (
            "allow-tool-download should default to 'false' for hermetic/offline mode"
        )

    def test_kubectl_version_default_is_pinned(self) -> None:
        """kubectl-version should default to a pinned version, not 'latest'."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        inputs = action.get("inputs", {})

        default = inputs.get("kubectl-version", {}).get("default", "latest")
        assert default != "latest", (
            f"kubectl-version should not default to 'latest' (got '{default}'). "
            "Use a pinned version like 'v1.31.0' for reproducible builds."
        )
