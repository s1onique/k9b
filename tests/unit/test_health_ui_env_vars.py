"""Tests for K9B_UI_HOST/K9B_UI_PORT/K9B_UI_TOKEN env var configuration.

Regression tests ensuring that Kubernetes deployment environment variables
correctly override CLI defaults for the health-ui backend server binding.
"""
import argparse
import os
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


class TestHandleHealthUIEnvVars(unittest.TestCase):
    """Tests for K9B_UI_HOST/K9B_UI_PORT env var configuration in handle_health_ui."""

    def setUp(self) -> None:
        self.tmpdir = Path("/tmp/test_env_vars")
        self.tmpdir.mkdir(exist_ok=True)
        self.health_dir = self.tmpdir / "health"
        self.health_dir.mkdir(exist_ok=True)
        # Clear any existing env vars that might interfere
        self._orig_env = {
            "K9B_UI_HOST": os.environ.get("K9B_UI_HOST"),
            "K9B_UI_PORT": os.environ.get("K9B_UI_PORT"),
            "K9B_UI_TOKEN": os.environ.get("K9B_UI_TOKEN"),
        }
        for key in ("K9B_UI_HOST", "K9B_UI_PORT", "K9B_UI_TOKEN"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        # Restore original env vars
        for key, val in self._orig_env.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    def test_env_var_k9b_ui_host_overrides_cli_arg(self) -> None:
        """K9B_UI_HOST env var should take precedence over --host CLI arg."""
        from k8s_diag_agent.cli_handlers import handle_health_ui

        # Set env var
        os.environ["K9B_UI_HOST"] = "0.0.0.0"

        # Create mock args with different host value
        args = argparse.Namespace(
            runs_dir=self.health_dir,
            host="127.0.0.1",  # CLI default - should be overridden
            port=8080,
            unsafe_bind=True,
            auth_token=None,
        )

        captured_host = None
        captured_port = None

        def mock_start_ui_server(runs_dir: Any, host: Any, port: Any, unsafe_bind: Any, auth_token: Any) -> None:
            nonlocal captured_host, captured_port
            captured_host = host
            captured_port = port

        with mock.patch(
            "k8s_diag_agent.cli_handlers.start_ui_server", side_effect=mock_start_ui_server
        ):
            handle_health_ui(args)

        # Env var should win
        self.assertEqual(captured_host, "0.0.0.0")
        self.assertEqual(captured_port, 8080)

    def test_env_var_k9b_ui_port_overrides_cli_arg(self) -> None:
        """K9B_UI_PORT env var should take precedence over --port CLI arg."""
        from k8s_diag_agent.cli_handlers import handle_health_ui

        # Set env var
        os.environ["K9B_UI_PORT"] = "9090"

        # Create mock args with different port value
        args = argparse.Namespace(
            runs_dir=self.health_dir,
            host="127.0.0.1",
            port=8080,  # CLI default - should be overridden
            unsafe_bind=True,
            auth_token=None,
        )

        captured_host = None
        captured_port = None

        def mock_start_ui_server(runs_dir: Any, host: Any, port: Any, unsafe_bind: Any, auth_token: Any) -> None:
            nonlocal captured_host, captured_port
            captured_host = host
            captured_port = port

        with mock.patch(
            "k8s_diag_agent.cli_handlers.start_ui_server", side_effect=mock_start_ui_server
        ):
            handle_health_ui(args)

        # Env var should win
        self.assertEqual(captured_host, "127.0.0.1")
        self.assertEqual(captured_port, 9090)

    def test_cli_args_used_when_no_env_vars(self) -> None:
        """When no env vars are set, CLI args should be used directly."""
        from k8s_diag_agent.cli_handlers import handle_health_ui

        # No env vars set (already cleared in setUp)
        args = argparse.Namespace(
            runs_dir=self.health_dir,
            host="127.0.0.1",
            port=8080,
            unsafe_bind=False,
            auth_token=None,
        )

        captured_host = None
        captured_port = None

        def mock_start_ui_server(runs_dir: Any, host: Any, port: Any, unsafe_bind: Any, auth_token: Any) -> None:
            nonlocal captured_host, captured_port
            captured_host = host
            captured_port = port

        with mock.patch(
            "k8s_diag_agent.cli_handlers.start_ui_server", side_effect=mock_start_ui_server
        ):
            handle_health_ui(args)

        # CLI args should be used
        self.assertEqual(captured_host, "127.0.0.1")
        self.assertEqual(captured_port, 8080)

    def test_env_vars_kubernetes_defaults(self) -> None:
        """Simulate Kubernetes deployment: env vars set to 0.0.0.0:8080."""
        from k8s_diag_agent.cli_handlers import handle_health_ui

        # Kubernetes sets these env vars
        os.environ["K9B_UI_HOST"] = "0.0.0.0"
        os.environ["K9B_UI_PORT"] = "8080"

        # CLI args have local defaults
        args = argparse.Namespace(
            runs_dir=self.health_dir,
            host="127.0.0.1",  # local dev default
            port=8080,
            unsafe_bind=True,
            auth_token=None,
        )

        captured_host = None
        captured_port = None

        def mock_start_ui_server(runs_dir: Any, host: Any, port: Any, unsafe_bind: Any, auth_token: Any) -> None:
            nonlocal captured_host, captured_port
            captured_host = host
            captured_port = port

        with mock.patch(
            "k8s_diag_agent.cli_handlers.start_ui_server", side_effect=mock_start_ui_server
        ):
            handle_health_ui(args)

        # Kubernetes env vars should win
        self.assertEqual(captured_host, "0.0.0.0")
        self.assertEqual(captured_port, 8080)

    def test_k9b_ui_token_env_var_used(self) -> None:
        """K9B_UI_TOKEN env var should be used when auth_token is not set."""
        from k8s_diag_agent.cli_handlers import handle_health_ui

        os.environ["K9B_UI_TOKEN"] = "secret-token-from-env"

        args = argparse.Namespace(
            runs_dir=self.health_dir,
            host="127.0.0.1",
            port=8080,
            unsafe_bind=True,
            auth_token=None,  # CLI arg not set
        )

        captured_auth_token = None

        def mock_start_ui_server(runs_dir: Any, host: Any, port: Any, unsafe_bind: Any, auth_token: Any) -> None:
            nonlocal captured_auth_token
            captured_auth_token = auth_token

        with mock.patch(
            "k8s_diag_agent.cli_handlers.start_ui_server", side_effect=mock_start_ui_server
        ):
            handle_health_ui(args)

        # Env var token should be used
        self.assertEqual(captured_auth_token, "secret-token-from-env")

    def test_cli_auth_token_takes_precedence_over_env_var(self) -> None:
        """CLI --auth-token arg should take precedence over K9B_UI_TOKEN env var."""
        from k8s_diag_agent.cli_handlers import handle_health_ui

        os.environ["K9B_UI_TOKEN"] = "env-token"

        args = argparse.Namespace(
            runs_dir=self.health_dir,
            host="127.0.0.1",
            port=8080,
            unsafe_bind=True,
            auth_token="cli-token",  # CLI arg set - should win
        )

        captured_auth_token = None

        def mock_start_ui_server(runs_dir: Any, host: Any, port: Any, unsafe_bind: Any, auth_token: Any) -> None:
            nonlocal captured_auth_token
            captured_auth_token = auth_token

        with mock.patch(
            "k8s_diag_agent.cli_handlers.start_ui_server", side_effect=mock_start_ui_server
        ):
            handle_health_ui(args)

        # CLI arg should win over env var
        self.assertEqual(captured_auth_token, "cli-token")


if __name__ == "__main__":
    unittest.main()
