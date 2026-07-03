"""Workflow behavior tests for OTel Demo K8s injection cleanup.

Tests live-lab workflow wiring, injection/cleanup sequencing,
failure-path behavior, and resilience.
"""

from __future__ import annotations

from unittest.mock import patch

from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import (
    _restore_node_selector,
    cleanup_unschedulable_shipping_rollout,
    reset_shipping_node_selector,
)
from tests.helpers.otel_demo_k8s_injection_cleanup_helpers import (
    make_connection_error_result,
    make_deployment_not_found_result,
    make_kubectl_result,
    make_namespace_not_found_result,
    make_nodeselector_absent_result,
    make_path_absent_result,
)


class TestIsJsonPatchPathAbsentError:
    """Test the helper function for distinguishing path-absent from other errors."""

    def test_accepts_node_selector_path(self) -> None:
        """nodeSelector path in error message should be accepted."""
        from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import _is_json_patch_path_absent_error

        assert _is_json_patch_path_absent_error("/spec/template/spec/nodeSelector not found") is True
        assert _is_json_patch_path_absent_error("spec.template.spec.nodeselector missing") is True

    def test_accepts_missing_path_wording(self) -> None:
        """'missing path' wording should be accepted."""
        from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import _is_json_patch_path_absent_error

        assert _is_json_patch_path_absent_error("doc is missing path") is True
        assert _is_json_patch_path_absent_error("missing path in document") is True

    def test_accepts_remove_operation_does_not_apply(self) -> None:
        """JSON Patch 'remove operation does not apply' should be accepted."""
        from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import _is_json_patch_path_absent_error

        assert _is_json_patch_path_absent_error("remove operation does not apply") is True

    def test_rejects_generic_not_found(self) -> None:
        """Generic 'not found' without path context should be rejected."""
        from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import _is_json_patch_path_absent_error

        assert _is_json_patch_path_absent_error('deployments.apps "shipping" not found') is False
        assert _is_json_patch_path_absent_error("namespace not found") is False
        assert _is_json_patch_path_absent_error("error: not found") is False

    def test_rejects_does_not_exist_without_path(self) -> None:
        """'doesn't exist' without path context should be rejected."""
        from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import _is_json_patch_path_absent_error

        assert _is_json_patch_path_absent_error('deployment "shipping" does not exist') is False
        assert _is_json_patch_path_absent_error('resource "shipping" not found') is False

    def test_accepts_does_not_exist_with_path(self) -> None:
        """'doesn't exist' with path context should be accepted."""
        from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import _is_json_patch_path_absent_error

        assert _is_json_patch_path_absent_error("/spec/template/spec/nodeSelector doesn't exist") is True
        assert _is_json_patch_path_absent_error("path doesn't exist: spec.template.spec.nodeSelector") is True

    def test_rejects_empty_stderr(self) -> None:
        """Empty stderr should be rejected."""
        from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import _is_json_patch_path_absent_error

        assert _is_json_patch_path_absent_error("") is False
        assert _is_json_patch_path_absent_error(None) is False  # type: ignore

    def test_rejects_connection_errors(self) -> None:
        """Connection/network errors should be rejected."""
        from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import _is_json_patch_path_absent_error

        assert _is_json_patch_path_absent_error("connection refused") is False
        assert _is_json_patch_path_absent_error("no route to host") is False
        assert _is_json_patch_path_absent_error("timeout") is False


class TestK8sInjectionCleanupKeyHandling:
    """Test precise cleanup with selective key removal for unschedulable-shipping."""

    def test_cleanup_removes_only_injected_key(self) -> None:
        """Cleanup should remove only k9b.dev/otel-lab-node, preserving other keys."""
        patch_remove = [{"op": "remove", "path": "/spec/template/spec/nodeSelector"}]
        assert patch_remove[0]["op"] == "remove"
        assert patch_remove[0]["path"] == "/spec/template/spec/nodeSelector"

    def test_cleanup_preserves_unrelated_node_selector_keys(self) -> None:
        """When previous_node_selector has other keys, only injected key should be removed."""
        previous_node_selector = {"kubernetes.io/os": "linux"}
        patch_replace = [
            {"op": "replace", "path": "/spec/template/spec/nodeSelector", "value": previous_node_selector}
        ]
        assert patch_replace[0]["op"] == "replace"
        assert patch_replace[0]["value"] == {"kubernetes.io/os": "linux"}

    def test_cleanup_idempotent_succeeds_on_json_patch_missing_path(self) -> None:
        """Cleanup should succeed (idempotent) when JSON Patch path is already absent."""
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = make_path_absent_result()

            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )

            assert result is True, "Should succeed when path already absent"

            mock_patch.assert_called_once()
            call_args = mock_patch.call_args
            patch_arg = call_args[0][4]
            assert patch_arg == [{"op": "remove", "path": "/spec/template/spec/nodeSelector"}]

    def test_cleanup_idempotent_succeeds_on_node_selector_path_absent(self) -> None:
        """Cleanup should succeed when nodeSelector path is absent."""
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = make_nodeselector_absent_result()

            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )

            assert result is True, "Should succeed when nodeSelector path absent"

    def test_cleanup_idempotent_fails_when_shipping_deployment_not_found(self) -> None:
        """Cleanup should FAIL (not succeed) when deployment is not found."""
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = make_deployment_not_found_result()

            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )

            assert result is False, "Should fail when deployment not found"

    def test_cleanup_idempotent_fails_when_namespace_not_found(self) -> None:
        """Cleanup should FAIL (not succeed) when namespace is not found."""
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = make_namespace_not_found_result()

            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )

            assert result is False, "Should fail when namespace not found"

    def test_cleanup_idempotent_fails_on_generic_not_found_without_patch_path(self) -> None:
        """Cleanup should fail on generic 'not found' without patch path context."""
        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch") as mock_patch:
            mock_patch.return_value = make_kubectl_result(
                success=False,
                stderr='{"message":"not found"}',
                returncode=1,
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
            mock_patch.return_value = make_connection_error_result()

            result = _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector=None,
            )

            assert result is False, "Should fail on connection errors"

    def test_cleanup_uses_json_patch_type(self) -> None:
        """Cleanup must use JSON Patch type, not strategic or merge patch."""
        patch_calls = []

        def mock_patch_fn(*args: object, **kwargs: object) -> object:
            patch_calls.append({"args": args, "kwargs": kwargs})
            return make_kubectl_result(success=True)

        with patch("scripts.k9b_otel_demo_lab_k8s_injection_cleanup.kubectl_patch", side_effect=mock_patch_fn):
            _restore_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
                previous_node_selector={"kubernetes.io/os": "linux"},
            )

        assert len(patch_calls) == 1
        assert patch_calls[0]["kwargs"].get("patch_type") == "json", \
            "Must use patch_type='json' for JSON Patch operations"

    def test_cleanup_targets_deployment_not_individual_pod(self) -> None:
        """Cleanup must patch the deployment template, not individual pods."""
        patch_calls = []

        def mock_scale(kubeconfig: str, namespace: str, deployment: str, replicas: int) -> object:
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
                "resource_type": resource_type,
                "name": name,
                "namespace": namespace,
            })
            return make_kubectl_result(success=True)

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

        assert len(patch_calls) == 1
        assert patch_calls[0]["resource_type"] == "deployment", "Must patch deployment, not pod"
        assert patch_calls[0]["name"] == "shipping", "Must target shipping deployment"


class TestResetShippingNodeSelectorPreflight:
    """Test lab-start preflight reset of shipping nodeSelector."""

    def test_reset_exports(self) -> None:
        """reset_shipping_node_selector is available for testing."""
        assert callable(reset_shipping_node_selector)

    def test_reset_skips_when_deployment_not_found(self) -> None:
        """Reset should succeed (skip) when shipping deployment doesn't exist yet."""
        def mock_kubectl_json(*args: object, **kwargs: object) -> object:
            return make_deployment_not_found_result()

        import scripts.k9b_otel_demo_lab_k8s_injection_cleanup as cleanup_module
        with patch.object(cleanup_module, "kubectl_json", side_effect=mock_kubectl_json):
            result = cleanup_module.reset_shipping_node_selector(
                kubeconfig="/fake/kubeconfig",
                namespace="otel-demo",
            )

        assert result is True, "Should succeed (skip) when deployment not found"

    def test_reset_clears_node_selector_and_waits_for_rollout(self) -> None:
        """Reset should patch nodeSelector to null and wait for rollout."""
        patch_calls = []
        rollout_calls = []

        def mock_kubectl_json(*args: object, **kwargs: object) -> object:
            return make_kubectl_result(
                success=True,
                stdout='{"metadata": {"name": "shipping"}}',
                data={"metadata": {"name": "shipping"}},
            )

        def mock_kubectl_patch(*args: object, **kwargs: object) -> object:
            patch_calls.append({"kwargs": kwargs})
            return make_kubectl_result(success=True)

        def mock_wait_for_rollout(*args: object, **kwargs: object) -> bool:
            rollout_calls.append({"args": args, "kwargs": kwargs})
            return True

        import scripts.k9b_otel_demo_lab_k8s_injection_cleanup as cleanup_module
        with patch.object(cleanup_module, "kubectl_json", side_effect=mock_kubectl_json):
            with patch.object(cleanup_module, "kubectl_patch", side_effect=mock_kubectl_patch):
                with patch.object(cleanup_module, "_wait_for_rollout", side_effect=mock_wait_for_rollout):
                    result = cleanup_module.reset_shipping_node_selector(
                        kubeconfig="/fake/kubeconfig",
                        namespace="otel-demo",
                    )

        assert result is True, "Reset should succeed"
        assert len(patch_calls) == 1, "Should patch exactly once"
        patch_arg = patch_calls[0]["kwargs"].get("patch")
        assert patch_arg == {"spec": {"template": {"spec": {"nodeSelector": None}}}}, \
            f"Should patch nodeSelector to null, got: {patch_arg}"
        assert patch_calls[0]["kwargs"].get("patch_type") == "merge", "Should use merge patch"
        assert len(rollout_calls) == 1, "Should wait for rollout"

    def test_reset_idempotent_when_node_selector_already_absent(self) -> None:
        """Reset should succeed (idempotent) when nodeSelector path is already absent."""
        patch_calls = []

        def mock_kubectl_json(*args: object, **kwargs: object) -> object:
            return make_kubectl_result(
                success=True,
                stdout='{"metadata": {"name": "shipping"}}',
                data={"metadata": {"name": "shipping"}},
            )

        def mock_kubectl_patch(*args: object, **kwargs: object) -> object:
            patch_calls.append({"kwargs": kwargs})
            return make_nodeselector_absent_result()

        def mock_wait_for_rollout(*args: object, **kwargs: object) -> bool:
            return True

        import scripts.k9b_otel_demo_lab_k8s_injection_cleanup as cleanup_module
        with patch.object(cleanup_module, "kubectl_json", side_effect=mock_kubectl_json):
            with patch.object(cleanup_module, "kubectl_patch", side_effect=mock_kubectl_patch):
                with patch.object(cleanup_module, "_wait_for_rollout", side_effect=mock_wait_for_rollout):
                    result = cleanup_module.reset_shipping_node_selector(
                        kubeconfig="/fake/kubeconfig",
                        namespace="otel-demo",
                    )

        assert result is True, "Should succeed (idempotent) when nodeSelector already absent"
        assert len(patch_calls) == 1, "Should attempt patch"

    def test_reset_fail_closed_on_real_error(self) -> None:
        """Reset should fail-closed on real errors (not path-absent)."""
        def mock_kubectl_json(*args: object, **kwargs: object) -> object:
            return make_kubectl_result(
                success=True,
                stdout='{"metadata": {"name": "shipping"}}',
                data={"metadata": {"name": "shipping"}},
            )

        def mock_kubectl_patch(*args: object, **kwargs: object) -> object:
            return make_connection_error_result()

        import scripts.k9b_otel_demo_lab_k8s_injection_cleanup as cleanup_module
        with patch.object(cleanup_module, "kubectl_json", side_effect=mock_kubectl_json):
            with patch.object(cleanup_module, "kubectl_patch", side_effect=mock_kubectl_patch):
                result = cleanup_module.reset_shipping_node_selector(
                    kubeconfig="/fake/kubeconfig",
                    namespace="otel-demo",
                )

        assert result is False, "Should fail-closed on real errors"

    def test_reset_rollout_timeout_still_succeeds(self) -> None:
        """Reset should succeed even if rollout status times out (patch succeeded)."""
        patch_calls = []

        def mock_kubectl_json(*args: object, **kwargs: object) -> object:
            return make_kubectl_result(
                success=True,
                stdout='{"metadata": {"name": "shipping"}}',
                data={"metadata": {"name": "shipping"}},
            )

        def mock_kubectl_patch(*args: object, **kwargs: object) -> object:
            patch_calls.append({"kwargs": kwargs})
            return make_kubectl_result(success=True)

        def mock_wait_for_rollout(*args: object, **kwargs: object) -> bool:
            return False  # Timeout

        import scripts.k9b_otel_demo_lab_k8s_injection_cleanup as cleanup_module
        with patch.object(cleanup_module, "kubectl_json", side_effect=mock_kubectl_json):
            with patch.object(cleanup_module, "kubectl_patch", side_effect=mock_kubectl_patch):
                with patch.object(cleanup_module, "_wait_for_rollout", side_effect=mock_wait_for_rollout):
                    result = cleanup_module.reset_shipping_node_selector(
                        kubeconfig="/fake/kubeconfig",
                        namespace="otel-demo",
                    )

        assert result is True, "Should succeed even if rollout times out (patch succeeded)"
        assert len(patch_calls) == 1, "Patch should have been called"
