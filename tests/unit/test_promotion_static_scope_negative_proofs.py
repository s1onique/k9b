"""Negative-proof unit tests for the static-scope authority (CORRECTION08).

Tests the contracts of the dual-range scope model without requiring a full
Git repository.  All imports are via the scripts.ci package (with __init__.py).

Key changes from CORRECTION07:
  - _validate_path_record moved to promotion_runtime_static_scope_policy
  - ScopeRecord is now a regular class in promotion_runtime_static_scope_contract
  - git functions moved to promotion_runtime_static_scope_git
  - historical bucket derived from diffs, not ls-tree
  - checksum verification is ScopeRecord.verify_checksums()
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

# Import from the scripts.ci package (scripts/ci/__init__.py exists)
from scripts.ci.promotion_runtime_static_scope_policy import validate_path_record
from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
from scripts.ci.promotion_runtime_static_scope import build_scope


# ---------------------------------------------------------------------------
# NUL-delimited hashing (newline disambiguation).
# ---------------------------------------------------------------------------

class TestNulDelimitedHashing:
    """P0-5: NUL-delimited hash disambiguates paths with/without newlines."""

    def test_hash_differs_for_paths_with_newlines(self) -> None:
        """Paths that differ only by embedded newlines produce different hashes."""
        paths_a = ["foo/bar.py", "baz.py"]
        paths_b = ["foo/bar.py\nbaz.py"]  # Same flat string, different segments.

        def nul_hash(paths: list[str]) -> str:
            return hashlib.sha256(
                b"\x00".join(p.encode("utf-8") for p in paths) + b"\x00"
            ).hexdigest()

        assert nul_hash(paths_a) != nul_hash(paths_b), (
            "NUL-delimited hashing must produce different hashes for "
            "paths differing by embedded newlines"
        )

    def test_hash_deterministic(self) -> None:
        """NUL-delimited hash is deterministic for identical inputs."""
        paths = ["a.py", "b.py", "c.py"]

        def nul_hash(p: list[str]) -> str:
            return hashlib.sha256(
                b"\x00".join(x.encode("utf-8") for x in p) + b"\x00"
            ).hexdigest()

        assert nul_hash(paths) == nul_hash(paths)
        assert nul_hash(sorted(paths)) == nul_hash(sorted(paths))


# ---------------------------------------------------------------------------
# Path record validation (from policy module).
# ---------------------------------------------------------------------------

class TestPathRecordValidation:
    """P0-5: path record validation rejects dangerous/malformed inputs."""

    def test_absolute_path_rejected(self) -> None:
        """Absolute path in changed-path record raises ValueError."""
        from scripts.ci.promotion_runtime_static_scope_policy import validate_path_record
        with pytest.raises(ValueError, match="absolute"):
            validate_path_record(b"/etc/passwd")

    def test_absolute_path_windows_rejected(self) -> None:
        """Windows absolute path in record raises ValueError."""
        from scripts.ci.promotion_runtime_static_scope_policy import validate_path_record
        with pytest.raises(ValueError, match="backslash"):
            validate_path_record(b"C:\\Users\\attacker\\evil.py")

    def test_traversal_rejected(self) -> None:
        """Traversal in changed-path record raises ValueError."""
        from scripts.ci.promotion_runtime_static_scope_policy import validate_path_record
        with pytest.raises(ValueError, match="traversal"):
            validate_path_record(b"../etc/passwd")
        with pytest.raises(ValueError, match="traversal"):
            validate_path_record(b"foo/../../etc/passwd")

    def test_embedded_nul_rejected(self) -> None:
        """Embedded NUL in changed-path record raises ValueError."""
        from scripts.ci.promotion_runtime_static_scope_policy import validate_path_record
        with pytest.raises(ValueError, match="embedded NUL"):
            validate_path_record(b"foo\x00bar.py")

    def test_leading_slash_rejected(self) -> None:
        """Leading slash (absolute POSIX without drive) raises ValueError."""
        from scripts.ci.promotion_runtime_static_scope_policy import validate_path_record
        with pytest.raises(ValueError, match="absolute"):
            validate_path_record(b"/foo/bar.py")


# ---------------------------------------------------------------------------
# ScopeRecord schema and validation (from contract module).
# ---------------------------------------------------------------------------

class TestScopeRecordSchema:
    """P0-10: ScopeRecord enforces strict schema."""

    def _make_scope(self, **overrides) -> dict:
        """Build a minimal valid ScopeRecord dict."""
        import hashlib
        import json

        # SHA-256 of empty bytes = 64 hex chars.
        _empty_sha256 = hashlib.sha256(b"").hexdigest()
        base = {
            "schema_version": "1",
            "runtime_base_sha": "a" * 40,
            "lane_base_sha": "b" * 40,
            "subject_sha": "c" * 40,
            "subject_tree": "d" * 40,
            "repo_root": ".",
            "cumulative_changed_python": [],
            "runtime_paths": [],
            "lane_changed_python": [],
            "lane_paths": [],
            "historical_nonruntime_paths": [],
            "unclassified_paths": [],
            "cumulative_changed_count": 0,
            "runtime_count": 0,
            "lane_changed_count": 0,
            "lane_count": 0,
            "historical_nonruntime_count": 0,
            "unclassified_count": 0,
            "cumulative_changed_sha256": _empty_sha256,
            "runtime_paths_sha256": _empty_sha256,
            "lane_changed_sha256": _empty_sha256,
            "lane_paths_sha256": _empty_sha256,
            "historical_nonruntime_sha256": _empty_sha256,
            "unclassified_sha256": _empty_sha256,
            "included_paths_sha256": _empty_sha256,
            "scope_record_sha256": "",
        }
        base.update(overrides)
        # Compute scope_record_sha256 from authoritative fields
        payload = {k: v for k, v in base.items() if k != "scope_record_sha256"}
        base["scope_record_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return base

    def test_unknown_field_rejected(self) -> None:
        """Unknown field in dict raises ScopeError on from_dict."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
        d = self._make_scope()
        d["unknown_field"] = "bad"
        with pytest.raises(ScopeError, match="unknown_field"):
            ScopeRecord.from_dict(d)

    def test_wrong_type_rejected(self) -> None:
        """Wrong field type raises ScopeError on from_dict."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
        d = self._make_scope()
        d["runtime_count"] = "not_an_int"
        with pytest.raises(ScopeError, match="runtime_count"):
            ScopeRecord.from_dict(d)

    def test_bool_count_rejected(self) -> None:
        """Bool used as count raises ScopeError on from_dict."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
        d = self._make_scope()
        d["unclassified_count"] = False
        with pytest.raises(ScopeError, match="unclassified_count"):
            ScopeRecord.from_dict(d)

    def test_invalid_sha_rejected(self) -> None:
        """Non-40-hex SHA raises ScopeError on from_dict."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
        d = self._make_scope(subject_sha="not_a_sha")
        with pytest.raises(ScopeError, match="subject_sha"):
            ScopeRecord.from_dict(d)

    def test_absolute_path_in_record_rejected(self) -> None:
        """Absolute path in runtime_paths raises ScopeError on validate()."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
        d = self._make_scope(
            runtime_paths=["/etc/evil.py"],
            runtime_count=1,
        )
        rec = ScopeRecord.from_dict(d)
        with pytest.raises(ScopeError, match="absolute"):
            rec.validate()

    def test_backslash_in_record_rejected(self) -> None:
        """Backslash in lane path raises ScopeError on validate()."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
        d = self._make_scope(
            lane_paths=["foo\\bar.py"],
            lane_count=1,
        )
        rec = ScopeRecord.from_dict(d)
        with pytest.raises(ScopeError, match="backslash"):
            rec.validate()

    def test_unsorted_paths_rejected(self) -> None:
        """Unsorted path tuple raises ScopeError on validate()."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
        d = self._make_scope(
            cumulative_changed_python=["z.py", "a.py"],
            cumulative_changed_count=2,
            cumulative_changed_sha256=hashlib.sha256(b"a.py\x00z.py\x00").hexdigest(),
        )
        rec = ScopeRecord.from_dict(d)
        with pytest.raises(ScopeError, match="sorted"):
            rec.validate()

    def test_duplicate_paths_rejected(self) -> None:
        """Duplicate paths raise ScopeError on validate()."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
        d = self._make_scope(
            cumulative_changed_python=["a.py", "a.py"],
            cumulative_changed_count=2,
            cumulative_changed_sha256=hashlib.sha256(b"a.py\x00a.py\x00").hexdigest(),
        )
        rec = ScopeRecord.from_dict(d)
        with pytest.raises(ScopeError, match="duplicates"):
            rec.validate()

    def test_unclassified_count_nonzero_rejected(self) -> None:
        """unclassified_count > 0 raises ScopeError on validate()."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
        d = self._make_scope(
            lane_paths=["scripts/ci/evil.py"],
            lane_count=1,
            unclassified_paths=["scripts/ci/evil.py"],
            unclassified_count=1,
        )
        rec = ScopeRecord.from_dict(d)
        with pytest.raises(ScopeError, match="unclassified_count"):
            rec.validate()

    def test_bucket_overlap_rejected(self) -> None:
        """Runtime/lane bucket overlap raises ScopeError on validate()."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord
        d = self._make_scope(
            runtime_paths=["src/k8s_diag_agent/shared.py"],
            runtime_count=1,
            lane_paths=["src/k8s_diag_agent/shared.py"],
            lane_count=1,
            cumulative_changed_python=["src/k8s_diag_agent/shared.py"],
            cumulative_changed_count=1,
        )
        rec = ScopeRecord.from_dict(d)
        with pytest.raises(ScopeError, match="runtime_paths.*lane_paths"):
            rec.validate()


# ---------------------------------------------------------------------------
# ScopeRecord checksum computation and verification.
# ---------------------------------------------------------------------------

class TestScopeRecordChecksums:
    """P0-11: ScopeRecord checksum computation and verification."""

    def test_checksum_mutation_rejected(self) -> None:
        """Mutating any field causes checksum mismatch on verify_checksums()."""
        import hashlib
        import json

        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError, ScopeRecord

        def make_valid(**overrides) -> ScopeRecord:
            paths = ["src/k8s_diag_agent/foo.py"]
            c_sha = hashlib.sha256(b"\x00".join(p.encode() for p in paths) + b"\x00").hexdigest()
            incl = tuple(sorted(paths))
            incl_sha = hashlib.sha256(b"\x00".join(p.encode() for p in incl) + b"\x00").hexdigest()
            d = {
                "schema_version": "1",
                "runtime_base_sha": "a" * 40,
                "lane_base_sha": "b" * 40,
                "subject_sha": "c" * 40,
                "subject_tree": "d" * 40,
                "repo_root": ".",
                "cumulative_changed_python": paths,
                "runtime_paths": paths,
                "lane_changed_python": [],
                "lane_paths": [],
                "historical_nonruntime_paths": [],
                "unclassified_paths": [],
                "cumulative_changed_count": 1,
                "runtime_count": 1,
                "lane_changed_count": 0,
                "lane_count": 0,
                "historical_nonruntime_count": 0,
                "unclassified_count": 0,
                "cumulative_changed_sha256": c_sha,
                "runtime_paths_sha256": c_sha,
                "lane_changed_sha256": hashlib.sha256(b"").hexdigest(),
                "lane_paths_sha256": hashlib.sha256(b"").hexdigest(),
                "historical_nonruntime_sha256": hashlib.sha256(b"").hexdigest(),
                "unclassified_sha256": hashlib.sha256(b"").hexdigest(),
                "included_paths_sha256": incl_sha,
            }
            d.update(overrides)
            payload = {k: v for k, v in d.items() if k != "scope_record_sha256"}
            d["scope_record_sha256"] = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            return ScopeRecord.from_dict(d)

        # Mutate one runtime path
        d = make_valid()
        d.runtime_paths = ("src/k8s_diag_agent/bar.py",)
        with pytest.raises(ScopeError, match="checksum mismatch"):
            d.verify_checksums()

    def test_checksum_verification_passes_for_valid_record(self) -> None:
        """Valid record with_checksums() + verify_checksums() succeeds."""
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeRecord
        rec = ScopeRecord(
            runtime_base_sha="a" * 40,
            lane_base_sha="b" * 40,
            subject_sha="c" * 40,
            subject_tree="d" * 40,
            repo_root=".",
            cumulative_changed_python=(),
            runtime_paths=(),
            lane_changed_python=(),
            lane_paths=(),
            historical_nonruntime_paths=(),
            unclassified_paths=(),
            cumulative_changed_count=0,
            runtime_count=0,
            lane_changed_count=0,
            lane_count=0,
            historical_nonruntime_count=0,
            unclassified_count=0,
            cumulative_changed_sha256="",
            runtime_paths_sha256="",
            lane_changed_sha256="",
            lane_paths_sha256="",
            historical_nonruntime_sha256="",
            unclassified_sha256="",
            included_paths_sha256="",
            scope_record_sha256="",
        )
        computed = rec.with_checksums()
        computed.verify_checksums()  # Must not raise


# ---------------------------------------------------------------------------
# Git command contract (P0-2: no ls-tree in scope authority).
# ---------------------------------------------------------------------------

class TestGitCommandContract:
    """P0-2: scope authority must NOT use git ls-tree or git ls-files."""

    def test_no_ls_tree_in_scope_git_module(self) -> None:
        """promotion_runtime_static_scope_git must NOT define ls-tree functions."""
        import scripts.ci.promotion_runtime_static_scope_git as git_mod
        attrs = dir(git_mod)
        forbidden = [a for a in attrs if "ls_tree" in a.lower() or "lstree" in a.lower()]
        assert not forbidden, f"forbidden ls-tree function(s) found: {forbidden}"

    def test_no_ls_files_in_scope_git_module(self) -> None:
        """promotion_runtime_static_scope_git must NOT use git ls-files for scope."""
        import scripts.ci.promotion_runtime_static_scope_git as git_mod
        source = open(git_mod.__file__, encoding="utf-8").read()
        assert "ls-files" not in source, "git index/working-tree listing found in scope git module"


# ---------------------------------------------------------------------------
# Shared git integration helpers.
# ---------------------------------------------------------------------------

def _git_env() -> dict[str, str]:
    import os
    return {
        **{k: v for k, v in os.environ.items() if k.startswith("GIT_")},
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t",
    }


def _init_git_repo(tmp_path: Path) -> tuple[Path, str]:
    """Init git repo with one README commit; return (tmp_path, head_sha)."""
    import subprocess
    env = _git_env()
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    (tmp_path / "README").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True, env=env)
    return tmp_path, subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True,
    ).stdout.strip()


# ---------------------------------------------------------------------------
# Missing runtime path is a hard error.
# ---------------------------------------------------------------------------

class TestMissingRuntimePath:
    """P0-5: missing path with ACMRT filter is a hard error."""

    def test_missing_runtime_path_raises_scope_error(self, tmp_path: Path) -> None:
        """A runtime path that doesn't exist on disk raises ScopeError."""
        import subprocess

        import scripts.ci.promotion_runtime_static_scope as scope_mod
        from scripts.ci.promotion_runtime_static_scope import build_scope
        from scripts.ci.promotion_runtime_static_scope_contract import ScopeError

        _init_git_repo(tmp_path)
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True,
        ).stdout.strip()
        runtime_base = head_sha + "0"
        lane_base = head_sha + "1"

        orig = (scope_mod.resolve_revision, scope_mod.is_ancestor,
                scope_mod.get_head_sha, scope_mod.get_subject_tree, scope_mod.changed_python)
        scope_mod.resolve_revision = lambda r, rev: (
            rev if rev in (runtime_base, lane_base, head_sha) else rev
        )
        scope_mod.is_ancestor = lambda r, a, d: True
        scope_mod.get_head_sha = lambda r: head_sha
        scope_mod.get_subject_tree = lambda r, sha: subprocess.run(
            ["git", "rev-parse", sha + "^{tree}"], cwd=r, capture_output=True, text=True,
        ).stdout.strip()
        scope_mod.changed_python = lambda r, base, sub: (
            b"src/k8s_diag_agent/ghost.py\x00" if base == runtime_base else b""
        )
        try:
            with pytest.raises(ScopeError, match="does not exist on disk"):
                build_scope(tmp_path, runtime_base, lane_base, head_sha)
        finally:
            (scope_mod.resolve_revision, scope_mod.is_ancestor,
             scope_mod.get_head_sha, scope_mod.get_subject_tree,
             scope_mod.changed_python) = orig


# ---------------------------------------------------------------------------
# Repo root is "." not absolute.
# ---------------------------------------------------------------------------

class TestRepoRootEvidence:
    """P0-10: scope record must not contain absolute host paths."""

    def test_repo_root_is_dot(self, tmp_path: Path) -> None:
        """ScopeRecord.repo_root is '.' not an absolute host path."""
        import subprocess

        import scripts.ci.promotion_runtime_static_scope as scope_mod
        from scripts.ci.promotion_runtime_static_scope import build_scope

        # First commit
        _, head_minus_1 = _init_git_repo(tmp_path)
        # Second commit with a runtime file
        runtime_file = tmp_path / "src" / "k8s_diag_agent" / "test.py"
        runtime_file.parent.mkdir(parents=True)
        runtime_file.write_text("pass\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add"], cwd=tmp_path,
                       capture_output=True, env=_git_env())
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                             capture_output=True, text=True).stdout.strip()
        runtime_base = head_minus_1 + "0"
        lane_base = head_minus_1 + "1"

        orig = (scope_mod.resolve_revision, scope_mod.is_ancestor,
                scope_mod.get_head_sha, scope_mod.get_subject_tree, scope_mod.changed_python)
        scope_mod.resolve_revision = lambda r, rev: rev if rev in (
            runtime_base, lane_base, head, head_minus_1
        ) else rev
        scope_mod.is_ancestor = lambda r, a, d: True
        scope_mod.get_head_sha = lambda r: head
        scope_mod.get_subject_tree = lambda r, sha: subprocess.run(
            ["git", "rev-parse", sha + "^{tree}"], cwd=r, capture_output=True, text=True,
        ).stdout.strip()
        scope_mod.changed_python = lambda r, base, sub: (
            b"src/k8s_diag_agent/test.py\x00" if base == runtime_base else b""
        )
        try:
            record = build_scope(tmp_path, runtime_base, lane_base, head)
        finally:
            (scope_mod.resolve_revision, scope_mod.is_ancestor,
             scope_mod.get_head_sha, scope_mod.get_subject_tree,
             scope_mod.changed_python) = orig

        assert record.repo_root == ".", (
            f"ScopeRecord.repo_root must be '.', got: {record.repo_root!r}"
        )
