#!/usr/bin/env python3
"""Helper script to collect and display diagnosis review packets for an incident.

This script provides a bounded review handoff for operator/ChatGPT review.

Usage:
    python scripts/collect_diagnosis_review_packet.py --incident-id <id>
    python scripts/collect_diagnosis_review_packet.py --incident-id <id> --external-dir <path>

Behavior:
- Finds the latest review packet for the incident
- Displays bounded summary (no raw artifact contents)
- Shows incident_id, run_id, decision, checks_run/checks_rejected
- Does NOT print absolute paths, secrets, or raw artifact contents

This script does NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell
- Perform remediation or mutation
- Print raw case file or runner results
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from k8s_diag_agent.collect.incident_diagnosis_review_packet import (
    find_latest_review_packet,
    load_review_packet_summary,
)

__all__ = []


def main() -> int:
    """Main entry point for review packet collector."""
    parser = argparse.ArgumentParser(
        description="Collect diagnosis review packet for an incident",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s --incident-id test-incident
    %(prog)s --incident-id test-incident --external-dir ./runs/external-analysis
        """,
    )

    parser.add_argument(
        "--incident-id",
        required=True,
        help="Incident ID to find review packet for",
    )

    parser.add_argument(
        "--external-dir",
        default="./runs/external-analysis",
        help="Path to external-analysis directory (default: ./runs/external-analysis)",
    )

    args = parser.parse_args()

    external_dir = Path(args.external_dir)
    incident_id = args.incident_id

    # Find latest packet
    packet_info = find_latest_review_packet(external_dir, incident_id)

    if packet_info is None:
        print(f"ERROR: No review packet found for incident: {incident_id}")
        print(f"       Checked directory: {external_dir}")
        print(f"       Expected pattern: auto-{incident_id}-*-diagnosis-review-packet.json")
        return 1

    # Load summary (bounded fields only)
    summary = load_review_packet_summary(external_dir, incident_id)

    if summary is None:
        print(f"ERROR: Could not load review packet summary for incident: {incident_id}")
        print(f"       Packet file: {packet_info['name']}")
        return 1

    # Print bounded summary
    print()
    print("=" * 60)
    print("  DIAGNOSIS LOOP REVIEW PACKET SUMMARY")
    print("=" * 60)
    print()
    print(f"  Incident ID:        {summary.get('incident_id', 'N/A')}")
    print(f"  Run ID:             {summary.get('run_id', 'N/A')}")
    print(f"  Collector Run ID:   {summary.get('collector_run_id', 'N/A')}")
    print(f"  Generated At:       {summary.get('generated_at', 'N/A')}")
    print()
    print(f"  Eligible:           {summary.get('eligible', False)}")
    print(f"  Eligibility Reason: {summary.get('eligibility_reason', 'N/A')}")
    print()
    print("-" * 60)
    print("  LOOP RESULT")
    print("-" * 60)
    print()
    print(f"  Decision:           {summary.get('decision', 'N/A')}")
    print(f"  Checks Requested:   {summary.get('checks_requested', 0)}")
    print(f"  Checks Run:         {summary.get('checks_run', 0)}")
    print(f"  Checks Rejected:    {summary.get('checks_rejected', 0)}")
    print()
    print("-" * 60)
    print("  ARTIFACT")
    print("-" * 60)
    print()
    print(f"  Review Packet:      {summary.get('artifact_name', 'N/A')}")
    print(f"  Location:           {external_dir}")
    print()
    print("=" * 60)
    print()
    print("  REVIEW INSTRUCTIONS:")
    print("  - This packet contains bounded evidence metadata only")
    print("  - No remediation was attempted or authorized")
    print("  - No kubectl/helm/subprocess commands were executed")
    print("  - Review is required before any action")
    print("  - See artifact file for detailed check results")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())