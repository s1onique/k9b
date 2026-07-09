"""Evidence type CLI: command-line interface.

This module provides the CLI entry point for evidence type contract verification.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .evidence_types_report import format_evidence_type_report
from .evidence_types_rules import check_evidence_type_contract


def main() -> int:
    """CLI entry point for evidence type contract verification.

    Returns:
        0 if all checks pass, 1 if violations found, 2 for errors.
    """
    parser = argparse.ArgumentParser(
        description="Verify evidence type contracts in incident lifecycle boundary"
    )
    parser.add_argument(
        "--evidence-module",
        type=str,
        default="src/k8s_diag_agent/collect/incident_evidence.py",
        help="Path to the evidence module (default: %(default)s)",
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default="src",
        help="Root directory to scan (default: %(default)s)",
    )
    args = parser.parse_args()

    evidence_filepath = Path(args.evidence_module)
    repo_root = Path(args.repo_root)

    if not evidence_filepath.exists():
        print(f"Error: Evidence module not found: {evidence_filepath}", file=sys.stderr)
        return 2

    errors = check_evidence_type_contract(str(evidence_filepath), repo_root)

    print(format_evidence_type_report(errors))

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
