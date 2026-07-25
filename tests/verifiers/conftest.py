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
        gate_classification=_synthetic_skipped_record(
            "module-scope audit fixture; the persisted "
            "gate_classification.json is the canonical on-disk record."
        ),
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
    assert after == before, (
        "canonical audit artifacts mutated during "
        f"{module_path.relative_to(module_path.parents[2])}: "
        f"before={before} after={after}"
    )
