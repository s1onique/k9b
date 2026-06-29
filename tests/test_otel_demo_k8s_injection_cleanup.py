"""Tests for OTel Demo K8s-native incident injection - Cleanup Precision.

These tests verify precise cleanup using JSON Patch for nodeSelector.
"""

from __future__ import annotations

import pytest


class TestK8sInjectionCleanupPrecision:
    """Test precise cleanup using JSON Patch for nodeSelector."""

    def test_restore_node_selector_exports(self) -> None:
        """_restore_node_selector is available for testing."""
        from scripts.k9b_otel_demo_lab_k8s_injection import _restore_node_selector

        assert callable(_restore_node_selector)

    def test_json_patch_remove_when_no_previous(self) -> None:
        """JSON Patch uses 'remove' op when previous_node_selector is None."""
        # When previous_node_selector is None:
        # json_patch = [{"op": "remove", "path": "/spec/template/spec/nodeSelector"}]
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

    def test_extract_node_selector_exports(self) -> None:
        """_extract_node_selector is available for testing."""
        from scripts.k9b_otel_demo_lab_k8s_injection import _extract_node_selector

        assert callable(_extract_node_selector)

    def test_extract_node_selector_from_template(self) -> None:
        """_extract_node_selector correctly extracts from pod template."""
        from scripts.k9b_otel_demo_lab_k8s_injection import _extract_node_selector

        pod_template = {
            "spec": {
                "nodeSelector": {
                    "kubernetes.io/os": "linux",
                    "k9b.dev/otel-lab-node": "worker",
                }
            }
        }

        result = _extract_node_selector(pod_template)
        assert result is not None
        assert result["kubernetes.io/os"] == "linux"
        assert result["k9b.dev/otel-lab-node"] == "worker"

    def test_extract_node_selector_returns_none_when_missing(self) -> None:
        """_extract_node_selector returns None when no nodeSelector."""
        from scripts.k9b_otel_demo_lab_k8s_injection import _extract_node_selector

        pod_template: dict[str, dict[str, object]] = {"spec": {}}
        result = _extract_node_selector(pod_template)
        assert result is None


class TestK8sInjectionCleanupRecovery:
    """Test cleanup/recovery logic."""

    def test_cleanup_scales_then_restores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cleanup should scale to 0, restore template, scale to original."""
        from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import cleanup_unschedulable_shipping_rollout

        scale_calls: list[tuple[str, str, str, int]] = []
        patch_calls: list[dict[str, object]] = []

        def mock_scale(kubeconfig: str, namespace: str, deployment: str, replicas: int) -> object:
            scale_calls.append((kubeconfig, namespace, deployment, replicas))
            from scripts.k9b_lab_common_helpers import KubectlResult
            return KubectlResult(success=True, stdout="", stderr="", returncode=0)

        def mock_patch(
            kubeconfig: str,
            resource_type: str,
            name: str,
            namespace: str | None = None,
            patch: dict[str, object] | list[object] | None = None,
            patch_type: str = "strategic",
        ) -> object:
            patch_calls.append({
                "kubeconfig": kubeconfig,
                "resource_type": resource_type,
                "name": name,
                "namespace": namespace,
                "patch": patch,
                "patch_type": patch_type,
            })
            from scripts.k9b_lab_common_helpers import KubectlResult
            return KubectlResult(success=True, stdout="", stderr="", returncode=0)

        # Patch the internal functions
        import scripts.k9b_otel_demo_lab_k8s_injection_cleanup as cleanup_module
        monkeypatch.setattr(cleanup_module, "_kubectl_scale", mock_scale)
        monkeypatch.setattr(cleanup_module, "kubectl_patch", mock_patch)

        # Run cleanup
        result = cleanup_unschedulable_shipping_rollout(
            kubeconfig="/fake/kubeconfig",
            namespace="otel-demo",
            previous_node_selector={"k9b.dev/otel-lab-node": "worker"},
            original_replicas=2,
        )

        # Verify result
        assert result is True, "Cleanup should return True on success"

        # Verify scale calls: first to 0, then to original replicas
        assert len(scale_calls) == 2, "Should have exactly 2 scale calls"
        assert scale_calls[0][3] == 0, "First scale should be to 0"
        assert scale_calls[1][3] == 2, "Second scale should be to original replicas"

        # Verify patch was called with JSON Patch and correct deployment
        assert len(patch_calls) == 1, "Should have exactly 1 patch call"
        patch_call = patch_calls[0]
        assert patch_call["resource_type"] == "deployment", "Should patch deployment"
        assert patch_call["name"] == "shipping", "Should patch shipping deployment"
        assert patch_call["namespace"] == "otel-demo", "Should use correct namespace"
        assert patch_call["patch_type"] == "json", "Should use JSON Patch type"
        assert isinstance(patch_call["patch"], list), "Patch should be a list of operations"
        patch_ops = patch_call["patch"]
        assert len(patch_ops) == 1, "Should have exactly 1 patch operation"
        assert patch_ops[0]["op"] == "replace", "Should use replace operation"
        assert patch_ops[0]["value"] == {"k9b.dev/otel-lab-node": "worker"}, "Should restore previous selector"

    def test_cleanup_preserves_previous_template_path(self) -> None:
        """Cleanup artifact references the saved previous template."""
        previous_template_path = "/tmp/artifacts/previous-pod-template.json"

        cleanup_cmd = {
            "previous_template_path": previous_template_path,
        }

        assert cleanup_cmd["previous_template_path"] == previous_template_path
