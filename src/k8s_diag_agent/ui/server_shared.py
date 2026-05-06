"""Shared path utilities for the UI server.

This module contains pure/shared helpers extracted from server.py to enable
incremental modularization. These helpers are self-contained and do not
depend on request-handler instance state.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)

# Default maximum content length for JSON mutation requests (1 MiB)
DEFAULT_MAX_CONTENT_LENGTH = 1 * 1024 * 1024


def _validate_json_mutation_request(
    handler: HealthUIRequestHandler,
    max_content_length: int = DEFAULT_MAX_CONTENT_LENGTH,
) -> dict[str, object] | None:
    """Validate Content-Type and request size for JSON mutation requests.

    This shared helper provides consistent validation for all mutation endpoints:
    - Validates Content-Type is application/json (or application/json with charset)
    - Enforces max Content-Length to prevent oversized payloads
    - Returns the parsed JSON payload if validation passes
    - Sends appropriate HTTP error responses (400, 413, 415) on failure

    Args:
        handler: The HealthUIRequestHandler instance
        max_content_length: Maximum allowed Content-Length in bytes (default 1 MiB)

    Returns:
        Parsed JSON payload dict if validation passes, None if validation failed
        (in which case the handler has already sent an error response)
    """
    # Validate Content-Type header
    content_type = handler.headers.get("Content-Type", "")
    # Normalize: strip parameters (e.g., charset) and lowercase for comparison
    if content_type:
        # Extract just the media type before any semicolon
        base_content_type = content_type.split(";")[0].strip().lower()
    else:
        base_content_type = ""

    # Require Content-Type to be application/json with optional charset parameter
    # Reject text/plain, form-urlencoded, multipart, or missing/empty content type
    if base_content_type not in ("application/json",):
        handler._send_json(
            {"error": "Content-Type must be application/json"},
            415,  # Unsupported Media Type
        )
        return None

    # Handle Content-Length
    content_length_str = handler.headers.get("Content-Length", "")
    try:
        content_length = int(content_length_str) if content_length_str else 0
    except ValueError:
        # Invalid Content-Length header - treat as missing/zero
        content_length = 0

    # Check for empty request body on POST endpoints
    if content_length <= 0:
        handler._send_json({"error": "Request body required"}, 400)
        return None

    # Enforce max Content-Length
    if content_length > max_content_length:
        handler._send_json(
            {"error": f"Request body too large (max {max_content_length} bytes)"},
            413,  # Payload Too Large
        )
        return None

    # Read and parse the request body
    try:
        raw_payload = handler.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
        return None

    # Ensure payload is a dict (not array, number, string, etc.)
    if not isinstance(payload, dict):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
        return None

    return payload


def _normalize_runs_dir(runs_dir: Path) -> Path:
    """Normalize runs_dir to the canonical parent directory.

    The canonical runs_dir can be either:
    - 'runs' (parent directory) - UI internally accesses runs/health/ subdirectory
    - 'runs/health' (leaf directory) - directly contains health artifacts

    This function detects which form is being used and normalizes appropriately.
    If user passes runs/health (where artifacts actually live), keep it.
    If user passes runs (parent), keep it.
    If runs/health is empty (no artifacts), normalize to parent runs.

    Args:
        runs_dir: The runs directory as provided by the user

    Returns:
        Normalized runs directory (either parent or leaf)
    """
    resolved = runs_dir.resolve()

    # Check if runs_dir itself is the health directory (e.g., runs/health)
    if resolved.name == "health":
        # Check if this directory itself contains health artifacts
        # (external-analysis, assessments, drilldowns are directly here)
        if any(
            (resolved / subdir).exists()
            for subdir in ["external-analysis", "assessments", "drilldowns"]
        ):
            logger.debug(
                "Kept runs_dir as health leaf directory",
                extra={"input": str(runs_dir), "resolved": str(resolved)},
            )
            return resolved

        # No artifacts in runs/health - normalize to parent runs
        parent = resolved.parent
        logger.debug(
            "Normalized runs_dir from leaf to parent",
            extra={"input": str(runs_dir), "normalized": str(parent)},
        )
        return parent

    # Check if runs_dir has a 'health' subdirectory with artifacts
    health_dir = resolved / "health"
    if health_dir.exists() and any(
        (health_dir / subdir).exists()
        for subdir in ["external-analysis", "assessments", "drilldowns"]
    ):
        logger.debug(
            "Kept runs_dir as parent (has health subdirectory)",
            extra={"input": str(runs_dir), "resolved": str(resolved)},
        )
        return resolved

    return resolved


def _validate_runs_dir(runs_dir: Path) -> None:
    """Validate that runs_dir has the expected structure.

    The canonical runs_dir should have a 'health' subdirectory (or be empty
    if no runs have been executed yet).

    Raises:
        ValueError: If runs_dir appears misconfigured
    """
    resolved = runs_dir.resolve()
    health_subdir = resolved / "health"

    # If neither the parent nor health subdir exists, warn but don't fail
    # This allows fresh startup before any health runs have been executed
    if not resolved.exists() and not health_subdir.exists():
        logger.warning(
            "runs_dir does not exist and may not have been initialized",
            extra={"runs_dir": str(resolved)},
        )
        return

    # If runs/health exists, this is the expected canonical structure
    if health_subdir.exists():
        return

    # Check if user passed runs/health directly (doubled-path bug symptom)
    if resolved.exists() and any(resolved.iterdir()):
        # runs/ exists but no health subdir - might be misconfigured
        logger.warning(
            "runs_dir may be misconfigured: expected parent 'runs' with 'health' subdirectory",
            extra={"runs_dir": str(resolved)},
        )


def _compute_health_root(runs_dir: Path) -> Path:
    """Compute the health root directory for artifact resolution.

    The health root is where artifact-backed source of truth lives:
    - If runs_dir is the parent (e.g., 'runs'), health_root = runs_dir / 'health'
    - If runs_dir is already the health leaf (e.g., 'runs/health'), health_root = runs_dir

    This distinction is critical because plan artifacts (external-analysis/*-next-check-plan.json)
    live under runs/health/external-analysis/, not directly under runs/external-analysis/.

    Args:
        runs_dir: The normalized runs directory

    Returns:
        The health root path for artifact resolution
    """
    resolved = runs_dir.resolve()

    # If runs_dir itself is the health directory, it's already the health root
    if resolved.name == "health":
        return resolved

    # Otherwise, compute health_root as runs_dir / "health"
    health_root = resolved / "health"

    # If health directory exists, use it; otherwise fall back to runs_dir
    # (allows operation before first health run completes)
    if health_root.exists():
        return health_root

    # Fall back to runs_dir if health doesn't exist yet
    return resolved
