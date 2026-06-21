#!/usr/bin/env python
"""Verify production readiness disclaimer is present in docs.

This script validates DOC-CLAIM-0064: Do not claim production readiness
without explicit evidence in the repository.

Usage:
    python scripts/verify_production_readiness_disclaimer.py           # verify
    python scripts/verify_production_readiness_disclaimer.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Suspicious production readiness phrases (require evidence or disclaimer)
SUSPICIOUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bproduction[-\s]ready\b", re.IGNORECASE),
    re.compile(r"\bproduction[-\s]grade\b", re.IGNORECASE),
    re.compile(r"\bproduction\s+readiness\b", re.IGNORECASE),
    re.compile(r"\bready\s+for\s+production\b", re.IGNORECASE),
]

# Phrases that are acceptable when properly caveated
ACCEPTABLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"not\s+production[-\s]ready", re.IGNORECASE),
    re.compile(r"not\s+production[-\s]grade", re.IGNORECASE),
    re.compile(r"not\s+ready\s+for\s+production", re.IGNORECASE),
    re.compile(r"beta\b.*production", re.IGNORECASE),
    re.compile(r"for\s+evaluation", re.IGNORECASE),
    re.compile(r"early[-\s]adopter", re.IGNORECASE),
]

# Allowlisted files where production readiness claims may be valid
ALLOWLIST: list[str] = [
    "README.md",  # Policy declarations, not claims
    "docs/reports/k8s-accelerator-real-cluster-demo-storyline-evidence.md",
    "docs/reports/current-agent-capabilities.md",
    "docs/beta-stakeholder-demo-script.md",
    "docs/post-beta-backlog.md",
    "docs/post-beta-operator-feedback-and-live-integrations.md",
    "docs/doctrine/blockstor-derived-rules.md",
    "docs/data-model/next-check-mapping.md",
]


def scan_file(content: str, file_path: str) -> tuple[list[str], list[str]]:
    """Scan a file for suspicious production readiness phrases."""
    errors: list[str] = []
    warnings: list[str] = []
    lines = content.split("\n")
    for line_num, line in enumerate(lines, 1):
        for pattern in SUSPICIOUS_PATTERNS:
            if pattern.search(line):
                is_allowlisted = any(a in file_path for a in ALLOWLIST)
                if is_allowlisted:
                    continue
                has_caveat = any(cp.search(line) for cp in ACCEPTABLE_PATTERNS)
                if has_caveat:
                    warnings.append(f"{file_path}:{line_num}: Caveat found")
                else:
                    errors.append(f"{file_path}:{line_num}: No caveat: {line.strip()[:60]}")
    return errors, warnings


def run_verification() -> bool:
    """Run verification checks."""
    print("=== Production Readiness Disclaimer Verification ===\n")
    docs_dir = Path("docs")
    readme_path = Path("README.md")
    if not docs_dir.exists() and not readme_path.exists():
        print("[FAIL] docs/ directory and README.md not found")
        return False
    all_errors: list[str] = []
    all_warnings: list[str] = []
    # Scan README.md first (root level)
    if readme_path.exists():
        try:
            content = readme_path.read_text(encoding="utf-8")
            errors, warnings = scan_file(content, "README.md")
            all_errors.extend(errors)
            all_warnings.extend(warnings)
        except Exception as e:
            all_warnings.append(f"Error reading README.md: {e}")
    # Scan docs/**/*.md
    for md_file in docs_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            errors, warnings = scan_file(content, str(md_file.relative_to(docs_dir.parent)))
            all_errors.extend(errors)
            all_warnings.extend(warnings)
        except Exception as e:
            all_warnings.append(f"Error reading {md_file}: {e}")
    all_passed = True
    if all_errors:
        print("[FAIL] Production readiness claims without proper disclaimers:")
        for err in all_errors:
            print(f"      {err}")
        all_passed = False
    if all_warnings:
        print("\n[WARN] Advisory warnings:")
        for warn in all_warnings:
            print(f"      {warn}")
    print()
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")
    return all_passed


def run_self_test() -> bool:
    """Run self-test mode."""
    print("=== Production Readiness Disclaimer Self-Test ===\n")
    all_passed = True
    # Test: no caveat = error
    errors, _ = scan_file("This is production-ready.", "test.md")
    if errors:
        print("[PASS] production-ready without caveat detected")
    else:
        print("[FAIL]")
        all_passed = False
    # Test: with caveat = warning only
    _, warnings = scan_file("Beta is production-ready but not for production.", "test.md")
    if warnings:
        print("[PASS] caveat generates warning")
    else:
        print("[FAIL]")
        all_passed = False
    print()
    print("SELF-TEST: PASSED" if all_passed else "SELF-TEST: FAILED")
    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify production readiness disclaimer")
    parser.add_argument("--self-test", action="store_true", help="Run self-test mode")
    args = parser.parse_args()
    success = run_self_test() if args.self_test else run_verification()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())