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

    Security Policy:
    - Path containment is validated using Path.relative_to()
    - Traversal/escape attempts fall back to index.html (SPA behavior)
    - No attacker-targeted file is served
    - No absolute host paths leak in responses

    Args:
        handler: The HealthUIRequestHandler instance
        route: The request path
    """
    target = route or "/"
    if target.endswith("/"):
        target += "index.html"

    static_root = handler.static_dir.resolve()
    candidate = (static_root / target.lstrip("/")).resolve()

    # Validate containment using Path.relative_to() - safe containment check
    # This correctly rejects sibling directories (e.g., /tmp/static-evil vs /tmp/static)
    # and traversal/escape attempts where resolved path is outside static_root
    try:
        candidate.relative_to(static_root)
    except ValueError:
        candidate = static_root / "index.html"

    if not candidate.exists():
        candidate = static_root / "index.html"

    if not candidate.exists():
        handler._send_text(404, "Static assets unavailable")
        return

    send_file(handler, candidate)


def serve_artifact(handler: HealthUIRequestHandler, query: str) -> None:
    """Serve artifact files from the runs directory.

    Security Policy:
    - Symlink artifacts are REJECTED (no following symlinks)
    - Only regular files under runs_dir are served
    - Path containment is validated using Path.relative_to()
    - Error responses do not leak absolute host paths

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

    # Reject hostile path components after query parsing and before filesystem access.
    if _contains_hostile_components(requested_relative):
        log_artifact_request(handler, requested_relative, None, None, "hostile-path", 400)
        handler._send_text(400, "Invalid artifact path")
        return

    try:
        candidate = handler.runs_dir / requested
    except Exception:  # pragma: no cover - defensive guard
        log_artifact_request(handler, requested_relative, None, None, "invalid-path", 400)
        handler._send_text(400, "Invalid artifact path")
        return

    # CRITICAL: Check if the candidate is a symlink and reject it entirely.
    # Symlinks inside runs_dir can point outside runs_dir, creating an escape.
    # This is the preferred policy: reject symlink artifacts with no exceptions.
    if candidate.is_symlink():
        log_artifact_request(handler, requested_relative, None, None, "symlink-rejected", 400)
        handler._send_text(400, "Invalid artifact path")
        return

    # Resolve both paths for final containment validation
    # This handles cases where runs_dir itself is a symlink
    try:
        root_resolved = handler.runs_dir.resolve()
    except Exception:
        log_artifact_request(handler, requested_relative, None, None, "root-resolve-error", 500)
        handler._send_text(500, "Unable to access artifact root")
        return

    try:
        artifact_resolved = candidate.resolve()
    except Exception:
        log_artifact_request(handler, requested_relative, None, None, "resolve-error", 400)
        handler._send_text(400, "Invalid artifact path")
        return

    # Validate containment using Path.relative_to() - safe containment check
    # This correctly rejects sibling directories (e.g., /tmp/root-evil vs /tmp/root)
    # and symlink escapes where resolved path is outside root
    try:
        artifact_resolved.relative_to(root_resolved)
    except ValueError:
        log_artifact_request(
            handler, requested_relative, str(artifact_resolved), str(root_resolved),
            "path-escape-attempt", 403
        )
        handler._send_text(403, "Access denied")
        return

    # Verify the final artifact is a regular file
    if not artifact_resolved.is_file():
        log_artifact_request(
            handler, requested_relative, str(artifact_resolved), str(root_resolved),
            "not-regular-file", 404
        )
        handler._send_text(404, "Artifact not found")
        return

    status = "success"
    if artifact_resolved.suffix.lower() == ".zip":
        try:
            artifact_bytes = artifact_resolved.read_bytes()
        except OSError:
            log_artifact_request(
                handler, requested_relative, str(artifact_resolved), str(root_resolved),
                "read-error", 500
            )
            handler._send_text(500, "Unable to read artifact")
            return
        handler.send_response(200)
        handler.send_header("Content-Type", "application/zip")
        handler.send_header("Content-Length", str(len(artifact_bytes)))
        handler.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{artifact_resolved.name}\"",
        )
        handler.end_headers()
        handler.wfile.write(artifact_bytes)
        log_artifact_request(
            handler, requested_relative, str(artifact_resolved), str(root_resolved),
            status, 200
        )
        return
    try:
        payload = artifact_resolved.read_text(encoding="utf-8")
    except OSError:
        log_artifact_request(
            handler, requested_relative, str(artifact_resolved), str(root_resolved),
            "read-error", 500
        )
        handler._send_text(500, "Unable to read artifact")
        return
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.end_headers()
    handler.wfile.write(payload.encode("utf-8"))
    log_artifact_request(
        handler, requested_relative, str(artifact_resolved), str(root_resolved),
        status, 200
    )


def _contains_hostile_components(path: str) -> bool:
    """Check for hostile path components after query parsing.

    The caller is expected to pass the decoded query parameter value returned
    by parse_qs(). This function rejects traversal, absolute paths, null bytes,
    and Windows-style absolute path forms before filesystem access.

    Args:
        path: The decoded path string to check

    Returns:
        True if the path contains hostile components, False otherwise
    """
    # Null byte check
    if "\x00" in path:
        return True

    # Absolute path check
    if path.startswith("/") or path.startswith("\\"):
        return True

    # Windows drive letter check
    if len(path) >= 2 and path[1] == ":":
        return True

    # UNC path check
    if path.startswith("\\\\"):
        return True

    # Path traversal check (.. components)
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        return True

    return False


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
