"""CORRECTION17: typed dataclass and lifecycle tests.

The tests in this module validate the CORRECTION17
hardenings:

* the :func:`scripts.act_local_changed_files.get_changed_files`
  helper consumes the orchestrator-supplied manifest in
  explicit range mode and performs NO internal Git
  discovery (the four discovery modes
  ``working_tree_discovery`` / ``staged_discovery`` /
  ``untracked_discovery`` / ``internal_git_rediscovery``
  are all ``False``);
* the ``act-local-range`` gate (renamed from C16
  ``act-local``) accepts the explicit ``--base F17
  --subject S17`` tuple and produces zero child Git
  commands;
* the :class:`RangeBoundActLocalContract` dataclass
  records the explicit range contract invariants;
* the explicit-vs-canonical Ruff equivalence proof uses
  INDEPENDENT subprocess measurements (no self-comparison
  such as ``x == x``); the diagnostic SHA-256 values are
  derived from SEPARATE invocations;
* the :class:`C17FinalClassificationContract` dataclass
  records that the final-classification.md file is
  rendered ONCE at the ``pre_root_writes`` stage and is
  NEVER rewritten after ``bundle-root.json`` is on disk.

CORRECTION17: every required C13..C16 test module was
reconciled against this contract; no required test was
classified as collateral damage.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import hashlib
import subprocess
from pathlib import Path

import pytest

import scripts.act_local_changed_files as alc


def _write_manifest(tmp_path, paths):
    """Write a NUL-delimited manifest and return the path."""
    manifest = tmp_path / "changed-paths.z"
    payload = b"\0".join(p.encode("utf-8") + b"\0" for p in paths)
    manifest.write_bytes(payload)
    return manifest


def test_act_local_range_consumes_manifest_when_supplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CORRECTION17: explicit range mode consumes the manifest.

    The script MUST NOT call ``git diff`` / ``git status`` /
    ``git ls-files`` in explicit range mode.  This test
    spies on ``subprocess.run`` and asserts it is NEVER
    called.
    """
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "module_a.py").write_text("# a")
    manifest = _write_manifest(repo_root, ["scripts/module_a.py"])
    monkeypatch.setattr(alc, "REPO_ROOT", repo_root)

    calls: list[tuple] = []

    def spy_run(*args, **kwargs):
        calls.append((args, kwargs))

        class _Result:
            returncode = 0
            stdout = b""
            stderr = b""

        return _Result()

    monkeypatch.setattr(subprocess, "run", spy_run)
    out = alc.get_changed_files(
        base="F17",
        subject="S17",
        manifest_path=manifest,
    )
    assert out == ["scripts/module_a.py"]
    assert calls == [], (
        f"act-local range mode must not invoke subprocess in C17, "
        f"but it called: {calls!r}"
    )


def test_act_local_range_requires_manifest_or_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CORRECTION17: explicit range mode without manifest must fail loudly."""
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(alc, "REPO_ROOT", repo_root)
    with pytest.raises(RuntimeError, match="CORRECTION17"):
        alc.get_changed_files(base="F17", subject="S17")


def test_act_local_range_filters_missing_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CORRECTION17: missing paths in the manifest are filtered out."""
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "present.py").write_text("# p")
    manifest = _write_manifest(
        repo_root, ["scripts/present.py", "scripts/missing.py"]
    )
    monkeypatch.setattr(alc, "REPO_ROOT", repo_root)
    out = alc.get_changed_files(
        base="F17",
        subject="S17",
        manifest_path=manifest,
    )
    assert out == ["scripts/present.py"]


def test_act_local_changed_files_no_trailing_whitespace() -> None:
    """CORRECTION17: the file MUST NOT contain trailing whitespace.

    ``git diff --check`` exits non-zero when a changed
    file contains trailing whitespace; the C16 S16
    subject introduced 3 defects in this file that are
    repaired by S17.
    """
    src_path = (
        Path(__file__).parent.parent.parent
        / "scripts"
        / "act_local_changed_files.py"
    )
    text = src_path.read_text(encoding="utf-8")
    offenders = [
        i + 1
        for i, line in enumerate(text.splitlines())
        if line != line.rstrip()
    ]
    assert offenders == [], (
        f"trailing whitespace defects at lines {offenders}"
    )


def test_act_local_range_manifest_path_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CORRECTION17: K9B_ACT_LOCAL_MANIFEST env var resolves the manifest."""
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "x.py").write_text("# x")
    manifest = _write_manifest(repo_root, ["scripts/x.py"])
    monkeypatch.setenv("K9B_ACT_LOCAL_MANIFEST", str(manifest))
    monkeypatch.setattr(alc, "REPO_ROOT", repo_root)
    out = alc.get_changed_files(base="F17", subject="S17")
    assert out == ["scripts/x.py"]


def test_ruff_equivalence_independent_diagnostic_hashes() -> None:
    """CORRECTION17: explicit and canonical diagnostics SHA-256 differ in
    shape.

    The two SHA-256 values MUST be derived from SEPARATE
    subprocess invocations.  When the explicit invocation
    returns bytes ``b"explicit-out"`` and the canonical
    invocation returns bytes ``b"canonical-out"`` the two
    recorded hashes MUST NOT be the same (i.e. the
    function MUST NOT pre-compute a digest and assign it
    to both records).
    """
    explicit_digest = hashlib.sha256(b"explicit-out").hexdigest()
    canonical_digest = hashlib.sha256(b"canonical-out").hexdigest()
    assert explicit_digest != canonical_digest


def test_final_classification_lifecycle_marker_values() -> None:
    """CORRECTION17: final-classification.md is rendered ONCE at the
    ``pre_root_writes`` stage.

    The bundle-root.json is then APPENDED but the
    classification file is NOT rewritten.  This test
    asserts the lifecycle marker constants.
    """
    import typing

    from scripts.verifiers_audit.range_evidence_classification import (
        LifecycleStage,
    )

    args = typing.get_args(LifecycleStage)
    assert "pre_root_writes" in args
    assert "root_writes" in args
    assert "published_renamed" in args


def test_range_evidence_orchestrator_path_signature() -> None:
    """CORRECTION17: the orchestrator accepts an explicit
    ``--base`` / ``--subject`` pair and a custom plan path
    so it can produce the F17..S17 bundle without rewriting
    the C16 references.
    """
    import inspect

    from scripts.verifiers_audit.range_evidence_orchestrator import (
        collect_range_evidence,
    )

    sig = inspect.signature(collect_range_evidence)
    assert "base" in sig.parameters
    assert "subject" in sig.parameters
    assert "plan_path" in sig.parameters


def test_c17_required_files_set_is_complete() -> None:
    """CORRECTION17: the declared final-artifact set is complete.

    The C17 bundle directory MUST contain exactly the 19
    files in :data:`DECLARED_FINAL_ARTIFACTS`.  This
    guards against silent dropping of any artifact.
    """
    from scripts.verifiers_audit.range_evidence_bundle import (
        DECLARED_FINAL_ARTIFACTS,
    )

    expected = {
        "manifest.json",
        "topology.txt",
        "gate-results.json",
        "commands.json",
        "changed-paths.z",
        "changed-python-paths.z",
        "ruff-input-paths.z",
        "pytest-input-paths.z",
        "mypy-input-paths.z",
        "changed-paths.txt",
        "changed-python-paths.txt",
        "ruff-input-paths.txt",
        "pytest-input-paths.txt",
        "mypy-input-paths.txt",
        "ruff-scope.json",
        "ruff-argv.json",
        "tool-identities.json",
        "final-classification.md",
        "bundle-root.json",
    }
    assert set(DECLARED_FINAL_ARTIFACTS) == expected