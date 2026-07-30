"""Changed-paths manifest reader for the gate-summary producer.

Extracted from :mod:`scripts.factory.populate_gate_summary` so the
producer stays under the LLM-friendly 500-line cap.  The manifest
authoritatively lists the Python files whose changes the producer's
Ruff command must attest; the producer itself remains the orchestrator
that composes the gate-summary artifact from the manifest and the
canonical parser.
"""

from __future__ import annotations

from pathlib import Path
from subprocess import run

SCRIPT_REPO = Path(__file__).resolve().parent.parent.parent


def _read_changed_paths_manifest(manifest_path: Path) -> list[str]:
    """Parse a NUL-delimited changed-paths manifest into a stable sorted list.

    The manifest format is the output of:

        git diff --name-only -z --diff-filter=ACMRT <base>..<head>

    Validation rules:

    * every line MUST be a non-empty, repository-relative POSIX path;
    * no path may contain ``..`` segments, absolute prefixes, or
      backslashes;
    * every path must exist in the working tree (the manifest
      describes the exact range being attested);
    * only ``.py`` files are accepted (the gate-summary Ruff
      command MUST NOT receive non-Python arguments).

    An empty manifest is rejected; in range-attestation mode an
    empty manifest would silently attest zero changes which is
    never the intended contract.
    """
    raw = manifest_path.read_bytes()
    if b"\x00" in raw:
        paths = [segment.decode("utf-8") for segment in raw.split(b"\x00") if segment]
    else:
        paths = [line for line in raw.decode("utf-8").splitlines() if line]
    cleaned: list[str] = []
    for path in paths:
        if not path:
            continue
        if path.startswith("/") or path.startswith("\\") or "\\" in path:
            raise ValueError(
                f"changed-paths manifest entry MUST be repository-relative; "
                f"rejected {path!r}"
            )
        segments = path.split("/")
        if ".." in segments:
            raise ValueError(
                f"changed-paths manifest entry MUST NOT contain '..' traversal; "
                f"rejected {path!r}"
            )
        cleaned.append(path)
    if not cleaned:
        raise ValueError(
            "changed-paths manifest is empty; the producer refuses to attest "
            "an empty range (it would silently pass a no-change gate)"
        )
    seen: set[str] = set()
    deduped: list[str] = []
    for path in cleaned:
        if path in seen:
            raise ValueError(
                f"changed-paths manifest contains duplicate entry {path!r}"
            )
        seen.add(path)
        deduped.append(path)
    py_only = [path for path in deduped if path.endswith(".py")]
    if not py_only:
        raise ValueError(
            "changed-paths manifest contains no Python files; the gate-summary "
            "Ruff command has nothing to attest"
        )
    if len(py_only) != len(deduped):
        non_python = sorted(set(deduped) - set(py_only))
        raise ValueError(
            "changed-paths manifest MUST contain only Python files; "
            f"rejected {non_python}"
        )
    for path in py_only:
        if not (SCRIPT_REPO / path).exists():
            raise ValueError(
                f"changed-paths manifest entry does not exist in working tree: "
                f"{path!r}"
            )
    return sorted(py_only)


def _changed_python_files(
    manifest_path: Path | None = None,
) -> list[str]:
    """Return the list of Python files whose changes this run must attest.

    When ``manifest_path`` is supplied, the producer reads the
    NUL-delimited changed-paths manifest and uses it as the
    authoritative source.  Otherwise the producer falls back to the
    staged + unstaged ``git diff`` (kept for back-compat with
    ``scripts/verify_all.sh`` invocations that do not yet pass a
    manifest).
    """
    if manifest_path is not None:
        return _read_changed_paths_manifest(manifest_path)
    proc = run(
        ["git", "diff", "--name-only", "--cached", "--diff-filter=ACMR"],
        cwd=str(SCRIPT_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    staged = [line for line in proc.stdout.splitlines() if line.endswith(".py")]
    proc = run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR"],
        cwd=str(SCRIPT_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    unstaged = [line for line in proc.stdout.splitlines() if line.endswith(".py")]
    return sorted(set(staged + unstaged))
