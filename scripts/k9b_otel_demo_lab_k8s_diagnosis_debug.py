"""Debug helpers for P4c diagnosis packet snippets.

This module provides bounded, redacted debug output for the P4c
unschedulable-shipping diagnosis path. It helps diagnose cases where
both passes end with `stop_no_checks_proposed` while the final artifact
misses `shipping`, `nodeSelector`, and `k9b.dev/otel-lab-node`.

Enable with environment variables:
- K9B_DIAGNOSIS_PACKET_SNIPPETS=1  - Enable diagnosis packet debug (review packets, deployment health)
- K9B_DIAGNOSIS_LOOP_DEBUG=1       - Enable loop summary debug (decisions, proposed checks)

Security: All dumps are bounded and redacted. Provider credentials,
tokens, cookies, kubeconfigs, and full LLM prompts are NOT emitted.

GitHub Actions hardening: Packet content is wrapped with stop-commands
to prevent accidental workflow command injection from untrusted content.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any


def _is_packet_debug_enabled() -> bool:
    """Check if diagnosis packet snippets are enabled."""
    return os.environ.get("K9B_DIAGNOSIS_PACKET_SNIPPETS", "0") == "1"


def _is_loop_debug_enabled() -> bool:
    """Check if diagnosis loop debug is enabled."""
    return os.environ.get("K9B_DIAGNOSIS_LOOP_DEBUG", "0") == "1"


def _redact_sensitive_fields(data: Any, max_length: int = 500) -> Any:
    """Redact sensitive fields from data structures.

    Redacts: tokens, keys, credentials, kubeconfigs, cookies.
    Truncates long strings to max_length.
    """
    sensitive_patterns = (
        "token", "key", "secret", "password", "credential",
        "kubeconfig", "cookie", "authorization", "bearer",
        "api_key", "apikey", "auth",
    )

    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            k_lower = k.lower()
            if any(p in k_lower for p in sensitive_patterns):
                result[k] = "[REDACTED]"
            else:
                result[k] = _redact_sensitive_fields(v, max_length)
        return result
    elif isinstance(data, list):
        return [_redact_sensitive_fields(item, max_length) for item in data]
    elif isinstance(data, str):
        if len(data) > max_length:
            return data[:max_length] + "...[TRUNCATED]"
        return data
    else:
        return data


def _emit_github_group(title: str, content: str | dict | list) -> None:
    """Emit content to GitHub Actions log group with stop-command hardening.

    Wraps untrusted packet content with stop-commands to prevent
    accidental workflow command injection from untrusted content.
    Uses a random UUID token per call for safety.
    """
    token = f"k9b-debug-{uuid.uuid4()}"
    print(f"::group::{title}")
    print(f"::stop-commands::{token}")
    try:
        if isinstance(content, (dict, list)):
            print(json.dumps(content, indent=2, default=str))
        else:
            print(content)
    finally:
        print(f"::{token}::")
        print("::endgroup::")


def dump_incident_signals(
    case_file_signals: dict[str, Any] | None,
    incident_id: str,
) -> None:
    """Dump bounded incident signals snippet.

    Args:
        case_file_signals: The signals dict from case_file.signals
        incident_id: The incident ID for labeling
    """
    if not _is_packet_debug_enabled():
        return
    if case_file_signals is None:
        return

    redacted = _redact_sensitive_fields(case_file_signals)
    title = f"P4c [{incident_id}] case_file.signals snippet"
    _emit_github_group(title, redacted)


def dump_evidence_links(
    evidence_links: list[dict[str, Any]] | None,
    incident_id: str,
) -> None:
    """Dump bounded evidence links snippet.

    Args:
        evidence_links: The evidence_links from case_file
        incident_id: The incident ID for labeling
    """
    if not _is_packet_debug_enabled():
        return
    if not evidence_links:
        return

    # Limit to first 10 evidence links
    redacted = _redact_sensitive_fields(evidence_links[:10])
    title = f"P4c [{incident_id}] case_file.evidence_links snippet (first 10)"
    _emit_github_group(title, redacted)


def dump_review_packet(
    review_packet: dict[str, Any] | None,
    incident_id: str,
    pass_num: int,
) -> None:
    """Dump bounded review packet snippet.

    Args:
        review_packet: The diagnosis review packet
        incident_id: The incident ID for labeling
        pass_num: Pass number (1 or 2)
    """
    if not _is_packet_debug_enabled():
        return
    if review_packet is None:
        return

    redacted = _redact_sensitive_fields(review_packet)
    title = f"P4c [{incident_id}] review_packet (pass {pass_num}) snippet"
    _emit_github_group(title, redacted)


def dump_failing_pods(
    failing_pods: list[dict[str, Any]] | None,
    incident_id: str,
) -> None:
    """Dump bounded failing pods snippet.

    Args:
        failing_pods: The failing_pods from review packet
        incident_id: The incident ID for labeling
    """
    if not _is_packet_debug_enabled():
        return
    if not failing_pods:
        return

    # Limit to first 5 failing pods
    redacted = _redact_sensitive_fields(failing_pods[:5])
    title = f"P4c [{incident_id}] review_packet.failing_pods snippet (first 5)"
    _emit_github_group(title, redacted)


def dump_deployment_health(
    deployment_health: dict[str, Any] | None,
    incident_id: str,
) -> None:
    """Dump bounded deployment health snippet.

    Args:
        deployment_health: The deployment_health from review packet
        incident_id: The incident ID for labeling
    """
    if not _is_packet_debug_enabled():
        return
    if deployment_health is None:
        return

    redacted = _redact_sensitive_fields(deployment_health)
    title = f"P4c [{incident_id}] review_packet.deployment_health snippet"
    _emit_github_group(title, redacted)


def dump_loop_summary(
    loop_summary: dict[str, Any] | None,
    incident_id: str,
    pass_num: int,
) -> None:
    """Dump bounded diagnosis loop summary snippet.

    Args:
        loop_summary: The diagnosis_loop_summary from pass
        incident_id: The incident ID for labeling
        pass_num: Pass number
    """
    if not _is_loop_debug_enabled():
        return
    if loop_summary is None:
        return

    redacted = _redact_sensitive_fields(loop_summary)
    title = f"P4c [{incident_id}] diagnosis_loop_summary (pass {pass_num}) snippet"
    _emit_github_group(title, redacted)


def dump_proposed_next_checks(
    proposed_next_checks: list[dict[str, Any]] | None,
    incident_id: str,
    pass_num: int,
) -> None:
    """Dump bounded proposed next checks snippet.

    Args:
        proposed_next_checks: The proposed_next_checks from loop summary
        incident_id: The incident ID for labeling
        pass_num: Pass number
    """
    if not _is_loop_debug_enabled():
        return
    if not proposed_next_checks:
        return

    # Limit to first 5 proposed checks
    redacted = _redact_sensitive_fields(proposed_next_checks[:5])
    title = f"P4c [{incident_id}] proposed_next_checks (pass {pass_num}) snippet"
    _emit_github_group(title, redacted)


def dump_final_decision(
    final_decision: str | None,
    incident_id: str,
    pass_num: int,
) -> None:
    """Dump final decision snippet.

    Args:
        final_decision: The final_decision from loop summary
        incident_id: The incident ID for labeling
        pass_num: Pass number
    """
    if not _is_loop_debug_enabled():
        return
    if final_decision is None:
        return

    title = f"P4c [{incident_id}] final_decision (pass {pass_num})"
    _emit_github_group(title, final_decision)


def dump_backend_incident_detail(
    incident_detail: dict[str, Any] | None,
    incident_id: str,
) -> None:
    """Dump bounded backend incident detail snippet.

    Args:
        incident_detail: The incident detail from GET /api/incidents/{id}
        incident_id: The incident ID for labeling
    """
    if not _is_packet_debug_enabled():
        return
    if incident_detail is None:
        return

    redacted = _redact_sensitive_fields(incident_detail)
    title = f"P4c [{incident_id}] backend incident detail snippet"
    _emit_github_group(title, redacted)
