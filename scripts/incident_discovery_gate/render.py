"""Render functions for incident discovery gate.

Provides artifact writing and bounded summary rendering for incident discovery results.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .types import IncidentDiscoveryResult

# Patterns for sensitive data to redact in logs
_SENSITIVE_PATTERNS = [
    # API keys and tokens
    (re.compile(r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-]{8,})', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(token["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-\.]{8,})', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(bearer\s+)([a-zA-Z0-9_\-\.]+)', re.IGNORECASE), r'\1[REDACTED]'),
    # Provider-specific keys
    (re.compile(r'(openai[_\-]?api[_\-]?key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-]{8,})', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(anthropic[_\-]?api[_\-]?key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-]{8,})', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(azure[_\-]?openai[_\-]?key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-]{8,})', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(gigachat[_\-]?api[_\-]?key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-]{8,})', re.IGNORECASE), r'\1[REDACTED]'),
    # Authorization headers
    (re.compile(r'(authorization["\']?\s*[:=]\s*["\']?)([^"\s,\n]+)', re.IGNORECASE), r'\1[REDACTED]'),
    # Provider URLs that might contain sensitive info
    (re.compile(r'https?://[^@\s]+:[^@\s]+@', re.IGNORECASE), r'https://[REDACTED_USER]:[REDACTED_PASS]@'),
]


def sanitize_logs_for_artifacts(logs: str) -> str:
    """Sanitize sensitive data from logs before artifact writing.

    Args:
        logs: Raw log content

    Returns:
        Sanitized log content with sensitive patterns redacted
    """
    if not logs:
        return logs

    sanitized = logs
    for pattern, replacement in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def write_all_artifacts(
    discovery_dir: Path,
    result: IncidentDiscoveryResult,
    backend_logs: str,
    scheduler_logs: str,
) -> None:
    """Write all artifacts for incident discovery gate.

    Args:
        discovery_dir: Final artifact directory for incident discovery.
                     Caller is responsible for constructing the correct path.
        result: Incident discovery result
        backend_logs: Backend logs (will be sanitized)
        scheduler_logs: Scheduler logs (will be sanitized)
    """
    # discovery_dir is the final directory - do NOT append anything
    discovery_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize logs before writing
    backend_logs = sanitize_logs_for_artifacts(backend_logs)
    scheduler_logs = sanitize_logs_for_artifacts(scheduler_logs)

    # Write main result JSON
    result_path = discovery_dir / "incident-discovery-result.json"
    result_path.write_text(json.dumps(result.to_dict(), indent=2))

    # Write bounded summary
    summary_path = discovery_dir / "bounded-summary.txt"
    summary_path.write_text(render_bounded_summary(result))

    # Write diagnostics snapshot
    if result.diagnostics:
        diag_path = discovery_dir / "diagnostics.json"
        diag_path.write_text(json.dumps(result.diagnostics, indent=2))

    # Write backend logs (sanitized)
    if backend_logs:
        logs_path = discovery_dir / "backend-logs.txt"
        # Only write last 200 lines to keep bounded
        lines = backend_logs.strip().split("\n")
        logs_path.write_text("\n".join(lines[-200:]))

    # Write scheduler logs (sanitized)
    if scheduler_logs:
        sched_logs_path = discovery_dir / "scheduler-logs.txt"
        lines = scheduler_logs.strip().split("\n")
        sched_logs_path.write_text("\n".join(lines[-200:]))


def render_bounded_summary(result: IncidentDiscoveryResult) -> str:
    """Render bounded summary for incident discovery.

    Args:
        result: Incident discovery result

    Returns:
        Formatted summary string
    """
    lines = [
        "=== Incident Discovery Gate Result ===",
        f"Status: {'PASSED' if result.passed else 'FAILED'}",
        f"Failure class: {result.failure_class or '(none)'}",
        "",
        "--- Timing ---",
        f"Polls: {result.poll_count}",
        f"Total elapsed: {result.total_elapsed_seconds:.1f}s",
        "",
        "--- Fixture Status ---",
        f"Name: {result.fixture_name or '(none)'}",
        f"Namespace: {result.fixture_namespace or '(none)'}",
        f"Exists: {result.fixture_exists}",
        f"Phase: {result.fixture_phase or '(unknown)'}",
        f"Is healthy: {result.fixture_is_healthy}",
        "",
        "--- Candidate Detection ---",
        f"Detected: {result.candidate_detected}",
        f"Type: {result.candidate_type or '(none)'}",
        "",
        "--- API Response ---",
    ]

    # Add API response tracking
    if result.http_status_codes_seen:
        unique_statuses = list(dict.fromkeys(result.http_status_codes_seen))
        lines.append(f"HTTP statuses seen: {', '.join(unique_statuses[:5])}")

    if result.api_response_shapes_seen:
        unique_shapes = list(dict.fromkeys(result.api_response_shapes_seen))
        lines.append(f"Response shapes: {', '.join(unique_shapes[:5])}")

    # Add incident info if found
    if result.incident_found:
        lines.extend([
            "",
            "--- Incident Found ---",
            f"ID: {result.incident_id}",
        ])

    # Add LLM enrichment info if available
    if result.provider_enabled or result.provider_configured:
        lines.extend([
            "",
            "--- LLM Enrichment ---",
            f"Provider enabled: {result.provider_enabled}",
            f"Provider configured: {result.provider_configured}",
            f"Provider name: {result.provider_name or '(unknown)'}",
            f"Provider model: {result.provider_model or '(unknown)'}",
            f"Provider invocation count: {result.provider_invocation_count}",
            f"Enrichment status: {result.enrichment_status or '(none)'}",
        ])

    # Add last response shape
    if result.last_api_response:
        from .classify import sanitize_api_response_for_logging
        sanitized = sanitize_api_response_for_logging(result.last_api_response)
        lines.extend([
            "",
            "--- Last API Response (sanitized) ---",
            sanitized,
        ])

    return "\n".join(lines)


def format_polling_history(
    poll_results: list[dict[str, Any]],
) -> str:
    """Format polling history for display.

    Args:
        poll_results: List of poll results

    Returns:
        Formatted polling history
    """
    if not poll_results:
        return "(no polls)"

    lines = [
        "Poll History:",
        "-" * 60,
    ]

    for i, poll in enumerate(poll_results, 1):
        elapsed = poll.get("elapsed_seconds", 0)
        http_code = poll.get("http_status", "")
        incident_id = poll.get("incident_id", "")
        response_shape = poll.get("response_shape", "")

        if incident_id:
            lines.append(f"  {i:2d}. {elapsed:6.1f}s | HTTP {http_code} | incident_id={incident_id}")
        else:
            lines.append(f"  {i:2d}. {elapsed:6.1f}s | HTTP {http_code} | shape={response_shape}")

    return "\n".join(lines)
