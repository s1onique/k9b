"""Transcript writer for the promotion runtime gate.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION05/06
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from promotion_runtime_gate_manifest import InventoryReport
from promotion_runtime_gate_pytest import (
    _PytestSubprocessResult,
)


def _append_transcript_section(
    transcript: Path,
    title: str,
    body: str,
) -> None:
    """Append a titled section to the transcript file."""
    transcript.parent.mkdir(parents=True, exist_ok=True)
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write(f"\n=== {title} ===\n")
        fh.write(body)
        if not body.endswith("\n"):
            fh.write("\n")


def _emit_runtime_gate_record(
    transcript: Path,
    inventory_report: InventoryReport,
    collection_result: _PytestSubprocessResult,
    execution_result: _PytestSubprocessResult | None,
    repo_root: Path,
) -> None:
    """Write the structured runtime_gate_record as the FINAL section.

    Workflow stdout MUST NOT concurrently append to this transcript; the
    runner is the SOLE writer.
    """
    subject_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subject_tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    collected_set = set(collection_result.gate_result.collected_nodeids)
    exec_result = execution_result or collection_result
    executed_set = set(exec_result.gate_result.executed_nodeids)
    outcome_counts = exec_result.gate_result.outcome_counts
    pytest_rc = exec_result.gate_result.pytest_exit_code

    record: dict[str, Any] = {
        "subject_sha": subject_sha,
        "subject_tree": subject_tree,
        "manifest_path_repo_relative": inventory_report.manifest_path_repo_relative,
        "manifest_sha256": inventory_report.manifest_sha256,
        "manifest_entry_count": inventory_report.manifest_entry_count,
        "per_entry_sha256": inventory_report.per_entry_sha256,
        "collected_node_count": len(collected_set),
        "executed_node_count": len(executed_set),
        "collected_nodeids": sorted(collected_set),
        "executed_nodeids": sorted(executed_set),
        "node_set_equal": collected_set == executed_set,
        "outcome_counts": outcome_counts,
        "pytest_exit_code": pytest_rc,
    }

    payload = json.dumps(record, indent=2, sort_keys=True)
    transcript.parent.mkdir(parents=True, exist_ok=True)
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write("\n=== runtime_gate_record ===\n")
        fh.write(payload)
        fh.write("\n")
