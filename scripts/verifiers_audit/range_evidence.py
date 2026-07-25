"""CORRECTION13/CORRECTION14/CORRECTION15/CORRECTION16: detached range evidence
CLI shim.

This module is a thin CLI wrapper.  The orchestrator lives
in :mod:`range_evidence_orchestrator`; the bundle writers
live in :mod:`range_evidence_writer` and
:mod:`range_evidence_builders`; the typed result
dataclasses live in :mod:`typed_results`; the bundle
directory enumeration lives in
:mod:`range_evidence_bundle`.

CORRECTION16: the CLI

* derives the F16 / S16 topology from the Git transcript
  (the caller-supplied environment topology is treated as
  an expectation only);
* records every Git invocation through the seam (the
  orchestrator tags every command with its kind);
* writes the external publication result AFTER the
  rename (the in-bundle files NEVER claim their own
  later publication succeeded).

Usage::

    python scripts/verifiers_audit/range_evidence.py \\
        --base F16 --subject S16 --output-dir /tmp/closure_evidence_16
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.verifiers_audit.discovery import REPO_ROOT
from scripts.verifiers_audit.range_evidence_bundle import (
    rehash_published_bundle,
)
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
    staging_dir: Path | None,
    success: bool,
    bundle_bound_to: str,
    exit_nonzero: bool,
) -> None:
    """Write the external publication transcript.

    CORRECTION16: the manual publication transcript lives
    OUTSIDE the immutable bundle.  The file is created
    AFTER the atomic rename (or its failure).  The
    function records the bundle-bound subject, the rename
    result, the staging removal status, and the nonzero
    exit status.  The in-bundle ``READY_TO_PUBLISH`` claim
    is NEVER duplicated here.
    """
    transcript_path = output_dir.parent / (
        f"{output_dir.name}-publication-result.json"
    )
    bundle_root_sha = ""
    bundle_root = output_dir / "bundle-root.json"
    if bundle_root.exists():
        bundle_root_sha = hashlib.sha256(
            bundle_root.read_bytes()
        ).hexdigest()
    staging_removed = True
    if staging_dir is not None and staging_dir.exists():
        staging_removed = False
    published_hashes: dict[str, str] = {}
    if success:
        try:
            published_hashes = rehash_published_bundle(output_dir)
        except FileNotFoundError:
            published_hashes = {}
    payload = {
        "final_path": str(output_dir) if success else None,
        "rename_succeeded": success,
        "staging_removed": staging_removed,
        "staging_path": str(staging_dir) if staging_dir else None,
        "bundle_root_sha256": bundle_root_sha,
        "published_at": datetime.now(UTC).isoformat(),
        "protocol_stage": "manual-preclosure-publication-result",
        "leamas_protocol_E": False,
        "bundle_bound_to": bundle_bound_to,
        "exit_nonzero": exit_nonzero,
        "published_hashes": published_hashes,
    }
    transcript_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _synthesise_closure_topology() -> ClosureTopology:
    """Build a placeholder ClosureTopology.

    CORRECTION16: the orchestrator derives the topology from
    the Git transcript; the CLI passes a placeholder so the
    ``ClosureTopology`` argument has a value.  The
    orchestrator does NOT consult this object.
    """
    return ClosureTopology(
        F16="",
        F16_tree="",
        plan_blob="",
        S16=None,
        S16_tree=None,
        parent_F16="",
        parent_S16=None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--plan-path",
        type=str,
        default="docs/closure-plans/ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION16.json",
    )
    args = parser.parse_args(argv)
    topology = _synthesise_closure_topology()
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
            plan_path=args.plan_path,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        # Remove the staging directory on failure.
        if staging.exists():
            try:
                shutil.rmtree(staging)
            except OSError:
                pass
        _record_publication_result(
            output_dir=args.output_dir,
            staging_dir=staging,
            success=False,
            bundle_bound_to=(
                f"FAILED_TRANSACTION: {args.base}..{args.subject}"
            ),
            exit_nonzero=True,
        )
        return 1
    _record_publication_result(
        output_dir=args.output_dir,
        staging_dir=None,
        success=True,
        bundle_bound_to=evidence.subject_oid,
        exit_nonzero=False,
    )
    print(
        f"wrote {args.output_dir}: "
        f"base={evidence.base_oid[:12]} "
        f"subject={evidence.subject_oid[:12]} "
        f"publication_status={evidence.publication_status} "
        f"topology_git_commands="
        f"{evidence.transaction_summary.topology_git_commands} "
        f"range_git_commands="
        f"{evidence.transaction_summary.range_git_commands} "
        f"gate_git_commands="
        f"{evidence.transaction_summary.gate_git_commands} "
        f"unrecorded={evidence.transaction_summary.unrecorded_git_commands} "
        f"hidden_shell={evidence.transaction_summary.hidden_shell_git_invocations}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
