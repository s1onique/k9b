"""Pytest subprocess execution and result validation for the promotion runtime gate.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION05/06
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.ci.promotion_runtime_gate_manifest import (
    REPO_ROOT,
    InventoryError,
    InventoryReport,
    _load_manifest,
    _verify_inventory,
)


@dataclass(frozen=True)
class GatePluginResult:
    collected_nodeids: list[str]
    executed_nodeids: list[str]
    outcome_counts: dict[str, int]
    pytest_exit_code: int


def _validate_result_payload(
    payload: dict[str, Any],
    subprocess_returncode: int,
    executed_nodeids: list[str],
) -> GatePluginResult:
    """Validate a plugin result payload and return a GatePluginResult.

    This is the SINGLE authority for result validation.  Both production
    (_run_pytest_subprocess) and unit tests call this function directly.

    P0-1 contract: production calls this function — no duplicate inline
    validation exists anywhere else.
    """
    # P0-4/P0-6: plugin.pytest_exit_code MUST equal subprocess return code.
    plugin_exit_code = int(payload.get("pytest_exit_code", -1))
    if plugin_exit_code != subprocess_returncode:
        raise InventoryError(
            f"plugin/subprocess exit-code mismatch: plugin wrote "
            f"pytest_exit_code={plugin_exit_code} but subprocess returned "
            f"{subprocess_returncode}; possible partial write or stale artifact"
        )

    # P0-4: validate structured result schema — required fields.
    for field, expected_type in [
        ("collected_nodeids", list),
        ("executed_nodeids", list),
        ("outcome_counts", dict),
        ("pytest_exit_code", int),
    ]:
        if field not in payload:
            raise InventoryError(f"plugin result missing required field: {field}")
        if not isinstance(payload[field], expected_type):
            raise InventoryError(
                f"plugin result field {field} has wrong type "
                f"({type(payload[field]).__name__}; expected {expected_type.__name__})"
            )

    # P0-4: exact outcome key set (no extra keys).
    valid_keys = {"passed", "failed", "skipped", "xfailed", "xpassed", "error"}
    outcome_counts_raw: dict[str, Any] = payload["outcome_counts"]
    if set(outcome_counts_raw.keys()) != valid_keys:
        extra = set(outcome_counts_raw.keys()) - valid_keys
        missing = valid_keys - set(outcome_counts_raw.keys())
        msg = ""
        if extra:
            msg += f" unknown outcome keys: {sorted(extra)}"
        if missing:
            msg += f" missing outcome keys: {sorted(missing)}"
        raise InventoryError(f"plugin result outcome_counts schema violation:{msg}")

    # P0-4: each count must be a non-negative int (not bool, not float).
    for key in valid_keys:
        val = outcome_counts_raw[key]
        if isinstance(val, bool) or not isinstance(val, int):
            raise InventoryError(
                f"plugin result outcome_counts[{key!r}] is not int "
                f"(got {type(val).__name__}): {val!r}"
            )
        if val < 0:
            raise InventoryError(
                f"plugin result outcome_counts[{key!r}] is negative: {val}"
            )

    # P0-4: outcome-count sum must equal executed-nodeid count.
    total = sum(outcome_counts_raw[k] for k in valid_keys)
    if total != len(executed_nodeids):
        raise InventoryError(
            f"plugin result outcome_counts sum ({total}) != "
            f"len(executed_nodeids) ({len(executed_nodeids)})"
        )

    return GatePluginResult(
        collected_nodeids=list(payload["collected_nodeids"]),
        executed_nodeids=list(payload["executed_nodeids"]),
        outcome_counts=dict(outcome_counts_raw),
        pytest_exit_code=plugin_exit_code,
    )


def _run_pytest_subprocess(
    args: list[str],
    repo_root: Path,
    collect_only: bool,
) -> _PytestSubprocessResult:
    """Invoke pytest with the structured plugin and return its result.

    argv is preserved verbatim: no shell, no metacharacter
    interpretation.  The plugin writes a structured JSON record to
    PLUGIN_RESULT_PATH (an env var we set) which is read back by this
    function.  The subprocess is NEVER called with shell=True.

    P0-1 contract: this function delegates ALL result validation to
    _validate_result_payload — there is no duplicate inline validation.
    """
    result_path = repo_root / "artifacts" / "runtime-gate-pytest-result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    if result_path.exists():
        result_path.unlink()

    # PYTHONPATH must include scripts/ci so that the local
    # ``pytest_runtime_gate_plugin.py`` is importable as
    # ``pytest_runtime_gate_plugin`` (not a package).
    # Capture current process env so callers can pass WITNESS_PATH etc.
    env = os.environ.copy()
    _pythonpath = env.get("PYTHONPATH", "")
    scripts_ci = str(REPO_ROOT / "scripts" / "ci")
    env["PYTHONPATH"] = f"{scripts_ci}{os.pathsep}{_pythonpath}" if _pythonpath else scripts_ci
    env["K9B_RUNTIME_GATE_RESULT_PATH"] = str(result_path)
    env["K9B_RUNTIME_GATE_COLLECT_ONLY"] = "1" if collect_only else "0"

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
    ]
    if collect_only:
        cmd.append("--collect-only")
    cmd.extend(["-p", "pytest_runtime_gate_plugin", *args])
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
    )

    if not result_path.exists():
        raise InventoryError(
            "pytest plugin did not write structured result; "
            f"exit_code={proc.returncode} stderr={proc.stderr[-400:]}"
        )
    payload: dict[str, Any] = json.loads(result_path.read_text("utf-8"))

    # P0-1: delegate ALL validation to the single authority.
    # P0-6: extract executed_nodeids before validation so we can check
    # the count invariant.
    executed: list[str] = list(payload.get("executed_nodeids", []))
    result = _validate_result_payload(
        payload,
        subprocess_returncode=proc.returncode,
        executed_nodeids=executed,
    )

    # P0-6: preserve pytest argv, stdout, stderr for transcript diagnostics.
    return _PytestSubprocessResult(
        argv=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        gate_result=result,
    )


@dataclass(frozen=True)
class _PytestSubprocessResult:
    """Result of a pytest subprocess call with full diagnostic capture."""
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    gate_result: GatePluginResult


def collect_inventory(
    manifest_path: Path,
    repo_root: Path,
) -> tuple[InventoryReport, _PytestSubprocessResult]:
    """Run pytest --collect-only against the manifest."""
    entries = _load_manifest(manifest_path)
    inventory_report = _verify_inventory(entries, repo_root, manifest_path)
    real_entries = [
        e.normalized for e in entries if not e.is_comment
    ]
    result = _run_pytest_subprocess(
        real_entries, repo_root=repo_root, collect_only=True
    )
    return inventory_report, result


def execute_inventory(
    manifest_path: Path,
    repo_root: Path,
) -> tuple[InventoryReport, _PytestSubprocessResult, _PytestSubprocessResult]:
    """Run collection, enforce zero-exit collection, then execute."""
    entries = _load_manifest(manifest_path)
    inventory_report = _verify_inventory(entries, repo_root, manifest_path)
    real_entries = [
        e.normalized for e in entries if not e.is_comment
    ]
    collection_result = _run_pytest_subprocess(
        real_entries, repo_root=repo_root, collect_only=True
    )
    if collection_result.returncode != 0:
        raise InventoryError(
            "collection exit code is non-zero; aborting before execution: "
            f"exit_code={collection_result.returncode}"
        )
    execution_result = _run_pytest_subprocess(
        real_entries, repo_root=repo_root, collect_only=False
    )
    return inventory_report, collection_result, execution_result
