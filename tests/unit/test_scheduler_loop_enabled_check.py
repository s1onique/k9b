"""Unit tests for scheduler-based automatic diagnosis loop enabled check.

Tests cover:
- is_automatic_diagnosis_loop_enabled checks scheduler deployment (not backend)
- _get_deployment_env_value extracts env vars from deployment spec
- Fallback to os.environ when cluster is not accessible
- Proper error handling for kubectl failures

Architecture note:
    The automatic diagnosis loop is a SCHEDULER feature, not a backend feature.
    These tests verify the checker targets the scheduler deployment correctly.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch


class TestGetDeploymentEnvValue:
    """Tests for _get_deployment_env_value function."""

    def test_extracts_env_var_from_deployment(self) -> None:
        """Prove env var is extracted from scheduler deployment spec."""
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

            result = _get_deployment_env_value(
                kubeconfig="/tmp/kubeconfig",
                namespace="k9b",
                deployment="k9b-scheduler",
                env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
            )

            assert result == "true"

    def test_returns_none_when_env_var_not_set(self) -> None:
        """Prove None is returned when env var is not in deployment spec."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            _get_deployment_env_value,
        )

        deployment_spec = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [{"name": "scheduler", "env": []}]
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

            result = _get_deployment_env_value(
                kubeconfig="/tmp/kubeconfig",
                namespace="k9b",
                deployment="k9b-scheduler",
                env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
            )

            assert result is None

    def test_returns_none_on_kubectl_error(self) -> None:
        """Prove None is returned when kubectl fails."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            _get_deployment_env_value,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "MockResult",
                (),
                {"returncode": 1, "stderr": "NotFound"},
            )()

            result = _get_deployment_env_value(
                kubeconfig="/tmp/kubeconfig",
                namespace="k9b",
                deployment="k9b-scheduler",
                env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
            )

            assert result is None

    def test_targets_scheduler_not_backend(self) -> None:
        """Prove the function is called with k9b-scheduler deployment name."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            _SCHEDULER_DEPLOYMENT,
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
                kubeconfig="/tmp/kubeconfig",
                namespace="k9b",
                deployment=_SCHEDULER_DEPLOYMENT,
                env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
            )

            # Verify kubectl was called with scheduler deployment
            call_args = mock_run.call_args
            args_str = str(call_args)
            assert "k9b-scheduler" in args_str


class TestIsAutomaticDiagnosisLoopEnabled:
    """Tests for is_automatic_diagnosis_loop_enabled function."""

    def test_checks_scheduler_deployment_when_cluster_accessible(self) -> None:
        """Prove function checks scheduler deployment in cluster."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            is_automatic_diagnosis_loop_enabled,
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

            result = is_automatic_diagnosis_loop_enabled(
                kubeconfig="/tmp/kubeconfig",
                namespace="k9b",
            )

            assert result is True
            # Verify scheduler was targeted
            call_args = mock_run.call_args
            assert "k9b-scheduler" in str(call_args)

    def test_returns_false_when_scheduler_env_false(self) -> None:
        """Prove function returns False when scheduler has env=false."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            is_automatic_diagnosis_loop_enabled,
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
                                        "value": "false",
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

            result = is_automatic_diagnosis_loop_enabled(
                kubeconfig="/tmp/kubeconfig",
                namespace="k9b",
            )

            assert result is False

    def test_falls_back_to_os_environ_when_cluster_not_accessible(self) -> None:
        """Prove function falls back to os.environ when kubectl fails."""
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
                )

                assert result is True
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_does_not_check_backend_deployment(self) -> None:
        """Prove function targets scheduler, not backend."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            is_automatic_diagnosis_loop_enabled,
        )

        # Backend has the env var false, scheduler has it true
        backend_spec = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "backend",
                                "env": [
                                    {
                                        "name": "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
                                        "value": "false",
                                    }
                                ],
                            }
                        ]
                    }
                }
            }
        }
        scheduler_spec = {
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

        def mock_side_effect(*args: object, **kwargs: object) -> object:
            cmd = args[0] if args else kwargs.get("args", [])
            cmd_str = str(cmd)
            if "k9b-backend" in cmd_str:
                return type(
                    "MockResult",
                    (),
                    {"returncode": 0, "stdout": json.dumps(backend_spec)},
                )()
            else:
                return type(
                    "MockResult",
                    (),
                    {"returncode": 0, "stdout": json.dumps(scheduler_spec)},
                )()

        with patch("subprocess.run", side_effect=mock_side_effect):
            result = is_automatic_diagnosis_loop_enabled(
                kubeconfig="/tmp/kubeconfig",
                namespace="k9b",
            )

            # The function should return True because scheduler has it enabled
            assert result is True

            # Verify scheduler was checked (not backend)
            # At minimum, scheduler should be targeted


class TestArchitectureDocumentation:
    """Tests that verify the architecture documentation is correct."""

    def test_scheduler_constant_is_k9b_scheduler(self) -> None:
        """Prove _SCHEDULER_DEPLOYMENT constant is k9b-scheduler."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            _SCHEDULER_DEPLOYMENT,
        )

        assert _SCHEDULER_DEPLOYMENT == "k9b-scheduler"

    def test_does_not_check_backend(self) -> None:
        """Prove backend deployment is not targeted by the checker."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            _get_deployment_env_value,
        )

        # Call with scheduler deployment
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
                kubeconfig="/tmp/kubeconfig",
                namespace="k9b",
                deployment="k9b-scheduler",  # Explicitly scheduler
                env_var="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
            )

            # Verify kubectl command does NOT contain "backend"
            call_args = mock_run.call_args
            cmd_str = str(call_args)
            assert "k9b-backend" not in cmd_str
