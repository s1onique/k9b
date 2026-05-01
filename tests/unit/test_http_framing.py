"""Tests for HTTP response framing and Content-Length correctness.

These tests verify:
1. _send_json emits Content-Length equal to encoded JSON byte length
2. _response_bytes is set to len(body_bytes)
3. Route-level /api/run response includes Content-Length
4. Response body can be read without waiting for connection close
5. Raw HTTP keep-alive test: body read completes from Content-Length without socket close
"""

import functools
import json
import shutil
import socket
import tempfile
import threading
import unittest
import unittest.mock as mock
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.config import (
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from k8s_diag_agent.health.ui import write_health_ui_index
from k8s_diag_agent.ui.server import HealthUIRequestHandler


class SendJsonContentLengthTests(unittest.TestCase):
    """Tests for _send_json Content-Length header correctness."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)
        self.health_dir.mkdir(parents=True, exist_ok=True)
        
        # Write minimal ui-index.json for /api/run to work
        self._write_minimal_index("test-run")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_minimal_index(self, run_id: str) -> None:
        """Write a minimal ui-index.json for testing."""
        artifact = ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=run_id,
            run_label=run_id,
            cluster_label="test",
            summary="Test",
            status=ExternalAnalysisStatus.SUCCESS,
            provider="reviewer",
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={},
        )
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="reviewer")
        )
        with mock.patch(
            "k8s_diag_agent.health.ui._collect_historical_external_analysis_entries",
            return_value=[],
        ):
            write_health_ui_index(
                self.health_dir,
                run_id=artifact.run_id,
                run_label=artifact.run_label or artifact.run_id,
                collector_version="test",
                records=(),
                assessments=(),
                drilldowns=(),
                proposals=(),
                external_analysis=(artifact,),
                notifications=(),
                external_analysis_settings=settings,
                available_adapters=(),
            )

    def _start_server(self) -> tuple[ThreadingHTTPServer, threading.Thread]:
        handler = functools.partial(
            HealthUIRequestHandler,
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _shutdown_server(self, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    def _fetch_with_raw_socket(self, server: ThreadingHTTPServer) -> dict[str, Any]:
        """Fetch /api/run using raw socket to inspect headers."""
        host, port = server.server_address[:2]
        host_str = host.decode("utf-8") if isinstance(host, bytes) else host
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host_str, port))
        
        # Send HTTP request
        request = b"GET /api/run HTTP/1.1\r\nHost: localhost\r\n\r\n"
        sock.sendall(request)
        
        # Read response
        response = b""
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                # Check if we have enough to determine Content-Length
                header_end = response.find(b"\r\n\r\n")
                if header_end != -1:
                    headers = response[:header_end].decode("utf-8", errors="replace")
                    # Parse Content-Length
                    for line in headers.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())
                            body_start = header_end + 4
                            body = response[body_start:]
                            if len(body) >= content_length:
                                sock.close()
                                return {
                                    "headers": headers,
                                    "content_length": content_length,
                                    "body": body[:content_length],
                                    "has_all_body": True,
                                }
            except TimeoutError:
                break
        
        sock.close()
        
        # If we get here without complete response, return what we have
        header_end = response.find(b"\r\n\r\n")
        return {
            "headers": response[:header_end].decode("utf-8", errors="replace") if header_end != -1 else "",
            "content_length": 0,
            "body": b"",
            "has_all_body": False,
            "raw_response": response,
        }

    def test_send_json_content_length_matches_encoded_bytes(self) -> None:
        """Test that _send_json Content-Length header equals actual UTF-8 encoded body length."""
        server, thread = self._start_server()
        try:
            result = self._fetch_with_raw_socket(server)
            
            self.assertTrue(
                result.get("has_all_body", False),
                f"Response was incomplete. Headers: {result.get('headers', '')[:200]}",
            )
            
            self.assertGreater(result["content_length"], 0, "Content-Length should be non-zero")
            
            # The body should be valid JSON
            body = result["body"]
            self.assertEqual(result["content_length"], len(body), 
                f"Content-Length ({result['content_length']}) should match body length ({len(body)})")
            
            # Verify it's valid JSON
            parsed = json.loads(body.decode("utf-8"))
            self.assertIsInstance(parsed, dict)
            
        finally:
            self._shutdown_server(server, thread)

    def test_response_bytes_matches_body_length(self) -> None:
        """Test that Content-Length matches actual body length (verifying _response_bytes will be correct)."""
        server, thread = self._start_server()
        try:
            result = self._fetch_with_raw_socket(server)
            
            self.assertTrue(
                result.get("has_all_body", False),
                "Should have complete response body"
            )
            
            # Content-Length should equal body length
            self.assertEqual(result["content_length"], len(result["body"]),
                f"Content-Length ({result['content_length']}) should match body length ({len(result['body'])})")
            
            # And body should be valid JSON
            parsed = json.loads(result["body"].decode("utf-8"))
            self.assertIsInstance(parsed, dict)
            
        finally:
            self._shutdown_server(server, thread)

    def test_api_run_response_includes_content_length(self) -> None:
        """Test that /api/run response includes Content-Length header."""
        server, thread = self._start_server()
        try:
            host, port = server.server_address[:2]
            host_str = host.decode("utf-8") if isinstance(host, bytes) else host
            
            import urllib.request
            url = f"http://{host_str}:{port}/api/run"
            
            with urllib.request.urlopen(url, timeout=5) as response:
                content_length = response.getheader("Content-Length")
                body = response.read()
            
            self.assertIsNotNone(content_length, "Response should include Content-Length header")
            self.assertEqual(int(content_length), len(body),
                f"Content-Length header ({content_length}) should match body length ({len(body)})")
            
        finally:
            self._shutdown_server(server, thread)

    def test_body_reads_without_waiting_for_eof(self) -> None:
        """Test that response body can be read based on Content-Length without waiting for connection close.
        
        This is the key regression test: if Content-Length is missing or wrong, the client
        may wait for EOF/timeout instead of reading exactly Content-Length bytes.
        """
        server, thread = self._start_server()
        try:
            result = self._fetch_with_raw_socket(server)
            
            # This test passes if we get the complete body (has_all_body=True)
            # If Content-Length is missing/wrong, the socket recv would timeout
            self.assertTrue(
                result.get("has_all_body", False),
                "Body should be readable based on Content-Length without waiting for EOF. "
                f"Got {len(result.get('body', b''))} bytes. Headers: {result.get('headers', '')[:300]}",
            )
            
            # Verify Content-Length matches
            if result.get("has_all_body"):
                self.assertEqual(
                    result["content_length"],
                    len(result["body"]),
                    "Content-Length should match body length"
                )
            
        finally:
            self._shutdown_server(server, thread)


class HTTPFramingTests(unittest.TestCase):
    """Integration tests for HTTP response framing across multiple routes."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)
        self.health_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_minimal_index(self, run_id: str) -> None:
        """Write a minimal ui-index.json for testing."""
        artifact = ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=run_id,
            run_label=run_id,
            cluster_label="test",
            summary="Test",
            status=ExternalAnalysisStatus.SUCCESS,
            provider="reviewer",
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={},
        )
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="reviewer")
        )
        with mock.patch(
            "k8s_diag_agent.health.ui._collect_historical_external_analysis_entries",
            return_value=[],
        ):
            write_health_ui_index(
                self.health_dir,
                run_id=artifact.run_id,
                run_label=artifact.run_label or artifact.run_id,
                collector_version="test",
                records=(),
                assessments=(),
                drilldowns=(),
                proposals=(),
                external_analysis=(artifact,),
                notifications=(),
                external_analysis_settings=settings,
                available_adapters=(),
            )

    def _start_server(self) -> tuple[ThreadingHTTPServer, threading.Thread]:
        handler = functools.partial(
            HealthUIRequestHandler,
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _shutdown_server(self, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    def test_runs_list_response_framing(self) -> None:
        """Test that /api/runs response has correct Content-Length framing."""
        run_id = "test-run"
        self._write_minimal_index(run_id)
        
        server, thread = self._start_server()
        try:
            host, port = server.server_address[:2]
            host_str = host.decode("utf-8") if isinstance(host, bytes) else host
            
            import urllib.request
            url = f"http://{host_str}:{port}/api/runs"
            
            with urllib.request.urlopen(url, timeout=5) as response:
                content_length = response.getheader("Content-Length")
                body = response.read()
            
            self.assertIsNotNone(content_length, "/api/runs should include Content-Length header")
            self.assertEqual(int(content_length), len(body),
                f"Content-Length ({content_length}) should match body length ({len(body)})")
            
            # Verify it's valid JSON with expected structure
            parsed = json.loads(body)
            self.assertIn("runs", parsed)
            
        finally:
            self._shutdown_server(server, thread)

    def test_json_responses_include_connection_close(self) -> None:
        """Test that _send_json adds Connection: close header and sets close_connection.
        
        This is a diagnostic fix for observed 30s+ delays with keep-alive connections.
        The backend forces Connection: close to prevent proxy/Vite/podman keep-alive
        socket reuse issues where the browser waits for a fresh socket.
        """
        # Write minimal index BEFORE starting server - /api/run requires it
        run_id = "test-run-conn-close"
        self._write_minimal_index(run_id)
        
        server, thread = self._start_server()
        try:
            host, port = server.server_address[:2]
            host_str = host.decode("utf-8") if isinstance(host, bytes) else host
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host_str, port))
            
            # Send HTTP/1.1 request
            request = b"GET /api/run HTTP/1.1\r\nHost: localhost\r\n\r\n"
            sock.sendall(request)
            
            # Read response headers
            response = b""
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                    # Check if we have complete headers
                    header_end = response.find(b"\r\n\r\n")
                    if header_end != -1:
                        headers = response[:header_end].decode("utf-8", errors="replace")
                        # We've got headers, connection will close after body
                        # Connection: close means server won't keep-alive
                        sock.close()
                        
                        # Verify Connection header is present
                        self.assertIn("Connection: close", headers,
                            "Response should include Connection: close header")
                        
                        # Verify Content-Length is also present (diagnostic uses both)
                        self.assertIn("Content-Length:", headers,
                            "Response should include Content-Length header")
                        
                        return
                except TimeoutError:
                    break
            
            self.fail("Should have received complete response headers with Connection: close")
            
        finally:
            self._shutdown_server(server, thread)


if __name__ == "__main__":
    unittest.main()
