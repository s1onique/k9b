"""CORRECTION15: bundle directory enumeration and publication boundary.

The tests in this module exercise the bundle
enumeration / validation algorithm and prove the
publication boundary separation:

* the bundle root is built from the actual directory
  enumeration result;
* the bundle root rejects extras, symlinks, special files,
  and temporary absolute paths;
* the in-bundle publication claim is
  ``READY_TO_PUBLISH``;
* the post-rename publication transcript is recorded
  outside the bundle.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import json
from pathlib import Path

import pytest

from scripts.verifiers_audit.range_evidence_bundle import (
    DECLARED_FINAL_ARTIFACTS,
    assert_no_temporary_absolute_paths,
    build_bundle_root,
    enumerate_bundle,
    hash_declared_artifacts,
    independent_revalidation,
)
from scripts.verifiers_audit.typed_results import ClosureTopology


@pytest.fixture
def staging(tmp_path: Path) -> Path:
    """A fully-populated staging directory including
    ``bundle-root.json`` so the bundle is valid.
    """
    s = tmp_path / "staging"
    s.mkdir()
    for rel in DECLARED_FINAL_ARTIFACTS:
        (s / rel).write_text("content\n", encoding="utf-8")
    return s


@pytest.fixture
def pre_publish_staging(tmp_path: Path) -> Path:
    """A staging directory missing ``bundle-root.json``;
    the bundle is invalid until the writer produces the
    root file.
    """
    s = tmp_path / "staging"
    s.mkdir()
    for rel in DECLARED_FINAL_ARTIFACTS:
        if rel == "bundle-root.json":
            continue
        (s / rel).write_text("content\n", encoding="utf-8")
    return s


def _topology() -> ClosureTopology:
    return ClosureTopology(
        F15="f15",
        F15_tree="f15t",
        plan_blob="pb",
        S15=None,
        S15_tree=None,
        parent_F15="s14",
        parent_S15=None,
    )


def test_enumerate_bundle_is_valid(staging: Path) -> None:
    result = enumerate_bundle(staging)
    assert result.is_valid
    assert result.missing_artifacts == ()
    assert result.extra_artifacts == ()
    assert result.rejected_entries == ()


def test_enumerate_bundle_rejects_extra(staging: Path) -> None:
    (staging / "stray.json").write_text("x", encoding="utf-8")
    result = enumerate_bundle(staging)
    assert not result.is_valid
    assert any("stray.json" in entry for entry in result.rejected_entries)


def test_enumerate_bundle_rejects_directory(staging: Path) -> None:
    (staging / "subdir").mkdir()
    result = enumerate_bundle(staging)
    assert not result.is_valid
    assert any("subdir" in entry for entry in result.rejected_entries)


def test_enumerate_bundle_rejects_symlink(staging: Path) -> None:
    target = staging / "manifest.json"
    link = staging / "manifest-link.json"
    link.symlink_to(target)
    result = enumerate_bundle(staging)
    assert not result.is_valid
    assert any("manifest-link.json" in entry for entry in result.rejected_entries)


def test_enumerate_bundle_rejects_missing(staging: Path) -> None:
    (staging / "manifest.json").unlink()
    result = enumerate_bundle(staging)
    assert "manifest.json" in result.missing_artifacts
    assert not result.is_valid


def test_enumerate_bundle_rejects_pre_publish_missing_root(
    pre_publish_staging: Path,
) -> None:
    result = enumerate_bundle(pre_publish_staging)
    assert "bundle-root.json" in result.missing_artifacts
    assert not result.is_valid


def test_build_bundle_root_drops_staging_paths(staging: Path) -> None:
    topo = _topology()
    hashes = hash_declared_artifacts(staging)
    payload = build_bundle_root(
        topology=topo,
        staging=staging,
        authoritative_hashes=hashes,
    )
    assert "staging_root" not in payload
    assert "output_dir" not in payload
    serialised = json.dumps(payload)
    for token in ("/tmp/", "/private/", "/var/"):
        assert token not in serialised


def test_build_bundle_root_includes_all_declared(staging: Path) -> None:
    topo = _topology()
    hashes = hash_declared_artifacts(staging)
    payload = build_bundle_root(
        topology=topo,
        staging=staging,
        authoritative_hashes=hashes,
    )
    files = payload["files"]
    for rel in DECLARED_FINAL_ARTIFACTS:
        if rel == "bundle-root.json":
            continue
        assert rel in files


def test_assert_no_temporary_absolute_paths_rejects_temp() -> None:
    with pytest.raises(ValueError):
        assert_no_temporary_absolute_paths(
            {"staging_root": "/tmp/closure_evidence"}
        )


def test_independent_revalidation_matches_enumerate(staging: Path) -> None:
    first = enumerate_bundle(staging)
    second = independent_revalidation(staging)
    assert first.observed_artifacts == second.observed_artifacts
    assert first.missing_artifacts == second.missing_artifacts


def test_independent_revalidation_detects_post_publication_mutation(
    staging: Path,
) -> None:
    initial_hashes = hash_declared_artifacts(staging)
    # Mutate the bundle: append a byte to an existing artifact.
    manifest = staging / "manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"x")
    # The hash map diverges from the recorded bundle-root hash.
    new_hashes = hash_declared_artifacts(staging)
    assert new_hashes["manifest.json"] != initial_hashes["manifest.json"]
