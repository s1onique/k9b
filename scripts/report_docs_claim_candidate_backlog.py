#!/usr/bin/env python
"""Report documentation claim candidate backlog after ACT 5.0 and ACT 5.2.

This script summarizes and ranks remaining documentation claim candidates
for future review tranches. It is reporting-only and does not modify any CSV data.

Usage:
    python scripts/report_docs_claim_candidate_backlog.py                    # summary
    python scripts/report_docs_claim_candidate_backlog.py --top 100         # top 100
    python scripts/report_docs_claim_candidate_backlog.py --json /tmp/out.json
    python scripts/report_docs_claim_candidate_backlog.py --tsv /tmp/out.tsv
    python scripts/report_docs_claim_candidate_backlog.py --self-test
    python scripts/report_docs_claim_candidate_backlog.py --include-reviewed
    python scripts/report_docs_claim_candidate_backlog.py --disposition ignored_by_policy
    python scripts/report_docs_claim_candidate_backlog.py --doc docs/security/operator-auth-design.md

Exit codes:
    0 = success (including --self-test pass)
    1 = failure (parse error, file not found, self-test fail)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import cast

# High-value doc path terms (security-relevant or operator-facing)
HIGH_VALUE_PATH_TERMS = {
    "security",
    "auth",
    "incident",
    "diagnosis",
    "automatic",
    "runtime",
    "artifact",
    "evidence",
    "review-packets",
    "operator",
    "ci",
    "gate",
    "truthfulness",
    "data-model",
}

# Normative text terms
NORMATIVE_TEXT_TERMS = {
    "must",
    "should",
    "cannot",
    "never",
    "only",
    "guarantee",
    "required",
    "protected",
    "authenticated",
    "secure",
    "immutable",
    "append-only",
    "read-only",
    "mutation",
    "source of truth",
    "evidence",
    "invariant",
    "production",
    "operator",
}

# Generic note patterns to detect low-value ignored notes
GENERIC_NOTE_PATTERNS = [
    re.compile(r"^Low-value prose fragment from:"),
    re.compile(r"^From stale doc:"),
    re.compile(r"^From historical doc:"),
    re.compile(r"^Already registered to DOC-CLAIM-"),
]

# ACT review markers (case-insensitive, handles trailing punctuation)
# Actual data contains "(ACT 5.0 review)." and "(ACT 5.2 review)."
_ACT_5_0_RE = re.compile(r"\bACT\s*5\.0\s*review\b", re.IGNORECASE)
_ACT_5_2_RE = re.compile(r"\bACT\s*5\.2\s*review\b", re.IGNORECASE)


def get_repo_root() -> Path:
    """Get repository root path."""
    return Path(__file__).parent.parent


def get_disposition_shard_paths() -> list[Path]:
    """Get all disposition shard file paths."""
    claims_dir = get_repo_root() / "docs" / "claims"
    return sorted(claims_dir.glob("docs_claim_dispositions-shard-*.csv"))


def get_candidate_shard_paths() -> list[Path]:
    """Get all candidate shard file paths."""
    claims_dir = get_repo_root() / "docs" / "claims"
    return sorted(claims_dir.glob("generated_claim_candidates-shard-*.csv"))


def read_dispositions() -> tuple[list[dict[str, str]], str | None]:
    """Read all disposition shards. Returns (rows, error)."""
    shard_paths = get_disposition_shard_paths()
    if not shard_paths:
        return [], "No disposition shards found"
    
    all_rows: list[dict[str, str]] = []
    for shard_path in shard_paths:
        try:
            with open(shard_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                all_rows.extend(list(reader))
        except Exception as e:
            return [], f"Error reading {shard_path}: {e}"
    
    return all_rows, None


def read_candidates() -> tuple[list[dict[str, str]], str | None]:
    """Read all candidate shards. Returns (rows, error)."""
    shard_paths = get_candidate_shard_paths()
    if not shard_paths:
        return [], "No candidate shards found"
    
    all_rows: list[dict[str, str]] = []
    for shard_path in shard_paths:
        try:
            with open(shard_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                all_rows.extend(list(reader))
        except Exception as e:
            return [], f"Error reading {shard_path}: {e}"
    
    return all_rows, None


def read_inventory() -> tuple[dict[str, str], str | None]:
    """Read inventory and return dict of doc_path -> truth_status."""
    repo_root = get_repo_root()
    inventory_path = repo_root / "docs" / "docs_inventory.csv"
    
    if not inventory_path.exists():
        return {}, "Inventory file not found"
    
    inventory: dict[str, str] = {}
    try:
        with open(inventory_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                doc_path = row.get("doc_path", "").strip()
                truth_status = row.get("truth_status", "").strip()
                if doc_path:
                    inventory[doc_path] = truth_status
        return inventory, None
    except Exception as e:
        return {}, f"Error reading inventory: {e}"


def has_act_5_0_marker(notes: str) -> bool:
    """Check if reviewer notes contain ACT 5.0 marker."""
    return bool(_ACT_5_0_RE.search(notes))


def has_act_5_2_marker(notes: str) -> bool:
    """Check if reviewer notes contain ACT 5.2 marker."""
    return bool(_ACT_5_2_RE.search(notes))


def has_any_act_marker(notes: str) -> bool:
    """Check if reviewer notes contain any ACT review marker."""
    return has_act_5_0_marker(notes) or has_act_5_2_marker(notes)


def is_generic_low_value_note(notes: str) -> bool:
    """Check if reviewer notes match generic low-value patterns."""
    notes = notes.strip()
    for pattern in GENERIC_NOTE_PATTERNS:
        if pattern.match(notes):
            return True
    return False


def is_stale_disposition(disposition: str) -> bool:
    """Check if disposition indicates stale."""
    return disposition == "stale"


def is_historical_disposition(disposition: str) -> bool:
    """Check if disposition indicates historical."""
    return disposition == "historical"


def is_high_value_doc(doc_path: str) -> bool:
    """Check if doc path contains high-value terms."""
    doc_path_lower = doc_path.lower()
    for term in HIGH_VALUE_PATH_TERMS:
        if term in doc_path_lower:
            return True
    return False


def has_normative_text(candidate_text: str) -> bool:
    """Check if candidate text contains normative language."""
    text_lower = candidate_text.lower()
    # Simple word boundary check
    words = re.findall(r"\b\w+\b", text_lower)
    for term in NORMATIVE_TEXT_TERMS:
        if term in words:
            return True
        # Also check multi-word terms
        if " " in term and term in text_lower:
            return True
    return False


def get_truth_status_from_inventory(doc_path: str, inventory: dict[str, str]) -> str:
    """Get truth_status for a doc from inventory."""
    return inventory.get(doc_path, "")


def is_stale_doc(doc_path: str, inventory: dict[str, str]) -> bool:
    """Check if doc is marked stale in inventory."""
    return get_truth_status_from_inventory(doc_path, inventory) == "stale"


def is_historical_doc(doc_path: str, inventory: dict[str, str]) -> bool:
    """Check if doc is marked historical in inventory."""
    return get_truth_status_from_inventory(doc_path, inventory) == "historical"


def compute_risk_score(
    disposition: str,
    reason_code: str,
    notes: str,
    doc_path: str,
    candidate_text: str,
    inventory: dict[str, str],
    has_act_5_0: bool,
    has_act_5_2: bool,
) -> tuple[int, list[str]]:
    """Compute risk score and reasons for a candidate.
    
    Returns (score, reasons).
    """
    score = 0
    reasons: list[str] = []
    
    # Base score adjustments
    if disposition == "ignored_by_policy" and is_generic_low_value_note(notes):
        score += 20
        reasons.append("generic_ignored_note")
    
    if disposition == "covered_by_existing_claim" and is_generic_low_value_note(notes):
        score += 12
        reasons.append("covered_note_weak")
    
    # High-value doc check
    if is_high_value_doc(doc_path):
        # Find which high-value terms matched
        doc_lower = doc_path.lower()
        for term in HIGH_VALUE_PATH_TERMS:
            if term in doc_lower:
                reasons.append(f"high_value_doc:{term}")
        score += 10
        # Extra boost if stale/historical but in high-value doc
        if is_stale_doc(doc_path, inventory):
            score += 5
            reasons.append("high_value_but_stale")
        if is_historical_doc(doc_path, inventory):
            score += 3
            reasons.append("high_value_but_historical")
    
    # Normative text check
    if has_normative_text(candidate_text):
        score += 8
        reasons.append("normative_text")
        # Identify specific normative terms
        text_lower = candidate_text.lower()
        for term in ["must", "should", "cannot", "never", "required", "guarantee"]:
            if f" {term} " in f" {text_lower} " or text_lower.startswith(f"{term} "):
                reasons.append(f"normative:{term}")
                break
    
    # Reviewer note quality check (no ACT marker)
    if not has_any_act_marker(notes):
        score += 4
        reasons.append("no_act_marker")
    
    # Already reviewed deprioritization
    if has_act_5_0:
        score -= 20
        reasons.append("deprioritized:act_5_0_reviewed")
    elif has_act_5_2:
        score -= 20
        reasons.append("deprioritized:act_5_2_reviewed")
    
    # Stale/historical doc deprioritization
    if is_stale_doc(doc_path, inventory) and not is_high_value_doc(doc_path):
        score -= 12
        reasons.append("deprioritized:stale")
    elif is_historical_doc(doc_path, inventory) and not is_high_value_doc(doc_path):
        score -= 15
        reasons.append("deprioritized:historical")
    
    return score, reasons


CandidateData = dict[str, str]
BacklogEntry = dict[str, str | int | list[str]]


def build_backlog(
    candidates: list[CandidateData],
    dispositions: list[CandidateData],
    inventory: dict[str, str],
    include_reviewed: bool = False,
    disposition_filter: str | None = None,
    doc_filter: str | None = None,
) -> list[BacklogEntry]:
    """Build ranked backlog entries from candidates and dispositions."""
    # Index dispositions by candidate_id
    disp_by_id: dict[str, CandidateData] = {}
    for disp in dispositions:
        cid = disp.get("candidate_id", "").strip()
        if cid:
            disp_by_id[cid] = disp
    
    entries: list[BacklogEntry] = []
    
    for cand in candidates:
        cid = cand.get("candidate_id", "").strip()
        if not cid:
            continue
        
        disp = disp_by_id.get(cid, {})
        disposition = disp.get("disposition", "").strip()
        reason_code = disp.get("reason_code", "").strip()
        reviewed_at = disp.get("reviewed_at", "").strip()
        notes = disp.get("reviewer_notes", "").strip()
        
        doc_path = cand.get("doc_path", "").strip()
        candidate_text = cand.get("candidate_text", "").strip()
        
        # Apply filters
        if disposition_filter and disposition != disposition_filter:
            continue
        
        if doc_filter and doc_filter not in doc_path:
            continue
        
        # Check ACT markers
        has_5_0 = has_act_5_0_marker(notes)
        has_5_2 = has_act_5_2_marker(notes)
        has_any = has_any_act_marker(notes)
        
        # Skip reviewed entries if not including them
        if not include_reviewed and has_any:
            continue
        
        # Compute risk score
        risk_score, risk_reasons = compute_risk_score(
            disposition=disposition,
            reason_code=reason_code,
            notes=notes,
            doc_path=doc_path,
            candidate_text=candidate_text,
            inventory=inventory,
            has_act_5_0=has_5_0,
            has_act_5_2=has_5_2,
        )
        
        entry: BacklogEntry = {
            "candidate_id": cid,
            "disposition": disposition,
            "reason_code": reason_code,
            "source_doc_path": doc_path,
            "candidate_text": candidate_text[:200] + "..." if len(candidate_text) > 200 else candidate_text,
            "reviewed_at": reviewed_at,
            "reviewer_notes": notes[:150] + "..." if len(notes) > 150 else notes,
            "score": risk_score,
            "risk_reasons": risk_reasons,
            "is_act_5_0_reviewed": has_5_0,
            "is_act_5_2_reviewed": has_5_2,
            "has_any_act_review_marker": has_any,
            "is_generic_low_value_note": is_generic_low_value_note(notes),
            "is_stale": is_stale_disposition(disposition),
            "is_historical": is_historical_disposition(disposition),
            "is_stale_doc": is_stale_doc(doc_path, inventory),
            "is_historical_doc": is_historical_doc(doc_path, inventory),
            "is_high_value_doc": is_high_value_doc(doc_path),
        }
        
        entries.append(entry)
    
    # Sort by score descending, then by candidate_id for determinism
    entries.sort(key=lambda e: (-cast(int, e["score"]), cast(str, e["candidate_id"])))
    
    return entries


def compute_summary(entries: list[BacklogEntry]) -> dict:
    """Compute summary statistics from backlog entries."""
    total = len(entries)
    
    # Disposition counts
    disp_counts: dict[str, int] = defaultdict(int)
    reason_counts: dict[str, int] = defaultdict(int)
    doc_counts: dict[str, int] = defaultdict(int)
    generic_counts: dict[str, int] = defaultdict(int)
    doc_risk_scores: dict[str, list[int]] = defaultdict(list)
    
    act_5_0_count = 0
    act_5_2_count = 0
    unreviewed_count = 0
    
    for entry in entries:
        disp = entry.get("disposition", "")
        reason = entry.get("reason_code", "")
        doc = entry.get("source_doc_path", "")
        
        disp_counts[cast(str, disp)] += 1
        if reason:
            reason_counts[cast(str, reason)] += 1
        
        # Generic note counts by disposition prefix
        if entry.get("is_generic_low_value_note"):
            generic_counts[cast(str, disp)] += 1
        
        # Doc counts for unreviewed generic ignored
        if disp == "ignored_by_policy" and entry.get("is_generic_low_value_note") and not entry.get("has_any_act_review_marker"):
            doc_counts[cast(str, doc)] += 1
        
        # Doc risk score tracking
        doc_risk_scores[cast(str, doc)].append(cast(int, entry["score"]))
        
        # Review marker counts
        if entry.get("is_act_5_0_reviewed"):
            act_5_0_count += 1
        elif entry.get("is_act_5_2_reviewed"):
            act_5_2_count += 1
        elif not entry.get("has_any_act_review_marker"):
            unreviewed_count += 1
    
    # Top docs by unreviewed generic ignored
    top_docs_by_generic = sorted(doc_counts.items(), key=lambda x: -x[1])[:20]
    
    # Top docs by total risk score
    doc_total_risk: dict[str, tuple[int, int]] = {}
    for doc, scores in doc_risk_scores.items():
        doc_total_risk[doc] = (sum(scores), len(scores))
    top_docs_by_risk = sorted(doc_total_risk.items(), key=lambda x: -x[1][0])[:20]
    
    return {
        "total_candidates": total,
        "disposition_counts": dict(sorted(disp_counts.items())),
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "review_marker_counts": {
            "act_5_0": act_5_0_count,
            "act_5_2": act_5_2_count,
            "unreviewed": unreviewed_count,
        },
        "generic_note_counts": dict(sorted(generic_counts.items())),
        "top_docs_by_unreviewed_generic_ignored": [
            {"doc_path": doc, "count": count}
            for doc, count in top_docs_by_generic
        ],
        "top_docs_by_risk": [
            {"doc_path": doc, "total_score": score, "candidate_count": count}
            for doc, (score, count) in top_docs_by_risk
        ],
    }


def print_summary(entries: list[BacklogEntry], summary: dict) -> None:
    """Print human-readable summary to stdout."""
    print("\nDocumentation claim candidate backlog\n")
    
    print("Totals:")
    print(f"  total candidates: {summary['total_candidates']}")
    
    print("\n  By disposition:")
    for disp, count in summary["disposition_counts"].items():
        print(f"    {disp}: {count}")
    
    print("\n  By reason_code:")
    for reason, count in summary["reason_code_counts"].items():
        print(f"    {reason}: {count}")
    
    print("\n  By review marker:")
    print(f"    ACT 5.0 reviewed: {summary['review_marker_counts']['act_5_0']}")
    print(f"    ACT 5.2 reviewed: {summary['review_marker_counts']['act_5_2']}")
    print(f"    unreviewed/no ACT marker: {summary['review_marker_counts']['unreviewed']}")
    
    print("\nGeneric notes remaining (by disposition):")
    for disp, count in summary["generic_note_counts"].items():
        print(f"  {disp}: {count}")
    
    total_generic = sum(summary["generic_note_counts"].values())
    print(f"\n  Total generic notes: {total_generic}")
    
    print("\nTop docs by remaining unreviewed generic ignored notes:")
    for item in summary["top_docs_by_unreviewed_generic_ignored"][:10]:
        print(f"  {item['doc_path']}: {item['count']}")
    
    print("\nTop docs by risk score:")
    for item in summary["top_docs_by_risk"][:10]:
        print(f"  {item['doc_path']}: score={item['total_score']}, count={item['candidate_count']}")


def print_recommended(entries: list[BacklogEntry], top_n: int = 50) -> None:
    """Print recommended next tranche candidates."""
    print(f"\nRecommended next tranche (top {top_n}):")
    
    unreviewed_entries = [
        e for e in entries
        if not e.get("has_any_act_review_marker")
    ]
    
    for entry in unreviewed_entries[:top_n]:
        reasons = cast(list, entry.get("risk_reasons", []))
        print(f"\n  {entry['candidate_id']}")
        print(f"    disposition: {entry['disposition']}")
        print(f"    score: {entry['score']}")
        print(f"    reasons: {', '.join(reasons)}")
        print(f"    doc: {entry['source_doc_path']}")
        notes = cast(str, entry.get("reviewer_notes", ""))
        if notes:
            print(f"    note: {notes[:100]}")


def write_json(entries: list[BacklogEntry], summary: dict, output_path: Path) -> None:
    """Write deterministic JSON output."""
    # Build recommended candidates (unreviewed, top 100)
    unreviewed = [
        e for e in entries
        if not e.get("has_any_act_review_marker")
    ]
    
    recommended = []
    for entry in unreviewed[:100]:
        recommended.append({
            "candidate_id": entry["candidate_id"],
            "score": entry["score"],
            "risk_reasons": entry["risk_reasons"],
            "disposition": entry["disposition"],
            "reason_code": entry["reason_code"],
            "source_doc_path": entry["source_doc_path"],
            "reviewer_notes": entry["reviewer_notes"],
            "candidate_text": entry["candidate_text"],
        })
    
    output = {
        "total_candidates": summary["total_candidates"],
        "disposition_counts": summary["disposition_counts"],
        "reason_code_counts": summary["reason_code_counts"],
        "review_marker_counts": summary["review_marker_counts"],
        "generic_note_counts": summary["generic_note_counts"],
        "top_docs_by_unreviewed_generic_ignored": summary["top_docs_by_unreviewed_generic_ignored"],
        "top_docs_by_risk": summary["top_docs_by_risk"],
        "recommended_candidates": recommended,
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, sort_keys=True)
        f.write("\n")


def write_tsv(entries: list[BacklogEntry], output_path: Path) -> None:
    """Write TSV output for future tranche selection."""
    unreviewed = [
        e for e in entries
        if not e.get("has_any_act_review_marker")
    ]
    
    fieldnames = [
        "score",
        "candidate_id",
        "disposition",
        "reason_code",
        "source_doc_path",
        "risk_reasons",
        "reviewed_at",
        "reviewer_notes",
        "candidate_text",
    ]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
            delimiter="\t",
        )
        writer.writeheader()
        for entry in unreviewed:
            # Convert risk_reasons list to comma-separated string
            row = dict(entry)
            row["risk_reasons"] = ",".join(cast(list, entry["risk_reasons"]))
            writer.writerow(row)


def run_self_test() -> bool:
    """Run self-test fixtures. Returns True if all pass."""
    print("=== Self-Test Fixtures ===\n")
    
    all_passed = True
    
    # Fixture 1: generic ignored note is scored and ranked
    score1, reasons1 = compute_risk_score(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Low-value prose fragment from: docs/foo.md",
        doc_path="docs/security/bar.md",
        candidate_text="This must be handled securely.",
        inventory={},
        has_act_5_0=False,
        has_act_5_2=False,
    )
    if score1 > 30 and "generic_ignored_note" in reasons1 and "high_value_doc:security" in reasons1:
        print("[PASS] ranks generic ignored note")
    else:
        print(f"[FAIL] ranks generic ignored note: score={score1}, reasons={reasons1}")
        all_passed = False
    
    # Fixture 2: ACT 5.0 reviewed row is deprioritized
    score2, reasons2 = compute_risk_score(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Some note (ACT 5.0 review)",
        doc_path="docs/security/bar.md",
        candidate_text="This must be handled securely.",
        inventory={},
        has_act_5_0=True,
        has_act_5_2=False,
    )
    if score2 < 0 and "deprioritized:act_5_0_reviewed" in reasons2:
        print("[PASS] deprioritizes ACT 5.0 reviewed row")
    else:
        print(f"[FAIL] deprioritizes ACT 5.0: score={score2}, reasons={reasons2}")
        all_passed = False
    
    # Fixture 3: ACT 5.2 reviewed row is deprioritized
    score3, reasons3 = compute_risk_score(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Some note (ACT 5.2 review)",
        doc_path="docs/security/bar.md",
        candidate_text="This must be handled securely.",
        inventory={},
        has_act_5_0=False,
        has_act_5_2=True,
    )
    if score3 < 0 and "deprioritized:act_5_2_reviewed" in reasons3:
        print("[PASS] deprioritizes ACT 5.2 reviewed row")
    else:
        print(f"[FAIL] deprioritizes ACT 5.2: score={score3}, reasons={reasons3}")
        all_passed = False
    
    # Fixture 4: high-value doc path increases score
    score4, reasons4 = compute_risk_score(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Some generic note",
        doc_path="docs/security/auth.md",
        candidate_text="Normal text here.",
        inventory={"docs/security/auth.md": "current"},
        has_act_5_0=False,
        has_act_5_2=False,
    )
    if "high_value_doc:security" in reasons4 and "high_value_doc:auth" in reasons4 and score4 > 10:
        print("[PASS] high-value doc path increases score")
    else:
        print(f"[FAIL] high-value doc: score={score4}, reasons={reasons4}")
        all_passed = False
    
    # Fixture 5: normative candidate text increases score
    score5, reasons5 = compute_risk_score(
        disposition="ignored_by_policy",
        reason_code="low_value_context",
        notes="Some generic note",
        doc_path="docs/normal.md",
        candidate_text="The system must handle authentication correctly.",
        inventory={},
        has_act_5_0=False,
        has_act_5_2=False,
    )
    if "normative_text" in reasons5 and score5 > 10:
        print("[PASS] normative candidate text increases score")
    else:
        print(f"[FAIL] normative text: score={score5}, reasons={reasons5}")
        all_passed = False
    
    # Fixture 6: stale/historical rows are normally deprioritized
    score6, reasons6 = compute_risk_score(
        disposition="stale",
        reason_code="stale_doc",
        notes="Some generic note",
        doc_path="docs/old/design.md",
        candidate_text="Some text.",
        inventory={"docs/old/design.md": "stale"},
        has_act_5_0=False,
        has_act_5_2=False,
    )
    if "deprioritized:stale" in reasons6:
        print("[PASS] stale rows deprioritized")
    else:
        print(f"[FAIL] stale deprioritization: score={score6}, reasons={reasons6}")
        all_passed = False
    
    # Fixture 7: covered_by_existing_claim with weak note is flagged
    score7, reasons7 = compute_risk_score(
        disposition="covered_by_existing_claim",
        reason_code="covered_by_broader_claim",
        notes="Low-value prose fragment from: docs/foo.md",
        doc_path="docs/normal.md",
        candidate_text="Some text.",
        inventory={},
        has_act_5_0=False,
        has_act_5_2=False,
    )
    if "covered_note_weak" in reasons7:
        print("[PASS] covered_by_existing_claim with weak note flagged")
    else:
        print(f"[FAIL] covered_note_weak: score={score7}, reasons={reasons7}")
        all_passed = False
    
    # Fixture 8: deterministic JSON output (same input = same output)
    test_entries = [
        {
            "candidate_id": "DOC-CAND-000000000001",
            "disposition": "ignored_by_policy",
            "reason_code": "low_value_context",
            "source_doc_path": "docs/security/auth.md",
            "candidate_text": "Test text.",
            "reviewed_at": "2026-06-19",
            "reviewer_notes": "Low-value prose fragment from: docs/foo.md",
            "score": 42,
            "risk_reasons": ["generic_ignored_note", "high_value_doc:security"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": False,
            "is_historical": False,
            "is_stale_doc": False,
            "is_historical_doc": False,
            "is_high_value_doc": True,
        },
        {
            "candidate_id": "DOC-CAND-000000000002",
            "disposition": "stale",
            "reason_code": "stale_doc",
            "source_doc_path": "docs/old/design.md",
            "candidate_text": "Test text 2.",
            "reviewed_at": "2026-06-19",
            "reviewer_notes": "From stale doc: docs/old/design.md",
            "score": -12,
            "risk_reasons": ["deprioritized:stale"],
            "is_act_5_0_reviewed": False,
            "is_act_5_2_reviewed": False,
            "has_any_act_review_marker": False,
            "is_generic_low_value_note": True,
            "is_stale": True,
            "is_historical": False,
            "is_stale_doc": True,
            "is_historical_doc": False,
            "is_high_value_doc": False,
        },
    ]
    test_summary = {
        "total_candidates": 2,
        "disposition_counts": {"ignored_by_policy": 1, "stale": 1},
        "reason_code_counts": {"low_value_context": 1, "stale_doc": 1},
        "review_marker_counts": {"act_5_0": 0, "act_5_2": 0, "unreviewed": 2},
        "generic_note_counts": {"ignored_by_policy": 1, "stale": 1},
        "top_docs_by_unreviewed_generic_ignored": [],
        "top_docs_by_risk": [],
    }
    
    import os
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json_path = Path(f.name)
    
    try:
        write_json(test_entries, test_summary, json_path)  # type: ignore[arg-type]
        with open(json_path) as f:
            data = json.load(f)
        
        if (
            data["total_candidates"] == 2
            and "disposition_counts" in data
            and len(data["recommended_candidates"]) == 2
        ):
            print("[PASS] deterministic JSON output")
        else:
            print(f"[FAIL] JSON output structure: {data}")
            all_passed = False
        
        # Run twice and compare for determinism
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json_path2 = Path(f.name)
        try:
            write_json(test_entries, test_summary, json_path2)  # type: ignore[arg-type]
            with open(json_path) as f1:
                data1 = json.load(f1)
            with open(json_path2) as f2:
                data2 = json.load(f2)
            
            if data1 == data2:
                print("[PASS] JSON output is deterministic")
            else:
                print("[FAIL] JSON output not deterministic")
                all_passed = False
        finally:
            os.unlink(json_path2)
    finally:
        os.unlink(json_path)
    
    # Fixture 9: TSV output contains expected columns/order
    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
        tsv_path = Path(f.name)
    
    try:
        write_tsv(test_entries, tsv_path)  # type: ignore[arg-type]
        with open(tsv_path) as f:
            lines = f.readlines()
        
        expected_header = "score\tcandidate_id\tdisposition\treason_code\tsource_doc_path\trisk_reasons\treviewed_at\treviewer_notes\tcandidate_text\n"
        if lines and lines[0] == expected_header:
            print("[PASS] TSV output contains expected columns/order")
        else:
            print(f"[FAIL] TSV header mismatch: {lines[0] if lines else 'empty'}")
            all_passed = False
    finally:
        os.unlink(tsv_path)
    
    # Fixture 10: covered_by_existing_claim with generic note detected correctly
    if is_generic_low_value_note("Low-value prose fragment from: docs/foo.md"):
        print("[PASS] generic note pattern detection")
    else:
        print("[FAIL] generic note pattern detection")
        all_passed = False
    
    print()
    if all_passed:
        print("[PASS] all self-tests passed")
        return True
    else:
        print("[FAIL] some self-tests failed")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report documentation claim candidate backlog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        metavar="N",
        help="Number of top candidates to show in summary (default: 50)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        metavar="PATH",
        help="Write JSON output to path",
    )
    parser.add_argument(
        "--tsv",
        type=Path,
        metavar="PATH",
        help="Write TSV output to path (unreviewed candidates only)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode",
    )
    parser.add_argument(
        "--include-reviewed",
        action="store_true",
        help="Include already-reviewed candidates in output",
    )
    parser.add_argument(
        "--disposition",
        type=str,
        metavar="DISPOSITION",
        help="Filter by disposition (e.g., ignored_by_policy)",
    )
    parser.add_argument(
        "--doc",
        type=str,
        metavar="PATH",
        help="Filter by doc path (substring match)",
    )
    
    args = parser.parse_args()
    
    if args.self_test:
        success = run_self_test()
        return 0 if success else 1
    
    # Load data
    candidates, c_error = read_candidates()
    if c_error:
        print(f"[ERROR] {c_error}", file=sys.stderr)
        return 1
    
    dispositions, d_error = read_dispositions()
    if d_error:
        print(f"[ERROR] {d_error}", file=sys.stderr)
        return 1
    
    inventory, i_error = read_inventory()
    if i_error:
        print(f"[WARNING] {i_error}", file=sys.stderr)
    
    # Build backlog
    entries = build_backlog(
        candidates=candidates,
        dispositions=dispositions,
        inventory=inventory,
        include_reviewed=args.include_reviewed,
        disposition_filter=args.disposition,
        doc_filter=args.doc,
    )
    
    # Compute summary
    summary = compute_summary(entries)
    
    # Output
    print_summary(entries, summary)
    print_recommended(entries, args.top)
    
    # Write JSON if requested
    if args.json:
        write_json(entries, summary, args.json)
        print(f"\n[INFO] JSON output written to {args.json}")
    
    # Write TSV if requested
    if args.tsv:
        write_tsv(entries, args.tsv)
        print(f"[INFO] TSV output written to {args.tsv}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
