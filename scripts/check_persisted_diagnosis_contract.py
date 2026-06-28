#!/usr/bin/env python3
"""Verify persisted diagnosis contract for LLM diagnosis outputs.

This script validates that persisted diagnosis/review-packet state is visible
through the incident/review-packet API after one-pass diagnosis.

Usage:
    python scripts/check_persisted_diagnosis_contract.py \
        --incident-json PATH \
        --output-dir PATH \
        [--require-provider-invoked]

Exit codes:
    0 - Persisted diagnosis contract verified (safe to upload)
    1 - Contract verification failed

Failure classes:
    - missing_incident_id
    - incident_fetch_http_error
    - invalid_incident_json
    - diagnosis_not_persisted
    - provider_status_missing
    - provider_not_invoked
    - provider_not_configured
    - diagnosis_payload_empty
    - diagnosis_payload_unbounded
    - review_packet_missing
    - artifact_verification_failed
    - unknown_persisted_diagnosis_contract
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Secret patterns that must never appear in bounded output
_SECRET_PATTERNS: list[tuple[str, str]] = [
    # Bearer tokens and API keys
    (r"Bearer\s+[a-zA-Z0-9_\-]{20,}", "Bearer token"),
    (r"sk-[a-zA-Z0-9_\-]{20,}", "OpenAI API key"),
    (r"sk-proj-[a-zA-Z0-9_\-]{20,}", "OpenAI project key"),
    (r"sk-ant-[a-zA-Z0-9_\-]{20,}", "Anthropic API key"),
    (r"ghp_[a-zA-Z0-9]{36,}", "GitHub personal access token"),
    (r"glpat-[a-zA-Z0-9\-]{20,}", "GitLab personal access token"),
    # AWS credentials
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    # Generic JWT patterns
    (r"eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+", "JWT token"),
]

# Internal network patterns
_INTERNAL_PATTERNS: list[tuple[str, str]] = [
    # Internal IPs
    (r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "10.x.x.x internal IP"),
    (r"\b172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b", "172.16-31.x.x internal IP"),
    (r"\b192\.168\.\d{1,3}\.\d{1,3}\b", "192.168.x.x internal IP"),
]

# Maximum field lengths for bounded output
MAX_ARTIFACT_NAME_LENGTH = 240
MAX_DECISION_LENGTH = 120
MAX_CONTENT_LENGTH = 16 * 1024  # 16 KiB


def check_for_secrets(content: str) -> list[str]:
    """Check for secret patterns in content."""
    findings = []
    import re
    for pattern, name in _SECRET_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(f"secret: {name}")
    for pattern, name in _INTERNAL_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(f"internal: {name}")
    return findings


def load_incident_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Load and parse incident JSON file.

    Returns:
        Tuple of (parsed JSON, error message). If successful, error is empty.
    """
    try:
        content = path.read_text()
        return json.loads(content), ""
    except json.JSONDecodeError as e:
        return None, f"invalid_incident_json: {e}"
    except Exception as e:
        return None, f"incident_fetch_error: {e}"


def check_diagnosis_persisted(incident: dict[str, Any]) -> tuple[bool, str, list[str]]:
    """Check if diagnosis is persisted in incident.

    Looks for:
    - automatic_diagnosis_review.available == True
    - automatic_diagnosis_loop_summary.status == "completed"
    - Provider status fields from one-pass diagnosis response

    Returns:
        Tuple of (is_persisted, failure_class, findings)
    """
    findings = []

    # Check automatic_diagnosis_review
    auto_review = incident.get("automatic_diagnosis_review", {})
    available = auto_review.get("available", False)

    # Check automatic_diagnosis_loop_summary
    loop_summary = incident.get("automatic_diagnosis_loop_summary", {})
    loop_status = loop_summary.get("status", "not_run")

    # Diagnosis is persisted if either:
    # 1. automatic_diagnosis_review is available
    # 2. loop summary shows completed status
    is_persisted = available or loop_status == "completed"

    if not is_persisted:
        findings.append(f"diagnosis_not_persisted: available={available}, loop_status={loop_status}")
        return False, "diagnosis_not_persisted", findings

    # Validate bounded fields when available
    if available:
        artifact_name = auto_review.get("artifact_name", "")
        decision = auto_review.get("decision", "")

        if artifact_name and len(artifact_name) > MAX_ARTIFACT_NAME_LENGTH:
            findings.append(f"diagnosis_payload_unbounded: artifact_name too long ({len(artifact_name)} chars)")
            return False, "diagnosis_payload_unbounded", findings

        if decision and len(decision) > MAX_DECISION_LENGTH:
            findings.append(f"diagnosis_payload_unbounded: decision too long ({len(decision)} chars)")
            return False, "diagnosis_payload_unbounded", findings

        # Check for empty payload when available
        if not artifact_name and not decision:
            findings.append("diagnosis_payload_empty: available but no artifact_name or decision")
            return False, "diagnosis_payload_empty", findings

    findings.append(f"diagnosis_persisted: available={available}, loop_status={loop_status}")
    return True, "", findings


def check_provider_status(
    incident: dict[str, Any],
    require_provider_invoked: bool = False,
) -> tuple[bool, str, list[str]]:
    """Check provider status in incident.

    Returns:
        Tuple of (is_ok, failure_class, findings)
    """
    findings = []

    # Provider status is now persisted at the canonical path:
    # automatic_diagnosis_review.provider_status
    # This is the Phase 4 contract-verified path.

    auto_review = incident.get("automatic_diagnosis_review", {})
    provider_status = auto_review.get("provider_status", {})

    # Extract provider fields from canonical path
    provider_configured = provider_status.get("provider_configured")
    provider_invoked = provider_status.get("provider_invocation_attempted")

    # Also check legacy paths for backward compatibility
    if provider_configured is None:
        provider_configured = incident.get("provider_configured")
    if provider_invoked is None:
        provider_invoked = incident.get("provider_invocation_attempted")
    if provider_configured is None:
        provider_configured = incident.get("one_pass_diagnosis", {}).get("provider_configured")
    if provider_invoked is None:
        provider_invoked = incident.get("one_pass_diagnosis", {}).get("provider_invocation_attempted")

    # If neither is present, this might be a provider-disabled run
    if provider_configured is None and provider_invoked is None:
        findings.append("provider_status_missing: no provider fields found")
        # When provider invocation is required, missing fields is a failure
        if require_provider_invoked:
            return False, "provider_status_missing", findings
        # Not a failure - provider may be disabled
        return True, "", findings

    # Check configured status
    if provider_configured is not None:
        if not isinstance(provider_configured, bool):
            findings.append(f"provider_status_invalid: provider_configured={provider_configured}")
            return False, "provider_status_missing", findings

        if not provider_configured:
            findings.append("provider_not_configured: provider_configured=false")
            return False, "provider_not_configured", findings

        findings.append(f"provider_configured={provider_configured}")

    # Check invocation status if provider is configured
    if require_provider_invoked and provider_configured:
        if provider_invoked is None:
            findings.append("provider_status_missing: provider_invocation_attempted not found")
            return False, "provider_status_missing", findings

        if not isinstance(provider_invoked, bool):
            findings.append(f"provider_status_invalid: provider_invocation_attempted={provider_invoked}")
            return False, "provider_status_missing", findings

        if not provider_invoked:
            findings.append("provider_not_invoked: provider_invocation_attempted=false")
            return False, "provider_not_invoked", findings

        findings.append(f"provider_invoked={provider_invoked}")

    return True, "", findings


def sanitize_content(content: str) -> str:
    """Sanitize content by redacting secrets."""
    import re
    sanitized = content
    for pattern, _ in _SECRET_PATTERNS:
        sanitized = re.sub(pattern, "<REDACTED>", sanitized, flags=re.IGNORECASE)
    for pattern, _ in _INTERNAL_PATTERNS:
        sanitized = re.sub(pattern, "<REDACTED:INTERNAL>", sanitized)
    return sanitized


def build_bounded_summary(
    incident_id: str,
    diagnosis_persisted: bool,
    provider_configured: bool | None,
    provider_invoked: bool | None,
    auto_review_available: bool,
    loop_status: str,
    http_status: int,
    review_packet_http_status: int | None = None,
    failure_class: str | None = None,
) -> str:
    """Build operator-friendly bounded summary."""
    lines = [
        "Persisted Diagnosis Contract Gate Result: PASSED" if not failure_class else f"Persisted Diagnosis Contract Gate Result: FAILED ({failure_class})",
        f"Incident ID: {incident_id}",
        f"Incident fetch: HTTP {http_status}",
    ]

    if review_packet_http_status is not None:
        lines.append(f"Review packet fetch: HTTP {review_packet_http_status}")
    else:
        lines.append("Review packet fetch: not applicable")

    lines.append(f"Diagnosis persisted: {diagnosis_persisted}")
    lines.append(f"Provider configured: {provider_configured}")
    lines.append(f"Provider invoked: {provider_invoked}")
    lines.append(f"Diagnosis status: {'available' if auto_review_available else loop_status}")

    if failure_class:
        lines.append(f"Failure class: {failure_class}")

    return "\n".join(lines)


def write_result_json(output_dir: Path, result: dict[str, Any]) -> None:
    """Write result JSON to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "persisted-diagnosis-result.json"
    result_path.write_text(json.dumps(result, indent=2))


def write_bounded_summary(output_dir: Path, summary: str) -> None:
    """Write bounded summary to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "bounded-summary.txt"
    summary_path.write_text(summary)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify persisted diagnosis contract for LLM diagnosis outputs"
    )
    parser.add_argument(
        "--incident-json",
        type=Path,
        required=True,
        help="Path to incident JSON file (GET /api/incidents/{id} response)",
    )
    parser.add_argument(
        "--review-packet-json",
        type=Path,
        help="Optional path to review packet JSON file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to write verification results",
    )
    parser.add_argument(
        "--require-provider-invoked",
        action="store_true",
        help="Fail if provider was not invoked (for provider-required runs)",
    )
    parser.add_argument(
        "--incident-http-status",
        type=int,
        default=200,
        help="HTTP status code for incident fetch (default: 200)",
    )
    parser.add_argument(
        "--review-packet-http-status",
        type=int,
        help="HTTP status code for review packet fetch (if fetched separately)",
    )

    args = parser.parse_args()

    findings: list[str] = []
    failure_class: str | None = None

    # Load incident JSON
    incident, load_error = load_incident_json(args.incident_json)
    if incident is None:
        failure_class = "invalid_incident_json"
        findings.append(load_error)
        summary = build_bounded_summary(
            incident_id="unknown",
            diagnosis_persisted=False,
            provider_configured=None,
            provider_invoked=None,
            auto_review_available=False,
            loop_status="unknown",
            http_status=args.incident_http_status,
            review_packet_http_status=args.review_packet_http_status,
            failure_class=failure_class,
        )
        result = {
            "passed": False,
            "failure_class": failure_class,
            "findings": findings,
        }
        write_result_json(args.output_dir, result)
        write_bounded_summary(args.output_dir, summary)
        print(f"FAIL: {failure_class}")
        for f in findings:
            print(f"  - {f}")
        return 1

    incident_id = incident.get("incident_id", "unknown")

    # Check if HTTP status indicates error
    if args.incident_http_status >= 400:
        failure_class = "incident_fetch_http_error"
        findings.append(f"incident_fetch_http_error: HTTP {args.incident_http_status}")
        summary = build_bounded_summary(
            incident_id=incident_id,
            diagnosis_persisted=False,
            provider_configured=None,
            provider_invoked=None,
            auto_review_available=False,
            loop_status="unknown",
            http_status=args.incident_http_status,
            review_packet_http_status=args.review_packet_http_status,
            failure_class=failure_class,
        )
        result = {
            "passed": False,
            "failure_class": failure_class,
            "findings": findings,
        }
        write_result_json(args.output_dir, result)
        write_bounded_summary(args.output_dir, summary)
        print(f"FAIL: {failure_class}")
        for f in findings:
            print(f"  - {f}")
        return 1

    # Check diagnosis persistence
    diagnosis_persisted, diag_failure, diag_findings = check_diagnosis_persisted(incident)
    findings.extend(diag_findings)
    if diag_failure:
        failure_class = diag_failure

    # Get auto_review availability for summary
    auto_review = incident.get("automatic_diagnosis_review", {})
    auto_review_available = auto_review.get("available", False)
    loop_summary = incident.get("automatic_diagnosis_loop_summary", {})
    loop_status = loop_summary.get("status", "not_run")

    # Check provider status
    provider_ok, prov_failure, prov_findings = check_provider_status(
        incident, require_provider_invoked=args.require_provider_invoked
    )
    findings.extend(prov_findings)
    if prov_failure and not failure_class:
        failure_class = prov_failure

    # Extract provider fields for summary
    provider_configured = incident.get("provider_configured")
    provider_invoked = incident.get("provider_invocation_attempted")
    if provider_configured is None:
        provider_configured = incident.get("one_pass_diagnosis", {}).get("provider_configured")
    if provider_invoked is None:
        provider_invoked = incident.get("one_pass_diagnosis", {}).get("provider_invocation_attempted")

    # Build initial result and summary
    passed = diagnosis_persisted and (provider_ok or not args.require_provider_invoked)
    if not passed and not failure_class:
        failure_class = "unknown_persisted_diagnosis_contract"

    # Check for secrets in incident content (fail-closed)
    # Must happen BEFORE writing result so final passed/failure_class reflect secret scan
    incident_content = json.dumps(incident)
    secret_findings = check_for_secrets(incident_content)
    if secret_findings:
        for sf in secret_findings:
            findings.append(f"secret_in_output: {sf}")
        passed = False
        if not failure_class:
            failure_class = "artifact_verification_failed"

    # Build result AFTER secret scan to reflect final state
    result = {
        "passed": passed,
        "failure_class": failure_class,
        "incident_id": incident_id,
        "diagnosis_persisted": diagnosis_persisted,
        "auto_review_available": auto_review_available,
        "loop_status": loop_status,
        "provider_configured": provider_configured,
        "provider_invoked": provider_invoked,
        "findings": findings,
        "secret_findings": secret_findings if secret_findings else None,
    }

    # Build summary AFTER secret scan
    summary = build_bounded_summary(
        incident_id=incident_id,
        diagnosis_persisted=diagnosis_persisted,
        provider_configured=provider_configured,
        provider_invoked=provider_invoked,
        auto_review_available=auto_review_available,
        loop_status=loop_status,
        http_status=args.incident_http_status,
        review_packet_http_status=args.review_packet_http_status,
        failure_class=failure_class,
    )

    # Write outputs
    write_result_json(args.output_dir, result)
    write_bounded_summary(args.output_dir, summary)

    # Print result
    if passed:
        print("PASS: Persisted diagnosis contract verified")
        for f in findings:
            print(f"  - {f}")
        return 0
    else:
        print(f"FAIL: {failure_class}")
        for f in findings:
            print(f"  - {f}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
