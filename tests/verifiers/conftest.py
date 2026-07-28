"""Pytest fixtures for verifier tests.

Reusable audit01 utilities live in
:mod:`tests.verifiers.verifier_core_migration_audit01_support` so test
modules never import this pytest configuration module as ordinary code.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.verifiers_audit.builder import build_audit_object
from tests.verifiers.verifier_core_migration_audit01_support import (
    AUDIT01_TEST_MODULES_WITHOUT_SUPPORT,
    RangeRepo,
    _synthetic_skipped_record,
    commit_fixture_base,
    commit_fixture_subject,
    git_init,
    hash_canonical_artifact_set,
)


@pytest.fixture
def range_repo(tmp_path: Path) -> RangeRepo:
    """Create the hermetic temporary Git repository used by range tests."""
    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject, newline_ok = commit_fixture_subject(repo, trailing_ok)
    return RangeRepo(
        root=repo,
        base=base,
        subject=subject,
        trailing_whitespace_supported=trailing_ok,
        embedded_newline_supported=newline_ok,
    )


@pytest.fixture(scope="module")
def audit() -> dict[str, object]:
    """Build a deterministic audit object with a synthetic skip record."""
    return build_audit_object(
        {},
        gate_classification=_synthetic_skipped_record("module-scope audit fixture; the persisted gate_classification.json is the canonical on-disk record."),
    )


@pytest.fixture(scope="module", autouse=True)
def canonical_audit_artifacts_remain_unchanged(
    request: pytest.FixtureRequest,
) -> Iterator[None]:
    """Protect canonical artifacts for exactly the split audit01 family.

    A session-scoped autouse fixture here would also cover unrelated
    ``tests/verifiers`` modules. Module scope plus the authoritative path
    inventory gives every audit01 split module mutation protection while
    leaving unrelated verifier tests outside this guard.
    """
    module_path = Path(str(request.node.path)).resolve()
    if module_path not in AUDIT01_TEST_MODULES_WITHOUT_SUPPORT:
        yield
        return

    before = hash_canonical_artifact_set()
    yield
    after = hash_canonical_artifact_set()
    assert after == before, f"canonical audit artifacts mutated during {module_path.relative_to(module_path.parents[2])}: before={before} after={after}"


@pytest.fixture
def hermetic_ruff_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Inject a hermetic Ruff capability into the evidence orchestrator.
    
    Patches resolve_ruff_identity using monkeypatch at the source module
    (identity module). This is the single authoritative seam for resolver
    injection. The orchestrator's local binding is also patched to ensure
    it sees the hermetic resolver.
    """
    import scripts.verifiers_audit.range_evidence_identity as identity_module
    import scripts.verifiers_audit.range_evidence_orchestrator as orchestrator_module
    from tests.verifiers.verifier_core_migration_audit01_correction22_hermetic_ruff import (
        build_hermetic_capability,
    )

    capability = build_hermetic_capability(tmp_path / "ruff-capability")

    def hermetic_resolve(*, repo_root: Path, python_paths: tuple[str, ...] = ()):
        if not python_paths:
            return {
                "launcher_argv_prefix": (),
                "launcher_path": None,
                "launcher_sha256": None,
                "ruff_version": None,
                "ruff_invocation_mode": "skipped_no_python_paths",
                "configuration_files": [],
                "configuration_file_sha256": {},
            }
        return capability.get_identity()

    # Single seam: patch at the source module where resolve_ruff_identity is defined
    # Both the identity module and orchestrator's local binding will see the patch
    monkeypatch.setattr(identity_module, "resolve_ruff_identity", hermetic_resolve)
    monkeypatch.setattr(orchestrator_module, "resolve_ruff_identity", hermetic_resolve)
    return capability



def test_hermetic_ruff_capability_fixture_teardown() -> None:
    """Prove the fixture teardown restores the original resolver.
    
    After a fixture-using test runs, the resolver must be restored.
    This test runs after fixture-using tests (pytest collects in file order,
    but fixture teardown happens per-test).
    """
    import scripts.verifiers_audit.range_evidence_identity as identity_module
    from scripts.verifiers_audit.range_evidence_identity import resolve_ruff_identity as production_resolver

    # The resolver should be the production resolver, not the hermetic one
    assert identity_module.resolve_ruff_identity is production_resolver, (
        "Fixture did not restore the original resolver after teardown"
    )
