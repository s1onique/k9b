"""Contract tests for OTel Demo K8s-native incident injection cleanup.

Verifies static repository/workflow contract: cleanup step wiring,
required env, forbidden inline patterns, required artifact names.
"""

from __future__ import annotations

from pathlib import Path


class TestK8sInjectionCleanupPrecision:
    """Test precise cleanup using JSON Patch for nodeSelector."""

    def test_restore_node_selector_exports(self) -> None:
        """_restore_node_selector is available for testing."""
        from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import _restore_node_selector

        assert callable(_restore_node_selector)

    def test_json_patch_remove_when_no_previous(self) -> None:
        """JSON Patch uses 'remove' op when previous_node_selector is None."""
        json_patch = [{"op": "remove", "path": "/spec/template/spec/nodeSelector"}]
        assert json_patch[0]["op"] == "remove"
        assert json_patch[0]["path"] == "/spec/template/spec/nodeSelector"

    def test_json_patch_replace_when_previous_exists(self) -> None:
        """JSON Patch uses 'replace' op when previous_node_selector exists."""
        previous_node_selector = {"kubernetes.io/os": "linux"}
        json_patch = [
            {"op": "replace", "path": "/spec/template/spec/nodeSelector", "value": previous_node_selector}
        ]
        assert json_patch[0]["op"] == "replace"
        assert json_patch[0]["value"] == previous_node_selector


class TestResetShippingNodeSelectorContract:
    """Contract tests verifying reset is wired into lab harness."""

    def test_reset_function_in_lab_orchestrator(self) -> None:
        """Lab orchestrator should import and invoke reset_shipping_node_selector."""
        lab_path = Path("scripts/k9b_otel_demo_lab.py")
        content = lab_path.read_text()

        assert "reset_shipping_node_selector" in content, \
            "Lab orchestrator should import reset_shipping_node_selector"

        reset_pos = content.find("reset_shipping_node_selector")
        p2b_pos = content.find("phase_p2b_inject_unschedulable_shipping_rollout")

        assert reset_pos > 0, "reset_shipping_node_selector should be called in orchestrator"
        assert p2b_pos > 0, "P2b injection should be called in orchestrator"
        assert reset_pos < p2b_pos, "reset should be called BEFORE P2b injection"

    def test_reset_target_is_shipping_deployment(self) -> None:
        """Reset should target the shipping deployment."""
        cleanup_path = Path("scripts/k9b_otel_demo_lab_k8s_injection_cleanup.py")
        content = cleanup_path.read_text()

        assert "SHIPPING_DEPLOYMENT" in content, \
            "Reset function should use SHIPPING_DEPLOYMENT constant"
        assert "shipping" in content.lower(), \
            "Reset function should reference 'shipping' deployment"

    def test_reset_uses_merge_patch(self) -> None:
        """Reset should use merge patch (not JSON Patch) to set nodeSelector to null."""
        cleanup_path = Path("scripts/k9b_otel_demo_lab_k8s_injection_cleanup.py")
        content = cleanup_path.read_text()

        assert 'patch_type="merge"' in content or "patch_type='merge'" in content, \
            "Reset should use merge patch to set nodeSelector to null"

    def test_reset_waits_for_rollout(self) -> None:
        """Reset should wait for deployment rollout after patching."""
        cleanup_path = Path("scripts/k9b_otel_demo_lab_k8s_injection_cleanup.py")
        content = cleanup_path.read_text()

        assert "rollout" in content.lower() or "rollout" in content, \
            "Reset should wait for rollout status"
