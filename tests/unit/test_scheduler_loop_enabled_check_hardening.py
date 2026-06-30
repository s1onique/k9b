"""Hardening tests for scheduler-based automatic diagnosis loop enabled check.

These tests cover:
- kubeconfig flag handling (only include when non-empty)
- allow_env_fallback parameter behavior for fail-closed live-lab mode

Architecture note:
    The automatic diagnosis loop is a SCHEDULER feature, not a backend feature.
    These tests verify the checker handles edge cases correctly for live-lab deployment.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch


class TestKubeconfigFlagHandling:
    """Tests for kubeconfig flag handling in kubectl commands."""

    def test_omits_kubeconfig_flag_when_kubeconfig_is_none(self) -> None:
        """Prove --kubeconfig flag is not included when kubeconfig is None."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            _get_deployment_env_value,
        )

        deployment_spec = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "scheduler",
                                "env": [
                                    {
                                        "name": "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
                                        "value": "true",
                                    }
                                ],
                            }
                        ]
                    }
                }
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "MockResult",
                (),
                {"returncode": 0, "stdout": json.dumps(deployment_spec)},
            )()

            _get_deployment_env_value(
                kubeconfig=None,  # Explicitly None
                namespace="k9b",
                deployment="k9b-scheduler",
                env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
            )

            # Verify --kubeconfig flag is NOT in the command
            call_args = mock_run.call_args
            cmd_list = call_args[0][0]  # First positional arg is the cmd list
            assert "--kubeconfig" not in cmd_list

    def test_includes_kubeconfig_flag_when_kubeconfig_is_set(self) -> None:
        """Prove --kubeconfig flag is included when kubeconfig path is provided."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            _get_deployment_env_value,
        )

        deployment_spec = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "scheduler",
                                "env": [
                                    {
                                        "name": "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
                                        "value": "true",
                                    }
                                ],
                            }
                        ]
                    }
                }
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "MockResult",
                (),
                {"returncode": 0, "stdout": json.dumps(deployment_spec)},
            )()

            _get_deployment_env_value(
                kubeconfig="/path/to/kubeconfig",
                namespace="k9b",
                deployment="k9b-scheduler",
                env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
            )

            # Verify --kubeconfig flag IS in the command
            call_args = mock_run.call_args
            cmd_list = call_args[0][0]  # First positional arg is the cmd list
            assert "--kubeconfig" in cmd_list
            # Verify it comes before the path
            kubeconfig_idx = cmd_list.index("--kubeconfig")
            assert kubeconfig_idx + 1 < len(cmd_list)
            assert cmd_list[kubeconfig_idx + 1] == "/path/to/kubeconfig"


class TestAllowEnvFallback:
    """Tests for allow_env_fallback parameter behavior."""

    def test_returns_false_when_cluster_unreachable_and_fallback_disabled(self) -> None:
        """Prove function returns False when cluster unreachable and allow_env_fallback=False."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            is_automatic_diagnosis_loop_enabled,
        )

        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Set env var to true - but this should NOT be used
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            with patch("subprocess.run") as mock_run:
                # kubectl fails
                mock_run.return_value = type(
                    "MockResult",
                    (),
                    {"returncode": 1, "stderr": "connection refused"},
                )()

                result = is_automatic_diagnosis_loop_enabled(
                    kubeconfig="/tmp/kubeconfig",
                    namespace="k9b",
                    allow_env_fallback=False,
                )

                # Should return False (fail-closed) instead of using env
                assert result is False
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_returns_true_from_env_when_cluster_unreachable_and_fallback_enabled(
        self,
    ) -> None:
        """Prove function falls back to env when cluster unreachable and allow_env_fallback=True."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            is_automatic_diagnosis_loop_enabled,
        )

        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Set env var to true
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            with patch("subprocess.run") as mock_run:
                # kubectl fails
                mock_run.return_value = type(
                    "MockResult",
                    (),
                    {"returncode": 1, "stderr": "connection refused"},
                )()

                result = is_automatic_diagnosis_loop_enabled(
                    kubeconfig="/tmp/kubeconfig",
                    namespace="k9b",
                    allow_env_fallback=True,
                )

                # Should return True (uses env fallback)
                assert result is True
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_uses_cluster_when_accessible_regardless_of_fallback_setting(
        self,
    ) -> None:
        """Prove cluster value is used when accessible, regardless of allow_env_fallback."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            is_automatic_diagnosis_loop_enabled,
        )

        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Set env var to false (should be ignored)
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "false"

            deployment_spec = {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "scheduler",
                                    "env": [
                                        {
                                            "name": "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
                                            "value": "true",  # Cluster has true
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                }
            }

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = type(
                    "MockResult",
                    (),
                    {"returncode": 0, "stdout": json.dumps(deployment_spec)},
                )()

                # Even with allow_env_fallback=False, cluster value should be used
                result = is_automatic_diagnosis_loop_enabled(
                    kubeconfig="/tmp/kubeconfig",
                    namespace="k9b",
                    allow_env_fallback=False,
                )

                # Should return True from cluster, not False from env
                assert result is True
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]
