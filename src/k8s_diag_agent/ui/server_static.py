"""Static file and artifact serving logic for the UI server.

This module contains the read-only static/artifact-serving family extracted from
server.py. Functions here accept the request handler instance as an argument.

Keep all behavior consistent: no URL changes, no MIME/content-type changes,
no path-security changes, no HTTP status code changes.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler


def serve_static(handler: HealthUIRequestHandler, route: str) -> None:
    """Serve static files from the frontend dist directory.

    Args:
        handler: The HealthUIRequestHandler instance
        route: The request path
    """
    target = route or "/"
    if target.endswith("/"):
        target += "index.html"
    candidate = (handler.static_dir / target.lstrip("/")).resolve()
    static_root = handler.static_dir.resolve()
    if not str(candidate).startswith(str(static_root)) or not candidate.exists():
        candidate = static_root / "index.html"
        if not candidate.exists():
            handler._send_text(404, "Static assets unavailable")
            return
    send_file(handler, candidate)


def serve_artifact(handler: HealthUIRequestHandler, query: str) -> None:
    """Serve artifact files from the runs directory.

    Args:
        handler: The HealthUIRequestHandler instance
        query: The query string containing the artifact path
    """
    params = parse_qs(query)
    paths = params.get("path")
    if not paths:
        handler._send_text(400, "Artifact path required")
        return
    requested = Path(paths[0])
    requested_relative = str(requested)
    try:
        artifact_path = (handler.runs_dir / requested).resolve()
    except Exception:  # pragma: no cover - defensive guard
        log_artifact_request(handler, requested_relative, None, None, "invalid-path", 400)
        handler._send_text(400, "Invalid artifact path")
        return
    root_resolved = handler.runs_dir.resolve()
    normalized_path = str(artifact_path)
    within_allowed_root = normalized_path.startswith(str(root_resolved))
    if not within_allowed_root:
        log_artifact_request(
            handler, requested_relative, normalized_path, str(root_resolved),
            "path-escape-attempt", 400
        )
        handler._send_text(400, "Invalid artifact path")
        return
    exists = artifact_path.exists()
    if not exists:
        log_artifact_request(
            handler, requested_relative, normalized_path, str(root_resolved),
            "not-found", 404
        )
        handler._send_text(404, "Artifact not found")
        return
    status = "success"
    if artifact_path.suffix.lower() == ".zip":
        try:
            artifact_bytes = artifact_path.read_bytes()
        except OSError as exc:
            log_artifact_request(
                handler, requested_relative, normalized_path, str(root_resolved),
                "read-error", 500
            )
            handler._send_text(500, f"Unable to read artifact: {exc}")
            return
        handler.send_response(200)
        handler.send_header("Content-Type", "application/zip")
        handler.send_header("Content-Length", str(len(artifact_bytes)))
        handler.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{artifact_path.name}\"",
        )
        handler.end_headers()
        handler.wfile.write(artifact_bytes)
        log_artifact_request(
            handler, requested_relative, normalized_path, str(root_resolved),
            status, 200
        )
        return
    try:
        payload = artifact_path.read_text(encoding="utf-8")
    except OSError as exc:
        log_artifact_request(
            handler, requested_relative, normalized_path, str(root_resolved),
            "read-error", 500
        )
        handler._send_text(500, f"Unable to read artifact: {exc}")
        return
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.end_headers()
    handler.wfile.write(payload.encode("utf-8"))
    log_artifact_request(
        handler, requested_relative, normalized_path, str(root_resolved),
        status, 200
    )


def log_artifact_request(
    handler: HealthUIRequestHandler,
    requested_relative: str,
    normalized_absolute: str | None,
    runs_root: str | None,
    result: str,
    status_code: int,
) -> None:
    """Log structured information about artifact download requests.

    Args:
        handler: The HealthUIRequestHandler instance
        requested_relative: The relative path requested by the client
        normalized_absolute: The resolved absolute path
        runs_root: The runs root directory
        result: The result status string
        status_code: The HTTP status code
    """
    from ..structured_logging import emit_structured_log

    emit_structured_log(
        component="artifact-download",
        message="Artifact download request",
        severity="INFO" if status_code < 400 else "WARNING",
        run_label="",
        run_id="",
        metadata={
            "requested_relative_path": requested_relative,
            "normalized_absolute_path": normalized_absolute,
            "runs_root": runs_root,
            "health_root": str(Path(runs_root) / "health") if runs_root else None,
            "exists": normalized_absolute and Path(normalized_absolute).exists() if normalized_absolute else False,
            "within_allowed_root": normalized_absolute and runs_root and normalized_absolute.startswith(runs_root) if (normalized_absolute and runs_root) else False,
            "result": result,
            "status_code": status_code,
        },
    )


def send_file(handler: HealthUIRequestHandler, path: Path) -> None:
    """Send a file as the HTTP response.

    Args:
        handler: The HealthUIRequestHandler instance
        path: The path to the file to send
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        handler._send_text(500, f"Unable to read asset: {exc}")
        return
    content_type, _ = mimetypes.guess_type(path.name)
    handler.send_response(200)
    handler.send_header("Content-Type", content_type or "application/octet-stream")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
