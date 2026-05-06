"""Tests for AUTH-01/02: explicit unsafe-bind protection.

Tests that non-loopback binding requires explicit --unsafe-bind flag
to prevent accidental exposure of the k9b UI/API mutation endpoints.
"""
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

from k8s_diag_agent.ui.server import _SAFE_LOOPBACK_HOSTS, _is_exposed_host, start_ui_server


class TestIsExposedHost(unittest.TestCase):
    """Tests for the _is_exposed_host helper function."""

    def test_loopback_ipv4_is_safe(self) -> None:
        """127.0.0.1 should not be considered exposed."""
        self.assertFalse(_is_exposed_host("127.0.0.1"))

    def test_loopback_localhost_is_safe(self) -> None:
        """localhost should not be considered exposed."""
        self.assertFalse(_is_exposed_host("localhost"))

    def test_loopback_ipv6_is_safe(self) -> None:
        """::1 (IPv6 loopback) should not be considered exposed."""
        self.assertFalse(_is_exposed_host("::1"))

    def test_all_interfaces_ipv4_is_exposed(self) -> None:
        """0.0.0.0 should be considered exposed."""
        self.assertTrue(_is_exposed_host("0.0.0.0"))

    def test_all_interfaces_ipv6_is_exposed(self) -> None:
        """:: (IPv6 all interfaces) should be considered exposed."""
        self.assertTrue(_is_exposed_host("::"))

    def test_external_ip_is_exposed(self) -> None:
        """External IPs should be considered exposed."""
        self.assertTrue(_is_exposed_host("192.168.1.100"))
        self.assertTrue(_is_exposed_host("10.0.0.5"))
        self.assertTrue(_is_exposed_host("172.16.0.1"))

    def test_hostname_is_exposed(self) -> None:
        """Non-loopback hostnames should be considered exposed."""
        self.assertTrue(_is_exposed_host("my-hostname"))
        self.assertTrue(_is_exposed_host("cluster.example.com"))

    def test_hostname_case_insensitive(self) -> None:
        """localhost should be case-insensitive."""
        self.assertFalse(_is_exposed_host("LOCALHOST"))
        self.assertFalse(_is_exposed_host("Localhost"))

    def test_safe_loopback_hosts_defined_correctly(self) -> None:
        """Verify the safe loopback hosts constant."""
        self.assertEqual(_SAFE_LOOPBACK_HOSTS, frozenset({"127.0.0.1", "localhost", "::1"}))


class TestStartUIServerUnsafeBind(unittest.TestCase):
    """Tests for start_ui_server with unsafe_bind protection."""

    def setUp(self) -> None:
        self.tmpdir = Path("/tmp/test_unsafe_bind")
        self.tmpdir.mkdir(exist_ok=True)
        # Create minimal health directory structure
        self.health_dir = self.tmpdir / "health"
        self.health_dir.mkdir(exist_ok=True)

    def test_loopback_ipv4_no_unsafe_flag_starts(self) -> None:
        """Server starts on 127.0.0.1 without --unsafe-bind."""
        # This should not raise SystemExit
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", new_callable=io.StringIO):
                with mock.patch(
                    "k8s_diag_agent.ui.server.ThreadingHTTPServer"
                ) as _mock_server:
                    # Should start without error
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="127.0.0.1",
                        port=8080,
                        unsafe_bind=False,
                    )

    def test_localhost_no_unsafe_flag_starts(self) -> None:
        """Server starts on localhost without --unsafe-bind."""
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", new_callable=io.StringIO):
                with mock.patch(
                    "k8s_diag_agent.ui.server.ThreadingHTTPServer"
                ) as _mock_server:
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="localhost",
                        port=8080,
                        unsafe_bind=False,
                    )

    def test_loopback_ipv6_no_unsafe_flag_starts(self) -> None:
        """Server starts on ::1 without --unsafe-bind."""
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", new_callable=io.StringIO):
                with mock.patch(
                    "k8s_diag_agent.ui.server.ThreadingHTTPServer"
                ) as _mock_server:
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="::1",
                        port=8080,
                        unsafe_bind=False,
                    )

    def test_all_interfaces_without_unsafe_flag_rejected(self) -> None:
        """Server refuses to start on 0.0.0.0 without --unsafe-bind."""
        stderr_output = io.StringIO()
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", stderr_output):
                with self.assertRaises(SystemExit) as context:
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="0.0.0.0",
                        port=8080,
                        unsafe_bind=False,
                    )

        self.assertEqual(context.exception.code, 1)
        stderr_text = stderr_output.getvalue()
        self.assertIn("ERROR: Refusing to bind to exposed address '0.0.0.0' without --unsafe-bind", stderr_text)
        self.assertIn("mutation endpoints", stderr_text)
        self.assertIn("--unsafe-bind", stderr_text)

    def test_ipv6_all_interfaces_without_unsafe_flag_rejected(self) -> None:
        """Server refuses to start on :: without --unsafe-bind."""
        stderr_output = io.StringIO()
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", stderr_output):
                with self.assertRaises(SystemExit) as context:
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="::",
                        port=8080,
                        unsafe_bind=False,
                    )

        self.assertEqual(context.exception.code, 1)
        stderr_text = stderr_output.getvalue()
        self.assertIn("ERROR: Refusing to bind to exposed address '::' without --unsafe-bind", stderr_text)
        self.assertIn("mutation endpoints", stderr_text)
        self.assertIn("--unsafe-bind", stderr_text)

    def test_external_ip_without_unsafe_flag_rejected(self) -> None:
        """Server refuses to start on external IP without --unsafe-bind."""
        stderr_output = io.StringIO()
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", stderr_output):
                with self.assertRaises(SystemExit) as context:
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="192.168.1.100",
                        port=8080,
                        unsafe_bind=False,
                    )

        self.assertEqual(context.exception.code, 1)
        stderr_text = stderr_output.getvalue()
        self.assertIn("ERROR: Refusing to bind to exposed address '192.168.1.100' without --unsafe-bind", stderr_text)

    def test_all_interfaces_with_unsafe_flag_warns(self) -> None:
        """Server starts on 0.0.0.0 with --unsafe-bind but prints warning."""
        stderr_output = io.StringIO()
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", stderr_output):
                with mock.patch(
                    "k8s_diag_agent.ui.server.ThreadingHTTPServer"
                ) as _mock_server:
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="0.0.0.0",
                        port=8080,
                        unsafe_bind=True,
                    )

        stderr_text = stderr_output.getvalue()
        self.assertIn("WARNING: Starting operator UI on exposed address '0.0.0.0:8080'", stderr_text)
        self.assertIn("mutation endpoints", stderr_text)
        self.assertIn("trusted networks", stderr_text)

    def test_ipv6_all_interfaces_with_unsafe_flag_warns(self) -> None:
        """Server starts on :: with --unsafe-bind but prints warning."""
        stderr_output = io.StringIO()
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", stderr_output):
                with mock.patch(
                    "k8s_diag_agent.ui.server.ThreadingHTTPServer"
                ) as _mock_server:
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="::",
                        port=8080,
                        unsafe_bind=True,
                    )

        stderr_text = stderr_output.getvalue()
        # IPv6 address :: with port 8080 may be rendered as :::8080 or ::8080 depending on context
        self.assertIn("WARNING: Starting operator UI on exposed address '::", stderr_text)
        self.assertIn("8080'", stderr_text)
        self.assertIn("mutation endpoints", stderr_text)

    def test_external_ip_with_unsafe_flag_warns(self) -> None:
        """Server starts on external IP with --unsafe-bind but prints warning."""
        stderr_output = io.StringIO()
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", stderr_output):
                with mock.patch(
                    "k8s_diag_agent.ui.server.ThreadingHTTPServer"
                ) as _mock_server:
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="192.168.1.100",
                        port=8080,
                        unsafe_bind=True,
                    )

        stderr_text = stderr_output.getvalue()
        self.assertIn("WARNING: Starting operator UI on exposed address '192.168.1.100:8080'", stderr_text)
        self.assertIn("mutation endpoints", stderr_text)
        self.assertIn("trusted networks", stderr_text)

    def test_error_message_mentions_port_forwarding_alternative(self) -> None:
        """Error message suggests port-forwarding as safer alternative."""
        stderr_output = io.StringIO()
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", stderr_output):
                with self.assertRaises(SystemExit):
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="0.0.0.0",
                        port=8080,
                        unsafe_bind=False,
                    )

        stderr_text = stderr_output.getvalue()
        self.assertIn("port-forwarding", stderr_text)
        self.assertIn("127.0.0.1", stderr_text)
        self.assertIn("localhost", stderr_text)
        self.assertIn("::1", stderr_text)

    def test_error_message_mentions_mutation_endpoints(self) -> None:
        """Error message specifically mentions mutation endpoints."""
        stderr_output = io.StringIO()
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(sys, "stderr", stderr_output):
                with self.assertRaises(SystemExit):
                    start_ui_server(
                        runs_dir=self.health_dir,
                        host="0.0.0.0",
                        port=8080,
                        unsafe_bind=False,
                    )

        stderr_text = stderr_output.getvalue()
        # Should mention specific mutation endpoint paths
        self.assertIn("/api/next-check-approval", stderr_text)
        self.assertIn("/api/next-check-execution", stderr_text)
        self.assertIn("/api/deterministic-next-check/promote", stderr_text)


class TestCLIParserUnsafeBind(unittest.TestCase):
    """Tests for CLI parser handling of --unsafe-bind flag."""

    def test_health_ui_parser_has_unsafe_bind_flag(self) -> None:
        """Verify the health-ui subcommand has --unsafe-bind argument."""
        from k8s_diag_agent.cli import build_parser

        parser = build_parser()
        # Parse health-ui with --unsafe-bind
        args = parser.parse_args(["health-ui", "--host", "0.0.0.0", "--unsafe-bind"])
        self.assertTrue(args.unsafe_bind)
        self.assertEqual(args.command, "health-ui")
        self.assertEqual(args.host, "0.0.0.0")

    def test_health_ui_parser_unsafe_bind_defaults_false(self) -> None:
        """Verify --unsafe-bind defaults to False."""
        from k8s_diag_agent.cli import build_parser

        parser = build_parser()
        # Parse health-ui without --unsafe-bind
        args = parser.parse_args(["health-ui"])
        self.assertFalse(args.unsafe_bind)

    def test_unsafe_bind_with_loopback_is_accepted(self) -> None:
        """--unsafe-bind flag is accepted even with loopback (no-op but valid)."""
        from k8s_diag_agent.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["health-ui", "--host", "127.0.0.1", "--unsafe-bind"])
        self.assertTrue(args.unsafe_bind)
        self.assertEqual(args.host, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()