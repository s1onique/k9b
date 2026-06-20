"""Report building and output for documentation claim candidate backlog reporter."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import cast

from .model import (
    BacklogEntry,
    CandidateData,
    classify_review_class,
    compute_calibrated_score,
    compute_risk_score,
    has_act_5_0_marker,
    has_act_5_2_marker,
    has_any_act_marker,
    is_generic_low_value_note,
    is_high_value_doc,
    is_historical_disposition,
    is_historical_doc,
    is_stale_disposition,
    is_stale_doc,
)
from .planning import get_priority_band


def filter_entries(
    entries: list[BacklogEntry],
    *,
    review_classes: set[str] | None = None,
    priority_bands: set[str] | None = None,
) -> list[BacklogEntry]:
    """Filter entries by review_class and/or priority_band.

    Args:
        entries: List of backlog entries to filter.
        review_classes: Set of allowed review classes (e.g., {"claim_candidate"}).
            None means no review-class filter.
        priority_bands: Set of allowed priority bands (e.g., {"P0", "P1"}).
            None means no priority-band filter.
            Priority band is computed from calibrated_score.

    Returns:
        Filtered list preserving original ranking order.
        No mutation of entries.
    """
    if review_classes is None and priority_bands is None:
        return list(entries)

    result: list[BacklogEntry] = []
    for entry in entries:
        # Filter by review_class if specified
        if review_classes is not None:
            entry_class = entry.get("review_class", "unknown")
            if entry_class not in review_classes:
                continue

        # Filter by priority_band if specified
        if priority_bands is not None:
            calibrated = entry.get("calibrated_score", entry.get("score", 0))
            band = get_priority_band(calibrated)
            if band not in priority_bands:
                continue

        result.append(entry)

    return result


def build_backlog(
    candidates: list[CandidateData],
    dispositions: list[CandidateData],
    inventory: dict[str, str],
    include_reviewed: bool = False,
    disposition_filter: str | None = None,
    doc_filter: str | None = None,
) -> list[BacklogEntry]:
    """Build ranked backlog entries from candidates and dispositions."""
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

        if disposition_filter and disposition != disposition_filter:
            continue

        if doc_filter and doc_filter not in doc_path:
            continue

        has_5_0 = has_act_5_0_marker(notes)
        has_5_2 = has_act_5_2_marker(notes)
        has_any = has_any_act_marker(notes)

        if not include_reviewed and has_any:
            continue

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

        # Classify review class and compute calibrated score
        review_class, review_class_reasons = classify_review_class(
            disposition=disposition,
            reason_code=reason_code,
            notes=notes,
            has_any_act_marker=has_any,
            doc_path=doc_path,
            inventory=inventory,
            candidate_text=candidate_text,
        )
        calibrated_score = compute_calibrated_score(risk_score, review_class)

        entry: BacklogEntry = {
            "candidate_id": cid,
            "disposition": disposition,
            "reason_code": reason_code,
            "source_doc_path": doc_path,
            "candidate_text": candidate_text[:200] + "..." if len(candidate_text) > 200 else candidate_text,
            "reviewed_at": reviewed_at,
            "reviewer_notes": notes[:150] + "..." if len(notes) > 150 else notes,
            "score": risk_score,
            "calibrated_score": calibrated_score,
            "risk_reasons": risk_reasons,
            "review_class": review_class,
            "review_class_reasons": review_class_reasons,
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

    # Sort by calibrated_score for final ranking
    entries.sort(key=lambda e: (-cast(int, e.get("calibrated_score", e["score"])), cast(str, e["candidate_id"])))
    return entries


def compute_summary(entries: list[BacklogEntry]) -> dict:
    """Compute summary statistics from backlog entries."""
    total = len(entries)

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

        if entry.get("is_generic_low_value_note"):
            generic_counts[cast(str, disp)] += 1

        if disp == "ignored_by_policy" and entry.get("is_generic_low_value_note") and not entry.get("has_any_act_review_marker"):
            doc_counts[cast(str, doc)] += 1

        doc_risk_scores[cast(str, doc)].append(cast(int, entry["score"]))

        if entry.get("is_act_5_0_reviewed"):
            act_5_0_count += 1
        elif entry.get("is_act_5_2_reviewed"):
            act_5_2_count += 1
        elif not entry.get("has_any_act_review_marker"):
            unreviewed_count += 1

    top_docs_by_generic = sorted(doc_counts.items(), key=lambda x: -x[1])[:20]

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


def write_json(
    entries: list[BacklogEntry],
    summary: dict,
    output_path: Path,
    include_planning: bool = False,
    planning: dict | None = None,
    filters: dict | None = None,
) -> None:
    """Write deterministic JSON output."""
    unreviewed = [
        e for e in entries
        if not e.get("has_any_act_review_marker")
    ]

    recommended = []
    for entry in unreviewed[:100]:
        # Use calibrated_score for ranking, but report base score as score
        base_score = cast(int, entry.get("score", 0))
        calibrated = cast(int, entry.get("calibrated_score", base_score))
        score_for_output = calibrated if calibrated != base_score else base_score
        
        # Get priority band from calibrated score
        priority_band = get_priority_band(calibrated)
        
        recommended.append({
            "candidate_id": entry["candidate_id"],
            "score": score_for_output,
            "calibrated_score": calibrated,
            "priority_band": priority_band,
            "review_class": entry.get("review_class", "unknown"),
            "review_class_reasons": entry.get("review_class_reasons", []),
            "risk_reasons": entry["risk_reasons"],
            "disposition": entry["disposition"],
            "reason_code": entry["reason_code"],
            "source_doc_path": entry["source_doc_path"],
            "reviewer_notes": entry["reviewer_notes"],
            "candidate_text": entry["candidate_text"],
        })

    output: dict = {
        "total_candidates": summary["total_candidates"],
        "disposition_counts": summary["disposition_counts"],
        "reason_code_counts": summary["reason_code_counts"],
        "review_marker_counts": summary["review_marker_counts"],
        "generic_note_counts": summary["generic_note_counts"],
        "top_docs_by_unreviewed_generic_ignored": summary["top_docs_by_unreviewed_generic_ignored"],
        "top_docs_by_risk": summary["top_docs_by_risk"],
        "recommended_candidates": recommended,
    }

    # Add planning block if requested
    if include_planning and planning:
        output["planning"] = planning

    # Add filters block if provided
    if filters:
        output["filters"] = filters

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, sort_keys=True)
        f.write("\n")


def write_tsv(
    entries: list[BacklogEntry],
    output_path: Path,
    include_priority_band: bool = False,
) -> None:
    """Write TSV output for future tranche selection."""
    unreviewed = [
        e for e in entries
        if not e.get("has_any_act_review_marker")
    ]

    # TSV schema with review_class and review_class_reasons
    fieldnames: list[str] = [
        "score",
        "priority_band",
        "review_class",
        "review_class_reasons",
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
            row: dict[str, str] = dict(entry)
            row["risk_reasons"] = ",".join(cast(list, entry["risk_reasons"]))
            # Use calibrated score for priority band
            calibrated = cast(int, entry.get("calibrated_score", entry.get("score", 0)))
            row["score"] = calibrated
            row["priority_band"] = get_priority_band(calibrated)
            # Add review_class_reasons as comma-separated
            row["review_class_reasons"] = ",".join(cast(list, entry.get("review_class_reasons", [])))
            writer.writerow(row)
