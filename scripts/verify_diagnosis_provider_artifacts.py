#!/usr/bin/env python3
"""Provider artifact verifier - fail-closed sanitizer for LLM diagnosis outputs.

This module validates that provider artifacts do not contain sensitive data
or action-oriented content that should not be logged/uploaded.

Fail-closed design: Any artifact failing validation is rejected and returns exit code 1.

Usage:
    python scripts/verify_diagnosis_provider_artifacts.py [--input FILE] [--output FILE]

Exit codes:
    0 - Artifact passed validation (safe to upload)
    1 - Artifact failed validation (contains sensitive data or blocked patterns)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Secret patterns that must never appear in artifacts
_SECRET_PATTERNS: list[tuple[str, str]] = [
    # Bearer tokens and API keys
    (r"Bearer\s+[a-zA-Z0-9_\-]{20,}", "Bearer token"),
    (r"sk-[a-zA-Z0-9_\-]{20,}", "OpenAI API key"),
    (r"sk-proj-[a-zA-Z0-9_\-]{20,}", "OpenAI project key"),
    (r"sk-ant-[a-zA-Z0-9_\-]{20,}", "Anthropic API key"),
    (r"ghp_[a-zA-Z0-9]{36,}", "GitHub personal access token"),
    (r"glpat-[a-zA-Z0-9\-]{20,}", "GitLab personal access token"),
    (r"AKP[a-zA-Z0-9]{20,}", "Azure token"),
    (r"gsk_[a-zA-Z0-9]{20,}", "GitLab secret key"),
    # AWS credentials
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    # Generic JWT patterns (may contain sensitive data)
    (r"eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+", "JWT token"),
]

# Internal network patterns
_INTERNAL_PATTERNS: list[tuple[str, str]] = [
    # Internal IPs
    (r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "10.x.x.x internal IP"),
    (r"\b172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b", "172.16-31.x.x internal IP"),
    (r"\b192\.168\.\d{1,3}\.\d{1,3}\b", "192.168.x.x internal IP"),
    # Kubernetes internal DNS
    (r"[a-zA-Z0-9_-]+\.default\.svc\.cluster\.local", "Kubernetes internal DNS"),
    (r"[a-zA-Z0-9_-]+\.kube-system\.svc\.cluster\.local", "Kubernetes system DNS"),
]

# Blocked field patterns - fields that should not contain action/mutation content
_BLOCKED_FIELD_PATTERNS: list[tuple[str, str]] = [
    # kubectl exec, run, delete, apply commands
    (r"kubectl\s+(exec|run|delete|apply|create|replace|patch|edit)\s", "kubectl mutation command"),
    # helm commands
    (r"helm\s+(install|upgrade|uninstall|rollback)\s", "helm mutation command"),
    # docker commands
    (r"docker\s+(run|rm|rmi|pull|push|build)\s", "docker mutation command"),
    # API mutations
    (r"(POST|PUT|PATCH)\s+/api/.*(create|update|delete|remove)", "API mutation"),
]

# Raw-like filename patterns that indicate sensitive data and should be rejected
_RAW_LIKE_FILENAME_PATTERNS: list[tuple[str, str]] = [
    (r"\.raw\.json$", "raw JSON file"),
    (r"\.payload\.json$", "payload JSON file"),
    (r"\.request\.json$", "request JSON file"),
    (r"\.response\.json$", "response JSON file"),
    (r"\.secret", "secret file"),
    (r"\.credential", "credential file"),
    (r"\.token", "token file"),
    (r"\.apikey", "API key file"),
    (r"\.key$", "key file"),
]


def _check_secret_patterns(content: str) -> list[str]:
    """Check for secret patterns in content."""
    findings = []
    for pattern, name in _SECRET_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(f"secret: {name}")
    return findings


def _check_internal_patterns(content: str) -> list[str]:
    """Check for internal network patterns in content."""
    findings = []
    for pattern, name in _INTERNAL_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(f"internal: {name}")
    return findings


def _check_blocked_field_content(obj: Any, path: str = "") -> list[str]:
    """Recursively check for blocked patterns in object."""
    findings = []

    if isinstance(obj, str):
        for pattern, name in _BLOCKED_FIELD_PATTERNS:
            if re.search(pattern, obj, re.IGNORECASE):
                findings.append(f"blocked: {name} in {path}")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            findings.extend(_check_blocked_field_content(value, f"{path}.{key}" if path else key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            findings.extend(_check_blocked_field_content(item, f"{path}[{i}]"))
    return findings


def _check_raw_like_filename(filename: str) -> list[str]:
    """Check if filename indicates raw/sensitive data that should not be uploaded.

    Args:
        filename: The filename to check (not the full path)

    Returns:
        List of findings (empty if filename is acceptable)
    """
    findings = []
    for pattern, name in _RAW_LIKE_FILENAME_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            findings.append(f"filename: {name}")
    return findings


def _classify_and_redact(content: str) -> tuple[list[str], str]:
    """Classify findings and redact sensitive data.

    Returns:
        Tuple of (findings, redacted_content)
    """
    all_findings: list[str] = []

    # Check for secrets
    all_findings.extend(_check_secret_patterns(content))

    # Check for internal patterns
    all_findings.extend(_check_internal_patterns(content))

    # Redact secrets
    redacted = content
    for pattern, _ in _SECRET_PATTERNS:
        redacted = re.sub(pattern, "<REDACTED:API_KEY>", redacted, flags=re.IGNORECASE)

    # Redact internal IPs (keep structure but mask actual IPs)
    for pattern, name in _INTERNAL_PATTERNS:
        if "internal IP" in name or "DNS" in name:
            # Replace with placeholder preserving structure
            if "internal IP" in name:
                redacted = re.sub(pattern, "<REDACTED:INTERNAL_IP>", redacted)
            elif "DNS" in name:
                redacted = re.sub(pattern, "<REDACTED:INTERNAL_DNS>", redacted)

    return all_findings, redacted


def verify_artifact(input_path: Path, output_path: Path | None = None) -> bool:
    """Verify and sanitize a provider artifact.

    Args:
        input_path: Path to input artifact (JSON or text)
        output_path: Optional path to write sanitized output

    Returns:
        True if artifact passed validation (safe to upload)
        False if artifact failed validation
    """
    # Check filename for raw-like patterns (fail-closed boundary)
    filename = input_path.name
    filename_findings = _check_raw_like_filename(filename)
    if filename_findings:
        print("ARTIFACT VALIDATION FAILED", file=sys.stderr)
        print(f"Input: {input_path}", file=sys.stderr)
        for finding in filename_findings:
            print(f"  - {finding}", file=sys.stderr)
        print("Artifact filename indicates raw/sensitive data - not safe to upload", file=sys.stderr)
        return False

    # Read input
    try:
        raw_content = input_path.read_text()
    except Exception as exc:
        print(f"ERROR: Failed to read input: {exc}", file=sys.stderr)
        return False

    # Check for secrets and internal patterns in raw content
    findings: list[str] = []

    # JSON content: parse and check recursively
    try:
        obj = json.loads(raw_content)
        findings.extend(_check_blocked_field_content(obj))
    except json.JSONDecodeError:
        # Not JSON, just text - check patterns
        pass

    # Check raw content for secrets/internal
    secret_findings, redacted_content = _classify_and_redact(raw_content)
    findings.extend(secret_findings)

    # Report findings
    if findings:
        print("ARTIFACT VALIDATION FAILED", file=sys.stderr)
        print(f"Input: {input_path}", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print("Artifact contains sensitive data - not safe to upload", file=sys.stderr)
        return False

    # Passed validation
    print("ARTIFACT VALIDATION PASSED", file=sys.stderr)
    print(f"Input: {input_path}", file=sys.stderr)
    print("No sensitive data detected", file=sys.stderr)

    # Write sanitized output if requested
    if output_path:
        try:
            output_path.write_text(redacted_content)
            print(f"Sanitized artifact written to: {output_path}", file=sys.stderr)
        except Exception as exc:
            print(f"WARNING: Failed to write output: {exc}", file=sys.stderr)

    return True


def verify_directory(input_dir: Path, output_dir: Path | None = None) -> tuple[bool, list[str]]:
    """Verify and sanitize all artifacts in a directory.

    Args:
        input_dir: Directory containing artifacts
        output_dir: Optional output directory for sanitized artifacts

    Returns:
        Tuple of (all_passed, list of results)
    """
    results: list[str] = []
    all_passed = True

    if not input_dir.is_dir():
        print(f"ERROR: Not a directory: {input_dir}", file=sys.stderr)
        return False, results

    # Create output directory if specified
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Fail-closed: subdirectories are not allowed
    for file_path in sorted(input_dir.iterdir()):
        if file_path.is_dir():
            print("ARTIFACT VALIDATION FAILED", file=sys.stderr)
            print(f"Subdirectory not allowed: {file_path.name}/", file=sys.stderr)
            results.append(f"{file_path.name}/: FAIL subdirectory_not_allowed")
            all_passed = False

    # Process each file
    for file_path in sorted(input_dir.iterdir()):
        if file_path.is_file():
            out_path = None
            if output_dir:
                out_path = output_dir / file_path.name
            
            passed = verify_artifact(file_path, out_path)
            results.append(f"{file_path.name}: {'PASS' if passed else 'FAIL'}")
            if not passed:
                all_passed = False

    return all_passed, results


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify diagnosis provider artifacts for sensitive data"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="Input artifact file or directory (JSON or text)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output path for sanitized artifact (optional, used for single file mode)"
    )
    parser.add_argument(
        "--directory", "-d",
        action="store_true",
        help="Treat input as directory (verify all files, optionally copy to output)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: Input not found: {args.input}", file=sys.stderr)
        return 1

    if args.directory:
        # Directory mode
        if not args.input.is_dir():
            print(f"ERROR: --directory specified but input is not a directory: {args.input}", file=sys.stderr)
            return 1
        all_passed, results = verify_directory(args.input, args.output)
        print("Directory verification results:")
        for result in results:
            print(f"  {result}")
        print(f"Overall: {'PASS' if all_passed else 'FAIL'}")
        return 0 if all_passed else 1
    else:
        # Single file mode
        success = verify_artifact(args.input, args.output)
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
