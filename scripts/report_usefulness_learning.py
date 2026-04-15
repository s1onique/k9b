#!/usr/bin/env python3
"""Generate planner-improvement report from imported usefulness summaries.

This script scans run-scoped usefulness_summary.json files and produces
a deterministic, evidence-backed report showing command family performance
across different contexts.

Output:
- Readable table to stdout
- Optional JSON output for programmatic consumption
- Candidate recommendations for planner policy changes

Usage:
    # Console output only
    .venv/bin/python scripts/report_usefulness_learning.py

    # With JSON output
    .venv/bin/python scripts/report_usefulness_learning.py --json output.json

    # Filter to specific runs
    .venv/bin/python scripts/report_usefulness_learning.py --runs-dir ./runs --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# Enums for context-aware analysis
WORKSTREAMS_INCIDENT = {"incident"}
WORKSTREAMS_VALIDATION = {"drift", "evidence"}

REVIEW_STAGES_TRIAGE = {"initial_triage", "unknown"}
REVIEW_STAGES_VALIDATION = {"parity_validation"}


@dataclass
class FamilyStats:
    """Aggregated statistics for a command family."""
    total_count: int = 0
    useful_count: int = 0
    partial_count: int = 0
    noisy_count: int = 0
    empty_count: int = 0
    # Context breakdown
    incident_count: int = 0
    incident_useful: int = 0
    incident_noisy: int = 0
    drift_count: int = 0
    drift_useful: int = 0
    drift_noisy: int = 0
    initial_triage_count: int = 0
    initial_triage_useful: int = 0
    initial_triage_noisy: int = 0
    parity_validation_count: int = 0
    parity_validation_useful: int = 0
    parity_validation_noisy: int = 0
    # Context keys for sensitivity analysis
    context_scores: dict[str, dict[str, int]] = field(default_factory=dict)
    # Runs where this family appeared
    run_ids: set[str] = field(default_factory=set)

    @property
    def useful_rate(self) -> float:
        """Rate of useful judgments."""
        if self.total_count == 0:
            return 0.0
        return self.useful_count / self.total_count

    @property
    def noisy_rate(self) -> float:
        """Rate of noisy judgments."""
        if self.total_count == 0:
            return 0.0
        return self.noisy_count / self.total_count

    @property
    def context_sensitivity(self) -> float:
        """Measure of how much performance varies across contexts.

        Returns 0.0 if no variation, higher values indicate more sensitivity.
        """
        if not self.context_scores or len(self.context_scores) < 2:
            return 0.0
        rates = []
        for context_key, scores in self.context_scores.items():
            total = sum(scores.values())
            if total > 0:
                useful = scores.get("useful", 0)
                rates.append(useful / total)
        if len(rates) < 2:
            return 0.0
        # Compute coefficient of variation (higher = more sensitive)
        mean = sum(rates) / len(rates)
        if mean == 0:
            return 0.0
        variance = sum((r - mean) ** 2 for r in rates) / len(rates)
        std_dev = variance ** 0.5
        return std_dev / mean if mean > 0 else 0.0


@dataclass
class ReportData:
    """Aggregated report data across all summaries."""
    summaries_loaded: int = 0
    total_entries: int = 0
    families: dict[str, FamilyStats] = field(default_factory=dict)
    runs_analyzed: set[str] = field(default_factory=set)


def load_summary_files(runs_dir: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Load all usefulness_summary.json files from run-scoped directories.

    Args:
        runs_dir: Path to the runs directory (contains health/)
        limit: Optional limit on number of summaries to load

    Returns:
        List of loaded summary dictionaries
    """
    health_dir = runs_dir / "health"
    diagnostic_packs_dir = health_dir / "diagnostic-packs"

    if not diagnostic_packs_dir.exists():
        return []

    summaries = []
    for run_dir in diagnostic_packs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        summary_path = run_dir / "usefulness_summary.json"
        if summary_path.exists():
            try:
                data = json.loads(summary_path.read_text(encoding="utf-8"))
                summaries.append(data)
                if limit and len(summaries) >= limit:
                    break
            except (json.JSONDecodeError, OSError):
                continue

    return summaries


def _parse_key(key: str) -> tuple[str, str | None, str | None, str | None]:
    """Parse a context key into components.

    Keys are formatted as:
    - "command_family" (flat aggregate)
    - "command_family:workstream" (by_command_family_workstream)
    - "command_family:review_stage" (by_command_family_review_stage)
    - "command_family:problem_class" (by_command_family_problem_class)

    Returns:
        Tuple of (family, workstream, review_stage, problem_class)
    """
    parts = key.split(":")
    family = parts[0]
    workstream = parts[1] if len(parts) > 1 else None
    review_stage = parts[2] if len(parts) > 2 else None
    # For 4-part keys, problem_class is part 2 (after workstream)
    problem_class = parts[2] if len(parts) > 2 and len(parts) < 4 else None
    if len(parts) == 4:
        problem_class = parts[3]
    return family, workstream, review_stage, problem_class


def _parse_workstream_key(key: str) -> tuple[str, str]:
    """Parse a workstream key (command_family:workstream)."""
    parts = key.split(":", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _parse_stage_key(key: str) -> tuple[str, str]:
    """Parse a review stage key (command_family:review_stage)."""
    parts = key.split(":", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _parse_problem_key(key: str) -> tuple[str, str]:
    """Parse a problem class key (command_family:problem_class)."""
    parts = key.split(":", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def aggregate_summaries(summaries: list[dict[str, Any]]) -> ReportData:
    """Aggregate statistics across multiple summary files.

    Args:
        summaries: List of loaded summary dictionaries

    Returns:
        ReportData with aggregated statistics
    """
    report = ReportData()
    report.summaries_loaded = len(summaries)

    for summary in summaries:
        run_id = summary.get("run_id", "unknown")
        report.runs_analyzed.add(run_id)

        context_aggregates = summary.get("context_aggregates", {})

        # Process by_command_family
        by_family = context_aggregates.get("by_command_family", {})
        for family, scores in by_family.items():
            if family not in report.families:
                report.families[family] = FamilyStats()
            stats = report.families[family]
            stats.run_ids.add(run_id)
            stats.total_count += sum(scores.values())
            stats.useful_count += scores.get("useful", 0)
            stats.partial_count += scores.get("partial", 0)
            stats.noisy_count += scores.get("noisy", 0)
            stats.empty_count += scores.get("empty", 0)
            # Track context for sensitivity
            stats.context_scores[f"cf:{family}"] = scores.copy()

        # Process by_command_family_workstream
        # Keys are "command_family:workstream" format
        by_workstream = context_aggregates.get("by_command_family_workstream", {})
        for key, scores in by_workstream.items():
            family, workstream = _parse_workstream_key(key)
            if family not in report.families:
                report.families[family] = FamilyStats()
            stats = report.families[family]
            stats.run_ids.add(run_id)
            stats.context_scores[f"ws:{key}"] = scores.copy()

            if workstream == "incident":
                stats.incident_count += sum(scores.values())
                stats.incident_useful += scores.get("useful", 0)
                stats.incident_noisy += scores.get("noisy", 0)
            elif workstream in {"drift", "evidence"}:
                stats.drift_count += sum(scores.values())
                stats.drift_useful += scores.get("useful", 0)
                stats.drift_noisy += scores.get("noisy", 0)

        # Process by_command_family_review_stage
        # Keys are "command_family:review_stage" format
        by_stage = context_aggregates.get("by_command_family_review_stage", {})
        for key, scores in by_stage.items():
            family, review_stage = _parse_stage_key(key)
            if family not in report.families:
                report.families[family] = FamilyStats()
            stats = report.families[family]
            stats.context_scores[f"stage:{key}"] = scores.copy()

            if review_stage in {"initial_triage", "unknown"}:
                stats.initial_triage_count += sum(scores.values())
                stats.initial_triage_useful += scores.get("useful", 0)
                stats.initial_triage_noisy += scores.get("noisy", 0)
            elif review_stage == "parity_validation":
                stats.parity_validation_count += sum(scores.values())
                stats.parity_validation_useful += scores.get("useful", 0)
                stats.parity_validation_noisy += scores.get("noisy", 0)

        # Process by_command_family_problem_class
        # Keys are "command_family:problem_class" format
        by_problem = context_aggregates.get("by_command_family_problem_class", {})
        for key, scores in by_problem.items():
            family, problem_class = _parse_problem_key(key)
            if family not in report.families:
                report.families[family] = FamilyStats()
            stats = report.families[family]
            stats.context_scores[f"pc:{key}"] = scores.copy()

    # Update total entries
    for summary in summaries:
        stats = summary.get("statistics", {})
        report.total_entries += stats.get("total_entries", 0)

    return report


@dataclass
class Recommendation:
    """A planner policy recommendation."""
    family: str
    action: str  # "promote", "demote", "keep_context_gated"
    reason: str
    evidence: dict[str, Any]


def generate_recommendations(report: ReportData) -> list[Recommendation]:
    """Generate deterministic recommendations based on aggregated data.

    Args:
        report: Aggregated report data

    Returns:
        List of recommendations
    """
    recommendations = []

    for family, stats in report.families.items():
        if stats.total_count < 3:
            continue  # Not enough data for recommendation

        # Calculate rates for different contexts
        incident_useful_rate = stats.incident_useful / stats.incident_count if stats.incident_count > 0 else 0.0
        drift_useful_rate = stats.drift_useful / stats.drift_count if stats.drift_count > 0 else 0.0
        initial_triage_noisy_rate = stats.initial_triage_noisy / stats.initial_triage_count if stats.initial_triage_count > 0 else 0.0
        parity_validation_useful_rate = stats.parity_validation_useful / stats.parity_validation_count if stats.parity_validation_count > 0 else 0.0

        sensitivity = stats.context_sensitivity

        # Decision logic (deterministic)
        if sensitivity > 0.3:
            # High context sensitivity - keep gated
            if incident_useful_rate > 0.5 and stats.incident_noisy > 0:
                recommendations.append(Recommendation(
                    family=family,
                    action="keep_context_gated",
                    reason=f"High context sensitivity ({sensitivity:.2f}). Useful in incident ({incident_useful_rate:.0%}) but noisy in initial_triage ({initial_triage_noisy_rate:.0%}).",
                    evidence={
                        "sensitivity": round(sensitivity, 3),
                        "incident_useful_rate": round(incident_useful_rate, 3),
                        "incident_noisy": stats.incident_noisy,
                        "initial_triage_noisy_rate": round(initial_triage_noisy_rate, 3),
                    }
                ))

        # Promote candidates: useful in both incident and validation contexts
        if (incident_useful_rate > 0.6 and drift_useful_rate > 0.5) or (parity_validation_useful_rate > 0.6 and incident_useful_rate > 0.4):
            if stats.noisy_rate < 0.3:  # Not too noisy overall
                recommendations.append(Recommendation(
                    family=family,
                    action="promote",
                    reason=f"Strong performance in both incident ({incident_useful_rate:.0%}) and validation ({drift_useful_rate:.0%}) contexts.",
                    evidence={
                        "incident_useful_rate": round(incident_useful_rate, 3),
                        "drift_useful_rate": round(drift_useful_rate, 3),
                        "parity_validation_useful_rate": round(parity_validation_useful_rate, 3),
                        "noisy_rate": round(stats.noisy_rate, 3),
                    }
                ))

        # Demote candidates: consistently noisy across contexts
        if stats.noisy_rate > 0.5 and stats.useful_rate < 0.2:
            recommendations.append(Recommendation(
                family=family,
                action="demote",
                reason=f"High noisy rate ({stats.noisy_rate:.0%}) with low useful rate ({stats.useful_rate:.0%}).",
                evidence={
                    "noisy_rate": round(stats.noisy_rate, 3),
                    "useful_rate": round(stats.useful_rate, 3),
                    "total_count": stats.total_count,
                }
            ))

    # Sort by action priority: demote > promote > keep_context_gated
    action_order = {"demote": 0, "promote": 1, "keep_context_gated": 2}
    recommendations.sort(key=lambda r: (action_order.get(r.action, 99), r.family))

    return recommendations


def format_report(report: ReportData, recommendations: list[Recommendation]) -> str:
    """Format the report as a readable table.

    Args:
        report: Aggregated report data
        recommendations: Generated recommendations

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 80)
    lines.append("PLANNER IMPROVEMENT REPORT")
    lines.append("Evidence-backed command family performance analysis")
    lines.append("=" * 80)
    lines.append(f"")
    lines.append(f"Summaries analyzed: {report.summaries_loaded}")
    lines.append(f"Total runs analyzed: {len(report.runs_analyzed)}")
    lines.append(f"Total entries: {report.total_entries}")
    lines.append(f"Unique command families: {len(report.families)}")
    lines.append("")

    # Best families for incident + initial_triage
    lines.append("-" * 80)
    lines.append("BEST COMMAND FAMILIES FOR INCIDENT + INITIAL_TRIAGE")
    lines.append("-" * 80)
    incident_families = []
    for family, stats in report.families.items():
        if stats.incident_count > 0 and stats.initial_triage_count > 0:
            rate = stats.incident_useful / stats.incident_count if stats.incident_count > 0 else 0
            noisy_in_triage = stats.initial_triage_noisy / stats.initial_triage_count if stats.initial_triage_count > 0 else 0
            incident_families.append((family, rate, noisy_in_triage, stats))
    incident_families.sort(key=lambda x: (x[1], -x[2]), reverse=True)

    if incident_families:
        lines.append(f"{'Family':<30} {'Useful Rate':<15} {'Noisy in Triage':<15} {'Total':<10}")
        lines.append("-" * 70)
        for family, useful_rate, noisy_rate, stats in incident_families[:10]:
            lines.append(f"{family:<30} {useful_rate:>12.1%}    {noisy_rate:>12.1%}    {stats.total_count:>8}")
    else:
        lines.append("No data for this category")
    lines.append("")

    # Worst families for incident + initial_triage
    lines.append("-" * 80)
    lines.append("WORST COMMAND FAMILIES FOR INCIDENT + INITIAL_TRIAGE")
    lines.append("-" * 80)
    worst_families = []
    for family, stats in report.families.items():
        if stats.initial_triage_count >= 3:  # Minimum threshold
            noisy_rate = stats.initial_triage_noisy / stats.initial_triage_count
            worst_families.append((family, noisy_rate, stats.initial_triage_noisy, stats.initial_triage_count))
    worst_families.sort(key=lambda x: (x[1], -x[3]), reverse=True)

    if worst_families:
        lines.append(f"{'Family':<30} {'Noisy Rate':<15} {'Noisy Count':<15} {'Total':<10}")
        lines.append("-" * 70)
        for family, noisy_rate, noisy_count, total in worst_families[:10]:
            lines.append(f"{family:<30} {noisy_rate:>12.1%}    {noisy_count:>12}    {total:>8}")
    else:
        lines.append("No data for this category")
    lines.append("")

    # Best families for parity_validation + drift
    lines.append("-" * 80)
    lines.append("BEST COMMAND FAMILIES FOR PARITY_VALIDATION + DRIFT")
    lines.append("-" * 80)
    validation_families = []
    for family, stats in report.families.items():
        if stats.drift_count > 0 or stats.parity_validation_count > 0:
            drift_rate = stats.drift_useful / stats.drift_count if stats.drift_count > 0 else 0
            parity_rate = stats.parity_validation_useful / stats.parity_validation_count if stats.parity_validation_count > 0 else 0
            best_rate = max(drift_rate, parity_rate)
            validation_families.append((family, best_rate, stats))
    validation_families.sort(key=lambda x: x[1], reverse=True)

    if validation_families:
        lines.append(f"{'Family':<30} {'Best Validation Rate':<20} {'Total Validation':<15}")
        lines.append("-" * 65)
        for family, best_rate, stats in validation_families[:10]:
            total = stats.drift_count + stats.parity_validation_count
            lines.append(f"{family:<30} {best_rate:>17.1%}     {total:>13}")
    else:
        lines.append("No data for this category")
    lines.append("")

    # Families with largest context sensitivity
    lines.append("-" * 80)
    lines.append("FAMILIES WITH LARGEST CONTEXT SENSITIVITY")
    lines.append("-" * 80)
    sensitivity_list = [(f, s.context_sensitivity, s) for f, s in report.families.items() if s.context_sensitivity > 0.1]
    sensitivity_list.sort(key=lambda x: x[1], reverse=True)

    if sensitivity_list:
        lines.append(f"{'Family':<30} {'Sensitivity':<15} {'Contexts':<10}")
        lines.append("-" * 55)
        for family, sensitivity, stats in sensitivity_list[:10]:
            contexts = len(stats.context_scores)
            lines.append(f"{family:<30} {sensitivity:>12.3f}    {contexts:>8}")
    else:
        lines.append("No significant sensitivity detected")
    lines.append("")

    # Families with highest noisy rate
    lines.append("-" * 80)
    lines.append("FAMILIES WITH HIGHEST NOISY RATE (min 3 observations)")
    lines.append("-" * 80)
    noisy_list = [(f, s.noisy_rate, s.noisy_count, s.total_count) for f, s in report.families.items() if s.total_count >= 3]
    noisy_list.sort(key=lambda x: x[1], reverse=True)

    if noisy_list:
        lines.append(f"{'Family':<30} {'Noisy Rate':<15} {'Noisy':<10} {'Total':<10}")
        lines.append("-" * 65)
        for family, noisy_rate, noisy_count, total in noisy_list[:10]:
            lines.append(f"{family:<30} {noisy_rate:>12.1%}    {noisy_count:>8}    {total:>8}")
    else:
        lines.append("No data for this category")
    lines.append("")

    # Families with highest useful rate
    lines.append("-" * 80)
    lines.append("FAMILIES WITH HIGHEST USEFUL RATE (min 3 observations)")
    lines.append("-" * 80)
    useful_list = [(f, s.useful_rate, s.useful_count, s.total_count) for f, s in report.families.items() if s.total_count >= 3]
    useful_list.sort(key=lambda x: x[1], reverse=True)

    if useful_list:
        lines.append(f"{'Family':<30} {'Useful Rate':<15} {'Useful':<10} {'Total':<10}")
        lines.append("-" * 65)
        for family, useful_rate, useful_count, total in useful_list[:10]:
            lines.append(f"{family:<30} {useful_rate:>12.1%}    {useful_count:>8}    {total:>8}")
    else:
        lines.append("No data for this category")
    lines.append("")

    # Recommendations
    lines.append("=" * 80)
    lines.append("CANDIDATE RECOMMENDATIONS")
    lines.append("=" * 80)

    demote_recs = [r for r in recommendations if r.action == "demote"]
    promote_recs = [r for r in recommendations if r.action == "promote"]
    gated_recs = [r for r in recommendations if r.action == "keep_context_gated"]

    if demote_recs:
        lines.append("")
        lines.append("DEMOTE (reduce priority):")
        lines.append("-" * 40)
        for rec in demote_recs:
            lines.append(f"  • {rec.family}")
            lines.append(f"    Reason: {rec.reason}")
            lines.append(f"    Evidence: noisy_rate={rec.evidence.get('noisy_rate', 'N/A')}, useful_rate={rec.evidence.get('useful_rate', 'N/A')}")

    if promote_recs:
        lines.append("")
        lines.append("PROMOTE (increase priority):")
        lines.append("-" * 40)
        for rec in promote_recs:
            lines.append(f"  • {rec.family}")
            lines.append(f"    Reason: {rec.reason}")
            lines.append(f"    Evidence: incident_rate={rec.evidence.get('incident_useful_rate', 'N/A')}, drift_rate={rec.evidence.get('drift_useful_rate', 'N/A')}")

    if gated_recs:
        lines.append("")
        lines.append("KEEP CONTEXT-GATED (use selectively):")
        lines.append("-" * 40)
        for rec in gated_recs:
            lines.append(f"  • {rec.family}")
            lines.append(f"    Reason: {rec.reason}")
            lines.append(f"    Evidence: sensitivity={rec.evidence.get('sensitivity', 'N/A')}")

    if not recommendations:
        lines.append("")
        lines.append("No clear recommendations based on current data.")
        lines.append("More feedback data needed for evidence-based decisions.")

    lines.append("")
    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)

    return "\n".join(lines)


def report_to_dict(report: ReportData, recommendations: list[Recommendation]) -> dict[str, Any]:
    """Convert report to JSON-serializable dictionary.

    Args:
        report: Aggregated report data
        recommendations: Generated recommendations

    Returns:
        Dictionary suitable for JSON serialization
    """
    families_data = {}
    for family, stats in report.families.items():
        families_data[family] = {
            "total_count": stats.total_count,
            "useful_count": stats.useful_count,
            "partial_count": stats.partial_count,
            "noisy_count": stats.noisy_count,
            "empty_count": stats.empty_count,
            "useful_rate": round(stats.useful_rate, 3),
            "noisy_rate": round(stats.noisy_rate, 3),
            "context_sensitivity": round(stats.context_sensitivity, 3),
            "incident_count": stats.incident_count,
            "incident_useful": stats.incident_useful,
            "incident_noisy": stats.incident_noisy,
            "drift_count": stats.drift_count,
            "drift_useful": stats.drift_useful,
            "drift_noisy": stats.drift_noisy,
            "initial_triage_count": stats.initial_triage_count,
            "initial_triage_useful": stats.initial_triage_useful,
            "initial_triage_noisy": stats.initial_triage_noisy,
            "parity_validation_count": stats.parity_validation_count,
            "parity_validation_useful": stats.parity_validation_useful,
            "parity_validation_noisy": stats.parity_validation_noisy,
            "runs_analyzed": list(stats.run_ids),
            "context_keys_count": len(stats.context_scores),
        }

    recommendations_data = []
    for rec in recommendations:
        recommendations_data.append({
            "family": rec.family,
            "action": rec.action,
            "reason": rec.reason,
            "evidence": rec.evidence,
        })

    return {
        "schema_version": "planner-improvement-report/v1",
        "summaries_loaded": report.summaries_loaded,
        "total_entries": report.total_entries,
        "runs_analyzed": sorted(list(report.runs_analyzed)),
        "command_families": families_data,
        "recommendations": recommendations_data,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate planner-improvement report from usefulness summaries."
    )
    parser.add_argument(
        "--runs-dir",
        default=str(ROOT / "runs"),
        help=f"Path to the runs directory (default: {ROOT / 'runs'})",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        metavar="PATH",
        help="Write JSON output to the specified file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of summary files to process",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runs_dir = Path(args.runs_dir)

    # Load and aggregate summaries
    summaries = load_summary_files(runs_dir, limit=args.limit)

    if not summaries:
        print("No usefulness_summary.json files found.", file=sys.stderr)
        print(f"Searched in: {runs_dir / 'health' / 'diagnostic-packs'}", file=sys.stderr)
        sys.exit(0)

    # Aggregate data
    report = aggregate_summaries(summaries)

    # Generate recommendations
    recommendations = generate_recommendations(report)

    # Output formatted report
    formatted = format_report(report, recommendations)
    print(formatted)

    # Output JSON if requested
    if args.json_output:
        json_path = Path(args.json_output)
        json_data = report_to_dict(report, recommendations)
        json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
        print(f"\n[JSON report written to: {json_path}]")


if __name__ == "__main__":
    main()