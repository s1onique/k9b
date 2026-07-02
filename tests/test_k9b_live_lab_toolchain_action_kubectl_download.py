"""Regression tests for kubectl download-on-miss behavior in k9b-live-lab-toolchain.

These tests verify:
1. kubectl wiring downloads from dl.k8s.io with checksum validation
2. File locking for atomic cache population
3. Offline mode (allow-tool-download=false) fails fast
4. Architecture support (amd64, arm64)
5. Version resolution ('latest' via stable.txt)

See: .github/actions/k9b-live-lab-toolchain/action.yml
"""

from __future__ import annotations

from tests.helpers.k9b_live_lab_toolchain_action_helpers import (
    TOOLCHAIN_ACTION_FILE,
    _get_step_by_id,
    _load_action_yaml,
)


class TestToolchainActionKubectlDownload:
    """Test kubectl download-on-miss behavior with checksum validation."""

    def test_kubectl_wiring_includes_download_path(self) -> None:
        """kubectl wiring should have download-from-dl.k8s.io path."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # Should download from dl.k8s.io
        assert "dl.k8s.io" in run_text, (
            "kubectl wiring should download from dl.k8s.io"
        )

    def test_kubectl_wiring_validates_checksum(self) -> None:
        """kubectl download should validate SHA256 checksum with Kubernetes' official format."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # Should download .sha256 file and validate using Kubernetes' official format:
        # echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check
        assert "sha256" in run_text.lower(), (
            "kubectl download should validate SHA256 checksum"
        )
        # Check for the correct format (not just sha256sum -c)
        assert "echo \"$(cat kubectl.sha256)  kubectl\"" in run_text or "echo \"$(cat kubectl.sha256)  ${" in run_text, (
            "kubectl should validate using Kubernetes' official format: "
            "echo \"$(cat kubectl.sha256)  kubectl\" | sha256sum --check"
        )

    def test_kubectl_wiring_uses_atomic_install_with_rm_rf(self) -> None:
        """kubectl install should remove existing dir before mv to handle broken cache."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # Should use rm -rf before mv -T to handle broken partial cache dirs
        assert "flock" in run_text, (
            "kubectl install should use flock for concurrent cache population safety"
        )
        assert "rm -rf" in run_text and "mv -T" in run_text, (
            "kubectl install should use 'rm -rf' before 'mv -T' to handle broken partial cache dirs"
        )

    def test_kubectl_wiring_fails_when_download_disallowed(self) -> None:
        """kubectl should fail when not in cache and allow-tool-download=false."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # Should have error message for offline mode
        assert "allow-tool-download=false" in run_text or "allow-tool-download" in run_text, (
            "kubectl wiring should check allow-tool-download flag"
        )

    def test_kubectl_wiring_resolves_latest_version(self) -> None:
        """kubectl wiring should resolve 'latest' to actual version via stable.txt."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # Should fetch stable.txt when version is 'latest'
        assert "stable.txt" in run_text, (
            "kubectl should resolve 'latest' via dl.k8s.io/release/stable.txt"
        )

    def test_kubectl_wiring_supports_arm64(self) -> None:
        """kubectl wiring should support arm64 architecture."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # Should detect arm64 architecture
        assert "arm64" in run_text or "aarch64" in run_text, (
            "kubectl wiring should support arm64 architecture"
        )

    def test_kubectl_wiring_resolves_latest_before_cache_lookup(self) -> None:
        """'latest' should be resolved before cache lookup, not as a fallback."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # Find the position of stable.txt fetch and cache lookup
        stable_txt_pos = run_text.find("stable.txt")
        kubectl_cache_pos = run_text.find("${tool_cache}/kubectl/${kubectl_version}")

        assert stable_txt_pos != -1, "Should resolve 'latest' via stable.txt"
        assert kubectl_cache_pos != -1, "Should have cache lookup path"

        # stable.txt should be resolved BEFORE cache lookup for 'latest'
        # This is a structural check: the 'latest' resolution block must come
        # before the cache lookup in the script flow
        latest_block_start = run_text.rfind("if [[ \"${kubectl_version}\" == \"latest\" ]]")
        cache_lookup_start = run_text.rfind("exact_path=\"${tool_cache}/kubectl/${kubectl_version}")

        assert latest_block_start != -1, "Should have 'latest' resolution block"
        assert cache_lookup_start != -1, "Should have exact cache lookup"

        # The 'latest' resolution must come before cache lookup
        assert latest_block_start < cache_lookup_start, (
            "'latest' resolution must happen before cache lookup "
            "to ensure 'latest' actually means latest"
        )

    def test_kubectl_wiring_no_fallback_for_pinned_versions(self) -> None:
        """Pinned kubectl versions should not silently fall back to older versions."""
        action = _load_action_yaml(TOOLCHAIN_ACTION_FILE)
        step = _get_step_by_id(action, "wire-tools")

        assert step is not None, "wire-tools step not found"
        run_text = step.get("run", "")

        # There should be no fallback_versions array or loop
        # for exact cache lookups (only exact_path lookup should exist)
        assert "fallback_versions=" not in run_text, (
            "Should not have fallback_versions array for pinned kubectl versions"
        )

        # The script should only do exact version lookup, not iterate over versions
        # Count occurrences of exact_path - should be just one
        exact_path_count = run_text.count("exact_path=\"${tool_cache}/kubectl/${kubectl_version}")
        assert exact_path_count <= 2, (  # 1 for setting, 1 for checking if -x
            "Should only have exact version lookup, no fallback iteration"
        )
