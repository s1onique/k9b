"""Source preservation evidence (R5 / CORRECTION03).

For every tracked production verifier and core file, record:

* ``head_sha256``     - the SHA-256 of the file at HEAD
* ``index_sha256``    - the SHA-256 of the file staged in the index
* ``working_tree_sha256`` - the SHA-256 of the file in the working tree

Closure requires ``working_tree_sha256 == head_sha256`` and
``index_sha256 == head_sha256`` for every protected path.
The audit also proves that no protected path appears in
``git diff --name-only`` or ``git diff --cached --name-only``.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import hashlib
import subprocess

from scripts.verifiers_audit.discovery import REPO_ROOT


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)!r} failed with exit code {proc.returncode}: "
            f"{proc.stderr!r}"
        )
    return proc.stdout


def _tracked_production_paths() -> list[str]:
    out = _git(
        "ls-files", "scripts/verifiers/*.py", "scripts/verifiers/**/*.py"
    )
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def _hash_blob(ref: str, path: str) -> str:
    """Return the SHA-256 of ``ref:path``. ``ref`` may be ``HEAD``,
    the literal string ``:0`` (index), or empty (working tree)."""
    if ref == ":0":
        spec = f":0:{path}"
    elif ref:
        spec = f"{ref}:{path}"
    else:
        full = REPO_ROOT / path
        if not full.exists():
            return ""
        return hashlib.sha256(full.read_bytes()).hexdigest()
    proc = subprocess.run(
        ["git", "cat-file", "blob", spec],
        cwd=str(REPO_ROOT),
        capture_output=True,
        check=False,
    )
    return hashlib.sha256(proc.stdout).hexdigest()


def build_source_preservation() -> dict[str, object]:
    paths = _tracked_production_paths()
    rows: list[dict[str, object]] = []
    for path in paths:
        head = _hash_blob("HEAD", path)
        idx = _hash_blob(":0", path)
        wt = _hash_blob("", path)
        rows.append({
            "path": path,
            "head_sha256": head,
            "index_sha256": idx,
            "working_tree_sha256": wt,
            "preserved": (head == wt == idx and head != ""),
        })
    working_diff = sorted(
        line.strip() for line in
        _git("diff", "--name-only").splitlines()
        if line.strip()
    )
    staged_diff = sorted(
        line.strip() for line in
        _git("diff", "--cached", "--name-only").splitlines()
        if line.strip()
    )
    protected_in_working = sorted(
        set(working_diff) & set(paths)
    )
    protected_in_staged = sorted(
        set(staged_diff) & set(paths)
    )
    preserved_count = sum(1 for r in rows if r["preserved"])
    return {
        "schema_version": "1.0",
        "totals": {
            "tracked_path_count": len(paths),
            "preserved_path_count": preserved_count,
            "working_tree_drift_count": len(protected_in_working),
            "staged_drift_count": len(protected_in_staged),
        },
        "protected_paths": rows,
        "working_tree_drift": protected_in_working,
        "staged_drift": protected_in_staged,
    }
