"""CORRECTION13/CORRECTION14/CORRECTION15: detached range evidence CLI shim.

This module is a thin CLI wrapper.  The orchestrator lives
in :mod:`range_evidence_orchestrator`; the bundle writers
live in :mod:`range_evidence_writer` and
:mod:`range_evidence_builders`; the typed result
dataclasses live in :mod:`typed_results`; the bundle
directory enumeration lives in
:mod:`range_evidence_bundle`.

Usage::

    python scripts/verifiers_audit/range_evidence.py \\
        --base F15 --subject S15 --output-dir /tmp/closure_evidence_15
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import argparse
import json
import os
import sys
from datetime import UTC, datetime
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


def _record_publication_result(
    *,
    output_dir: Path,
    staging_dir: Path,
    success: bool,
) -> None:
    """Write the external publication transcript.

    CORRECTION15: the manual publication transcript lives
    OUTSIDE the immutable bundle and records
    ``leamas_protocol_E=false``.  The file is created
    after the atomic rename (or its failure); the function
    never modifies the published bundle.
    """
    transcript_path = output_dir.parent / (
        f"{output_dir.name}-publication-result.json"
    )
    bundle_root_sha = ""
    bundle_root = output_dir / "bundle-root.json"
    if bundle_root.exists():
        import hashlib

        bundle_root_sha = hashlib.sha256(
            bundle_root.read_bytes()
        ).hexdigest()
    payload = {
        "final_path": str(output_dir) if success else None,
        "rename_succeeded": success,
        "staging_path": str(staging_dir) if staging_dir else None,
        "bundle_root_sha256": bundle_root_sha,
        "published_at": datetime.now(UTC).isoformat(),
        "protocol_stage": "manual-preclosure-publication-result",
        "leamas_protocol_E": False,
    }
    transcript_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


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
        F15=os.environ.get("K9B_F15", ""),
        F15_tree=os.environ.get("K9B_F15_TREE", ""),
        plan_blob=os.environ.get("K9B_PLAN_BLOB", ""),
        S15=os.environ.get("K9B_S15") or None,
        S15_tree=os.environ.get("K9B_S15_TREE") or None,
        parent_F15=os.environ.get("K9B_PARENT_F15", ""),
        parent_S15=os.environ.get("K9B_PARENT_S15") or None,
    )
    staging = args.output_dir.parent / (
        f"{args.output_dir.name}.tmp.{os.getpid()}"
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
        _record_publication_result(
            output_dir=args.output_dir,
            staging_dir=staging,
            success=False,
        )
        return 1
    _record_publication_result(
        output_dir=args.output_dir,
        staging_dir=staging,
        success=True,
    )
    print(
        f"wrote {args.output_dir}: "
        f"base={evidence.base_oid[:12]} "
        f"subject={evidence.subject_oid[:12]} "
        f"publication_status={evidence.publication_status}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
