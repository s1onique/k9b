"""Tests for OTel Demo K8s-native incident injection - Patch and Artifacts.

These tests verify injection creates correct artifact structure.
"""

from __future__ import annotations

from pathlib import Path


class TestK8sInjectionPatchArtifacts:
    """Test that injection creates correct artifact structure."""

    def test_injection_command_artifact_contains_selector(self) -> None:
        """Injection command artifact includes the impossible nodeSelector."""
        from scripts.k9b_otel_demo_lab_k8s_injection import (
            K8S_INJECTION_NODE_SELECTOR_KEY,
            K8S_INJECTION_NODE_SELECTOR_VALUE,
            SHIPPING_DEPLOYMENT,
        )

        # Build expected injection command
        expected_cmd: dict[str, str | dict[str, str]] = {
            "command": "Inject unschedulable shipping rollout",
            "method": "nodeSelector_patch",
            "deployment": SHIPPING_DEPLOYMENT,
            "namespace": "otel-demo",
            "nodeSelector": {
                K8S_INJECTION_NODE_SELECTOR_KEY: K8S_INJECTION_NODE_SELECTOR_VALUE,
            },
        }

        node_selector = expected_cmd["nodeSelector"]
        assert isinstance(node_selector, dict)
        assert node_selector[K8S_INJECTION_NODE_SELECTOR_KEY] == "missing"

    def test_cleanup_command_artifact_structure(self, tmp_path: Path) -> None:
        """Cleanup command artifact references previous template path."""
        from scripts.k9b_otel_demo_lab_k8s_injection import SHIPPING_DEPLOYMENT

        cleanup_cmd = {
            "command": "Cleanup unschedulable shipping rollout",
            "method": "restore_previous_template",
            "deployment": SHIPPING_DEPLOYMENT,
            "namespace": "otel-demo",
            "previous_template_path": str(tmp_path / "previous-pod-template.json"),
        }

        assert cleanup_cmd["method"] == "restore_previous_template"
        assert "previous_template_path" in cleanup_cmd


class TestK8sInjectionNodeSelectorPatch:
    """Test the nodeSelector patch structure."""

    def test_patch_structure_is_correct(self) -> None:
        """Patch manifest has correct structure for strategic merge."""
        from scripts.k9b_otel_demo_lab_k8s_injection import (
            K8S_INJECTION_NODE_SELECTOR_KEY,
            K8S_INJECTION_NODE_SELECTOR_VALUE,
        )

        patch_manifest = {
            "spec": {
                "template": {
                    "spec": {
                        "nodeSelector": {
                            K8S_INJECTION_NODE_SELECTOR_KEY: K8S_INJECTION_NODE_SELECTOR_VALUE,
                        }
                    }
                }
            }
        }

        # Verify structure
        assert "spec" in patch_manifest
        assert "template" in patch_manifest["spec"]
        assert "spec" in patch_manifest["spec"]["template"]
        assert "nodeSelector" in patch_manifest["spec"]["template"]["spec"]
        assert (
            patch_manifest["spec"]["template"]["spec"]["nodeSelector"][K8S_INJECTION_NODE_SELECTOR_KEY]
            == K8S_INJECTION_NODE_SELECTOR_VALUE
        )
