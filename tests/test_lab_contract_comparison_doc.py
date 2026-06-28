#!/usr/bin/env python3
"""Contract inventory test for CNPG vs OTel lab comparison document.

This test verifies that the lab contract comparison document exists and contains
the critical sections required for the comparison ACT.

Exit codes:
    0 - All critical sections present
    1 - Document missing or critical sections absent
"""

from __future__ import annotations

import sys
from pathlib import Path

# Establish repo root as import root
REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "labs" / "cnpg-vs-otel-lab-contract-comparison.md"

# Critical sections that must be present in the comparison document
CRITICAL_SECTIONS = [
    "Current Verdict",
    "Lab Claims",
    "Phase-by-Phase Comparison",
    "Provider and Persistence Parity",
    "Connectivity Failure Classification",
    "Proposed Shared Extraction Boundary",
    "Recommended Next ACT",
]


def check_document_exists() -> tuple[bool, str]:
    """Check that the comparison document exists."""
    if not DOC_PATH.exists():
        return False, f"Comparison document not found: {DOC_PATH}"
    return True, ""


def check_critical_sections() -> tuple[bool, list[str]]:
    """Check that all critical sections are present in the document."""
    content = DOC_PATH.read_text()
    missing = []
    for section in CRITICAL_SECTIONS:
        if f"## {section}" not in content:
            missing.append(section)
    return len(missing) == 0, missing


def main() -> int:
    """Main entry point."""
    print("=== Lab Contract Comparison Document Verification ===")
    print()

    # Check document exists
    exists, error = check_document_exists()
    if not exists:
        print(f"FAIL: {error}")
        return 1
    print(f"OK: Comparison document exists: {DOC_PATH}")

    # Check critical sections
    present, missing = check_critical_sections()
    if not present:
        print("FAIL: Missing critical sections:")
        for section in missing:
            print(f"  - {section}")
        return 1

    print("OK: All critical sections present:")
    for section in CRITICAL_SECTIONS:
        print(f"  - {section}")

    # Check that the "Recommended Next ACT" section contains the expected next ACT title
    content = DOC_PATH.read_text()
    next_act_section_start = content.find("## Recommended Next ACT")
    if next_act_section_start == -1:
        print("FAIL: Recommended Next ACT section not found")
        return 1

    next_act_section = content[next_act_section_start:]
    expected_next_act = "ACT: Bring OTel Lab to Provider/Persisted-Diagnosis Parity with CNPG Before Extraction"
    if expected_next_act not in next_act_section:
        print("FAIL: Expected next ACT not found in Recommended Next ACT section")
        print(f"  Expected: {expected_next_act}")
        return 1

    print()
    print("PASS: Lab contract comparison document verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
