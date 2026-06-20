"""Git/ref and CSV loading for disposition diff reporter.

Responsibilities:
- Git operations (ls-tree, show) against REPO_ROOT
- Loading all disposition shards from a git ref or local directory
- Strict CSV parsing with header and row validation
"""
from __future__ import annotations

import csv
import io
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SHARDS_DIR = REPO_ROOT / "docs" / "claims"
SHARD_PATTERN = "docs_claim_dispositions-shard-*.csv"
CANDIDATE_ID_RE = re.compile(r"^DOC-CAND-[0-9a-f]{12}$")
REQUIRED_COLUMNS = [
    "candidate_id",
    "disposition",
    "claim_id",
    "covered_by_claim_id",
    "reason_code",
    "reviewed_at",
    "reviewer_notes",
]
# Fields that matter for semantic diff (reviewer_notes is user-facing annotation)
SEMANTIC_FIELDS = [
    "candidate_id",
    "disposition",
    "claim_id",
    "covered_by_claim_id",
    "reason_code",
    "reviewed_at",
    "reviewer_notes",
]


def git_ls_tree(ref: str, path: str) -> list[str]:
    """List files at path within a git ref using ls-tree.

    Args:
        ref: Git ref (commit, branch, tag, etc.)
        path: Relative path within repo

    Returns:
        List of relative file paths from the repo root

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-tree", "-r", "--name-only", ref, "--", path],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def git_show(ref: str, path: str) -> str:
    """Get file content from a git ref.

    Args:
        ref: Git ref
        path: Relative path within repo

    Returns:
        File content as string

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{ref}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def load_dispositions_from_ref(ref: str) -> tuple[list[dict[str, str]], list[str]]:
    """Load all disposition shards from a git ref.

    Args:
        ref: Git ref to load from

    Returns:
        (rows, errors) where rows is list of parsed CSV rows and errors is list
        of validation error messages
    """
    errors: list[str] = []
    all_rows: list[dict[str, str]] = []

    # Find all shard files in the ref
    try:
        shard_paths = git_ls_tree(ref, "docs/claims")
    except subprocess.CalledProcessError as exc:
        return [], [f"git ls-tree failed: {exc.stderr.strip()}"]

    shard_files = sorted(
        p for p in shard_paths if "docs_claim_dispositions-shard-" in p and p.endswith(".csv")
    )

    if not shard_files:
        return [], [f"No disposition shards found in ref {ref}"]

    for shard_path in shard_files:
        try:
            content = git_show(ref, shard_path)
        except subprocess.CalledProcessError as exc:
            errors.append(f"git show failed for {shard_path}: {exc.stderr.strip()}")
            continue

        shard_errors, shard_rows = _parse_shard_content(shard_path, content)
        errors.extend(shard_errors)
        all_rows.extend(shard_rows)

    # Validate overall structure
    if not all_rows and not errors:
        errors.append(f"No data rows found in any shard from ref {ref}")

    return all_rows, errors


def load_dispositions_from_dir(base_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Load all disposition shards from a local directory.

    Args:
        base_dir: Directory containing disposition shards

    Returns:
        (rows, errors)
    """
    errors: list[str] = []
    all_rows: list[dict[str, str]] = []

    shard_files = sorted(base_dir.glob("docs/claims/docs_claim_dispositions-shard-*.csv"))

    if not shard_files:
        return [], [f"No disposition shards found in {base_dir}/docs/claims/"]

    for shard_path in shard_files:
        try:
            content = shard_path.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"Failed to read {shard_path}: {exc}")
            continue

        shard_errors, shard_rows = _parse_shard_content(str(shard_path), content)
        errors.extend(shard_errors)
        all_rows.extend(shard_rows)

    return all_rows, errors


def _parse_shard_content(shard_path: str, content: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parse a single shard's content with strict validation.

    Args:
        shard_path: Path for error messages
        content: Raw CSV content

    Returns:
        (errors, rows)
    """
    errors: list[str] = []
    rows: list[dict[str, str]] = []

    if not content.strip():
        return [f"{shard_path}: empty file"], []

    # Check for physical blank lines
    for line_num, line in enumerate(content.splitlines(), start=1):
        if line.strip() == "":
            errors.append(f"{shard_path}:{line_num}: physical blank line")
            return errors, []

    try:
        buf = io.StringIO(content)
        reader = csv.DictReader(buf)

        if reader.fieldnames is None:
            return [f"{shard_path}: no header row"], []

        if list(reader.fieldnames) != REQUIRED_COLUMNS:
            actual = reader.fieldnames
            if len(actual) > len(REQUIRED_COLUMNS):
                extra = [c for c in actual if c not in REQUIRED_COLUMNS]
                errors.append(f"{shard_path}: extra named columns: {extra}")
            elif len(actual) < len(REQUIRED_COLUMNS):
                missing = [c for c in REQUIRED_COLUMNS if c not in actual]
                errors.append(f"{shard_path}: missing required columns: {missing}")
            else:
                errors.append(f"{shard_path}: header mismatch")
            return errors, []

        seen_ids: set[str] = set()
        for line_num, raw_row in enumerate(reader, start=2):
            if None in raw_row.values():
                errors.append(f"{shard_path}:{line_num}: row has fewer fields than header")
                continue

            if all(v == "" for v in raw_row.values()):
                errors.append(f"{shard_path}:{line_num}: blank row")
                continue

            if list(raw_row.keys()) != REQUIRED_COLUMNS:
                errors.append(f"{shard_path}:{line_num}: row shape mismatch")
                continue

            cid = raw_row.get("candidate_id", "")
            if not cid:
                errors.append(f"{shard_path}:{line_num}: empty candidate_id")
                continue

            if not CANDIDATE_ID_RE.match(cid):
                errors.append(f"{shard_path}:{line_num}: invalid candidate_id format: {cid!r}")
                continue

            if cid in seen_ids:
                errors.append(f"{shard_path}:{line_num}: duplicate candidate_id: {cid}")
                continue
            seen_ids.add(cid)
            rows.append(raw_row)

        if not rows and not errors:
            errors.append(f"{shard_path}: header-only CSV (0 data rows)")

    except csv.Error as exc:
        errors.append(f"{shard_path}: csv.Error: {exc}")
    except Exception as exc:
        errors.append(f"{shard_path}: {type(exc).__name__}: {exc}")

    return errors, rows
