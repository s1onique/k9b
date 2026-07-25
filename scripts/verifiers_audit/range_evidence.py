"""CORRECTION13/CORRECTION14: detached range evidence CLI shim.

This module is a thin CLI wrapper.  The orchestrator lives
in :mod:`range_evidence_orchestrator`; the bundle writers
live in :mod:`range_evidence_writer` and
:mod:`range_evidence_builders`; the typed result
dataclasses live in :mod:`typed_results`.

Usage::

    python scripts/verifiers_audit/range_evidence.py \\
        --base F13 --subject S13 --output-dir /tmp/closure_evidence_14
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from scripts.verifiers_audit.discovery import REPO_ROOT
from scripts.verifiers_audit.range_evidence_identity import (
    RuffToolUnavailable,
)
from scripts.verifiers_audit.range_evidence_orchestrator import (
    REQUIRED_FINAL_ARTIFACTS,
    collect_range_evidence,
)
from scripts.verifiers_audit.typed_results import ClosureTopology

__all__ = [
    "REQUIRED_FINAL_ARTIFACTS",
    "RuffToolUnavailable",
    "collect_range_evidence",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    topology = ClosureTopology(
        F14=os.environ.get("K9B_F14", ""),
        F14_tree=os.environ.get("K9B_F14_TREE", ""),
        plan_blob=os.environ.get("K9B_PLAN_BLOB", ""),
        S14=os.environ.get("K9B_S14") or None,
        S14_tree=os.environ.get("K9B_S14_TREE") or None,
        parent_F14=os.environ.get("K9B_PARENT_F14", ""),
        parent_S14=os.environ.get("K9B_PARENT_S14") or None,
    )
    try:
        evidence = collect_range_evidence(
            base=args.base,
            subject=args.subject,
            repo_root=args.repo_root,
            output_dir=args.output_dir,
            topology=topology,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"wrote {args.output_dir}: "
        f"base={evidence.base_oid[:12]} "
        f"subject={evidence.subject_oid[:12]} "
        f"publication_status={evidence.publication_status}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())