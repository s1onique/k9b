"""Classification policy for the dual-range static-scope model.

Owner: runtime/lane/historical partition, lane-authority policy.
Git primitives live in promotion_runtime_static_scope_git.py.
ScopeRecord schema lives in promotion_runtime_static_scope_contract.py.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Runtime source prefix (P0-6).
# ---------------------------------------------------------------------------

# Files under this prefix are always classified as runtime_paths.
RUNTIME_SOURCE_PREFIXES: tuple[str, ...] = (
    "src/k8s_diag_agent/",
)


def is_runtime_test_path(
    path: str,
    runtime_test_paths: frozenset[str],
) -> bool:
    """Return True if path is in the runtime-test manifest paths.

    CORRECTION10: The policy accepts the manifest paths explicitly as a
    frozenset parameter. No global cache or hidden I/O - the caller
    provides the authority.

    Args:
        path: The path to classify.
        runtime_test_paths: Frozenset of manifest paths from load_manifest().

    Returns:
        True if the path is in the manifest.
    """
    return path in runtime_test_paths

# ---------------------------------------------------------------------------
# Lane-authority policy (P0-7).
# ---------------------------------------------------------------------------

# Prefix-based policy for experimental lane authority.
# This replaces the exact frozenset approach to avoid growing allowlists.
_LANE_PREFIXES: tuple[str, ...] = (
    "scripts/ci/promotion_runtime_",     # All promotion runtime CI scripts
    "scripts/ci/run_promotion_runtime_gate.py",
    "scripts/ci/pytest_runtime_gate_plugin.py",
    "scripts/ci/bootstrap_python_dev.sh",
    "scripts/verify_promotion_experimental_lab_build_lane",
    "tests/unit/test_promotion_experimental_lab_build_lane_",
    "tests/unit/test_runtime_gate_plugin_and_runner",
    "tests/unit/test_promotion_static_scope_",
    "tests/unit/test_promotion_static_gate_",
    # CORRECTION03: Experimental lab deploy bridge authorities
    "scripts/ci/promotion_experimental_lab_",
    "scripts/ci/verify_promotion_experimental_lab_",
    "tests/unit/test_promotion_experimental_lab_",
    # Legacy R12 tests (still exist in repo)
    "tests/unit/test_promotion_static_scope_authority_r12.py",
    "tests/unit/test_promotion_static_gate_runner_r12.py",
    "tests/unit/test_promotion_runtime_gate_collect_execute_split_r12.py",
    "tests/unit/test_promotion_runtime_gate_structured_outcomes_r12.py",
    "tests/unit/test_promotion_runtime_gate_manifest_identity_r12.py",
    "tests/unit/test_promotion_runtime_gate_transcript_writer_r12.py",
    "tests/unit/test_promotion_runtime_gate_static_scope_integration_r12.py",
)

# Package-marker policy: __init__.py files under scripts/ci/ are lane authority.
# This makes the scripts/ci directory a proper Python package without requiring
# individual __init__.py entries.
_LANE_PACKAGE_MARKERS: tuple[str, ...] = (
    "scripts/ci/__init__.py",
)


def is_lane_authority_path(path: str) -> bool:
    """Return True if path is governed by the experimental lane authority."""
    # Check exact package markers first
    if path in _LANE_PACKAGE_MARKERS:
        return True
    # Check prefix-based policy
    for prefix in _LANE_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# Runtime classification (P0-6).
# ---------------------------------------------------------------------------

def is_runtime_path(path: str) -> bool:
    """Return True if path is under the runtime source prefix."""
    for prefix in RUNTIME_SOURCE_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# Path record validation (NUL-safe, no ls-tree).
# ---------------------------------------------------------------------------

_ABS_RE = re.compile(r"^/|^[A-Za-z]:[\\/]")
_TRAVERSAL_SEG = re.compile(r"(^|/)\.\.($|/)")


def validate_path_record(record: bytes) -> str:
    """Decode one NUL-delimited record into a repository-relative POSIX path.

    Reject: embedded NUL, absolute paths, traversal, backslashes, leading slash.
    """
    if b"\x00" in record:
        raise ValueError(f"embedded NUL in changed-path record: {record!r}")
    text = record.decode("utf-8")
    if "\\" in text:
        raise ValueError(f"backslash in changed-path record: {text!r}")
    if _ABS_RE.match(text):
        raise ValueError(f"absolute changed-path record: {text!r}")
    if _TRAVERSAL_SEG.search(text):
        raise ValueError(f"traversal in changed-path record: {text!r}")
    if text.startswith("/"):
        raise ValueError(f"leading slash in changed-path record: {text!r}")
    return text


def parse_nul_records(raw: bytes) -> list[str]:
    """Split raw NUL-delimited bytes into validated path strings.

    - Strips trailing NUL if present.
    - Returns empty list for empty input.
    - Validates each record; raises ValueError on malformed.
    - Newlines inside filenames are preserved as part of the same record.
    """
    if raw.endswith(b"\x00"):
        raw = raw[:-1]
    if not raw:
        return []
    records = raw.split(b"\x00")
    return [validate_path_record(r) for r in records if r]
