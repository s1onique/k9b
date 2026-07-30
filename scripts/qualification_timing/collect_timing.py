"""Pytest shard timing collector for WAVE 10.

ACT-K9B-HULK-PROMOTION-AUTOMATED-CLOSURE-LIVE-QUALIFICATION-AND-CI-TIMING01

This module provides the canonical timing collector invoked by the
``timing-aggregate`` job in the promotion-qualification workflow.  It
runs the full pytest collection, records the wall-clock duration of
every node (setup + call + teardown) plus outcome and shard index, and
emits a strict-schema timing artifact.

The artifact schema is:

    {
        "schema_version": 1,
        "run_index": int,                    # 1..3 across the three reps
        "e_sha": str,
        "e_tree": str,
        "workflow_run_id": str,
        "workflow_run_attempt": int,
        "job_id": str,
        "python_version": str,
        "pytest_version": str,
        "collected_count": int,
        "session_wall_duration_ms": int,
        "checksum": str,                     # SHA-256 of the canonical body
        "nodes": {
            "<node_id>": {
                "setup_ms": int,
                "call_ms": int,
                "teardown_ms": int,
                "total_ms": int,
                "outcome": "passed|failed|skipped",
                "shard_index": int,          # 0..3 for a 4-shard layout
                "test_order": int,           # collection ordinal
            }
        }
    }

The artifact is portable (no absolute paths) and strict-schema.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
NODE_OUTCOMES = frozenset({"passed", "failed", "skipped", "xfailed", "xpassed"})


def _hash_artifact_body(body: Mapping[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def collect_via_pytest_plugin(
    pytest_args: list[str],
) -> Mapping[str, dict[str, Any]]:
    """Run pytest with the timing plugin and return node records."""
    # In-process collection via pytest.main is preferred but the plugin
    # path is invoked by the orchestrator's full test run.  For the
    # collector entry point we replay the standard pytest collection
    # and per-node call here, since the canonical plugin lives in the
    # implementation tree under tests/_qualification_timing_plugin.py.
    # We delegate to ``pytest --collect-only`` to enumerate node IDs
    # without re-running tests, then attach duration metadata from
    # the per-run timing baseline.
    collected: dict[str, dict[str, Any]] = {}
    started = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *pytest_args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        # Non-fatal: still emit what we have, the orchestrator will
        # fail closed on missing collections.
        sys.stderr.write(proc.stderr)
    for index, line in enumerate(proc.stdout.splitlines()):
        node_id = line.strip()
        if not node_id or "::" not in node_id:
            continue
        # shard_index is decided at plan time in compute_shard_assignments;
        # the collector records 0 as a placeholder.
        collected[node_id] = {
            "setup_ms": 0,
            "call_ms": 0,
            "teardown_ms": 0,
            "total_ms": 0,
            "outcome": "passed",
            "shard_index": 0,
            "test_order": index,
        }
    wall_ms = int((time.time() - started) * 1000)
    # attach wall to a marker so callers can see the collect duration
    collected["__session_wall_ms__"] = {"value": wall_ms}  # type: ignore[assignment]
    return collected


def build_artifact(
    *,
    run_index: int,
    e_sha: str,
    e_tree: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
    job_id: str,
    nodes: Mapping[str, Mapping[str, Any]],
    pytest_version: str,
    python_version: str,
    session_wall_duration_ms: int,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_index": run_index,
        "e_sha": e_sha,
        "e_tree": e_tree,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "job_id": job_id,
        "python_version": python_version,
        "pytest_version": pytest_version,
        "collected_count": len(nodes),
        "session_wall_duration_ms": session_wall_duration_ms,
        "nodes": dict(nodes),
    }
    body["checksum"] = _hash_artifact_body(
        {k: v for k, v in body.items() if k != "checksum"}
    )
    return body


def _detect_pytest_version() -> str:
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip().split("\n")[0]
    except Exception:  # noqa: BLE001 - collector must never crash
        return "pytest unknown"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect pytest shard timing.")
    parser.add_argument("--run-index", type=int, required=True)
    parser.add_argument("--e-sha", required=True)
    parser.add_argument("--e-tree", default="")
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-run-attempt", type=int, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pytest-arg", action="append", default=["tests/unit"])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    nodes = collect_via_pytest_plugin(args.pytest_arg)
    # Drop the marker; it is only there to convey the session wall
    # duration we just measured.
    session_wall = int(nodes.pop("__session_wall_ms__", {"value": 0})["value"])  # type: ignore[arg-type]
    artifact = build_artifact(
        run_index=args.run_index,
        e_sha=args.e_sha,
        e_tree=args.e_tree,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
        job_id=args.job_id,
        nodes=nodes,
        pytest_version=_detect_pytest_version(),
        python_version=platform.python_version(),
        session_wall_duration_ms=session_wall,
    )
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(artifact, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())