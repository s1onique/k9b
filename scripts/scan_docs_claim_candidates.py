#!/usr/bin/env python
"""Scan documentation for claim-like statements.

This script inspects markdown docs in the repository scope, detects
claim-like statements using deterministic rules, and outputs a candidate
report for review and registry expansion.

Usage:
    python scripts/scan_docs_claim_candidates.py           # scan docs
    python scripts/scan_docs_claim_candidates.py --update  # scan and update generated CSV
    python scripts/scan_docs_claim_candidates.py --self-test  # run self-test

Output:
    docs/claims/generated_claim_candidates.csv

Scope:
    - root README.md
    - docs/**/*.md

Ignores:
    - fenced code blocks
    - command blocks (unless API/config claims)
    - generated/historical docs (advisory only)
    - pure headings
    - pure table separator rows
    - trivial prose below minimum length
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"
GENERATED_CSV = REPO_ROOT / "docs" / "claims" / "generated_claim_candidates.csv"
INVENTORY_CSV = REPO_ROOT / "docs" / "docs_inventory.csv"

# Minimum prose length to consider
MIN_PROSE_LENGTH = 30

# Claim type definitions with their detection patterns
CLAIM_TYPE_PATTERNS: dict[str, dict[str, list[str]]] = {
    "normative": {
        "keywords": [
            r"\bmust\b", r"\bshould\b", r"\bshall\b", r"\brequired\b", r"\brequires\b",
            r"\bnever\b", r"\balways\b", r"\bonly\b", r"\bcannot\b", r"\bdo not\b",
            r"\bMUST\b", r"\bSHOULD\b", r"\bSHALL\b", r"\bREQUIRED\b",
        ],
    },
    "security": {
        "keywords": [
            r"\bauthentication\b", r"\bauthenticated\b", r"\bsession\b", r"\bcookie\b",
            r"\bHttpOnly\b", r"\bSameSite\b", r"\bSecure\b", r"\bpassword hash\b",
            r"\bPBKDF2\b", r"\btoken\b", r"\bRBAC\b", r"\bmutation\b",
            r"\bprotected route\b", r"\bCSRF\b", r"\bXSS\b", r"\binjection\b",
        ],
    },
    "api_contract": {
        "keywords": [
            r"/api/", r"\bGET\b", r"\bPOST\b", r"\bPUT\b", r"\bDELETE\b",
            r"\bendpoint\b", r"\brequest\b", r"\bresponse\b", r"\bpayload\b",
            r"\bGET /", r"\bPOST /", r"\bPUT /", r"\bDELETE /",
        ],
    },
    "config": {
        "keywords": [
            r"\bK9B_[A-Z_]+\b", r"\bHEALTH_UI_\b", r"\bKUBECONFIG\b",
            r"\benvironment variable\b", r"\bHelm value\b", r"\bdefault\b",
            r"\bflag\b", r"\boperator approval\b", r"\bsafeToAutomate\b",
            r"\bworklist\b", r"\brunbook\b", r"\btroubleshooting\b",
            r"\bsession.*timeout\b", r"\bidle.*timeout\b",
        ],
    },
    "data_model": {
        "keywords": [
            r"\blifecycle\b", r"\bstatus\b", r"\bstate\b",
            r"\baggregate root\b", r"\bobject model\b", r"\bfield\b",
            r"\bschema\b", r"\bartifact\b", r"\bEvidenceLink\b",
            r"\bIncident\b", r"\bReviewPacket\b", r"\bSnapshot\b",
            r"\bHealthRun\b", r"\brun_id\b", r"\bcluster_id\b",
            r"\bsource of truth\b", r"\bdurable source\b",
        ],
    },
    "source_of_truth": {
        "keywords": [
            r"\bsource of truth\b", r"\bdurable source\b", r"\bimmutable\b",
            r"\bwrite-once\b", r"\bappend-only\b", r"\bderived projection\b",
            r"\bconvenience alias\b", r"\bnot authoritative\b",
            r"\bimmutable source\b", r"\bderived.*alias\b",
        ],
    },
    "ci_gate": {
        "keywords": [
            r"\bverify_all\.sh\b", r"\bCI\b", r"\bgate\b", r"\bhard-gated\b",
            r"\bblocks merge\b", r"\bthreshold\b", r"\bcoverage\b",
            r"\bworkflow\b", r"\bGitHub Actions\b", r"\bruff\b",
            r"\bmypy\b", r"\bpytest\b", r"\bvitest\b", r"\bhelm lint\b",
            r"\bverification\b", r"\bself-test\b",
        ],
    },
    "performance": {
        "keywords": [
            r"\btimeout\b", r"\binterval\b", r"\bmax age\b", r"\bidle timeout\b",
            r"\bretention\b", r"\bthreshold\b", r"\bduration\b",
            r"\bseconds\b", r"\bminutes\b", r"\bmax.*\d+.*\b",
        ],
    },
}

# Severity scoring based on claim type
SEVERITY_BY_TYPE: dict[str, str] = {
    "security": "high",
    "source_of_truth": "high",
    "ci_gate": "medium",
    "normative": "medium",
    "api_contract": "medium",
    "data_model": "medium",
    "config": "low",
    "performance": "low",
}

# Registration status definitions
REGISTRATION_STATUS_VALUES = {
    "registered",
    "unregistered",
    "ignored_historical",
    "ignored_stale",
    "ignored_low_value",
    "ignored_by_policy",
}

# Candidate severity values
SEVERITY_VALUES = {"high", "medium", "low"}


class ScanResult:
    """Result of scanning a document."""

    def __init__(self) -> None:
        self.candidates: list[dict[str, str]] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []


def generate_candidate_id(doc_path: str, candidate_text: str, claim_type: str, line_number: int) -> str:
    """Generate a deterministic candidate ID from content.
    
    The ID includes line_number to ensure uniqueness per row, even if the same
    claim text appears multiple times in the same document.
    """
    normalized = f"{doc_path}|{line_number}|{candidate_text.lower().strip()}|{claim_type}"
    hash_digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"DOC-CAND-{hash_digest}"


def get_doc_class(doc_path: str) -> str:
    """Get doc_class from inventory."""
    if not INVENTORY_CSV.exists():
        return "unknown"
    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("doc_path", "").strip() == doc_path:
                    return row.get("doc_class", "").strip()
        return "unknown"
    except Exception:
        return "unknown"


def get_truth_status(doc_path: str) -> str:
    """Get truth_status from inventory."""
    if not INVENTORY_CSV.exists():
        return "unknown"
    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("doc_path", "").strip() == doc_path:
                    return row.get("truth_status", "").strip()
        return "unknown"
    except Exception:
        return "unknown"


def get_claim_trace_required(doc_path: str) -> bool:
    """Get claim_trace_required from inventory."""
    if not INVENTORY_CSV.exists():
        return False
    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("doc_path", "").strip() == doc_path:
                    return row.get("claim_trace_required", "").strip().lower() == "true"
        return False
    except Exception:
        return False


def detect_claim_types(text: str) -> list[str]:
    """Detect which claim types match the given text."""
    detected: list[str] = []
    text_lower = text.lower()

    for claim_type, patterns in CLAIM_TYPE_PATTERNS.items():
        keywords = patterns.get("keywords", [])
        for pattern in keywords:
            # Use case-insensitive matching
            if re.search(pattern, text_lower, re.IGNORECASE) is not None:
                if claim_type not in detected:
                    detected.append(claim_type)
                break

    return detected


def determine_severity(claim_types: list[str]) -> str:
    """Determine severity based on claim types present."""
    if not claim_types:
        return "low"

    # Check for high severity types first
    for claim_type in claim_types:
        if SEVERITY_BY_TYPE.get(claim_type) == "high":
            return "high"

    # Then medium
    for claim_type in claim_types:
        if SEVERITY_BY_TYPE.get(claim_type) == "medium":
            return "medium"

    return "low"


def determine_registration_status(doc_path: str, truth_status: str, doc_class: str) -> str:
    """Determine initial registration status based on doc classification."""
    if doc_class in ("historical", "external_import"):
        return "ignored_historical"
    if truth_status in ("historical",):
        return "ignored_historical"
    if truth_status in ("stale", "unknown"):
        return "ignored_stale"
    if doc_class == "generated":
        return "ignored_by_policy"
    return "unregistered"


def is_code_block(text: str) -> bool:
    """Check if text appears to be inside a code block."""
    return text.strip().startswith(("```", "    ", "\t"))


def is_table_separator(text: str) -> bool:
    """Check if text is a table separator row."""
    stripped = text.strip()
    return bool(stripped) and all(c in "|-: " for c in stripped) and "|" in stripped


def is_pure_heading(text: str) -> bool:
    """Check if text is just a heading."""
    stripped = text.strip()
    return bool(stripped) and stripped.startswith("#") and "\n" not in stripped


def is_trivial_prose(text: str, claim_types: list[str]) -> bool:
    """Check if text is too short or trivial to be a claim."""
    if len(text.strip()) < MIN_PROSE_LENGTH:
        return True

    # If no claim types detected, consider it low-value unless it's normative
    if not claim_types:
        return True

    return False


def is_stale_historical_doc(doc_path: str, truth_status: str, doc_class: str) -> bool:
    """Check if doc is stale or historical."""
    if doc_class in ("historical", "external_import"):
        return True
    if truth_status in ("historical", "stale", "unknown"):
        return True
    return False


def extract_candidate_text(line: str, doc_path: str, line_num: int) -> str:
    """Extract candidate text from a line, stripping formatting."""
    text = line.strip()

    # Remove markdown formatting
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
    text = re.sub(r"[*_`#]+", "", text)  # bold, italic, code, headings
    text = re.sub(r"\s+", " ", text)  # normalize whitespace
    text = text.strip()

    return text


def scan_document(doc_path: Path) -> ScanResult:
    """Scan a single document for claim candidates."""
    result = ScanResult()
    rel_path = str(doc_path.relative_to(REPO_ROOT)).replace("\\", "/")

    # Get inventory metadata
    truth_status = get_truth_status(rel_path)
    doc_class = get_doc_class(rel_path)
    claim_trace_required = get_claim_trace_required(rel_path)
    is_stale = is_stale_historical_doc(rel_path, truth_status, doc_class)

    try:
        content = doc_path.read_text(encoding="utf-8")
    except Exception as e:
        result.errors.append(f"Failed to read {rel_path}: {e}")
        return result

    # Track code block state
    in_code_block = False

    lines = content.split("\n")

    for line_num, line in enumerate(lines, start=1):
        # Track code blocks
        if re.match(r"```", line.strip()):
            in_code_block = not in_code_block
            continue

        # Skip if inside code block
        if in_code_block:
            continue

        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            continue

        # Skip pure headings (but not h2+ sections with content)
        if is_pure_heading(stripped) and not any(stripped.startswith(f"{'#' * i} ") for i in range(1, 5)):
            continue

        # Skip table separators
        if is_table_separator(stripped):
            continue

        # Skip code block lines (indented)
        if is_code_block(stripped):
            continue

        # Extract candidate text
        candidate_text = extract_candidate_text(stripped, rel_path, line_num)

        # Skip trivial prose
        if len(candidate_text) < MIN_PROSE_LENGTH:
            continue

        # Detect claim types
        claim_types = detect_claim_types(candidate_text)

        # Skip if no claim types detected
        if not claim_types:
            continue

        # Determine severity
        severity = determine_severity(claim_types)

        # Determine registration status
        registration_status = determine_registration_status(rel_path, truth_status, doc_class)

        # Determine if claim_trace_required
        trace_required = "true" if claim_trace_required else "false"

        # Generate candidate ID (include line_num for uniqueness)
        candidate_id = generate_candidate_id(rel_path, candidate_text, "|".join(claim_types), line_num)

        # Build anchor from context
        anchor = f"line-{line_num}"

        # Build detection rules string
        detection_rules = "|".join(claim_types)

        # Create candidate record
        candidate = {
            "candidate_id": candidate_id,
            "doc_path": rel_path,
            "line_number": str(line_num),
            "anchor": anchor,
            "candidate_text": candidate_text,
            "detected_claim_types": "|".join(claim_types),
            "detection_rules": detection_rules,
            "doc_class": doc_class,
            "truth_status": truth_status,
            "claim_trace_required": trace_required,
            "candidate_severity": severity,
            "registered_claim_id": "",
            "registration_status": registration_status,
            "notes": "",
        }

        result.candidates.append(candidate)

    return result


def scan_all_documents() -> tuple[list[dict[str, str]], list[str], list[str]]:
    """Scan all documents in scope."""
    all_candidates: list[dict[str, str]] = []
    all_errors: list[str] = []
    all_warnings: list[str] = []

    # Scope: README.md and docs/**/*.md
    files_to_scan: list[Path] = []

    # Root README.md
    readme = REPO_ROOT / "README.md"
    if readme.exists():
        files_to_scan.append(readme)

    # docs/**/*.md
    if DOCS_DIR.exists():
        for md_file in DOCS_DIR.rglob("*.md"):
            files_to_scan.append(md_file)

    print(f"[INFO] Scanning {len(files_to_scan)} documents...\n")

    for doc_path in sorted(files_to_scan):
        rel_path = str(doc_path.relative_to(REPO_ROOT)).replace("\\", "/")
        result = scan_document(doc_path)

        all_candidates.extend(result.candidates)

        if result.errors:
            for error in result.errors:
                all_errors.append(f"{rel_path}: {error}")
        if result.warnings:
            for warning in result.warnings:
                all_warnings.append(f"{rel_path}: {warning}")

        # Progress indicator
        if result.candidates:
            print(f"  [{rel_path}] {len(result.candidates)} candidates")

    return all_candidates, all_errors, all_warnings


def write_candidates_csv(candidates: list[dict[str, str]], output_path: Path) -> None:
    """Write candidates to CSV file."""
    fieldnames = [
        "candidate_id",
        "doc_path",
        "line_number",
        "anchor",
        "candidate_text",
        "detected_claim_types",
        "detection_rules",
        "doc_class",
        "truth_status",
        "claim_trace_required",
        "candidate_severity",
        "registered_claim_id",
        "registration_status",
        "notes",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candidates)


def print_summary(candidates: list[dict[str, str]], errors: list[str], warnings: list[str]) -> None:
    """Print scan summary statistics."""
    print("\n=== Claim Candidate Scan Summary ===\n")
    print(f"Total candidates detected: {len(candidates)}")

    # Count by claim type
    type_counts: dict[str, int] = {}
    for c in candidates:
        for ct in c["detected_claim_types"].split("|"):
            if ct:
                type_counts[ct] = type_counts.get(ct, 0) + 1

    if type_counts:
        print("\nBy claim type:")
        for ct, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {ct}: {count}")

    # Count by severity
    severity_counts: dict[str, int] = {}
    for c in candidates:
        sev = c["candidate_severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    if severity_counts:
        print("\nBy severity:")
        for sev, count in sorted(severity_counts.items()):
            print(f"  {sev}: {count}")

    # Count by truth_status
    status_counts: dict[str, int] = {}
    for c in candidates:
        status = c["truth_status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    if status_counts:
        print("\nBy truth_status:")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")

    # Count by registration_status
    reg_counts: dict[str, int] = {}
    for c in candidates:
        reg = c["registration_status"]
        reg_counts[reg] = reg_counts.get(reg, 0) + 1

    if reg_counts:
        print("\nBy registration_status:")
        for reg, count in sorted(reg_counts.items()):
            print(f"  {reg}: {count}")

    # Top 20 docs by candidate count
    doc_counts: dict[str, int] = {}
    for c in candidates:
        doc = c["doc_path"]
        doc_counts[doc] = doc_counts.get(doc, 0) + 1

    if doc_counts:
        print("\nTop 20 docs by candidate count:")
        for doc, count in sorted(doc_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
            print(f"  {doc}: {count}")

    # Errors and warnings
    if errors:
        print(f"\nErrors: {len(errors)}")
        for error in errors[:10]:
            print(f"  {error}")

    if warnings:
        print(f"\nWarnings: {len(warnings)}")
        for warning in warnings[:10]:
            print(f"  {warning}")


# Self-test cases - tests key scanner behaviors
SELF_TEST_CASES: list[dict[str, object]] = [
    {
        "name": "detects normative MUST claim",
        "input": "The agent MUST never mutate live clusters.",
        "expect_types": True,  # Should detect some types
        "expect_severity_above": "low",  # Should be medium or high
    },
    {
        "name": "detects security/auth claim",
        "input": "Sessions use PBKDF2 for password hashing with 600000 iterations.",
        "expect_types": True,
        "expect_severity": "high",  # Should be high (security)
    },
    {
        "name": "detects API route claim",
        "input": "POST /api/auth/login accepts username and password.",
        "expect_types": True,
        "expect_severity": "medium",  # api_contract is medium
    },
    {
        "name": "detects config claim",
        "input": "K9B_AUTH_ENABLED=true enables session-based authentication.",
        "expect_types": True,
        "expect_severity_above": "low",
    },
    {
        "name": "detects data-model claim",
        "input": "Incident lifecycle states include open, investigating, and resolved.",
        "expect_types": True,
        "expect_severity": "medium",  # data_model is medium
    },
    {
        "name": "detects source-of-truth claim",
        "input": "Diagnostic pack ZIPs are immutable source-of-truth artifacts.",
        "expect_types": True,
        "expect_severity": "high",  # source_of_truth is high
    },
    {
        "name": "detects CI/gate claim",
        "input": "verify_all.sh is the canonical gate that blocks merge on failure.",
        "expect_types": True,
        "expect_severity_above": "low",
    },
    {
        "name": "detects performance claim",
        "input": "Session idle timeout defaults to 1800 seconds (30 minutes).",
        "expect_types": True,
        "expect_severity_above": "low",
    },
    {
        "name": "assigns stable candidate IDs",
        "input": "The agent must never mutate live clusters.",
        "expect_id_pattern": r"^DOC-CAND-[a-f0-9]{12}$",
    },
    {
        "name": "deterministic ID generation",
        "input": "The agent must never mutate live clusters.",
        "expect_same_id_twice": True,
    },
]


def run_self_test() -> bool:
    """Run self-test mode with fixture cases."""
    print("=== Claim Candidate Scanner Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        input_text = str(case.get("input", ""))

        # Detect claim types
        detected_types = detect_claim_types(input_text)

        # Check type detection
        if case.get("expect_types"):
            if not detected_types:
                print(f"  [FAIL] Expected to detect types, got none")
                all_passed = False
                continue
            print(f"  [OK] Detected types: {detected_types}")

        # Check severity
        severity = determine_severity(detected_types)
        if "expect_severity" in case:
            expected = case["expect_severity"]
            if severity != expected:
                print(f"  [FAIL] Expected severity {expected}, got {severity}")
                all_passed = False
                continue
        elif "expect_severity_above" in case:
            threshold = case["expect_severity_above"]
            severity_order = {"low": 0, "medium": 1, "high": 2}
            if severity_order.get(severity, 0) < severity_order.get(threshold, 0):
                print(f"  [FAIL] Expected severity above {threshold}, got {severity}")
                all_passed = False
                continue

        print(f"  [OK] Severity: {severity}")

        # Check ID pattern
        if "expect_id_pattern" in case:
            pattern = case["expect_id_pattern"]
            doc_path = "test.md"
            line_number = 42
            candidate_id = generate_candidate_id(doc_path, input_text, "|".join(detected_types) if detected_types else "unknown", line_number)
            if not re.match(pattern, candidate_id):
                print(f"  [FAIL] ID {candidate_id} does not match pattern {pattern}")
                all_passed = False
                continue
            print(f"  [OK] ID: {candidate_id}")

        # Check deterministic generation
        if case.get("expect_same_id_twice"):
            doc_path = "test.md"
            line_number = 42
            claim_type = "|".join(detected_types) if detected_types else "unknown"
            id1 = generate_candidate_id(doc_path, input_text, claim_type, line_number)
            id2 = generate_candidate_id(doc_path, input_text, claim_type, line_number)
            if id1 != id2:
                print(f"  [FAIL] IDs not deterministic: {id1} != {id2}")
                all_passed = False
                continue
            print(f"  [OK] IDs are deterministic")

        print("  [OK] Passed")

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan documentation for claim-like statements")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode with inline fixture cases",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Scan docs and update generated CSV",
    )
    args = parser.parse_args()

    if args.self_test:
        success = run_self_test()
        return 0 if success else 1

    print("=== Claim Candidate Scanner ===\n")

    # Scan all documents
    candidates, errors, warnings = scan_all_documents()

    # Write output
    if args.update:
        write_candidates_csv(candidates, GENERATED_CSV)
        print(f"\n[INFO] Wrote {len(candidates)} candidates to {GENERATED_CSV}")
    else:
        # Just print to stdout
        print(f"\n[INFO] Found {len(candidates)} candidates (use --update to write CSV)")

    # Print summary
    print_summary(candidates, errors, warnings)

    if errors:
        print("\nVERIFICATION: COMPLETED WITH ERRORS")
        return 1

    print("\nVERIFICATION: COMPLETED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
