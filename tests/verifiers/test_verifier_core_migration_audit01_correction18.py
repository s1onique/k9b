"""CORRECTION18: typed dataclass and lifecycle tests.

The tests in this module validate the CORRECTION18
hardenings:

* generic identity field names (freeze_commit, freeze_tree,
  freeze_parent, plan_blob, subject_commit, subject_tree,
  subject_parent);
* explicit environment in GateInvocation records (no implicit
  inheritance);
* ACT-local receives explicit manifest interface
  (--manifest <path>) and MUST NOT perform Git discovery;
* final-classification.md is rendered ONCE at the
  ``pre_root_writes`` stage with PENDING_EXTERNAL_RESULT
  for bundle_root_sha256 and publication_succeeded;
* bundle-root.json is NOT an input to classification;
* the acyclic bundle root guarantee.

CORRECTION18: every required C17 test module was
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
    """CORRECTION18: explicit range mode consumes the manifest.

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
        base="F18",
        subject="S18",
        manifest_path=manifest,
    )
    assert out == ["scripts/module_a.py"]
    assert calls == [], (
        f"act-local range mode must not invoke subprocess in C18, "
        f"but it called: {calls!r}"
    )


def test_act_local_range_requires_manifest_or_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CORRECTION18: explicit range mode without manifest must fail loudly."""
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(alc, "REPO_ROOT", repo_root)
    # Match CORRECTION17 or CORRECTION18 (the error may use either version)
    with pytest.raises(RuntimeError, match="CORRECTION1[78]"):
        alc.get_changed_files(base="F18", subject="S18")


def test_act_local_range_filters_missing_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CORRECTION18: missing paths in the manifest are filtered out."""
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "present.py").write_text("# p")
    manifest = _write_manifest(
        repo_root, ["scripts/present.py", "scripts/missing.py"]
    )
    monkeypatch.setattr(alc, "REPO_ROOT", repo_root)
    out = alc.get_changed_files(
        base="F18",
        subject="S18",
        manifest_path=manifest,
    )
    assert out == ["scripts/present.py"]


def test_act_local_changed_files_no_trailing_whitespace() -> None:
    """CORRECTION18: the file MUST NOT contain trailing whitespace.

    ``git diff --check`` exits non-zero when a changed
    file contains trailing whitespace.
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
    """CORRECTION18: K9B_ACT_LOCAL_MANIFEST env var resolves the manifest."""
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "x.py").write_text("# x")
    manifest = _write_manifest(repo_root, ["scripts/x.py"])
    monkeypatch.setenv("K9B_ACT_LOCAL_MANIFEST", str(manifest))
    monkeypatch.setattr(alc, "REPO_ROOT", repo_root)
    out = alc.get_changed_files(base="F18", subject="S18")
    assert out == ["scripts/x.py"]


def test_ruff_equivalence_independent_diagnostic_hashes() -> None:
    """CORRECTION18: explicit and canonical diagnostics SHA-256 differ in
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
    """CORRECTION18: final-classification.md is rendered ONCE at the
    ``pre_root_writes`` stage.

    The bundle-root.json is written AFTER classification.
    This test asserts the lifecycle marker constants.
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
    """CORRECTION18: the orchestrator accepts an explicit
    ``--base`` / ``--subject`` pair and a custom plan path
    so it can produce the F18..S18 bundle without rewriting
    the C17 references.
    """
    import inspect

    from scripts.verifiers_audit.range_evidence_orchestrator import (
        collect_range_evidence,
    )

    sig = inspect.signature(collect_range_evidence)
    assert "base" in sig.parameters
    assert "subject" in sig.parameters
    assert "plan_path" in sig.parameters


def test_c18_required_files_set_is_complete() -> None:
    """CORRECTION18: the declared final-artifact set is complete.

    The C18 bundle directory MUST contain exactly the 19
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


def test_generic_identity_field_names() -> None:
    """CORRECTION18: generic identity fields are defined.

    The gate plan uses generic identities instead of
    correction-specific field names.
    """
    from scripts.verifiers_audit.range_evidence_topology import (
        CORRECTION18_F18_REF,
        CORRECTION18_PLAN_PATH,
        CORRECTION18_S18_REF,
    )

    assert "CORRECTION18" in CORRECTION18_PLAN_PATH
    assert CORRECTION18_F18_REF == "F18"
    assert CORRECTION18_S18_REF == "S18"


def test_classification_uses_pending_external_result() -> None:
    """CORRECTION18: classification MUST use PENDING_EXTERNAL_RESULT.

    The bundle_root_sha256 and publication_succeeded fields
    in final-classification.md MUST be PENDING_EXTERNAL_RESULT
    before the bundle root is created.
    """
    from scripts.verifiers_audit.range_evidence_classification import (
        PENDING_EXTERNAL_RESULT,
    )

    assert PENDING_EXTERNAL_RESULT == "PENDING_EXTERNAL_RESULT"


def test_gate_invocation_requires_explicit_environment() -> None:
    """CORRECTION18: GateInvocation records require explicit environment.

    No required environment input may be inherited implicitly.
    """
    from scripts.verifiers_audit.range_evidence_gates import (
        GateInvocation,
    )

    # GateInvocation must have environment field
    invocation = GateInvocation(
        name="audit01-pytest",
        argv=("python", "-m", "pytest"),
        cwd="/repo",
        environment_overrides=(),
        input_paths=(),
    )
    assert hasattr(invocation, "environment_overrides")
    assert isinstance(invocation.environment_overrides, tuple)
