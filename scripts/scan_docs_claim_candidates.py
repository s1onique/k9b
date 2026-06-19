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
import sys
from pathlib import Path

from scripts.docs_claim_candidates_contract import GENERATED_CSV
from scripts.docs_claim_candidates_loader import get_scope_files
from scripts.docs_claim_candidates_rules import CSV_FIELDS, scan_document
from scripts.docs_claim_candidates_selftest import run_self_test as run_selftest


def scan_all_documents() -> tuple[list[dict[str, str]], list[str], list[str]]:
    """Scan all documents in scope."""
    all_candidates: list[dict[str, str]] = []
    all_errors: list[str] = []
    all_warnings: list[str] = []

    files_to_scan = get_scope_files()
    print(f"[INFO] Scanning {len(files_to_scan)} documents...\n")

    for doc_path in files_to_scan:
        rel_path = str(doc_path.relative_to(Path(__file__).parent.parent)).replace("\\", "/")
        result = scan_document(doc_path)

        all_candidates.extend(result.candidates)

        if result.errors:
            for error in result.errors:
                all_errors.append(f"{rel_path}: {error}")
        if result.warnings:
            for warning in result.warnings:
                all_warnings.append(f"{rel_path}: {warning}")

        if result.candidates:
            print(f"  [{rel_path}] {len(result.candidates)} candidates")

    return all_candidates, all_errors, all_warnings


def write_candidates_csv(candidates: list[dict[str, str]], output_path: Path) -> None:
    """Write candidates to CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(candidates)


def print_summary(candidates: list[dict[str, str]], errors: list[str], warnings: list[str]) -> None:
    """Print scan summary statistics."""
    print("\n=== Claim Candidate Scan Summary ===\n")
    print(f"Total candidates detected: {len(candidates)}")

    type_counts: dict[str, int] = {}
    for c in candidates:
        for ct in c["detected_claim_types"].split("|"):
            if ct:
                type_counts[ct] = type_counts.get(ct, 0) + 1

    if type_counts:
        print("\nBy claim type:")
        for ct, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {ct}: {count}")

    severity_counts: dict[str, int] = {}
    for c in candidates:
        sev = c["candidate_severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    if severity_counts:
        print("\nBy severity:")
        for sev, count in sorted(severity_counts.items()):
            print(f"  {sev}: {count}")

    status_counts: dict[str, int] = {}
    for c in candidates:
        status = c["truth_status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    if status_counts:
        print("\nBy truth_status:")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")

    reg_counts: dict[str, int] = {}
    for c in candidates:
        reg = c["registration_status"]
        reg_counts[reg] = reg_counts.get(reg, 0) + 1

    if reg_counts:
        print("\nBy registration_status:")
        for reg, count in sorted(reg_counts.items()):
            print(f"  {reg}: {count}")

    doc_counts: dict[str, int] = {}
    for c in candidates:
        doc = c["doc_path"]
        doc_counts[doc] = doc_counts.get(doc, 0) + 1

    if doc_counts:
        print("\nTop 20 docs by candidate count:")
        for doc, count in sorted(doc_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
            print(f"  {doc}: {count}")

    if errors:
        print(f"\nErrors: {len(errors)}")
        for error in errors[:10]:
            print(f"  {error}")

    if warnings:
        print(f"\nWarnings: {len(warnings)}")
        for warning in warnings[:10]:
            print(f"  {warning}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan documentation for claim-like statements")
    parser.add_argument("--self-test", action="store_true", help="Run self-test mode")
    parser.add_argument("--update", action="store_true", help="Scan docs and update generated CSV")
    args = parser.parse_args()

    if args.self_test:
        success = run_selftest()
        return 0 if success else 1

    print("=== Claim Candidate Scanner ===\n")

    candidates, errors, warnings = scan_all_documents()

    if args.update:
        write_candidates_csv(candidates, GENERATED_CSV)
        print(f"\n[INFO] Wrote {len(candidates)} candidates to {GENERATED_CSV}")
    else:
        print(f"\n[INFO] Found {len(candidates)} candidates (use --update to write CSV)")

    print_summary(candidates, errors, warnings)

    if errors:
        print("\nVERIFICATION: COMPLETED WITH ERRORS")
        return 1

    print("\nVERIFICATION: COMPLETED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
