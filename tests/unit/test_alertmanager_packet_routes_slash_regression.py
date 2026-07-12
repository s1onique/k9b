"""HTTP regression tests for slash-containing sourceId on Alertmanager packet routes.

These tests guard the migration that moved ``{source_id}`` out of the URL
path: identifiers like ``crd:monitoring.coreos.com/v1/Alertmanager/example``
contain ``/`` and would otherwise be parsed as multiple path segments by
Starlette (``[^/]+`` regex), returning 404 before any handler runs.

The packet routes now carry the identifier either in the required
``sourceId`` query parameter (GET routes) or in the JSON request body
(POST probe). These tests assert:

* A request with a slash-containing sourceId is NOT 404 (the route is
  found and reaches the dispatcher).
* A request that omits sourceId is rejected with a validation response
  (400), never a silent 200 or 404.

Sibling module: ``tests/unit/test_alertmanager_packet_routes.py`` holds the
pure-registry contract tests for the same routes.

Run with: python -m pytest tests/unit/test_alertmanager_packet_routes_slash_regression.py -v
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from tests.helpers.ui_test_harness import (
    shutdown_test_server,
    start_ui_test_server_without_auth,
)


class TestAlertmanagerPacketRouteSlashRegression(unittest.TestCase):
    """HTTP regression tests for slash-containing sourceId on packet routes."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp()).resolve()
        self.runs_dir = self.tmpdir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = "test-run-slash-source-id"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _host_port(self, server: ThreadingHTTPServer) -> tuple[str, int]:
        address = server.server_address
        host_address, port, *_ = address
        host: str = host_address.decode("utf-8") if isinstance(host_address, bytes) else str(host_address)
        return host, port

    def _request_status(
        self,
        url: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> int:
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return int(response.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)

    def _start_server(
        self,
    ) -> tuple[ThreadingHTTPServer, threading.Thread, object]:
        return start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )

    def test_debug_packet_slash_source_id_in_query_routes(self) -> None:
        """GET debug-packet with slash sourceId in required query param must not 404."""
        source_id = "crd:monitoring.coreos.com/v1/Alertmanager/example"
        server, thread, patcher = self._start_server()
        try:
            host, port = self._host_port(server)
            encoded = urllib.parse.quote(source_id, safe="")
            url = (
                f"http://{host}:{port}/api/runs/{self.run_id}"
                f"/alertmanager-sources/debug-packet?sourceId={encoded}"
            )
            status = self._request_status(url, method="GET")
            self.assertNotEqual(
                status,
                404,
                "Slash-containing sourceId in query must not produce 404 from URL routing",
            )
        finally:
            shutdown_test_server(server, thread, patcher)

    def test_debug_packet_missing_source_id_returns_400(self) -> None:
        """GET debug-packet without sourceId must be rejected with 400, not 404.

        The route must be reached (so no 404) and must validate the required
        ``sourceId`` query parameter explicitly (so 400, not silent 200).
        """
        server, thread, patcher = self._start_server()
        try:
            host, port = self._host_port(server)
            url = (
                f"http://{host}:{port}/api/runs/{self.run_id}"
                f"/alertmanager-sources/debug-packet"
            )
            status = self._request_status(url, method="GET")
            self.assertNotEqual(
                status,
                404,
                "Route must be reached even when sourceId is missing",
            )
            self.assertEqual(
                status,
                400,
                "Missing sourceId query parameter must be rejected with 400",
            )
        finally:
            shutdown_test_server(server, thread, patcher)

    def test_debug_packet_probe_slash_source_id_in_body_routes(self) -> None:
        """POST probe with slash sourceId in JSON body must not 404."""
        source_id = "service:monitoring/kube-prometheus-stack"
        server, thread, patcher = self._start_server()
        try:
            host, port = self._host_port(server)
            url = (
                f"http://{host}:{port}/api/runs/{self.run_id}"
                f"/alertmanager-sources/debug-packet/probe"
            )
            body = json.dumps({"sourceId": source_id}).encode("utf-8")
            status = self._request_status(
                url,
                method="POST",
                body=body,
                headers={"Content-Type": "application/json"},
            )
            self.assertNotEqual(
                status,
                404,
                "Slash-containing sourceId in probe body must not produce 404",
            )
        finally:
            shutdown_test_server(server, thread, patcher)

    def test_debug_packet_probe_missing_source_id_returns_400(self) -> None:
        """POST probe without sourceId in body must be rejected with 400."""
        server, thread, patcher = self._start_server()
        try:
            host, port = self._host_port(server)
            url = (
                f"http://{host}:{port}/api/runs/{self.run_id}"
                f"/alertmanager-sources/debug-packet/probe"
            )
            body = json.dumps({}).encode("utf-8")
            status = self._request_status(
                url,
                method="POST",
                body=body,
                headers={"Content-Type": "application/json"},
            )
            self.assertNotEqual(
                status,
                404,
                "Probe route must be reached even when sourceId is missing",
            )
            self.assertEqual(
                status,
                400,
                "Missing sourceId in probe body must be rejected with 400",
            )
        finally:
            shutdown_test_server(server, thread, patcher)

    def test_promotion_review_slash_source_id_in_query_routes(self) -> None:
        """GET promotion-review with slash sourceId in query param must not 404."""
        source_id = "crd:monitoring.coreos.com/v1/Alertmanager/example"
        server, thread, patcher = self._start_server()
        try:
            host, port = self._host_port(server)
            encoded = urllib.parse.quote(source_id, safe="")
            url = (
                f"http://{host}:{port}/api/runs/{self.run_id}"
                f"/alertmanager-sources/promotion-review?sourceId={encoded}"
            )
            status = self._request_status(url, method="GET")
            self.assertNotEqual(
                status,
                404,
                "Slash-containing sourceId in promotion-review must not produce 404",
            )
        finally:
            shutdown_test_server(server, thread, patcher)

    def test_promotion_review_missing_source_id_returns_400(self) -> None:
        """GET promotion-review without sourceId must be rejected with 400."""
        server, thread, patcher = self._start_server()
        try:
            host, port = self._host_port(server)
            url = (
                f"http://{host}:{port}/api/runs/{self.run_id}"
                f"/alertmanager-sources/promotion-review"
            )
            status = self._request_status(url, method="GET")
            self.assertNotEqual(
                status,
                404,
                "Promotion-review route must be reached even when sourceId is missing",
            )
            self.assertEqual(
                status,
                400,
                "Missing sourceId in promotion-review must be rejected with 400",
            )
        finally:
            shutdown_test_server(server, thread, patcher)


if __name__ == "__main__":
    unittest.main()
