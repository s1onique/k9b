"""Manifest loading and verification for the promotion runtime gate.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION05/06

CORRECTION10: Manifest is now loaded from the subject Git object (git show),
not the working tree. This ensures the manifest is subject-bound and
repository-aware.
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
    """Result of manifest loading and verification.

    CORRECTION10: All fields are now subject-bound and repository-aware.
    """

    manifest_path: str
    manifest_blob_oid: str
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

    @property
    def runtime_test_paths(self) -> frozenset[str]:
        """Return the set of manifest paths as a frozenset for fast lookup."""
        return frozenset(self.per_entry_sha256.keys())


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
    # Get blob OID from working tree
    result = subprocess.run(
        ["git", "hash-object", "-t", "blob", "--", str(manifest_path)],
        capture_output=True,
        cwd=repo_root,
        check=True,
    )
    manifest_blob_oid = result.stdout.decode().strip()
    return InventoryReport(
        manifest_path=str(manifest_path.resolve()),
        manifest_blob_oid=manifest_blob_oid,
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


def _git_show(repo_root: Path, subject_sha: str, path: str) -> tuple[bytes, str]:
    """Read file contents from a Git object at a specific revision.

    Returns:
        Tuple of (content_bytes, blob_oid).
    """
    # First get the blob OID
    result = subprocess.run(
        ["git", "hash-object", "-t", "blob", "--stdin"],
        input=b"placeholder",
        capture_output=True,
        cwd=repo_root,
        check=True,
    )
    # Read the file from the subject
    result = subprocess.run(
        ["git", "show", f"{subject_sha}:{path}"],
        capture_output=True,
        cwd=repo_root,
        check=True,
    )
    # Get the blob OID for the content
    content = result.stdout
    blob_result = subprocess.run(
        ["git", "hash-object", "-t", "blob"],
        input=content,
        capture_output=True,
        cwd=repo_root,
        text=False,
        check=True,
    )
    blob_oid = blob_result.stdout.decode().strip()
    return content, blob_oid


def _git_cat_file_exists(repo_root: Path, subject_sha: str, path: str) -> bool:
    """Check if a file exists in a Git object at a specific revision."""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{subject_sha}:{path}"],
        capture_output=True,
        cwd=repo_root,
    )
    return result.returncode == 0


def load_manifest(
    *,
    repo_root: Path | None = None,
    subject_sha: str | None = None,
    manifest_path: str = "scripts/ci/promotion_runtime_tests.txt",
) -> InventoryReport:
    """Load and verify the promotion runtime test manifest from a subject Git object.

    CORRECTION10: The manifest is now loaded from the subject Git object using
    `git show`, not from the working tree. This ensures the manifest is
    subject-bound and repository-aware.

    Args:
        repo_root: Repository root. Defaults to REPO_ROOT.
        subject_sha: Git commit SHA to read manifest from. If None, reads from
            working tree (deprecated fallback).
        manifest_path: Repository-relative path to the manifest file.

    Returns:
        InventoryReport with manifest_blob_oid, manifest_sha256, paths, and
        entry count.

    Raises:
        InventoryError: If the manifest is missing, malformed, or references
            non-existent files.

    No global cache - each call loads fresh from the specified subject.
    """
    if repo_root is None:
        repo_root = REPO_ROOT

    if subject_sha is not None:
        # Subject-bound: read from Git object
        if not _git_cat_file_exists(repo_root, subject_sha, manifest_path):
            raise InventoryError(
                f"manifest blob not found at {subject_sha}:{manifest_path}"
            )
        manifest_bytes, manifest_blob_oid = _git_show(repo_root, subject_sha, manifest_path)
        manifest_text = manifest_bytes.decode("utf-8")
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    else:
        # Working-tree fallback (deprecated)
        manifest_path_obj = repo_root / manifest_path
        if not manifest_path_obj.exists():
            raise InventoryError(f"manifest not found: {manifest_path_obj}")
        manifest_bytes = manifest_path_obj.read_bytes()
        manifest_text = manifest_bytes.decode("utf-8")
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        # Get blob OID from working tree
        result = subprocess.run(
            ["git", "hash-object", "-t", "blob", "--", manifest_path],
            capture_output=True,
            cwd=repo_root,
            check=True,
        )
        manifest_blob_oid = result.stdout.decode().strip()

    # Parse entries from text
    entries: list[ManifestEntry] = []
    for line_no, raw_line in enumerate(manifest_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            entries.append(ManifestEntry(raw=raw_line, normalized=""))
            continue
        if stripped.startswith("#"):
            entries.append(ManifestEntry(raw=raw_line, normalized=""))
            continue
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

    # Extract real entries
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

    # Every referenced Python file must exist at SUBJECT_SHA (if provided)
    rel_paths = [e.split("::")[0] for e in real_entries]
    if subject_sha is not None:
        for path in rel_paths:
            if not _git_cat_file_exists(repo_root, subject_sha, path):
                raise InventoryError(
                    f"manifest entry not found at {subject_sha}:{path}"
                )

    per_entry: dict[str, str] = {}
    for path in rel_paths:
        if subject_sha is not None:
            content, _ = _git_show(repo_root, subject_sha, path)
            per_entry[path] = hashlib.sha256(content).hexdigest()
        else:
            per_entry[path] = _sha256(repo_root / path)

    return InventoryReport(
        manifest_path=manifest_path,
        manifest_blob_oid=manifest_blob_oid,
        manifest_sha256=manifest_sha256,
        manifest_entry_count=len(real_entries),
        per_entry_sha256=per_entry,
    )
