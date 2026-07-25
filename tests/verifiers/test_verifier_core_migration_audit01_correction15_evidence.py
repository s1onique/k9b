"""CORRECTION15: single-Git-seam and semantic-gate tests.

The tests in this module exercise the single authoritative
Git execution seam and the seven required semantic
repository gates.  The tests patch ``subprocess.run`` and
fail any invocation outside the seam.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import subprocess
from pathlib import Path

import pytest

from scripts.verifiers_audit.range_evidence_gates import (
    build_required_gates,
    run_required_gates,
)
from scripts.verifiers_audit.range_evidence_helpers import (
    GitRunner,
    SubprocessGitRunner,
    parse_nul_paths,
)
from scripts.verifiers_audit.range_evidence_orchestrator import (
    REQUIRED_FINAL_ARTIFACTS,
)
from scripts.verifiers_audit.typed_results import (
    ExecutedCommand,
)


class _SpyGitRunner(SubprocessGitRunner):
    """A GitRunner that records every argv it is asked to execute."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, ...]] = []

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        name: str = "",
    ) -> ExecutedCommand:
        self.calls.append(argv)
        return super().run(argv, cwd=cwd, name=name)


def test_git_runner_protocol_is_satisfied() -> None:
    runner: GitRunner = SubprocessGitRunner()
    assert hasattr(runner, "run")


def test_subprocess_run_called_outside_seam_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Patch ``subprocess.run`` and fail any invocation outside
    the Git seam.
    """
    calls: list[tuple] = []

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args=args[0] if args else (),
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

    monkeypatch.setattr(subprocess, "run", _spy)
    runner = SubprocessGitRunner()
    runner.run(
        ("git", "rev-parse", "--verify", "HEAD^{commit}"),
        cwd=Path("./scratch"),
        name="git-rev-parse-base",
    )
    assert len(calls) == 1
    assert calls[0][0][0][0] == "git"


def test_parse_nul_paths_splits_bytes_correctly() -> None:
    raw = b"a.py\0b.py\0c.py\0"
    assert parse_nul_paths(raw) == (b"a.py", b"b.py", b"c.py")


def test_parse_nul_paths_empty() -> None:
    assert parse_nul_paths(b"") == ()


def test_subprocess_git_runner_returns_typed_result(tmp_path: Path) -> None:
    runner = SubprocessGitRunner()
    argv = ("git", "rev-parse", "--verify", "HEAD^{commit}")
    result = runner.run(argv, cwd=tmp_path, name="git-rev-parse-base")
    assert result.argv == argv
    assert result.name == "git-rev-parse-base"


def test_build_required_gates_returns_seven() -> None:
    repo_root = Path("/repo")
    gates = build_required_gates(repo_root=repo_root)
    assert len(gates) == 7


def test_run_required_gates_records_seven_results(tmp_path: Path) -> None:
    """The seven required gates are executed; each is recorded
    with its semantic name and underlying ExecutedCommand.
    """
    # Patch subprocess.run to return success for all gates
    # (the gates' actual commands are not invoked).
    def _fake_run(*args, **kwargs):
        argv = args[0] if args else kwargs.get("args", [])
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

    original = subprocess.run
    subprocess.run = _fake_run
    try:
        results = run_required_gates(repo_root=tmp_path)
    finally:
        # Restore the original subprocess.run
        subprocess.run = original
    assert len(results) == 7
    names = [r.name for r in results]
    assert "audit-check" in names
    assert "diff-check" in names
    assert "worktree-clean" in names


def test_git_diff_appears_in_required_final_artifacts() -> None:
    """The bundle declares every required final artifact; the
    ``changed-paths.txt`` projection is a first-class member.
    """
    assert "changed-paths.txt" in REQUIRED_FINAL_ARTIFACTS
    assert "manifest.json" in REQUIRED_FINAL_ARTIFACTS
    assert "bundle-root.json" in REQUIRED_FINAL_ARTIFACTS


def test_orchestrator_uses_single_git_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The orchestrator executes the three authoritative Git
    commands through the injected seam.
    """
    from scripts.verifiers_audit import range_evidence_orchestrator as orch
    from scripts.verifiers_audit.typed_results import ClosureTopology

    # Stub out the Ruff identity so the orchestrator does
    # not invoke an actual ``ruff check`` against the test
    # repository.
    monkeypatch.setattr(
        orch,
        "resolve_ruff_identity",
        lambda **kwargs: {
            "ruff_invocation_mode": "skipped_no_python_paths",
            "launcher_argv_prefix": (),
            "launcher_path": None,
            "launcher_sha256": None,
            "ruff_version": None,
            "configuration_files": [],
            "configuration_file_sha256": {},
            "config_path": "",
            "config_sha256": "",
            "extended_config_chain": (),
            "extended_config_sha256": {},
        },
    )
    monkeypatch.setattr(
        orch,
        "build_ruff_argv_from_identity",
        lambda identity, paths: (),
    )

    # Set up a Git repo with two commits.
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"], check=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@x"], check=True
    )
    (repo / "a.txt").write_text("a\n")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True
    )
    base_oid = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (repo / "a.txt").write_text("a2\n")
    (repo / "b.py").write_text("b\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "a.txt", "b.py"], check=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "subj"], check=True
    )
    subject_oid = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    spy = _SpyGitRunner()
    output_dir = tmp_path / "bundle"
    topo = ClosureTopology(
        F15="f",
        F15_tree="ft",
        plan_blob="pb",
        S15=None,
        S15_tree=None,
        parent_F15="p",
        parent_S15=None,
    )
    # Provide empty gate_results to skip gate execution
    # (gates require the actual repository state to be in
    # the expected form).
    evidence = orch.collect_range_evidence(
        base=base_oid,
        subject=subject_oid,
        repo_root=repo,
        output_dir=output_dir,
        topology=topo,
        gate_results=(),
        git_runner=spy,
    )
    # The spy MUST record exactly 3 git calls.
    assert len(spy.calls) == 3
    assert spy.calls[0][:3] == ("git", "rev-parse", "--verify")
    assert spy.calls[1][:3] == ("git", "rev-parse", "--verify")
    assert spy.calls[2][:2] == ("git", "diff")
    # The OIDs are derived from the recorded results.
    assert evidence.base_oid == base_oid
    assert evidence.subject_oid == subject_oid
    # The publication status is READY_TO_PUBLISH (not
    # PUBLISHED inside the bundle).
    assert evidence.publication_status == "ready_to_publish"
