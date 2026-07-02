"""Shared helpers for OpenAPI contract tests.

This module provides utilities for loading, normalizing, and comparing
OpenAPI specs and routes across multiple test modules.
"""

from __future__ import annotations

import re
from pathlib import Path

# Root of the repository
REPO_ROOT = Path(__file__).resolve().parents[2]


def normalize_path_for_comparison(path: str) -> str:
    """Normalize a path to its template form for comparison.

    Examples:
        /api/incidents/abc123 -> /api/incidents/{incident_id}
        /api/runs/xyz/alertmanager-sources/foo/action -> /api/runs/{run_id}/alertmanager-sources/{source_id}/action
    """
    # Simple normalization: replace UUID-like segments with {param}
    segments = path.split("/")
    normalized = []
    for i, seg in enumerate(segments):
        if seg and seg not in (
            "api",
            "incidents",
            "runs",
            "alertmanager-sources",
            "diagnosis-loop",
            "automatic-diagnosis-loop",
            "automatic-diagnosis-review",
            "handoff",
            "one-pass",
            "review-packet",
            "snapshot",
        ):
            # Check if it looks like an ID (UUID, base64, hash)
            if len(seg) >= 8 and re.match(r"^[a-zA-Z0-9_-]+$", seg):
                # Determine param name from context
                if i > 0 and segments[i - 1] == "incidents":
                    normalized.append("{incident_id}")
                elif i > 0 and segments[i - 1] == "runs":
                    normalized.append("{run_id}")
                elif i > 0 and segments[i - 1] == "alertmanager-sources":
                    normalized.append("{source_id}")
                else:
                    normalized.append("{id}")
            else:
                normalized.append(seg)
        else:
            normalized.append(seg)

    return "/".join(normalized)


def discover_routes_from_source() -> set[tuple[str, str]]:
    """Discover all /api/* routes from server source code.

    This performs static analysis to find route patterns. It looks for:
    - Exact route matches: if route == "/api/path"
    - Prefix matching: route.startswith("/api/incidents")
    - Regex patterns: re.compile(r"^/api/...")

    Returns:
        Set of (method_lower, path) tuples for all routes in the codebase.
    """
    routes: set[tuple[str, str]] = set()
    server_dir = REPO_ROOT / "src" / "k8s_diag_agent" / "ui"

    # Walk all server Python files
    for py_file in server_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue  # Skip __pycache__, __init__, etc.
        if py_file.name == "api_contract.py":
            continue  # Skip this file
        if py_file.name == "api_openapi.py":
            continue  # Skip openapi handlers
        if py_file.name == "api_contract_types.py":
            continue  # Skip types
        if py_file.name.startswith("api_routes_"):
            continue  # Skip route registry files

        content = py_file.read_text()

        # Find exact route matches - scan line by line for route comparisons
        for line in content.split("\n"):
            route_match = re.search(r'route\s*==\s*"(/api/[^"]+)"', line)
            if not route_match:
                continue

            path = route_match.group(1)

            # Look at surrounding lines to determine method
            # Default to GET, but upgrade to POST if we see a handler pattern
            method = "get"

            # Check context: POST handlers typically import or call with "handle_" pattern
            lines = content.split("\n")
            current_line_idx = content[:content.find(line)].count("\n")

            # Check if we're in a do_POST or similar context
            context_start = max(0, current_line_idx - 20)
            context_end = min(len(lines), current_line_idx + 3)
            context = "\n".join(lines[context_start:context_end])

            # If we find POST handler patterns in context, it's POST
            if "do_POST" in context or "handle_" in line:
                # Further check: some routes are both GET and POST
                if py_file.name == "server_feedback.py":
                    method = "post"
                elif "POST" in context or "post" in context.lower():
                    method = "post"

            routes.add((method, path))

        # Find incident routes that use prefix matching
        if 'route.startswith("/api/incidents")' in content:
            # Incident routes use pattern matching for detail and handoff
            routes.add(("get", "/api/incidents"))
            routes.add(("get", "/api/incidents/{incident_id}"))
            routes.add(("get", "/api/incidents/{incident_id}/automatic-diagnosis-review/handoff"))

    # Add pattern-based routes
    pattern_routes = _extract_pattern_routes(server_dir)
    routes.update(pattern_routes)

    return routes


def _extract_pattern_routes(server_dir: Path) -> set[tuple[str, str]]:
    """Extract routes from regex patterns in server files.

    Scans for PATTERN definitions and extracts the path templates.
    """
    routes: set[tuple[str, str]] = set()

    for py_file in server_dir.glob("*.py"):
        content = py_file.read_text()

        # Find pattern definitions
        # Example: _INCIDENT_DIAGNOSIS_LOOP_PATTERN = re.compile(
        #     r"^/api/incidents/([^/]+)/diagnosis-loop/one-pass$"
        # )
        pattern_matches = re.finditer(
            r"(_PATTERN|_INCIDENT|_RUN)\s*=\s*re\.compile\(\s*r?['\"](\^?/api/[^\"']+)['\"]",
            content,
        )
        for match in pattern_matches:
            path_template = match.group(2).lstrip("^")

            # Convert regex to path template with proper param names
            # First pass: convert [^/]+ groups with context-aware param names
            segments = path_template.split("/")
            for i, seg in enumerate(segments):
                if "[^/]+" in seg:
                    # Determine param name from context
                    if "automatic-diagnosis-review" in path_template:
                        param_name = "incident_id"
                    elif "diagnosis-loop" in path_template:
                        param_name = "incident_id"
                    elif "automatic-diagnosis-loop" in path_template:
                        param_name = "incident_id"
                    elif "one-pass-diagnosis" in path_template:
                        param_name = "incident_id"
                    elif "alertmanager-sources" in seg:
                        param_name = "source_id"
                    else:
                        param_name = "incident_id"
                    # Replace the regex group with {param_name}
                    path_template = path_template.replace("[^/]+", "{" + param_name + "}", 1)

            if "/api/incidents" in path_template and "{incident_id}" in path_template:
                routes.add(("POST", path_template.replace("$", "")))
            elif "/api/runs" in path_template:
                routes.add(("POST", path_template.replace("$", "")))

    return routes


# Paths that are intentionally not documented (internal endpoints)
INTENTIONALLY_UNDOCUMENTED: set[tuple[str, str]] = {
    # OpenAPI spec/docs endpoints - these ARE documented but serve the spec itself
    ("GET", "/api/openapi.json"),
    ("GET", "/api/docs"),
}
