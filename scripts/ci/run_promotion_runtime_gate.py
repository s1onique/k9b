"""Canonical inventory runner for the promotion runtime gate.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION05/06

This is the CLI orchestrator. Core functionality is split into:
- promotion_runtime_gate_manifest: manifest loading and verification
- promotion_runtime_gate_pytest: pytest subprocess and result handling
- promotion_runtime_gate_transcript: transcript writing

Modes:

  --verify-inventory   validate the strict path/node-ID contract
  --collect-only       invoke pytest --collect-only against the complete
                       canonical inventory and record the collected node
                       IDs; never executes test bodies
  --run                execute exactly the same inventory; collection
                       runs first and is required to succeed before
                       execution begins
  --manifest PATH      path to the canonical manifest file (default:
                       scripts/ci/promotion_runtime_tests.txt)
  --transcript PATH    append the runtime transcript (default:
                       artifacts/runtime-gate-transcript.log)

Outcomes are obtained from a dedicated pytest plugin
(``scripts/ci/pytest_runtime_gate_plugin.py``) which records:

  collected_nodeids      (set[str])
  executed_nodeids       (set[str])
  outcome_counts         (Mapping[str, int]) with keys
                         passed / failed / skipped / xfailed /
                         xpassed / error
  pytest_exit_code       (int)

Collection and execution are atomic steps; the Python runner owns the
transcript writer exclusively (no concurrent shell ``tee``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Import and re-export everything needed by tests and the CLI
from scripts.ci.promotion_runtime_gate_manifest import (
    REPO_ROOT,
    InventoryError,
    _load_manifest,
    _verify_inventory,
)
from scripts.ci.promotion_runtime_gate_pytest import (  # noqa: F401
    GatePluginResult,
    _run_pytest_subprocess,
    _validate_result_payload,
    collect_inventory,
    execute_inventory,
)
from scripts.ci.promotion_runtime_gate_transcript import (
    _append_transcript_section,
    _emit_runtime_gate_record,
)

DEFAULT_MANIFEST = REPO_ROOT / "scripts" / "ci" / "promotion_runtime_tests.txt"
DEFAULT_TRANSCRIPT = REPO_ROOT / "artifacts" / "runtime-gate-transcript.log"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the promotion runtime gate."""
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="run_promotion_runtime_gate.py",
        description=__doc__,
    )
    parser.add_argument(
        "--verify-inventory",
        action="store_true",
        help="validate the strict path/node-ID contract only",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="invoke pytest --collect-only against the full inventory",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="collect then execute the full inventory",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        default=DEFAULT_TRANSCRIPT,
    )
    args = parser.parse_args(argv)

    if not (args.verify_inventory or args.collect_only or args.run):
        print(
            "ERROR: one of --verify-inventory, --collect-only or --run "
            "is required",
            file=sys.stderr,
        )
        return 2

    try:
        entries = _load_manifest(args.manifest)
        inventory_report = _verify_inventory(entries, REPO_ROOT, args.manifest)
    except InventoryError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(
        f"OK: manifest verified, "
        f"{inventory_report.manifest_entry_count} entries, "
        f"sha256={inventory_report.manifest_sha256}"
    )

    if args.verify_inventory:
        return 0

    transcript = args.transcript

    if args.collect_only:
        try:
            _inventory_report, result = collect_inventory(
                args.manifest, REPO_ROOT
            )
        except InventoryError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        # --collect-only must NEVER execute a test body.
        if result.gate_result.executed_nodeids:
            print(
                "FAIL: --collect-only executed test bodies: "
                f"{result.gate_result.executed_nodeids}",
                file=sys.stderr,
            )
            return 1
        _append_transcript_section(
            transcript,
            "collection",
            json.dumps(
                {
                    "collected_nodeids": result.gate_result.collected_nodeids,
                    "pytest_exit_code": result.gate_result.pytest_exit_code,
                    "mode": "collect-only",
                },
                indent=2,
                sort_keys=True,
            ),
        )
        _emit_runtime_gate_record(
            transcript,
            inventory_report,
            collection_result=result,
            execution_result=None,
            repo_root=REPO_ROOT,
        )
        return 0 if result.gate_result.pytest_exit_code == 0 else 1

    # --run
    try:
        (
            inventory_report,
            collection_result,
            execution_result,
        ) = execute_inventory(args.manifest, REPO_ROOT)
    except InventoryError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    _append_transcript_section(
        transcript,
        "collection",
        json.dumps(
            {
                "collected_nodeids": collection_result.gate_result.collected_nodeids,
                "pytest_exit_code": collection_result.gate_result.pytest_exit_code,
                "mode": "run",
            },
            indent=2,
            sort_keys=True,
        ),
    )
    _append_transcript_section(
        transcript,
        "execution",
        json.dumps(
            {
                "executed_nodeids": execution_result.gate_result.executed_nodeids,
                "outcome_counts": execution_result.gate_result.outcome_counts,
                "pytest_exit_code": execution_result.gate_result.pytest_exit_code,
                "mode": "run",
            },
            indent=2,
            sort_keys=True,
        ),
    )
    _emit_runtime_gate_record(
        transcript,
        inventory_report,
        collection_result=collection_result,
        execution_result=execution_result,
        repo_root=REPO_ROOT,
    )

    collected_set = set(collection_result.gate_result.collected_nodeids)
    executed_set = set(execution_result.gate_result.executed_nodeids)
    outcome_counts = execution_result.gate_result.outcome_counts
    failed = outcome_counts.get("failed", 0) + outcome_counts.get("error", 0)
    skipped = outcome_counts.get("skipped", 0) + outcome_counts.get(
        "xfailed", 0
    ) + outcome_counts.get("xpassed", 0)

    if (
        execution_result.gate_result.pytest_exit_code == 0
        and failed == 0
        and skipped == 0
        and collected_set == executed_set
        and len(collected_set) > 0
    ):
        print("runtime_gate=pass")
        return 0
    print("runtime_gate=fail", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
