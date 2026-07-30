"""Canonical inventory runner for the promotion runtime gate.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION05

Modes:

  --verify-inventory   validate the strict path/node-ID contract
  --collect-only       invoke pytest against the complete canonical
                       inventory and record the collected node IDs
  --run                execute exactly that same inventory
  --manifest PATH      path to the canonical manifest file
                       (default: scripts/ci/promotion_runtime_tests.txt)
  --transcript PATH    append the runtime transcript (default:
                       artifacts/runtime-gate-transcript.log)

`runtime_gate=pass` is emitted on stdout only when the inventory
verification, collection and execution all succeed AND the executed
node count equals the collected node count.

argv is preserved verbatim: no shell, no metacharacter interpretation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "scripts" / "ci" / "promotion_runtime_tests.txt"
DEFAULT_TRANSCRIPT = REPO_ROOT / "artifacts" / "runtime-gate-transcript.log"


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
    manifest_sha256: str
    manifest_entry_count: int
    per_entry_sha256: dict[str, str]


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
) -> InventoryReport:
    """Validate the strict path/node-ID contract and gather SHA-256."""
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
    manifest_text = (repo_root / "scripts/ci/promotion_runtime_tests.txt").read_text(
        encoding="utf-8"
    )
    manifest_sha256 = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    return InventoryReport(
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


def _run_pytest(
    args: list[str],
    repo_root: Path,
    transcript: Path,
) -> tuple[int, set[str]]:
    """Run pytest with the given args; return (exit_code, collected_node_ids)."""
    transcript.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=", *args]
    collect_proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    collected = _extract_collected(collect_proc.stdout)
    # Append the collection transcript immediately, before execution, so a
    # missing inventory path still produces an uploadable transcript.
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write("=== collection ===\n")
        fh.write(collect_proc.stdout)
        if collect_proc.stderr:
            fh.write("\n=== collection stderr ===\n")
            fh.write(collect_proc.stderr)

    # Now execute.
    cmd_run = [sys.executable, "-m", "pytest", "-v", "-o", "addopts=", *args]
    run_proc = subprocess.run(
        cmd_run,
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write("\n=== execution ===\n")
        fh.write(run_proc.stdout)
        if run_proc.stderr:
            fh.write("\n=== execution stderr ===\n")
            fh.write(run_proc.stderr)
    return run_proc.returncode, collected


_COLLECT_LINE = re.compile(r"^(?:tests/\S+::\S+|tests/\S+)$")


def _extract_collected(stdout: str) -> set[str]:
    """Extract pytest --collect-only -q node IDs from the output tail."""
    collected: set[str] = set()
    for line in stdout.splitlines():
        line = line.strip()
        if not line or "::" not in line:
            continue
        # Pytest -q prints one node id per line, with "::" only at the
        # parenthesised test ID; accept any "::" form to stay robust.
        if line.startswith("tests/"):
            collected.add(line)
    return collected


def _emit(
    transcript: Path,
    inventory_report: InventoryReport,
    collected: set[str],
    executed: int,
    pytest_rc: int,
    repo_root: Path,
) -> None:
    """Append a structured JSON line to the runtime-gate transcript."""
    subject_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    record = {
        "subject_sha": subject_sha,
        "subject_tree": subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
        "manifest_sha256": inventory_report.manifest_sha256,
        "manifest_entry_count": inventory_report.manifest_entry_count,
        "collected_node_count": len(collected),
        "executed_node_count": executed,
        "pytest_exit_code": pytest_rc,
        "passed": passed_count(transcript),
    }
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write("\n=== runtime_gate_record ===\n")
        fh.write(json.dumps(record, indent=2, sort_keys=True))
        fh.write("\n")


_PASSED_RE = re.compile(r"^tests/.* PASSED\b")


def passed_count(transcript: Path) -> int:
    """Best-effort count of passed tests from the pytest execution transcript."""
    if not transcript.exists():
        return 0
    text = transcript.read_text(encoding="utf-8")
    return sum(1 for line in text.splitlines() if _PASSED_RE.search(line))


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
        help="execute the full inventory",
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
        inventory_report = _verify_inventory(entries, REPO_ROOT)
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

    real_entries = [
        e.normalized
        for e in entries
        if not e.is_comment
    ]

    if args.collect_only:
        pytest_rc, collected = _run_pytest(real_entries, REPO_ROOT, args.transcript)
        _emit(
            args.transcript,
            inventory_report,
            collected,
            executed=len(collected),
            pytest_rc=pytest_rc,
            repo_root=REPO_ROOT,
        )
        return 0 if pytest_rc == 0 else 1

    # --run (always implies collection + execution)
    pytest_rc, collected = _run_pytest(real_entries, REPO_ROOT, args.transcript)
    executed = passed_count(args.transcript)
    _emit(
        args.transcript,
        inventory_report,
        collected,
        executed=executed,
        pytest_rc=pytest_rc,
        repo_root=REPO_ROOT,
    )
    if pytest_rc == 0 and executed == len(collected) and executed > 0:
        print("runtime_gate=pass")
        return 0
    print("runtime_gate=fail", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())