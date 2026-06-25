"""Shared helpers for verification scripts.

This module contains reusable verification utilities to keep verifier scripts small.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

# Evidence patterns that indicate prose-only evidence
PROSE_ONLY_PATTERNS = [
    r"^TODO$", r"^todo$", r"^TBD$", r"^N/A$", r"^pending$",
    r"^see doc", r"^see docs", r"^see documentation",
    r"^documented in", r"^described in", r"^explained in",
]

# Patterns that indicate TODO-only evidence
TODO_ONLY_PATTERNS = [
    r"^TODO$", r"^TODO:", r"^TODO -", r"^todo$", r"^FIXME$",
    r"^XXX$", r"^HACK$", r"^NOTE:", r"^NOTE -",
]

# Patterns that indicate command refs (executable verification)
COMMAND_REF_PATTERN = re.compile(r"^(\S+)(?:\s+.*)?$")

# N/A placeholders that are acceptable
NA_PLACEHOLDERS = frozenset({"N/A", "TODO", "TBD", "PENDING", "pending"})

# Traceability matrix ID pattern (e.g., DOC-TRACE-0001)
TRACE_ID_PATTERN = re.compile(r"^DOC-TRACE-\d+$")

# Path to traceability matrix (relative to repo root)
TRACEABILITY_MATRIX = Path("docs/claims/docs_claim_traceability_matrix.csv")


def is_na_placeholder(value: str) -> bool:
    """Check if a value is a N/A placeholder."""
    if not value:
        return False
    return value.upper() in NA_PLACEHOLDERS


def is_traceability_id(value: str) -> bool:
    """Check if a value is a traceability matrix ID."""
    if not value:
        return False
    return bool(TRACE_ID_PATTERN.match(value.strip()))


def is_prose_only_evidence(evidence_ref: str) -> bool:
    """Check if evidence is prose-only (not executable)."""
    if not evidence_ref:
        return True

    evidence_lower = evidence_ref.lower().strip()

    for pattern in PROSE_ONLY_PATTERNS:
        if re.match(pattern, evidence_lower):
            return True

    return False


def is_todo_only_evidence(evidence_ref: str) -> bool:
    """Check if evidence is TODO-only."""
    if not evidence_ref:
        return False

    evidence_lower = evidence_ref.lower().strip()

    for pattern in TODO_ONLY_PATTERNS:
        if re.match(pattern, evidence_lower):
            return True

    return False


def is_command_ref(ref: str) -> bool:
    """Check if ref looks like a command (has space after path)."""
    if not ref or " " not in ref:
        return False
    # Command pattern: path/to/script.py --arg or just path/to/script.py
    return True


def extract_command_path(ref: str) -> str:
    """Extract the executable path from a command ref."""
    return ref.split()[0]


def resolve_glob(ref: str, repo_root: Path) -> tuple[bool, str, list[str]]:
    """Resolve a glob pattern relative to repo root.
    
    Returns: (success, message, matched_files)
    """
    # Handle absolute paths or paths with ../
    glob_pattern = ref
    if not ref.startswith("/") and not ref.startswith("."):
        glob_pattern = str(repo_root / ref)
    elif ref.startswith(".."):
        glob_pattern = str(repo_root / ref)
    
    matches = glob.glob(glob_pattern)
    
    if not matches:
        return False, f"Glob '{ref}' matched no files", []
    
    # Return relative paths
    rel_matches = [str(Path(m).relative_to(repo_root)) for m in matches]
    return True, f"Glob matched {len(rel_matches)} file(s)", rel_matches


def check_ref_exists(ref: str, repo_root: Path) -> tuple[bool, str]:
    """Check if a reference path exists on disk.
    
    Handles:
    - Traceability matrix IDs (DOC-TRACE-XXXX) - validated against matrix
    - Regular file paths
    - Directory paths
    - Glob patterns (must match >=1 file)
    - Command refs (extracts and validates path)
    """
    if not ref or ref.strip() == "":
        return False, "Empty reference"

    ref = ref.strip()

    # Handle special cases
    if ref in NA_PLACEHOLDERS:
        return False, f"Placeholder reference: {ref}"

    # Handle traceability matrix IDs - validate against the matrix file
    if is_traceability_id(ref):
        matrix_path = repo_root / TRACEABILITY_MATRIX
        if not matrix_path.exists():
            return False, f"Traceability matrix not found: {TRACEABILITY_MATRIX}"
        
        try:
            import csv
            with open(matrix_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("trace_id", "").strip() == ref:
                        # Found the trace ID - return success
                        return True, f"Trace ID validated: {ref}"
                # Not found in matrix
                return False, f"Trace ID not found in {TRACEABILITY_MATRIX}: {ref}"
        except Exception as e:
            return False, f"Error reading traceability matrix: {e}"

    # Handle command refs: extract path before args
    if is_command_ref(ref):
        cmd_path = extract_command_path(ref)
        return check_ref_exists(cmd_path, repo_root)

    # Handle glob patterns
    if "*" in ref:
        success, msg, matches = resolve_glob(ref, repo_root)
        if success:
            return True, f"{msg}: {', '.join(matches[:5])}{'...' if len(matches) > 5 else ''}"
        return False, msg

    # Handle known prefixes
    for prefix in ("tests/", "src/", "docs/", "scripts/"):
        if ref.startswith(prefix):
            file_path = repo_root / ref
            if file_path.exists():
                return True, "Exists"
            return False, f"File not found: {ref}"

    # Check if it's a directory
    dir_path = repo_root / ref
    if dir_path.exists() and dir_path.is_dir():
        return True, "Directory exists"

    # Check if it's a file
    if dir_path.exists() and dir_path.is_file():
        return True, "Exists"

    return False, f"Reference not found: {ref}"


def check_refs_exist(
    rows: list[dict[str, str]],
    field_name: str,
    repo_root: Path,
) -> tuple[list[str], list[str]]:
    """Check that refs in a field exist on disk. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    for i, row in enumerate(rows):
        refs_value = row.get(field_name, "").strip()
        if not refs_value:
            continue
        if is_na_placeholder(refs_value):
            continue

        # Check each reference (split by comma or semicolon)
        refs = [r.strip() for r in refs_value.replace(";", ",").split(",")]
        for ref in refs:
            if not ref or is_na_placeholder(ref):
                continue
            # Glob refs are now validated
            exists, msg = check_ref_exists(ref, repo_root)
            if not exists:
                errors.append(f"Row {i + 2}: {field_name} '{ref}' does not exist ({msg})")

    return errors, warnings
