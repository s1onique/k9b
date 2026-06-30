"""Sensitive payload scanning for OTel demo lab contract verification."""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.otel_lab_contracts.constants import ALLOWED_SAFE_PATTERNS, FORBIDDEN_SENSITIVE_PATTERNS
from scripts.otel_lab_contracts.models import ContractCheck, VerificationReport


def _check_forbidden_pattern(artifact_str: str, pattern: re.Pattern[str]) -> tuple[bool, str | None]:
    """Check for a single forbidden pattern, returning (has_forbidden, matched_text).

    Safe patterns like 'sensitive_read_denied' do NOT exempt other forbidden
    patterns in the same artifact. Each forbidden pattern is checked independently.
    """
    match = pattern.search(artifact_str)
    if not match:
        return False, None

    # Check if the matched text is exactly a safe pattern (exact match exemption)
    matched_text = match.group(0)
    if matched_text in ALLOWED_SAFE_PATTERNS:
        # This match IS the safe pattern - not forbidden
        return False, None

    # Also check for quoted safe patterns that might match
    for safe in ALLOWED_SAFE_PATTERNS:
        quoted_safe = f'"{safe}"'
        if quoted_safe in artifact_str and matched_text == safe:
            return False, None

    # Forbidden pattern found that is not a safe pattern
    return True, matched_text


def scan_for_sensitive_payloads(artifact_dir: Path, report: VerificationReport) -> bool:
    """Scan JSON artifacts for forbidden sensitive payload patterns.

    Fail if artifacts contain likely raw secret/token material.
    Safe patterns (sensitive_read_denied, etc.) only prevent failure when
    the forbidden match is EXACTLY that safe pattern, not when safe text
    appears anywhere else in the artifact.
    """
    json_files = list(artifact_dir.glob("**/*.json"))
    sensitive_artifacts: list[str] = []
    sensitive_details: dict[str, list[str]] = {}

    for json_path in json_files:
        try:
            content = json_path.read_text()
            artifact = json.loads(content)

            # Convert to string for pattern matching
            artifact_str = json.dumps(artifact)

            # Track forbidden patterns found (after safe-pattern exemptions)
            forbidden_found: list[str] = []

            for pattern in FORBIDDEN_SENSITIVE_PATTERNS:
                has_forbidden, matched_text = _check_forbidden_pattern(artifact_str, pattern)
                if has_forbidden and matched_text:
                    # This forbidden pattern is present and not exempted by exact safe match
                    forbidden_found.append(pattern.pattern)

            if forbidden_found:
                sensitive_artifacts.append(str(json_path))
                sensitive_details[str(json_path)] = forbidden_found

        except (json.JSONDecodeError, OSError):
            continue

    if sensitive_artifacts:
        detail_lines = [f"{path}: {', '.join(patterns)}" for path, patterns in sensitive_details.items()]
        report.add_error("Sensitive payload scan: Forbidden patterns found:\n  " + "\n  ".join(detail_lines))
        return False

    report.add_check(
        ContractCheck(
            name="sensitive_payload_scan",
            passed=True,
            phase="security",
            reason="no_forbidden_payloads",
        )
    )
    return True
