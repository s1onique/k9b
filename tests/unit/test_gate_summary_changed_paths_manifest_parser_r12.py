"""R12 changed-paths manifest parser tests (CORRECTION11 split).

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION11-
RANGE-BOUND-EVIDENCE-TRUTH-AND-LLM-CAP01:

Split out of the original 680-line
``tests/unit/test_gate_summary_population_changed_paths_manifest_r12.py``
so each focused module stays under the LLM-friendly 500-line cap.

These tests cover the **manifest parser** contract:

* empty, whitespace, non-Python, absolute, traversal, duplicate,
  and missing manifest entries are all rejected;
* the stable sorted-order contract is preserved;
* the producer's ``ruff`` command targets exactly the manifest
  entries in stable sorted order.

No producer subprocess is invoked here; that responsibility lives in
``test_gate_summary_producer_isolation_r12``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_SUMMARY_PATH = REPO_ROOT / ".factory" / "gate-summary.json"


# ---------------------------------------------------------------------------
# Manifest parser tests
# ---------------------------------------------------------------------------


def test_changed_paths_manifest_rejects_empty_manifest(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import (
        _read_changed_paths_manifest,
    )

    empty = tmp_path / "empty.z"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        _read_changed_paths_manifest(empty)

    whitespace = tmp_path / "ws.z"
    whitespace.write_bytes(b"\x00\x00\x00")
    with pytest.raises(ValueError, match="empty"):
        _read_changed_paths_manifest(whitespace)


def test_changed_paths_manifest_rejects_absolute_or_traversal(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import (
        _read_changed_paths_manifest,
    )

    for bad in ("/Users/whoever/foo.py", "../escape/foo.py", "ok\\bad.py"):
        manifest = tmp_path / "bad.z"
        manifest.write_bytes(bad.encode("utf-8"))
        with pytest.raises(ValueError):
            _read_changed_paths_manifest(manifest)


def test_changed_paths_manifest_rejects_non_python(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import (
        _read_changed_paths_manifest,
    )

    manifest = tmp_path / "mixed.z"
    manifest.write_bytes(b"scripts/factory/populate_gate_summary.py\x00README.md\x00")
    with pytest.raises(ValueError, match="only Python"):
        _read_changed_paths_manifest(manifest)


def test_changed_paths_manifest_rejects_duplicate_or_missing(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import (
        _read_changed_paths_manifest,
    )

    duplicate = tmp_path / "dup.z"
    duplicate.write_bytes(
        b"scripts/factory/populate_gate_summary.py\x00"
        b"scripts/factory/populate_gate_summary.py\x00"
    )
    with pytest.raises(ValueError, match="duplicate"):
        _read_changed_paths_manifest(duplicate)

    missing = tmp_path / "missing.z"
    missing.write_bytes(b"scripts/factory/this_does_not_exist.py\x00")
    with pytest.raises(ValueError, match="does not exist"):
        _read_changed_paths_manifest(missing)


def test_changed_paths_manifest_returns_stable_sorted_python_paths(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import (
        _read_changed_paths_manifest,
    )

    # CORRECTION11 split: the manifest entries must point at files
    # that actually exist in the working tree.  The original 680-line
    # file was deleted during the split; the new sibling files take
    # its place.
    manifest = tmp_path / "ok.z"
    manifest.write_bytes(
        b"tests/unit/test_gate_summary_parser_adversarial.py\x00"
        b"scripts/factory/populate_gate_summary.py\x00"
        b"tests/unit/test_gate_summary_changed_paths_manifest_parser_r12.py\x00"
    )
    paths = _read_changed_paths_manifest(manifest)
    assert paths == sorted(paths)
    assert all(path.endswith(".py") for path in paths)


def test_populate_command_uses_manifest_targets_for_ruff(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import _command_specs

    # CORRECTION11 split: the manifest entries must point at files
    # that actually exist in the working tree.  The original 680-line
    # file was deleted during the split; the new sibling files take
    # its place.
    manifest = tmp_path / "changed.z"
    manifest.write_bytes(
        b"scripts/factory/populate_gate_summary.py\x00"
        b"tests/unit/test_gate_summary_changed_paths_manifest_parser_r12.py\x00"
    )
    specs = _command_specs(
        REPO_ROOT, GATE_SUMMARY_PATH, changed_paths_manifest=manifest
    )
    ruff = next(spec for spec in specs if spec.name == "ruff")
    argv = ruff.argv
    module_marker = argv.index("-m")
    assert argv[module_marker + 1] == "ruff"
    assert argv[module_marker + 2] == "check"
    targets = argv[module_marker + 3 :]
    assert targets == [
        "scripts/factory/populate_gate_summary.py",
        "tests/unit/test_gate_summary_changed_paths_manifest_parser_r12.py",
    ]
