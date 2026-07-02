"""Regression tests for k9b-live-lab-toolchain action Helm tool-cache wiring.

These tests verify Helm-specific tool-cache wiring behavior:
1. x64 path ordering (azure/setup-helm / Actions tool-cache style layout)
2. Legacy path fallback for older runner caches

See: .github/actions/k9b-live-lab-toolchain/action.yml
"""

from __future__ import annotations

from tests.helpers.k9b_live_lab_toolchain_action_helpers import (
    TOOLCHAIN_ACTION_FILE,
    _get_step_by_id,
    _load_action_yaml,
)


class TestHelmX64PathOrdering:
    """Test that Helm resolver checks x64 paths before legacy paths.

    Regression test: azure/setup-helm / Actions tool-cache style layout
    includes x64 architecture segment (e.g., helm/3.14.0/x64/linux-amd64/helm).
    The resolver must check x64 paths first to avoid false negatives on runners
    that cache Helm with the x64 segment.
    """

    def test_wire_tools_checks_x64_helm_paths_first(self) -> None:
        """Wire tools should check x64 paths before legacy paths for Helm."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # Find positions of x64 and legacy helm path patterns
        x64_pattern = "/helm/3.14.0/x64/linux-amd64/helm"
        legacy_pattern = "/helm/3.14.0/linux-amd64/helm"

        x64_pos = run_text.find(x64_pattern)
        legacy_pos = run_text.find(legacy_pattern)

        assert x64_pos != -1, (
            "Wire tools should check x64 Helm path pattern "
            "(e.g., /helm/3.14.0/x64/linux-amd64/helm)"
        )
        assert legacy_pos != -1, (
            "Wire tools should have legacy Helm path as fallback "
            "(e.g., /helm/3.14.0/linux-amd64/helm)"
        )
        assert x64_pos < legacy_pos, (
            "Wire tools must check x64 Helm paths BEFORE legacy paths. "
            f"Found x64 at position {x64_pos}, legacy at position {legacy_pos}. "
            "This ordering is required because azure/setup-helm caches Helm with "
            "the x64 segment (e.g., /helm/3.14.0/x64/linux-amd64/helm)."
        )

    def test_wire_tools_has_helm_paths_for_all_versions(self) -> None:
        """Wire tools should have x64 paths for all supported Helm versions."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # Supported Helm versions
        helm_versions = ["3.16.3", "3.16.2", "3.16.1", "3.16.0", "3.15.0", "3.14.0", "3.13.0"]

        for version in helm_versions:
            x64_path = f"/helm/{version}/x64/linux-amd64/helm"
            assert x64_path in run_text, (
                f"Wire tools should check x64 path for Helm {version}: {x64_path}"
            )

    def test_wire_tools_has_legacy_fallback_paths(self) -> None:
        """Wire tools should have legacy fallback paths for all supported Helm versions."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # Supported Helm versions
        helm_versions = ["3.16.3", "3.16.2", "3.16.1", "3.16.0", "3.15.0", "3.14.0", "3.13.0"]

        for version in helm_versions:
            legacy_path = f"/helm/{version}/linux-amd64/helm"
            assert legacy_path in run_text, (
                f"Wire tools should have legacy fallback for Helm {version}: {legacy_path}"
            )
