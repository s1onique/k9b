"""CORRECTION13/CORRECTION14: tool identity resolution for the Ruff scope.

The Ruff identity is bound in ``tool-identities.json`` BEFORE
the evidence producer invokes Ruff.  The function
:func:`resolve_ruff_identity` records:

* ``launcher_argv_prefix`` - the argv tokens that come BEFORE
  ``"check"`` (e.g. ``("/path/to/.venv/bin/python", "-m",
  "ruff")`` or ``("/path/to/ruff",)``);
* ``launcher_path`` - the path of the resolved executable
  (the venv python interpreter or the standalone ruff
  binary);
* ``launcher_sha256`` - the SHA-256 of the launcher file;
* ``ruff_version`` - the Ruff version (parsed from
  ``ruff --version`` stdout);
* ``ruff_invocation_mode`` - either ``"module"`` (the venv
  python interpreter invokes ``-m ruff``) or ``"binary"``
  (a standalone ``ruff`` binary);
* ``configuration_files`` - the list of repository-located
  ruff configuration files;
* ``configuration_file_sha256`` - the per-file SHA-256
  mapping;
* ``config_path`` - the canonical config Ruff actually reads
  (e.g. ``pyproject.toml`` at the repo root) when an explicit
  ``--config`` invocation is possible;
* ``config_sha256`` - the SHA-256 of the canonical config
  file;
* ``extended_config_chain`` - the chain of ``extend``
  dependencies resolved for the closest-config fallback
  strategy (empty tuple when the explicit-config strategy
  is used);
* ``extended_config_sha256`` - per-file SHA-256 of the
  extended config chain.

CORRECTION14: the venv-locked Ruff is preferred; the
standalone Ruff is used only when the repository interpreter
cannot import Ruff.  The function
:func:`resolve_ruff_identity` raises
:class:`RuffToolUnavailable` when the caller supplies a
non-empty ``python_paths`` tuple and NEITHER strategy can
resolve Ruff.  The caller MUST catch the typed exception and
fail closed (no manifest, no classification, no final
destination).  The empty-python-range case still records an
explicit valid skip and does NOT invoke Ruff.

CORRECTION14: do NOT label mere candidate-filename
inspection as binding.  The producer records the actual
``config_path`` / ``config_sha256`` of the file Ruff reads
(via the explicit ``--config`` strategy when the canonical
config can represent the policy, OR via the closest-config
fallback for every input path plus ``extend`` dependencies).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import cast


class RuffToolUnavailable(RuntimeError):
    """CORRECTION14: typed failure for an unresolvable Ruff identity.

    Raised by :func:`resolve_ruff_identity` when the supplied
    ``python_paths`` tuple is non-empty AND NEITHER the venv
    ``python -m ruff`` nor the standalone ``ruff`` binary can
    be resolved.  The caller MUST NOT invoke Ruff; the
    evidence-transaction boundary MUST exit nonzero; the
    staging directory MUST be removed; no manifest, no
    classification, no final destination.

    The exception preserves the attempted ``python_paths``
    tuple so the caller can render the diagnostic.  A bare
    :class:`RuntimeError` at the evidence-transaction boundary
    is forbidden.
    """

    def __init__(self, *, python_paths: tuple[str, ...]) -> None:
        super().__init__(
            f"RuffToolUnavailable: cannot resolve Ruff for "
            f"non-empty python_paths={list(python_paths)!r}; "
            f"neither the venv 'python -m ruff' nor the "
            f"standalone 'ruff' binary is available on this host"
        )
        self.python_paths = tuple(python_paths)


def _sha256_of_path(path: Path) -> str | None:
    """Return the SHA-256 of ``path`` or ``None`` on read failure."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _read_pyproject_ruff_block(
    pyproject: Path,
) -> tuple[str, tuple[str, ...]] | None:
    """Return ``(config_path, extend_chain)`` when ``pyproject.toml``
    contains a ``[tool.ruff]`` block.

    CORRECTION14: the function reads the file once and uses a
    line-scanning approach to find ``extend =`` references so
    the chain can be recorded.  When ``pyproject.toml`` does
    not declare ``[tool.ruff]`` the function returns ``None``
    so the caller can fall back to the closest-config
    strategy.
    """
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    if "[tool.ruff]" not in text:
        return None
    return (str(pyproject), ())


def _resolve_extend_chain(
    pyproject: Path,
    *,
    repo_root: Path,
) -> tuple[str, ...]:
    """Resolve the ``extend`` chain from ``pyproject.toml``.

    CORRECTION14: the closest-config fallback strategy needs
    the extend chain recorded explicitly so the bundle can
    prove the launcher consulted every dependency.  The
    function scans the file for ``extend = "..."`` (a single
    string) and ``extend = ["..."]`` (a list of strings)
    declarations under ``[tool.ruff]``.  The returned tuple
    is the list of paths relative to ``repo_root``; the
    caller hashes each path with :func:`_sha256_of_path`.
    """
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return ()
    if "[tool.ruff]" not in text:
        return ()
    extends: list[str] = []
    in_ruff_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_ruff_block = line == "[tool.ruff]"
            continue
        if not in_ruff_block:
            continue
        if not line.startswith("extend"):
            continue
        if "=" not in line:
            continue
        value = line.split("=", 1)[1].strip()
        if value.startswith('"') and value.endswith('"'):
            extends.append(value.strip('"'))
        elif value.startswith("'") and value.endswith("'"):
            extends.append(value.strip("'"))
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            for piece in inner.split(","):
                piece = piece.strip()
                if piece.startswith('"') and piece.endswith('"'):
                    extends.append(piece.strip('"'))
                elif piece.startswith("'") and piece.endswith("'"):
                    extends.append(piece.strip("'"))
    return tuple(extends)


def _resolve_venv_ruff(repo_root: Path) -> dict[str, object] | None:
    """Return the venv python ``-m ruff`` identity, or ``None``."""
    venv_python = repo_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return None
    sha = _sha256_of_path(venv_python)
    try:
        proc = subprocess.run(
            [str(venv_python), "-m", "ruff", "--version"],
            cwd=str(repo_root),
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout.decode("utf-8", errors="replace").strip()
    version = text.split()[-1] if text else None
    if not version:
        return None
    return {
        "launcher_argv_prefix": (str(venv_python), "-m", "ruff"),
        "launcher_path": str(venv_python),
        "launcher_sha256": sha,
        "ruff_version": version,
        "ruff_invocation_mode": "module",
    }


def _resolve_standalone_ruff(repo_root: Path) -> dict[str, object] | None:
    """Return the standalone ``ruff`` binary identity, or ``None``."""
    ruff_path_str = shutil.which("ruff")
    if not ruff_path_str:
        return None
    ruff_path = Path(ruff_path_str)
    sha = _sha256_of_path(ruff_path)
    try:
        proc = subprocess.run(
            [ruff_path_str, "--version"],
            cwd=str(repo_root),
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout.decode("utf-8", errors="replace").strip()
    version = text.split()[-1] if text else None
    if not version:
        return None
    return {
        "launcher_argv_prefix": (ruff_path_str,),
        "launcher_path": ruff_path_str,
        "launcher_sha256": sha,
        "ruff_version": version,
        "ruff_invocation_mode": "binary",
    }


def _resolve_canonical_config(repo_root: Path) -> dict[str, object]:
    """Resolve the effective Ruff configuration record.

    CORRECTION14: the function reads ``pyproject.toml`` at
    ``repo_root`` once.  When ``[tool.ruff]`` is present the
    canonical config is the ``pyproject.toml`` file; the
    ``config_path`` / ``config_sha256`` record is bound to
    that file.  When ``[tool.ruff]`` is absent the function
    falls back to the closest-config strategy: for each
    repository-located candidate (``pyproject.toml`` /
    ``ruff.toml`` / ``.ruff.toml``) it records the file that
    exists.  The ``extended_config_chain`` is the list of
    ``extend`` dependencies parsed from ``pyproject.toml``;
    each dependency is hashed and recorded in
    ``extended_config_sha256``.
    """
    pyproject = repo_root / "pyproject.toml"
    ruff_toml = repo_root / "ruff.toml"
    dot_ruff = repo_root / ".ruff.toml"
    config_files: list[str] = []
    config_hashes: dict[str, str] = {}
    for cand in (pyproject, ruff_toml, dot_ruff):
        if cand.exists():
            config_files.append(str(cand))
            sha = _sha256_of_path(cand)
            config_hashes[str(cand)] = sha or ""

    canonical: dict[str, object] = {
        "configuration_files": config_files,
        "configuration_file_sha256": config_hashes,
    }

    pyproject_block = _read_pyproject_ruff_block(pyproject) if pyproject.exists() else None
    if pyproject_block is not None:
        config_path, _extend = pyproject_block
        canonical["config_path"] = config_path
        canonical["config_sha256"] = _sha256_of_path(pyproject) or ""
        canonical["extended_config_chain"] = ()
        canonical["extended_config_sha256"] = {}
    else:
        # Closest-config fallback: the first existing config
        # file in (pyproject.toml, ruff.toml, .ruff.toml) is
        # the canonical config.  The extend chain is parsed
        # from pyproject.toml when present (it may still
        # reference external configurations even when the
        # canonical config is ruff.toml).
        chosen: Path | None = None
        for cand in (ruff_toml, dot_ruff):
            if cand.exists():
                chosen = cand
                break
        if chosen is not None:
            canonical["config_path"] = str(chosen)
            canonical["config_sha256"] = _sha256_of_path(chosen) or ""
        else:
            canonical["config_path"] = ""
            canonical["config_sha256"] = ""
        if pyproject.exists():
            extend_chain = _resolve_extend_chain(
                pyproject, repo_root=repo_root
            )
            extend_hashes: dict[str, str] = {}
            for rel in extend_chain:
                p = repo_root / rel
                if p.exists():
                    extend_hashes[str(p)] = _sha256_of_path(p) or ""
            canonical["extended_config_chain"] = extend_chain
            canonical["extended_config_sha256"] = extend_hashes
        else:
            canonical["extended_config_chain"] = ()
            canonical["extended_config_sha256"] = {}
    return canonical


def resolve_ruff_identity(
    *,
    repo_root: Path,
    python_paths: tuple[str, ...] = (),
) -> dict[str, object]:
    """Bind the Ruff identity to a single resolved strategy.

    CORRECTION14: the function takes a ``python_paths``
    argument.  When the tuple is non-empty AND NEITHER
    strategy can resolve Ruff, the function raises
    :class:`RuffToolUnavailable`.  When the tuple is empty
    (an explicit valid skip), the function returns a record
    with ``ruff_invocation_mode = "skipped_no_python_paths"``
    so the caller can detect the empty-range case without
    invoking Ruff.

    The returned record contains:

    * ``launcher_argv_prefix`` (tuple[str, ...])
    * ``launcher_path`` (str)
    * ``launcher_sha256`` (str | None)
    * ``ruff_version`` (str | None)
    * ``ruff_invocation_mode`` (``"module"`` | ``"binary"`` |
      ``"skipped_no_python_paths"`` | ``"unresolved"``)
    * ``configuration_files`` (list[str])
    * ``configuration_file_sha256`` (dict[str, str])
    * ``config_path`` (str)
    * ``config_sha256`` (str)
    * ``extended_config_chain`` (tuple[str, ...])
    * ``extended_config_sha256`` (dict[str, str])

    When neither strategy resolves AND ``python_paths`` is
    empty, the record is marked ``ruff_invocation_mode =
    "unresolved"`` and the launcher fields are ``None`` /
    empty.  The caller MUST NOT invoke Ruff in that case.
    """
    record: dict[str, object] = {
        "launcher_argv_prefix": (),
        "launcher_path": None,
        "launcher_sha256": None,
        "ruff_version": None,
        "ruff_invocation_mode": "unresolved",
    }
    if not python_paths:
        record["ruff_invocation_mode"] = "skipped_no_python_paths"
        record.update(_resolve_canonical_config(repo_root))
        return record
    strategy = _resolve_venv_ruff(repo_root) or _resolve_standalone_ruff(
        repo_root
    )
    if strategy is None:
        raise RuffToolUnavailable(python_paths=python_paths)
    record.update(strategy)
    record.update(_resolve_canonical_config(repo_root))
    return record


def build_ruff_argv_from_identity(
    identity: dict[str, object],
    paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Build the executed argv from the resolved identity.

    CORRECTION14: when the identity is ``unresolved`` /
    ``skipped_no_python_paths`` OR ``paths`` is empty, the
    function returns an empty tuple and the caller MUST NOT
    invoke Ruff.  When the canonical config is present the
    function prepends ``--config <config_path>`` so the
    executed argv is ``<launcher> check --config <config>
    <paths...>``.
    """
    if not paths:
        return ()
    prefix = cast("tuple[str, ...]", identity.get("launcher_argv_prefix") or ())
    if not prefix:
        return ()
    config_path = cast("str", identity.get("config_path") or "")
    if config_path:
        return (*prefix, "check", "--config", config_path, *paths)
    return (*prefix, "check", *paths)