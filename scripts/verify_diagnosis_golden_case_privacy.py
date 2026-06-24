#!/usr/bin/env python3
"""
verify_diagnosis_golden_case_privacy.py

Fail-closed privacy verifier for diagnosis golden-case fixtures.

This script scans committed golden-case fixture directories for leaked
internal topology or raw artifact paths. It is designed to prevent
accidental commits of private information.

This script:
- Scans .json, .yaml, .yml, .txt, and .md files under golden-case fixture directories
- Fails if private RFC1918 IPs are found (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
- Fails if internal K8s node names are found (k3s-worker-*, k3s-master-*)
- Fails if internal namespace names are found (k9b-cnpg-lab-[0-9]+)
- Fails if internal domains are found (*.spbnix.local, registry.spbnix.com)
- Fails if raw artifact paths are found (lab-artifacts/live)
- Allows intended placeholders: <PRIVATE_IP>, <K8S_NODE>, <LAB_NAMESPACE>, etc.
- Reports file, line number, pattern class, and bounded excerpt on failure

Usage:
    python scripts/verify_diagnosis_golden_case_privacy.py \\
        fixtures/diagnosis-golden-cases/pod-failure-readiness

Exit codes:
    0 - Verification passed (no privacy leaks found)
    1 - Verification failed (privacy leaks found)
    2 - Invalid arguments
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# =============================================================================
# Privacy Leak Detection Patterns
# =============================================================================

# Forbidden patterns (should NOT be in committed fixtures)
_FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # RFC1918 private IPv4 addresses
    # Use (?:^|[^\w]) to match start of string or non-word char (instead of \b)
    # because \b fails when preceded by word chars like 'x' or '10.'
    (
        "rfc1918_10",
        re.compile(r"(?:^|[^\w])10\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:\W|$)"),
        "RFC1918 10.x.x.x private IP",
    ),
    (
        "rfc1918_172",
        re.compile(r"(?:^|[^\w])172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}(?:\W|$)"),
        "RFC1918 172.16-31.x.x private IP",
    ),
    (
        "rfc1918_192",
        re.compile(r"(?:^|[^\w])192\.168\.\d{1,3}\.\d{1,3}(?:\W|$)"),
        "RFC1918 192.168.x.x private IP",
    ),
    # Internal K8s node names
    (
        "k8s_node_worker",
        re.compile(r"\bk3s-worker-\d+\b"),
        "Internal k3s-worker-* node name",
    ),
    (
        "k8s_node_master",
        re.compile(r"\bk3s-master-\d+\b"),
        "Internal k3s-master-* node name",
    ),
    # Internal namespace names
    (
        "internal_namespace",
        re.compile(r"\bk9b-cnpg-lab-\d+\b"),
        "Internal k9b-cnpg-lab-* namespace",
    ),
    # Internal domains
    (
        "internal_domain_harbor",
        re.compile(r"\bharbor-[a-z0-9-]+\.spbnix\.local\b", re.IGNORECASE),
        "Internal harbor-*.spbnix.local domain",
    ),
    (
        "internal_domain_registry",
        re.compile(r"\bregistry\.spbnix\.com\b", re.IGNORECASE),
        "Internal registry.spbnix.com domain",
    ),
    (
        "internal_domain_spbnix",
        re.compile(r"\b[a-z0-9-]+\.spbnix\.local\b", re.IGNORECASE),
        "Internal *.spbnix.local domain",
    ),
    # Raw artifact paths
    (
        "raw_artifact_path",
        re.compile(r"lab-artifacts/live"),
        "Raw artifact path 'lab-artifacts/live'",
    ),
    (
        "raw_artifact_path_abs",
        re.compile(r"(?:^|[/\\])lab-artifacts[/\\]live"),
        "Raw artifact path (absolute/relative)",
    ),
]

# Allowed placeholder patterns (these should NOT trigger failures)
_ALLOWED_PLACEHOLDERS: list[re.Pattern[str]] = [
    re.compile(r"<PRIVATE_IP>"),
    re.compile(r"<K8S_NODE>"),
    re.compile(r"<LAB_NAMESPACE>"),
    re.compile(r"<REGISTRY_HOST>"),
    re.compile(r"<INTERNAL_DOMAIN>"),
    re.compile(r"<REDACTED_RAW_ARTIFACT_DIR>"),
    re.compile(r"<SANITIZED_ARTIFACT_DIR>"),
]

# File extensions to scan
_SCAN_EXTENSIONS = {".json", ".yaml", ".yml", ".txt", ".md"}

# Directories to skip
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


# =============================================================================
# Finding Report
# =============================================================================

class PrivacyFinding:
    """Represents a single privacy leak finding."""

    def __init__(
        self,
        file_path: str,
        line_number: int,
        pattern_class: str,
        pattern_description: str,
        line_content: str,
    ) -> None:
        self.file_path = file_path
        self.line_number = line_number
        self.pattern_class = pattern_class
        self.pattern_description = pattern_description
        self.line_content = line_content

    def to_report(self) -> str:
        """Format finding for human-readable output."""
        # Truncate line content for safety (do not print full raw lines unbounded)
        excerpt = self.line_content[:120].strip()
        if len(self.line_content) > 120:
            excerpt += "..."
        return (
            f"  File: {self.file_path}:{self.line_number}\n"
            f"    Pattern: {self.pattern_description}\n"
            f"    Line excerpt: {excerpt}"
        )


# =============================================================================
# Scanning Logic
# =============================================================================

def is_binary_file(file_path: Path) -> bool:
    """Check if file appears to be binary."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            # Check for null bytes or other binary indicators
            return b"\x00" in chunk
    except Exception:
        return True


def scan_file(file_path: Path) -> list[PrivacyFinding]:
    """Scan a single file for privacy leaks.

    Returns a list of findings. Empty list means no leaks found.
    """
    findings: list[PrivacyFinding] = []

    # Skip binary files
    if is_binary_file(file_path):
        return findings

    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return findings

    # Check each forbidden pattern
    for pattern_class, pattern, description in _FORBIDDEN_PATTERNS:
        for line_num, line in enumerate(content.splitlines(), start=1):
            # Skip lines that only contain allowed placeholders
            if _is_placeholder_only_line(line):
                continue

            if pattern.search(line):
                findings.append(
                    PrivacyFinding(
                        file_path=str(file_path),
                        line_number=line_num,
                        pattern_class=pattern_class,
                        pattern_description=description,
                        line_content=line,
                    )
                )

    return findings


def _is_placeholder_only_line(line: str) -> bool:
    """Check if line contains only allowed placeholders (with whitespace)."""
    # Remove placeholders and check if anything substantial remains
    stripped = line.strip()
    for placeholder_pattern in _ALLOWED_PLACEHOLDERS:
        stripped = placeholder_pattern.sub("", stripped)
    # After removing all placeholders, line should be empty or just whitespace
    return not stripped.strip()


def scan_directory(case_dir: Path) -> list[PrivacyFinding]:
    """Scan a golden-case fixture directory recursively.

    Returns all findings across all relevant files.
    """
    all_findings: list[PrivacyFinding] = []

    for file_path in case_dir.rglob("*"):
        # Skip directories
        if file_path.is_dir():
            continue

        # Skip files in excluded directories
        if any(skip in file_path.parts for skip in _SKIP_DIRS):
            continue

        # Only scan relevant file types
        if file_path.suffix.lower() not in _SCAN_EXTENSIONS:
            continue

        # Scan the file
        findings = scan_file(file_path)
        all_findings.extend(findings)

    return all_findings


# =============================================================================
# Main Verification Logic
# =============================================================================

def verify_golden_case_privacy(case_dir: Path) -> tuple[bool, list[PrivacyFinding]]:
    """Verify a golden case directory for privacy leaks.

    Returns (success, findings) where:
    - success is True if no leaks found (exit 0)
    - findings is the list of all findings (empty if success)
    """
    findings = scan_directory(case_dir)
    return len(findings) == 0, findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed privacy verifier for diagnosis golden-case fixtures.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Verify pod-failure golden case privacy
    python scripts/verify_diagnosis_golden_case_privacy.py \\
        fixtures/diagnosis-golden-cases/pod-failure-readiness

    # Scan all golden cases
    for dir in fixtures/diagnosis-golden-cases/*/; do
        python scripts/verify_diagnosis_golden_case_privacy.py "$dir"
    done

Exit codes:
    0 - Verification passed (no privacy leaks found)
    1 - Verification failed (privacy leaks found)
    2 - Invalid arguments
        """,
    )
    parser.add_argument(
        "case_dir",
        type=Path,
        help="Path to golden case directory",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Validate case directory
    if not args.case_dir.exists():
        print(f"ERROR: Directory does not exist: {args.case_dir}", file=sys.stderr)
        return 2

    if not args.case_dir.is_dir():
        print(f"ERROR: Path is not a directory: {args.case_dir}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"Scanning golden case privacy: {args.case_dir}")
        print()

    # Run verification
    success, findings = verify_golden_case_privacy(args.case_dir)

    if success:
        if args.verbose:
            print("PRIVACY VERIFICATION PASSED")
            print("  No private topology or raw artifact paths found.")
        return 0

    # Report failures
    print("PRIVACY VERIFICATION FAILED")
    print("=" * 60)
    print(f"Found {len(findings)} privacy leak(s):")
    print()

    for finding in findings:
        print(finding.to_report())
        print()

    print("-" * 60)
    print()
    print("To fix these leaks, run:")
    print(f"  python scripts/sanitize_golden_case_topology.py {args.case_dir}")
    print()
    print("Then re-verify with:")
    print(f"  python scripts/verify_diagnosis_golden_case_privacy.py {args.case_dir}")
    print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
