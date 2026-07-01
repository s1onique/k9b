"""Unit tests for scheduler namespace isolation.

Regression tests for namespace isolation in scheduler deployment lookup.

These tests verify that when reading the scheduler deployment, the correct
k9b control-plane namespace is used, NOT the incident namespace.

This is critical for provider smoke tests where:
- k9b backend runs in namespace "k9b"
- OTel demo incidents run in namespace "otel-demo"
- Scheduler deployment k9b-scheduler exists in "k9b" namespace

Bug scenario: If someone passes incident_namespace="otel-demo" to
is_automatic_diagnosis_loop_enabled(), the function should NOT try to
read deployment/k9b-scheduler from namespace "otel-demo".
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch


def _make_deployment_spec(env_var_name: str, env_var_value: str) -> dict:
    """Create a deployment spec with the given env var."""
    return {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "scheduler",
                            "env": [
                                {
                                    "name": env_var_name,
                                    "value": env_var_value,
                                }
                            ],
                        }
                    ]
                }
            }
        }
    }


class TestSchedulerNamespaceIsolation:
    """Regression tests for namespace isolation in scheduler deployment lookup."""

    def test_uses_explicit_namespace_parameter_for_scheduler_lookup(self) -> None:
        """Prove the namespace parameter is used for scheduler deployment lookup."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            is_automatic_diagnosis_loop_enabled,
        )

        deployment_spec = _make_deployment_spec(
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", "true"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "MockResult",
                (),
                {"returncode": 0, "stdout": json.dumps(deployment_spec)},
            )()

            # Call with explicit namespace "k9b"
            result = is_automatic_diagnosis_loop_enabled(
                kubeconfig="/tmp/kubeconfig",
                namespace="k9b",
            )

            assert result is True
            # Verify exact kubectl argv - prove namespace is k9b, not otel-demo
            cmd = mock_run.call_args.args[0]
            assert cmd == [
                "kubectl",
                "--kubeconfig", "/tmp/kubeconfig",
                "-n", "k9b",
                "get", "deployment",
                "k9b-scheduler",
                "-o", "json",
            ]

    def test_fails_gracefully_when_scheduler_not_in_wrong_namespace(self) -> None:
        """Prove lookup fails with useful error when scheduler not in target namespace.

        This is the exact failure mode from the live lab:
        'Failed to read deployment k9b-scheduler in namespace otel-demo'

        When someone passes incident_namespace="otel-demo" but scheduler is in "k9b",
        the function should fail gracefully (fall back to env or return False)
        rather than crash.
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            get_automatic_loop_enabled_with_reason,
        )

        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Ensure env var is NOT set (so fallback would return False)
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            with patch("subprocess.run") as mock_run:
                # kubectl returns "not found" because scheduler doesn't exist in otel-demo
                mock_run.return_value = type(
                    "MockResult",
                    (),
                    {
                        "returncode": 1,
                        "stderr": 'error: deployments.apps "k9b-scheduler" not found',
                    },
                )()

                # Call with wrong namespace (otel-demo) - this is the bug scenario
                enabled, result = get_automatic_loop_enabled_with_reason(
                    kubeconfig="/tmp/kubeconfig",
                    namespace="otel-demo",  # Wrong namespace - scheduler is in k9b
                    allow_env_fallback=False,  # Fail-closed
                )

                # Should fail gracefully
                assert enabled is False
                assert result.source == "error"
                # Should indicate the lookup failed
                assert result.reason in (
                    "automatic_loop_env_read_failed",
                    "automatic_loop_env_rbac_denied",
                )
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_k9b_namespace_can_be_overridden_via_parameter(self) -> None:
        """Prove namespace parameter allows overriding the default 'k9b' namespace.

        This is useful for testing or unusual deployments where k9b runs in
        a different namespace.
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            is_automatic_diagnosis_loop_enabled,
        )

        deployment_spec = _make_deployment_spec(
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", "true"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "MockResult",
                (),
                {"returncode": 0, "stdout": json.dumps(deployment_spec)},
            )()

            # Call with custom namespace
            result = is_automatic_diagnosis_loop_enabled(
                kubeconfig="/tmp/kubeconfig",
                namespace="k9b-custom",  # Custom namespace
            )

            assert result is True
            # Verify exact kubectl argv
            cmd = mock_run.call_args.args[0]
            assert "-n" in cmd
            ns_idx = cmd.index("-n") + 1
            assert cmd[ns_idx] == "k9b-custom"


class TestDefaultNamespaceResolution:
    """Tests for K9B_NAMESPACE environment variable resolution."""

    def test_get_default_k9b_namespace_returns_default_when_env_not_set(self) -> None:
        """Prove default namespace is 'k9b' when K9B_NAMESPACE is not set."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            get_default_k9b_namespace,
        )

        env_backup = os.environ.get("K9B_NAMESPACE")
        try:
            # Ensure env var is not set
            if "K9B_NAMESPACE" in os.environ:
                del os.environ["K9B_NAMESPACE"]

            result = get_default_k9b_namespace()
            assert result == "k9b"
        finally:
            if env_backup is not None:
                os.environ["K9B_NAMESPACE"] = env_backup

    def test_get_default_k9b_namespace_respects_env_var(self) -> None:
        """Prove K9B_NAMESPACE env var overrides the default."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            get_default_k9b_namespace,
        )

        env_backup = os.environ.get("K9B_NAMESPACE")
        try:
            os.environ["K9B_NAMESPACE"] = "k9b-custom-ns"

            result = get_default_k9b_namespace()
            assert result == "k9b-custom-ns"
        finally:
            if env_backup is not None:
                os.environ["K9B_NAMESPACE"] = env_backup
            elif "K9B_NAMESPACE" in os.environ:
                del os.environ["K9B_NAMESPACE"]

    def test_get_default_k9b_namespace_guards_against_blank_values(self) -> None:
        """Prove blank K9B_NAMESPACE falls back to default 'k9b'."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            get_default_k9b_namespace,
        )

        env_backup = os.environ.get("K9B_NAMESPACE")
        try:
            os.environ["K9B_NAMESPACE"] = "   "  # blank with whitespace

            result = get_default_k9b_namespace()
            assert result == "k9b"
        finally:
            if env_backup is not None:
                os.environ["K9B_NAMESPACE"] = env_backup
            elif "K9B_NAMESPACE" in os.environ:
                del os.environ["K9B_NAMESPACE"]


class TestP4cCallerPattern:
    """Regression tests for P4c caller-level namespace handling.

    These tests prove that when P4c-style callers invoke the gate,
    they use get_default_k9b_namespace() for scheduler lookup, NOT the incident namespace.

    This is the exact pattern that should be used by any code that:
    - Has access to incidents in various namespaces (e.g., otel-demo)
    - Needs to check if automatic diagnosis is enabled
    - Should look up the scheduler in the k9b control-plane namespace
    """

    def test_p4c_caller_uses_k9b_namespace_for_scheduler_gate_not_incident_namespace(
        self,
    ) -> None:
        """Prove P4c-style caller uses k9b namespace for scheduler, not incident namespace.

        This test reproduces the exact failure mode from the live lab:
        - Incident is in namespace "otel-demo"
        - k9b scheduler runs in namespace "k9b"
        - Caller should use get_default_k9b_namespace() to resolve "k9b"
        - NOT pass the incident namespace "otel-demo" to the gate
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            get_automatic_loop_enabled_with_reason,
            get_default_k9b_namespace,
        )

        deployment_spec = _make_deployment_spec(
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", "true"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "MockResult",
                (),
                {"returncode": 0, "stdout": json.dumps(deployment_spec)},
            )()

            # Simulate P4c-style caller:
            # - incident_namespace = "otel-demo" (for context)
            # - k9b_namespace = get_default_k9b_namespace() -> "k9b"
            # - Pass k9b_namespace to gate, NOT incident_namespace
            _incident_namespace = "otel-demo"  # noqa: F841 - documented for context
            k9b_namespace = get_default_k9b_namespace()

            # This is the correct pattern:
            # Use k9b_namespace for scheduler lookup, not incident_namespace
            result = get_automatic_loop_enabled_with_reason(
                kubeconfig="/tmp/kubeconfig",
                namespace=k9b_namespace,  # Correct: use k9b namespace
            )

            assert result[0] is True
            # Inspect actual kubectl command - prove namespace is k9b, not otel-demo
            cmd = mock_run.call_args.args[0]
            assert "-n" in cmd
            ns_idx = cmd.index("-n") + 1
            assert cmd[ns_idx] == "k9b"
            # Verify otel-demo is NOT in the command at all
            assert "otel-demo" not in cmd

    def test_incorrect_p4c_caller_pattern_fails_gracefully(self) -> None:
        """Prove incorrect pattern (passing incident namespace) fails gracefully.

        This documents the bug that should NOT be used:
        - Passing incident_namespace="otel-demo" to the gate
        - When scheduler is actually in "k9b" namespace
        - Should fail-closed (return False) rather than crash
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            get_automatic_loop_enabled_with_reason,
        )

        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Ensure env var is NOT set
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            with patch("subprocess.run") as mock_run:
                # kubectl returns "not found" because scheduler doesn't exist in otel-demo
                mock_run.return_value = type(
                    "MockResult",
                    (),
                    {
                        "returncode": 1,
                        "stderr": 'error: deployments.apps "k9b-scheduler" not found',
                    },
                )()

                # INCORRECT pattern: passing incident namespace
                enabled, check_result = get_automatic_loop_enabled_with_reason(
                    kubeconfig="/tmp/kubeconfig",
                    namespace="otel-demo",  # Wrong: incident namespace
                    allow_env_fallback=False,  # Fail-closed
                )

                # Should fail gracefully
                assert enabled is False
                assert check_result.source == "error"
                assert check_result.reason in (
                    "automatic_loop_env_read_failed",
                    "automatic_loop_env_rbac_denied",
                )
                # Verify the wrong namespace was actually used in the command
                cmd = mock_run.call_args.args[0]
                assert "-n" in cmd
                ns_idx = cmd.index("-n") + 1
                assert cmd[ns_idx] == "otel-demo"
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]
