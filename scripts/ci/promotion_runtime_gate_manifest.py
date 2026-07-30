"""Manifest loading and verification for the promotion runtime gate.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION05/06
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


# Expose REPO_ROOT so the orchestrator can import it
def _get_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


REPO_ROOT = _get_repo_root()


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
