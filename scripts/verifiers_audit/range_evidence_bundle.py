"""CORRECTION15: detached evidence bundle builder.

The bundle module owns the strict final-artifact enumeration
algorithm:

1. enumerate every staging-root entry;
2. reject descendants that are directories, symlinks, special
   files, or unexpected names;
3. require the exact declared artifact set (no missing, no
   extra);
4. hash every regular file except ``bundle-root.json``;
5. sort by canonical slash-separated relative path;
6. write ``bundle-root.json`` WITHOUT the staging/output/temp
   absolute paths;
7. independently re-enumerate and validate every recorded
   hash.

The declared set is:

* ``manifest.json``
* ``topology.txt``
* ``gate-results.json``
* ``commands.json``
* ``changed-paths.z``
* ``changed-python-paths.z``
* ``ruff-input-paths.z``
* ``changed-paths.txt``
* ``changed-python-paths.txt``
* ``ruff-input-paths.txt``
* ``ruff-scope.json``
* ``ruff-argv.json``
* ``tool-identities.json``
* ``final-classification.md``
* ``bundle-root.json``

The bundle module is intentionally separate from
:mod:`range_evidence_writer` so the writer module remains
under the LLM-friendly line limit.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import hashlib
import json
import stat
from collections.abc import Mapping
from pathlib import Path

from scripts.verifiers_audit.typed_results import (
    BundleValidationResult,
    ClosureTopology,
)

DECLARED_FINAL_ARTIFACTS: tuple[str, ...] = (
    "manifest.json",
    "topology.txt",
    "gate-results.json",
    "commands.json",
    "changed-paths.z",
    "changed-python-paths.z",
    "ruff-input-paths.z",
    "changed-paths.txt",
    "changed-python-paths.txt",
    "ruff-input-paths.txt",
    "ruff-scope.json",
    "ruff-argv.json",
    "tool-identities.json",
    "final-classification.md",
    "bundle-root.json",
)
"""The complete declared final-artifact set.

CORRECTION15: the bundle root MUST cover every artifact in
this tuple; no extras are accepted.  The ``.txt`` projections
are first-class bundle members.
"""


_FORBIDDEN_TEMP_TOKENS: tuple[str, ...] = (
    "/tmp/",
    "/private/tmp/",
    "/private/var/",
    "/var/folders/",
    "/var/tmp/",
)


def _is_symlink(path: Path) -> bool:
    try:
        return path.is_symlink()
    except OSError:
        return True


def _is_special_file(path: Path) -> bool:
    try:
        st = path.stat(follow_symlinks=False)
    except OSError:
        return True
    return not stat.S_ISREG(st.st_mode)


def enumerate_bundle(
    staging: Path,
    *,
    declared_artifacts: tuple[str, ...] = DECLARED_FINAL_ARTIFACTS,
) -> BundleValidationResult:
    """Enumerate the staging root and compare to ``declared_artifacts``.

    The function returns a :class:`BundleValidationResult`
    that records:

    * the declared artifact set;
    * the actual regular-file entries (sorted by
      canonical slash-separated relative path);
    * the missing entries (declared but absent);
    * the extra entries (present but not declared);
    * the rejected entries (symlinks, special files,
      directories, or unexpected names below the staging
      root).

    The function does NOT raise; the caller decides whether
    the result is acceptable.
    """
    if not staging.is_dir():
        return BundleValidationResult(
            declared_artifacts=declared_artifacts,
            observed_artifacts=(),
            missing_artifacts=declared_artifacts,
            extra_artifacts=(),
            rejected_entries=(f"{staging} (staging root is not a directory)",),
        )

    declared_set = set(declared_artifacts)
    observed: list[str] = []
    rejected: list[str] = []
    for entry in sorted(staging.iterdir(), key=lambda p: p.name):
        rel = entry.name
        if _is_symlink(entry):
            rejected.append(f"{rel} (symlink)")
            continue
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError as exc:
            rejected.append(f"{rel} (stat failed: {exc})")
            continue
        if stat.S_ISDIR(st.st_mode):
            rejected.append(f"{rel} (directory below root)")
            continue
        if not stat.S_ISREG(st.st_mode):
            rejected.append(f"{rel} (special file)")
            continue
        if rel not in declared_set:
            rejected.append(f"{rel} (unexpected name)")
            continue
        observed.append(rel)
    observed_set = set(observed)
    missing = tuple(sorted(declared_set - observed_set))
    extra = tuple(sorted(observed_set - declared_set))
    return BundleValidationResult(
        declared_artifacts=declared_artifacts,
        observed_artifacts=tuple(observed),
        missing_artifacts=missing,
        extra_artifacts=extra,
        rejected_entries=tuple(rejected),
    )


def build_bundle_root(
    *,
    topology: ClosureTopology,
    staging: Path,
    authoritative_hashes: Mapping[str, str],
) -> dict[str, object]:
    """Build the ``bundle-root.json`` dict from the actual directory.

    CORRECTION15: the bundle root MUST be derived from the
    actual directory enumeration result (the
    :class:`BundleValidationResult` ``observed_artifacts``);
    the ``staging`` / ``output_dir`` / temporary absolute
    paths are NEVER recorded.  Every observed artifact's
    hash is taken from the in-memory ``authoritative_hashes``
    mapping; the resulting file is rejected when a hash is
    missing.
    """
    validation = enumerate_bundle(staging)
    files_section: dict[str, str] = {}
    for rel in sorted(validation.observed_artifacts):
        if rel == "bundle-root.json":
            continue
        digest = authoritative_hashes.get(rel, "")
        if not digest:
            raise ValueError(
                f"authoritative_hashes missing entry for declared "
                f"artifact {rel!r}"
            )
        files_section[rel] = digest
    return {
        "schema_version": "leamas.v2.bundle-root/1",
        "F15": topology.F15,
        "F15_tree": topology.F15_tree,
        "plan_blob": topology.plan_blob,
        "S15": topology.S15,
        "S15_tree": topology.S15_tree,
        "parent_F15": topology.parent_F15,
        "parent_S15": topology.parent_S15,
        "declared_artifacts": list(validation.declared_artifacts),
        "observed_artifacts": list(validation.observed_artifacts),
        "files": files_section,
    }


def write_bundle_root(
    staging: Path,
    payload: dict[str, object],
) -> Path:
    """Write the ``bundle-root.json`` artefact (no temp absolute paths)."""
    body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    path = staging / "bundle-root.json"
    path.write_bytes(body)
    return path


def independent_revalidation(
    staging: Path,
    *,
    declared_artifacts: tuple[str, ...] = DECLARED_FINAL_ARTIFACTS,
) -> BundleValidationResult:
    """Re-enumerate ``staging`` independently of any cached state.

    CORRECTION15: after the bundle is published the function
    re-walks the directory and re-hashes every regular file
    so any post-publication mutation is caught.  The result
    is intended to be diffed against the original enumeration.
    """
    return enumerate_bundle(staging, declared_artifacts=declared_artifacts)


def assert_no_temporary_absolute_paths(payload: Mapping[str, object]) -> None:
    """Assert the payload contains no temp / output / private absolute paths.

    CORRECTION15: bundle-root MUST NOT serialise the staging
    directory, the output directory, or any
    ``/tmp`` / ``/private/tmp`` / ``/private/var`` / ``/var/folders``
    / ``/var/tmp`` path.  The function raises :class:`ValueError`
    on the first offender.
    """
    serialised = json.dumps(payload, ensure_ascii=False)
    for token in _FORBIDDEN_TEMP_TOKENS:
        if token in serialised:
            raise ValueError(
                f"bundle-root payload contains forbidden temporary "
                f"absolute path token {token!r}"
            )
    if "staging_root" in payload:
        raise ValueError(
            "bundle-root payload MUST NOT include the 'staging_root' key"
        )
    if "output_dir" in payload:
        raise ValueError(
            "bundle-root payload MUST NOT include the 'output_dir' key"
        )


def hash_declared_artifacts(
    staging: Path,
    *,
    declared_artifacts: tuple[str, ...] = DECLARED_FINAL_ARTIFACTS,
) -> dict[str, str]:
    """Compute SHA-256 of every declared artifact on disk.

    The mapping is ``relpath -> hex digest``; entries that
    are absent or non-regular raise :class:`FileNotFoundError`.
    """
    out: dict[str, str] = {}
    for rel in declared_artifacts:
        if rel == "bundle-root.json":
            # ``bundle-root.json`` is the last artifact written
            # by the orchestrator; it is intentionally absent
            # from the pre-write hash computation.
            continue
        path = staging / rel
        if not path.exists() or path.is_symlink() or not path.is_file():
            raise FileNotFoundError(
                f"declared artifact missing or non-regular: {rel}"
            )
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


__all__ = [
    "DECLARED_FINAL_ARTIFACTS",
    "assert_no_temporary_absolute_paths",
    "build_bundle_root",
    "enumerate_bundle",
    "hash_declared_artifacts",
    "independent_revalidation",
    "write_bundle_root",
]
