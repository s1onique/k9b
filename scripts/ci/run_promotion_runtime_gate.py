"""Canonical inventory runner for the promotion runtime gate.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION05/06

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
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "scripts" / "ci" / "promotion_runtime_tests.txt"
DEFAULT_TRANSCRIPT = REPO_ROOT / "artifacts" / "runtime-gate-transcript.log"

PLUGIN_PATH = REPO_ROOT / "scripts" / "ci" / "pytest_runtime_gate_plugin.py"


class InventoryError(RuntimeError):
    """Raised when the manifest is invalid or execution fails."""


@dataclass(frozen=True)
class ManifestEntry:
    raw: str
    normalized: str

    @property
    def is_comment(self) -> bool:
        return self.raw.lstrip().startswith("#") or not self.normalized


@dataclass(frozen=True)
class InventoryReport:
    manifest_path: str
    manifest_sha256: str
    manifest_entry_count: int
    per_entry_sha256: dict[str, str]

    @property
    def manifest_path_repo_relative(self) -> str:
        try:
            return str(
                Path(self.manifest_path).resolve().relative_to(REPO_ROOT)
            )
        except ValueError:
            return self.manifest_path


def _load_manifest(manifest_path: Path) -> list[ManifestEntry]:
    """Read and parse the manifest strictly."""
    if not manifest_path.exists():
        raise InventoryError(f"manifest not found: {manifest_path}")
    raw = manifest_path.read_text(encoding="utf-8")
    entries: list[ManifestEntry] = []
    for line_no, raw_line in enumerate(raw.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            entries.append(ManifestEntry(raw=raw_line, normalized=""))
            continue
        if stripped.startswith("#"):
            entries.append(ManifestEntry(raw=raw_line, normalized=""))
            continue
        # No shell metacharacter interpretation.
        if "\\" in stripped:
            raise InventoryError(
                f"manifest line {line_no} contains backslash: {stripped!r}"
            )
        if ".." in stripped.split("/"):
            raise InventoryError(
                f"manifest line {line_no} contains traversal: {stripped!r}"
            )
        if Path(stripped).is_absolute():
            raise InventoryError(
                f"manifest line {line_no} is absolute: {stripped!r}"
            )
        if not stripped.startswith("tests/"):
            raise InventoryError(
                f"manifest line {line_no} is not under tests/: {stripped!r}"
            )
        entries.append(ManifestEntry(raw=raw_line, normalized=stripped))
    return entries


def _verify_inventory(
    entries: list[ManifestEntry],
    repo_root: Path,
    manifest_path: Path,
) -> InventoryReport:
    """Validate the strict path/node-ID contract and gather SHA-256.

    Hashes the exact bytes of the supplied manifest path; never the
    hard-coded DEFAULT_MANIFEST.
    """
    seen: set[str] = set()
    real_entries: list[str] = []
    for entry in entries:
        if entry.is_comment:
            continue
        if entry.normalized in seen:
            raise InventoryError(
                f"duplicate manifest entry: {entry.normalized!r}"
            )
        seen.add(entry.normalized)
        real_entries.append(entry.normalized)
    if not real_entries:
        raise InventoryError("manifest contains zero real entries")
    # Stable canonical order: lexicographic.
    real_entries_sorted = sorted(real_entries)
    if real_entries != real_entries_sorted:
        raise InventoryError(
            "manifest entries are not in stable lexicographic order"
        )
    # Every referenced Python file is Git-tracked.
    rel_paths = [e.split("::")[0] for e in real_entries]
    tracked = _git_ls_files(repo_root, rel_paths)
    missing = sorted(set(rel_paths) - set(tracked))
    if missing:
        raise InventoryError(
            "manifest references files not tracked in Git: "
            + ", ".join(missing)
        )
    # Every file must exist on disk at SUBJECT_SHA.
    absent = sorted(p for p in rel_paths if not (repo_root / p).exists())
    if absent:
        raise InventoryError(
            "manifest references files that do not exist on disk: "
            + ", ".join(absent)
        )
    per_entry = {p: _sha256(repo_root / p) for p in rel_paths}
    # Hash the exact bytes of the supplied manifest.  This is the
    # CORRECTION06 P0-7 manifest-identity correction.
    manifest_text = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_text).hexdigest()
    return InventoryReport(
        manifest_path=str(manifest_path.resolve()),
        manifest_sha256=manifest_sha256,
        manifest_entry_count=len(real_entries),
        per_entry_sha256=per_entry,
    )


def _git_ls_files(repo_root: Path, paths: list[str]) -> set[str]:
    """Return the subset of paths tracked by Git."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--", *paths],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise InventoryError(f"git ls-files failed: {exc.stderr}") from exc
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Pytest subprocess (single transcript writer authority).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GatePluginResult:
    collected_nodeids: list[str]
    executed_nodeids: list[str]
    outcome_counts: dict[str, int]
    pytest_exit_code: int


# ---------------------------------------------------------------------------
# Result schema (single authority — validated by _validate_result_payload).
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Transcript writer (single authority).
# ---------------------------------------------------------------------------


def _append_transcript_section(
    transcript: Path,
    title: str,
    body: str,
) -> None:
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


def main(argv: list[str] | None = None) -> int:
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