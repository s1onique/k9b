#!/usr/bin/env python
"""Generate initial disposition ledger for all candidates.

Usage:
    python scripts/generate_disposition_ledger.py [--dry-run]
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

from scripts.docs_claim_candidates_shard import read_all_shards
from scripts.docs_claims_registry_loader import read_registry

TODAY = date.today().isoformat()
OUTPUT_PATH = Path("docs/claims/docs_claim_dispositions.csv")

# Columns for the disposition ledger
COLUMNS = [
    "candidate_id",
    "disposition",
    "claim_id",
    "covered_by_claim_id",
    "reason_code",
    "reviewed_at",
    "reviewer_notes",
]


def get_registered_claims() -> set[str]:
    """Get set of claim IDs that exist in the registry."""
    registry, _ = read_registry()
    return {row.get("claim_id", "").strip() for row in registry if row.get("claim_id", "").strip()}


def auto_triage(candidate: dict[str, str], _registered_claims: set[str]) -> tuple[str, str, str, str, str]:
    """Automatically determine disposition for a candidate.

    Returns: (disposition, claim_id, covered_by_claim_id, reason_code, reviewer_notes)
    """
    # Extract key fields for decision making
    reg_status = candidate.get("registration_status", "").strip()
    truth_status = candidate.get("truth_status", "").strip()
    doc_class = candidate.get("doc_class", "").strip()
    reg_claim_id = candidate.get("registered_claim_id", "").strip()
    doc_path = candidate.get("doc_path", "").strip()
    severity = candidate.get("candidate_severity", "").strip()

    # Already registered - link to existing claim
    if reg_status == "registered" and reg_claim_id:
        return (
            "registered_existing_claim",
            reg_claim_id,
            "",
            "already_registered",
            f"Already registered to {reg_claim_id}",
        )

    # Historical docs - mark as historical
    if truth_status == "historical":
        return (
            "historical",
            "",
            "",
            "historical_doc",
            f"From historical doc: {doc_path}",
        )

    # Stale docs - mark as stale
    if truth_status == "stale" or reg_status == "ignored_stale":
        return (
            "stale",
            "",
            "",
            "stale_doc",
            f"From stale doc: {doc_path}",
        )

    # Unknown truth status - treat as stale
    if truth_status == "unknown":
        return (
            "stale",
            "",
            "",
            "stale_doc",
            f"Unknown truth status in: {doc_path}",
        )

    # Current unregistered candidates - need human review
    # Most current docs have low-value prose that doesn't need registry entry
    if truth_status == "current" and reg_status == "unregistered":
        # High-severity normative claims from canonical docs might be worth reviewing
        if severity == "high" and doc_class == "canonical":
            return (
                "needs_new_claim",
                "",
                "",
                "requires_future_human_review",
                f"High-severity from canonical doc: {doc_path}",
            )

        # Most unregistered candidates are low-value prose fragments
        return (
            "ignored_by_policy",
            "",
            "",
            "low_value_context",
            f"Low-value prose fragment from: {doc_path}",
        )

    # Default fallback
    return (
        "ignored_by_policy",
        "",
        "",
        "low_value_context",
        f"Default triage for: {doc_path}",
    )


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    print("=== Generating Disposition Ledger ===\n")

    # Load all candidates
    candidates, error = read_all_shards()
    if error:
        print(f"[ERROR] Failed to load candidates: {error}")
        return 1

    print(f"Loaded {len(candidates)} candidates")

    # Get registered claims for reference
    registered_claims = get_registered_claims()
    print(f"Registry has {len(registered_claims)} claims")

    # Generate dispositions for all candidates
    dispositions: list[dict[str, str]] = []

    for candidate in candidates:
        disposition, claim_id, covered_by, reason_code, notes = auto_triage(candidate, registered_claims)

        dispositions.append({
            "candidate_id": candidate.get("candidate_id", "").strip(),
            "disposition": disposition,
            "claim_id": claim_id,
            "covered_by_claim_id": covered_by,
            "reason_code": reason_code,
            "reviewed_at": TODAY,
            "reviewer_notes": notes,
        })

    # Print summary
    counts: dict[str, int] = {}
    for d in dispositions:
        disp = d["disposition"]
        counts[disp] = counts.get(disp, 0) + 1

    print("\nDisposition summary:")
    for disp, count in sorted(counts.items()):
        print(f"  {disp}: {count}")

    print(f"\nTotal dispositions: {len(dispositions)}")

    if dry_run:
        print("\n[DRY-RUN] Would write to:", OUTPUT_PATH)
        return 0

    # Write CSV
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(dispositions)

    print(f"\n[WROTE] {len(dispositions)} dispositions to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())