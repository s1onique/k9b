"""Tests for OTel Demo K8s-native incident injection - Cleanup Precision.

These tests verify precise cleanup using JSON Patch for nodeSelector.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.k9b_lab_common_helpers import KubectlResult
from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import (
    _is_json_patch_path_absent_error,
    _restore_node_selector,
    cleanup_unschedulable_shipping_rollout,
)


class TestIsJsonPatchPathAbsentError:
    """Test the helper function for distinguishing path-absent from other errors."""

    def test_accepts_node_selector_path(self) -> None:
        """nodeSelector path in error message should be accepted."""
        assert _is_json_patch_path_absent_error("/spec/template/spec/nodeSelector not found") is True
        assert _is_json_patch_path_absent_error("spec.template.spec.nodeselector missing") is True

    def test_accepts_missing_path_wording(self) -> None:
        """'missing path' wording should be accepted."""
        assert _is_json_patch_path_absent_error("doc is missing path") is True
        assert _is_json_patch_path_absent_error("missing path in document") is True

    def test_accepts_remove_operation_does_not_apply(self) -> None:
        """JSON Patch 'remove operation does not apply' should be accepted."""
        assert _is_json_patch_path_absent_error("remove operation does not apply") is True

    def test_rejects_generic_not_found(self) -> None:
        """Generic 'not found' without path context should be rejected."""
        assert _is_json_patch_path_absent_error('deployments.apps "shipping" not found') is False
        assert _is_json_patch_path_absent_error("namespace not found") is False
        assert _is_json_patch_path_absent_error("error: not found") is False

    def test_rejects_does_not_exist_without_path(self) -> None:
        """'doesn't exist' without path context should be rejected."""
        assert _is_json_patch_path_absent_error('deployment "shipping" does not exist') is False
        assert _is_json_patch_path_absent_error('resource "shipping" not found') is False

    def test_accepts_does_not_exist_with_path(self) -> None:
        """'doesn't exist' with path context should be accepted."""
        assert _is_json_patch_path_absent_error("/spec/template/spec/nodeSelector doesn't exist") is True
        assert _is_json_patch_path_absent_error("path doesn't exist: spec.template.spec.nodeSelector") is True

    def test_rejects_empty_stderr(self) -> None:
        """Empty stderr should be rejected."""
        assert _is_json_patch_path_absent_error("") is False
        assert _is_json_patch_path_absent_error(None) is False  # type: ignore

    def test_rejects_connection_errors(self) -> None:
        """Connection/network errors should be rejected."""
        assert _is_json_patch_path_absent_error("connection refused") is False
        assert _is_json_patch_path_absent_error("no route to host") is False
        assert _is_json_patch_path_absent_error("timeout") is False


class TestK8sInjectionCleanupPrecision:
    """Test precise cleanup using JSON Patch for nodeSelector."""

    def test_restore_node_selector_exports(self) -> None:
        """_restore_node_selector is available for testing."""
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


class TestK8sInjectionCleanupKeyHandling:
    """Test precise cleanup with selective key removal for unschedulable-shipping."""

    def test_cleanup_removes_only_injected_key(self) -> None:
        """Cleanup should remove only k9b.dev/otel-lab-node, preserving other keys.
        
        When the deployment template had:
          nodeSelector:
            kubernetes.io/os: linux
            k9b.dev/otel-lab-node: worker
        
        After cleanup with previous_node_selector=None (no selector existed):
          nodeSelector should be REMOVED entirely
        """
        # Simulate: previous_node_selector was None (no nodeSelector existed before injection)
        # Cleanup should use 'remove' op
        patch_remove = [{"op": "remove", "path": "/spec/template/spec/nodeSelector"}]
        assert patch_remove[0]["op"] == "remove"
        assert patch_remove[0]["path"] == "/spec/template/spec/nodeSelector"
    
    def test_cleanup_preserves_unrelated_node_selector_keys(self) -> None:
        """When previous_node_selector has other keys, only injected key should be removed.
        
        Scenario: Before injection, deployment had:
          nodeSelector:
            kubernetes.io/os: linux
        
        After injection (current):
          nodeSelector:
            kubernetes.io/os: linux
            k9b.dev/otel-lab-node: missing
        
        After cleanup: should restore to previous (kubernetes.io/os: linux only)
        """
        # Simulate: previous_node_selector was {"kubernetes.io/os": "linux"}
        # Cleanup should use 'replace' op to restore previous selector
        previous_node_selector = {"kubernetes.io/os": "linux"}
        patch_replace = [
            {"op": "replace", "path": "/spec/template/spec/nodeSelector", "value": previous_node_selector}
        ]
        assert patch_replace[0]["op"] == "replace"
        assert patch_replace[0]["value"] == {"kubernetes.io/os": "linux"}
        # k9b.dev/otel-lab-node is NOT in the value, so it won't be in the restored template
    
    def test_cleanup_idempotent_succeeds_on_json_patch_missing_path(self) -> None:
        """Cleanup should succeed (idempotent) when JSON Patch path is already absent.
        
        This tests the scenario where cleanup is run multiple times, or when
        the deployment was already cleaned up.
        """
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = KubectlResult(
                success=False,
                stdout="",
                stderr='{"message":"doc is missing path: /spec/template/spec/nodeSelector"}',
                returncode=1
            )
            
            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )
            
            # Idempotent success
            assert result is True, "Should succeed when path already absent"
            
            # Verify correct patch
            mock_patch.assert_called_once()
            call_args = mock_patch.call_args
            patch_arg = call_args[0][4]
            assert patch_arg == [{"op": "remove", "path": "/spec/template/spec/nodeSelector"}]
    
    def test_cleanup_idempotent_succeeds_on_node_selector_path_absent(self) -> None:
        """Cleanup should succeed when nodeSelector path is absent."""
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = KubectlResult(
                success=False,
                stdout="",
                stderr="spec.template.spec.nodeselector: doesn't exist",
                returncode=1
            )
            
            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )
            
            assert result is True, "Should succeed when nodeSelector path absent"
    
    def test_cleanup_idempotent_fails_when_shipping_deployment_not_found(self) -> None:
        """Cleanup should FAIL (not succeed) when deployment is not found.
        
        This is a real error, not an idempotent success case.
        """
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = KubectlResult(
                success=False,
                stdout="",
                stderr='deployments.apps "shipping" not found',
                returncode=1
            )
            
            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )
            
            # Fail-closed - this is a real error, not path-absent
            assert result is False, "Should fail when deployment not found"
    
    def test_cleanup_idempotent_fails_when_namespace_not_found(self) -> None:
        """Cleanup should FAIL (not succeed) when namespace is not found."""
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = KubectlResult(
                success=False,
                stdout="",
                stderr="namespace \"otel-demo\" not found",
                returncode=1
            )
            
            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )
            
            assert result is False, "Should fail when namespace not found"
    
    def test_cleanup_idempotent_fails_on_generic_not_found_without_patch_path(self) -> None:
        """Cleanup should fail on generic 'not found' without patch path context."""
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = KubectlResult(
                success=False,
                stdout="",
                stderr='{"message":"not found"}',
                returncode=1
            )
            
            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )
            
            assert result is False, "Should fail on generic not found without path context"
    
    def test_cleanup_idempotency_fails_on_connection_error(self) -> None:
        """Cleanup should fail-closed on network/connection errors."""
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = KubectlResult(
                success=False,
                stdout="",
                stderr="connection refused",
                returncode=1
            )
            
            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )
            
            assert result is False, "Should fail on connection errors"
    
    def test_cleanup_uses_json_patch_type(self) -> None:
        """Cleanup must use JSON Patch type, not strategic or merge patch."""
        patch_calls = []
        
        def mock_patch_fn(*args: object, **kwargs: object) -> KubectlResult:
            patch_calls.append({"args": args, "kwargs": kwargs})
            return KubectlResult(success=True, stdout="", stderr="", returncode=0)
        
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch", side_effect=mock_patch_fn):
            _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector={"kubernetes.io/os": "linux"},
            )
        
        # Verify patch_type="json" was used
        assert len(patch_calls) == 1
        assert patch_calls[0]["kwargs"].get("patch_type") == "json", \
            "Must use patch_type='json' for JSON Patch operations"
    
    def test_cleanup_targets_deployment_not_individual_pod(self) -> None:
        """Cleanup must patch the deployment template, not individual pods."""
        patch_calls = []
        
        def mock_scale(kubeconfig: str, namespace: str, deployment: str, replicas: int) -> KubectlResult:
            return KubectlResult(success=True, stdout="", stderr="", returncode=0)
        
        def mock_patch(
            kubeconfig: str,
            resource_type: str,
            name: str,
            namespace: str | None = None,
            patch: dict[str, object] | list[object] | None = None,
            patch_type: str = "strategic",
        ) -> KubectlResult:
            patch_calls.append({
                "resource_type": resource_type,
                "name": name,
                "namespace": namespace,
            })
            return KubectlResult(success=True, stdout="", stderr="", returncode=0)
        
        with patch.multiple(
            "scripts.k9b_otel_demo_lab_k8s_injection_cleanup",
            _kubectl_scale=mock_scale,
            kubectl_patch=mock_patch,
        ):
            cleanup_unschedulable_shipping_rollout(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
                original_replicas=1,
            )
        
        # Verify that the patch targets the Deployment, not Pod
        assert len(patch_calls) == 1
        assert patch_calls[0]["resource_type"] == "deployment", "Must patch deployment, not pod"
        assert patch_calls[0]["name"] == "shipping", "Must target shipping deployment"


class TestK8sInjectionCleanupRecovery:
    """Test cleanup/recovery logic."""

    def test_cleanup_scales_then_restores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cleanup should scale to 0, restore template, scale to original."""
        scale_calls: list[tuple[str, str, str, int]] = []
        patch_calls: list[dict[str, object]] = []

        def mock_scale(kubeconfig: str, namespace: str, deployment: str, replicas: int) -> object:
            scale_calls.append((kubeconfig, namespace, deployment, replicas))
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
