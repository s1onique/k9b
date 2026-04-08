"""HTTP server that serves the new UI assets and read model endpoints."""

from __future__ import annotations

import functools
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .api import (
    build_cluster_detail_payload,
    build_fleet_payload,
    build_proposals_payload,
    build_run_payload,
)
from .model import UIIndexContext, build_ui_context, load_ui_index
from .notifications import query_notifications

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STATIC_DIR = PROJECT_ROOT / "frontend" / "dist"


def start_ui_server(
    runs_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    static_dir: Path | None = None,
) -> None:
    assets = static_dir or DEFAULT_STATIC_DIR
    handler = functools.partial(HealthUIRequestHandler, runs_dir=runs_dir, static_dir=assets)
    server = ThreadingHTTPServer((host, port), handler)
    print(
        f"Operator UI listening on http://{host}:{port}/ (runs: {runs_dir}, assets: {assets})",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down operator UI server", file=sys.stderr)
        server.shutdown()
    finally:
        server.server_close()


class HealthUIRequestHandler(BaseHTTPRequestHandler):
    server_version = "HealthUI/2.0"

    def __init__(self, *args: object, runs_dir: Path, static_dir: Path, **kwargs: object) -> None:
        self.runs_dir = runs_dir
        self.static_dir = static_dir
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def do_GET(self) -> None:
        route, _, query = self.path.partition("?")
        if route.startswith("/api/"):
            self._handle_api(route, query)
        elif route == "/artifact":
            self._serve_artifact(query)
        else:
            self._serve_static(route)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_api(self, route: str, query: str) -> None:
        context = self._load_context()
        if context is None:
            return
        if route == "/api/run":
            self._send_json(build_run_payload(context))
            return
        if route == "/api/fleet":
            self._send_json(build_fleet_payload(context))
            return
        if route == "/api/proposals":
            self._send_json(build_proposals_payload(context))
            return
        if route == "/api/notifications":
            params = parse_qs(query)
            payload = query_notifications(
                self.runs_dir,
                kind=params.get("kind", [None])[0],
                cluster_label=params.get("cluster_label", [None])[0],
                search=params.get("search", [None])[0],
                limit=self._parse_limit(params.get("limit", [None])[0]),
                page=self._parse_page(params.get("page", [None])[0]),
            )
            self._send_json(payload)
            return
        if route == "/api/cluster-detail":
            params = parse_qs(query)
            label = params.get("cluster_label", [None])[0]
            self._send_json(build_cluster_detail_payload(context, cluster_label=label))
            return
        self._send_text(404, "Not Found")

    def _serve_static(self, route: str) -> None:
        target = route or "/"
        if target.endswith("/"):
            target += "index.html"
        candidate = (self.static_dir / target.lstrip("/")).resolve()
        static_root = self.static_dir.resolve()
        if not str(candidate).startswith(str(static_root)) or not candidate.exists():
            candidate = static_root / "index.html"
            if not candidate.exists():
                self._send_text(404, "Static assets unavailable")
                return
        self._send_file(candidate)

    def _serve_artifact(self, query: str) -> None:
        params = parse_qs(query)
        paths = params.get("path")
        if not paths:
            self._send_text(400, "Artifact path required")
            return
        requested = Path(paths[0])
        try:
            artifact_path = (self.runs_dir / requested).resolve()
        except Exception:  # pragma: no cover - defensive guard
            self._send_text(400, "Invalid artifact path")
            return
        root_resolved = self.runs_dir.resolve()
        if not str(artifact_path).startswith(str(root_resolved)):
            self._send_text(400, "Invalid artifact path")
            return
        if not artifact_path.exists():
            self._send_text(404, "Artifact not found")
            return
        try:
            payload = artifact_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._send_text(500, f"Unable to read artifact: {exc}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(payload.encode("utf-8"))

    def _load_context(self) -> UIIndexContext | None:
        try:
            index = load_ui_index(self.runs_dir)
            return build_ui_context(index)
        except Exception as exc:  # pragma: no cover - read-model may be malformed
            self._send_text(500, f"Unable to read ui-index.json: {exc}")
            return None

    def _parse_limit(self, value: str | None) -> int | None:
        if not value:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    def _parse_page(self, value: str | None) -> int:
        parsed = self._parse_limit(value)
        return parsed if parsed else 1

    def _send_json(self, body: object) -> None:
        payload = json.dumps(body, ensure_ascii=False)
        encoded = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError as exc:
            self._send_text(500, f"Unable to read asset: {exc}")
            return
        content_type, _ = mimetypes.guess_type(path.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, code: int, message: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))
