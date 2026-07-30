"""Real pytest timing plugin for WAVE 10 / P0-11.

ACT-K9B-HULK-PROMOTION-AUTOMATED-CLOSURE-LIVE-QUALIFICATION-AND-CI-TIMING01

This plugin records REAL setup, call, and teardown durations per test
node using the public ``pytest_runtest_logreport`` hook.  Per-phase
timings are accumulated from each report.  Real pytest exit status is
preserved; the plugin never swallows failures.

Artifact schema (strict):

    {
        "schema_version": 1,
        "run_index": int,
        "e_sha": str,
        "subject_sha": str,
        "subject_tree": str,
        "workflow_run_id": str,
        "workflow_run_attempt": int,
        "job_id": str,
        "shard_index": int,
        "python_version": str,
        "pytest_version": str,
        "collected_count": int,
        "session_wall_duration_ms": int,
        "checksum": str,                 # SHA-256 over canonical JSON
        "nodes": {
            "<node_id>": {
                "setup_ms": int,
                "call_ms": int,
                "teardown_ms": int,
                "total_ms": int,
                "outcome": "passed|failed|skipped|xfailed|xpassed",
                "shard_index": int,
                "test_order": int,
            }
        }
    }
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

SCHEMA_VERSION = 1

_NODE_STATE_KEY = "_k9b_qual_timing_state"


def _canonical_json(d: Mapping[str, Any]) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def _hash_artifact_body(d: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(d).encode("utf-8")).hexdigest()


class _PluginState:
    """Mutable state carried through the pytest session lifecycle."""

    def __init__(
        self,
        *,
        output: str,
        run_index: int,
        e_sha: str,
        subject_sha: str,
        subject_tree: str,
        shard_index: int,
        canonical_collection: str,
        workflow_run_id: str,
        workflow_run_attempt: int,
        job_id: str,
    ) -> None:
        self.output = output
        self.run_index = run_index
        self.e_sha = e_sha
        self.subject_sha = subject_sha
        self.subject_tree = subject_tree
        self.shard_index = shard_index
        self.canonical_collection = canonical_collection
        self.workflow_run_id = workflow_run_id
        self.workflow_run_attempt = workflow_run_attempt
        self.job_id = job_id
        # node_id -> { setup_ms, call_ms, teardown_ms, outcome, test_order }
        self.nodes: dict[str, dict[str, Any]] = {}
        # node_id -> { "phase": str, "started_at": float } tracking current phase
        self._phase_started_at: dict[str, float] = {}
        self._phase_accumulated: dict[str, dict[str, int]] = {}
        self._session_started_at = time.time()
        self._collected_count = 0

    def record_phase(self, nodeid: str, phase: str, duration_ms: int) -> None:
        node = self.nodes.setdefault(
            nodeid,
            {
                "setup_ms": 0,
                "call_ms": 0,
                "teardown_ms": 0,
                "total_ms": 0,
                "outcome": "passed",
                "shard_index": self.shard_index,
                "test_order": len(self.nodes),
            },
        )
        phase_key = f"{phase}_ms"
        node[phase_key] = int(node.get(phase_key, 0)) + int(duration_ms)
        node["total_ms"] = int(node["total_ms"]) + int(duration_ms)

    def finalize_outcome(self, nodeid: str, outcome: str) -> None:
        node = self.nodes.setdefault(
            nodeid,
            {
                "setup_ms": 0,
                "call_ms": 0,
                "teardown_ms": 0,
                "total_ms": 0,
                "outcome": "passed",
                "shard_index": self.shard_index,
                "test_order": len(self.nodes),
            },
        )
        node["outcome"] = outcome


def _add_option(parser: pytest.Parser) -> None:
    group = parser.getgroup("k9b-qualification-timing")
    group.addoption(
        "--qualification-timing-output",
        action="store",
        default="/tmp/k9b_qual_timing.json",
        help="Path to the timing artifact (default: /tmp/k9b_qual_timing.json).",
    )
    group.addoption(
        "--qualification-run-index",
        action="store",
        type=int,
        default=1,
        help="Repetition index (1..3) for this timing run.",
    )
    group.addoption(
        "--qualification-e-sha",
        action="store",
        default="",
        help="Closure SHA recorded for this run.",
    )
    group.addoption(
        "--qualification-subject-sha",
        action="store",
        default="",
        help="Subject SHA recorded for this run.",
    )
    group.addoption(
        "--qualification-subject-tree",
        action="store",
        default="",
        help="Subject tree SHA recorded for this run.",
    )
    group.addoption(
        "--qualification-shard-index",
        action="store",
        type=int,
        default=0,
        help="Shard index (0..3) for this run.",
    )
    group.addoption(
        "--qualification-canonical-collection",
        action="store",
        default="",
        help="Path to canonical collection JSON (used for bijection).",
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    _add_option(parser)


def pytest_configure(config: pytest.Config) -> None:
    state = _PluginState(
        output=config.getoption("--qualification-timing-output"),
        run_index=int(config.getoption("--qualification-run-index")),
        e_sha=config.getoption("--qualification-e-sha"),
        subject_sha=config.getoption("--qualification-subject-sha"),
        subject_tree=config.getoption("--qualification-subject-tree"),
        shard_index=int(config.getoption("--qualification-shard-index")),
        canonical_collection=config.getoption("--qualification-canonical-collection"),
        workflow_run_id=os.environ.get("GITHUB_RUN_ID", "local"),
        workflow_run_attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")),
        job_id=os.environ.get("GITHUB_JOB", "local"),
    )
    config._k9b_qual_state = state  # type: ignore[attr-defined]


@pytest.hookimpl(tryfirst=False)
def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Public hook: record real phase durations.

    pytest emits three logreport phases per node: setup, call, teardown.
    ``report.duration`` is the per-phase duration in seconds.  We
    accumulate these into setup_ms / call_ms / teardown_ms.
    """
    state: _PluginState = getattr(report, "_k9b_qual_state", None)  # type: ignore[arg-type]
    # Pytest does not pass the config to logreport; we attach via a
    # monkey-patch shim: pytest collects the state in the session
    # module.  Fall back to module-level state.
    if state is None:
        state = _module_state
    if state is None:
        return
    duration_ms = int(round(report.duration * 1000.0))
    nodeid = report.nodeid
    if report.when == "setup":
        state.record_phase(nodeid, "setup", duration_ms)
    elif report.when == "call":
        state.record_phase(nodeid, "call", duration_ms)
    elif report.when == "teardown":
        state.record_phase(nodeid, "teardown", duration_ms)
    if report.when in ("call", "teardown"):
        # outcome is finalised by the call phase; teardown only
        # reports error if teardown itself failed
        outcome = "passed"
        if report.outcome == "failed":
            outcome = "failed"
        elif report.outcome == "skipped":
            outcome = "skipped"
        elif report.outcome == "xfailed":
            outcome = "xfailed"
        elif report.outcome == "xpassed":
            outcome = "xpassed"
        state.finalize_outcome(nodeid, outcome)


_module_state: _PluginState | None = None


@pytest.hookimpl(tryfirst=True)
def pytest_collection(session: pytest.Session) -> None:
    state: _PluginState | None = getattr(session.config, "_k9b_qual_state", None)
    if state is not None:
        global _module_state
        _module_state = state
        state._collected_count = len(session.items)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    state: _PluginState | None = getattr(session.config, "_k9b_qual_state", None)
    if state is None:
        return
    session_wall_ms = int((time.time() - state._session_started_at) * 1000)
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_index": state.run_index,
        "e_sha": state.e_sha,
        "subject_sha": state.subject_sha,
        "subject_tree": state.subject_tree,
        "workflow_run_id": state.workflow_run_id,
        "workflow_run_attempt": state.workflow_run_attempt,
        "job_id": state.job_id,
        "shard_index": state.shard_index,
        "python_version": platform.python_version(),
        "pytest_version": pytest.__version__,
        "collected_count": state._collected_count,
        "session_wall_duration_ms": session_wall_ms,
        "nodes": dict(state.nodes),
    }
    body["checksum"] = _hash_artifact_body(
        {k: v for k, v in body.items() if k != "checksum"}
    )
    target = Path(state.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: temp + os.replace
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    # PRESERVE real exit status; never swallow failures
    if exitstatus != 0:
        sys.stderr.write(
            f"qual-timing: pytest exit={exitstatus}; artifact retained at {target}\n"
        )


def _detect_pytest_version() -> str:
    return pytest.__version__


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run qualification timing on a shard.")
    parser.add_argument("--run-index", type=int, required=True)
    parser.add_argument("--e-sha", required=True)
    parser.add_argument("--subject-sha", required=True)
    parser.add_argument("--subject-tree", default="")
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--canonical-collection", default="")
    parser.add_argument("--workflow-run-id", default="local")
    parser.add_argument("--workflow-run-attempt", type=int, default=1)
    parser.add_argument("--job-id", default="local")
    parser.add_argument("--output", required=True)
    parser.add_argument("--shard-manifest", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not Path(args.shard_manifest).exists():
        print(f"FATAL: shard manifest {args.shard_manifest} missing", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent.parent) + os.pathsep + env.get("PYTHONPATH", ""),
    })
    cmd = [
        sys.executable, "-m", "pytest",
        "-p", "scripts.qualification_timing.pytest_plugin",
        "--qualification-timing-output", args.output,
        "--qualification-run-index", str(args.run_index),
        "--qualification-e-sha", args.e_sha,
        "--qualification-subject-sha", args.subject_sha,
        "--qualification-subject-tree", args.subject_tree,
        "--qualification-shard-index", str(args.shard_index),
        "--qualification-canonical-collection", args.canonical_collection,
        "@" + args.shard_manifest,
    ]
    proc = subprocess.run(cmd, env=env, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())