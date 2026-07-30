"""Structured pytest plugin for the promotion runtime gate.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION06

The plugin records structured pytest information that the canonical
runner (``scripts/ci/run_promotion_runtime_gate.py``) consumes to
build a faithful runtime record.

For every test item the plugin records:

* the node ID at collection
* setup / call / teardown outcomes
* the final outcome (``passed`` / ``failed`` / ``skipped`` /
  ``xfailed`` / ``xpassed`` / ``error``)

Outcome classification:

  call failure          -> failed
  setup failure        -> error
  teardown failure     -> error
  expected failure     -> xfailed
  expected pass        -> xpassed  (non-strict xfail unexpectedly passes)
  strict-xpass         -> xpassed  (exit code reflects the strict violation)

A successful teardown does NOT downgrade a setup/call failure.

Configuration:

* ``K9B_RUNTIME_GATE_RESULT_PATH`` (env var, required)
  Path where the JSON result record is written.
* ``K9B_RUNTIME_GATE_COLLECT_ONLY`` (env var)
  ``"1"`` to enter collect-only mode (only collected_nodeids is
  populated, executed_nodeids is empty).

Final record schema::

    {
      "collected_nodeids":   [...],
      "executed_nodeids":    [...],
      "outcome_counts":      {"passed": N, "failed": N, "skipped": N,
                              "xfailed": N, "xpassed": N, "error": N},
      "pytest_exit_code":    <int>
    }

The plugin NEVER relies on terminal ``PASSED`` line parsing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

_OUTCOME_RANK = {
    "passed": 0,
    "skipped": 1,
    "xfailed": 2,
    "xpassed": 3,
    "failed": 4,
    "error": 5,
}


def _coerce_outcome(report: pytest.TestReport) -> str:
    """Return the canonical outcome name for a pytest report phase.

    Classification rules:
      - setup failure (when == "setup")         -> error
      - teardown failure (when == "teardown")   -> error
      - call failure (when == "call")            -> failed
      - skipped (any phase)                     -> skipped
      - wasxfail: failed in call                -> xpassed (expected fail, passed)
      - wasxfail: passed in call                -> xpassed (expected fail, passed)
      - wasxfail: skipped in call               -> xfailed (expected fail, skipped)
    """
    wasxfail = getattr(report, "wasxfail", False)

    # Setup / teardown failures are session-level errors.
    if report.when in ("setup", "teardown") and report.outcome == "failed":
        return "error"

    # Expected-failure handling — check before generic "skipped".
    if wasxfail:
        if report.outcome == "skipped":
            # xfail test was skipped (e.g. @pytest.mark.skip).
            return "xfailed"
        if report.outcome == "passed":
            return "xpassed"
        if report.outcome == "failed":
            # Strict xfail: expected to fail but passed.
            # pytest exits with 1 for strict-xpass, but the node outcome
            # is still "passed".  We map to xpassed so the gate counts it.
            return "xpassed"

    # Generic skipped.
    if report.outcome == "skipped":
        return "skipped"

    # Call failures.
    if report.outcome == "failed":
        return "failed"

    if report.outcome == "passed":
        return "passed"

    return report.outcome


class _RuntimeGatePlugin:
    """pytest plugin that records structured outcomes for the gate."""

    def __init__(self, result_path: Path, collect_only: bool) -> None:
        self._result_path = result_path
        self._collect_only = collect_only
        self._collected: list[str] = []
        self._executed: list[str] = []
        # nodeid -> ordered list of phase outcomes (setup/call/teardown)
        self._node_phases: dict[str, list[str]] = {}

    # -- pytest hooks ---------------------------------------------------------

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_finish(self, session: pytest.Session) -> None:
        """Record the complete list of collected node IDs.

        The canonical runner asserts that ``collected_nodeids`` equals
        ``executed_nodeids`` (when not in collect-only mode).
        """
        for item in session.items:
            nodeid = item.nodeid
            if nodeid not in self._collected:
                self._collected.append(nodeid)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_logreport(
        self, report: pytest.TestReport
    ) -> None:
        if self._collect_only:
            return
        nodeid = report.nodeid
        outcomes = self._node_phases.setdefault(nodeid, [])
        outcomes.append(_coerce_outcome(report))

    def pytest_sessionfinish(
        self, session: pytest.Session, exitstatus: int
    ) -> None:
        self._finalise(exitstatus)

    # -- helpers --------------------------------------------------------------

    def _final_outcome(self, nodeid: str) -> str:
        phases = self._node_phases.get(nodeid, [])
        if not phases:
            return "passed"  # collected but never run; default is "passed".
        # Worst-case phase by rank.
        worst = phases[0]
        for outcome in phases[1:]:
            if _OUTCOME_RANK[outcome] > _OUTCOME_RANK[worst]:
                worst = outcome
        return worst

    def _finalise(self, exitstatus: int) -> None:
        counts = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "xfailed": 0,
            "xpassed": 0,
            "error": 0,
        }
        executed: list[str] = []
        for nodeid in self._collected:
            if self._collect_only:
                continue
            if nodeid not in self._node_phases:
                # Never ran (e.g. collection-only or interrupted).
                continue
            final = self._final_outcome(nodeid)
            counts[final] = counts.get(final, 0) + 1
            executed.append(nodeid)
        self._executed = executed

        record: dict[str, Any] = {
            "collected_nodeids": sorted(self._collected),
            "executed_nodeids": sorted(self._executed),
            "outcome_counts": counts,
            "pytest_exit_code": exitstatus,
        }
        self._result_path.parent.mkdir(parents=True, exist_ok=True)
        self._result_path.write_text(
            json.dumps(record, indent=2, sort_keys=True),
            encoding="utf-8",
        )


@pytest.fixture
def _runtime_gate_record_path(
    request: pytest.FixtureRequest,
) -> Path | None:
    """Expose the structured result path to tests that want it."""
    env = os.environ.get("K9B_RUNTIME_GATE_RESULT_PATH")
    return Path(env) if env else None


def _build_plugin() -> _RuntimeGatePlugin | None:
    result_path_env = os.environ.get("K9B_RUNTIME_GATE_RESULT_PATH")
    if not result_path_env:
        return None
    collect_only = os.environ.get("K9B_RUNTIME_GATE_COLLECT_ONLY") == "1"
    return _RuntimeGatePlugin(Path(result_path_env), collect_only)


_PLUGIN = _build_plugin()


# Expose hook impls at module level so pytest discovery finds them.
_plugin = _PLUGIN


@pytest.hookimpl(tryfirst=True)
def pytest_collection_finish(session: pytest.Session) -> None:
    if _plugin is not None:
        _plugin.pytest_collection_finish(session)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if _plugin is not None:
        _plugin.pytest_runtest_logreport(report)


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(
    session: pytest.Session, exitstatus: int
) -> None:
    if _plugin is not None:
        _plugin.pytest_sessionfinish(session, exitstatus)
