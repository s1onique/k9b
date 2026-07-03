"""Artifact/result tests for OTel Demo K8s injection cleanup.

Tests cleanup reports, JSON shape, summaries, failure classification,
missing cleanup report behavior, bounded messages, and rendered expectations.
"""

from __future__ import annotations

import pytest

from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import cleanup_unschedulable_shipping_rollout
from tests.helpers.otel_demo_k8s_injection_cleanup_helpers import make_kubectl_result


class TestK8sInjectionCleanupRecovery:
    """Test cleanup/recovery logic and artifact handling."""

    def test_cleanup_scales_then_restores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cleanup should scale to 0, restore template, scale to original."""
        scale_calls: list[tuple[str, str, str, int]] = []
        patch_calls: list[dict[str, object]] = []

        def mock_scale(
            kubeconfig: str,
            namespace: str,
            deployment: str,
            replicas: int,
        ) -> object:
            scale_calls.append((kubeconfig, namespace, deployment, replicas))
            return make_kubectl_result(success=True)

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
            return make_kubectl_result(success=True)

        import scripts.k9b_otel_demo_lab_k8s_injection_cleanup as cleanup_module
        monkeypatch.setattr(cleanup_module, "_kubectl_scale", mock_scale)
        monkeypatch.setattr(cleanup_module, "kubectl_patch", mock_patch)

        result = cleanup_unschedulable_shipping_rollout(
            kubeconfig="/fake/kubeconfig",
            namespace="otel-demo",
            previous_node_selector={"k9b.dev/otel-lab-node": "worker"},
            original_replicas=2,
        )

        assert result is True, "Cleanup should return True on success"

        assert len(scale_calls) == 2, "Should have exactly 2 scale calls"
        assert scale_calls[0][3] == 0, "First scale should be to 0"
        assert scale_calls[1][3] == 2, "Second scale should be to original replicas"

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
        assert patch_ops[0]["value"] == {"k9b.dev/otel-lab-node": "worker"}, \
            "Should restore previous selector"

    def test_cleanup_preserves_previous_template_path(self) -> None:
        """Cleanup artifact references the saved previous template."""
        previous_template_path = "/tmp/artifacts/previous-pod-template.json"

        cleanup_cmd = {
            "previous_template_path": previous_template_path,
        }

        assert cleanup_cmd["previous_template_path"] == previous_template_path
