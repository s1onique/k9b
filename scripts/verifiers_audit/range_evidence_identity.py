"""CORRECTION13: tool identity resolution for the Ruff scope.

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
  mapping.

The producer records the resolved executable strategy and
its SHA-256 hash BEFORE invoking Ruff.  The executed argv
is built from this same identity; the recorded argv and the
executed argv MUST be identical.  The Python interpreter
hash is NEVER labelled as a Ruff executable hash.

CORRECTION13: the host's first ``ruff`` from ``$PATH`` is
NOT acceptable.  The venv-locked Ruff is preferred.  A
standalone ruff binary is used only when the repository
interpreter cannot import Ruff.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import cast


def _sha256_of_path(path: Path) -> str | None:
    """Return the SHA-256 of ``path`` or ``None`` on read failure."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


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


def resolve_ruff_identity(*, repo_root: Path) -> dict[str, object]:
    """Bind the Ruff identity to a single resolved strategy.

    Returns a dict with the following keys:

    * ``launcher_argv_prefix`` (tuple[str, ...])
    * ``launcher_path`` (str)
    * ``launcher_sha256`` (str | None)
    * ``ruff_version`` (str | None)
    * ``ruff_invocation_mode`` (``"module"`` | ``"binary"`` |
      ``"unresolved"``)
    * ``configuration_files`` (list[str])
    * ``configuration_file_sha256`` (dict[str, str])

    When neither the venv Ruff nor the standalone Ruff can be
    resolved, the record is marked ``ruff_invocation_mode =
    "unresolved"`` and the launcher fields are ``None`` /
    empty.  The evidence producer refuses to invoke Ruff in
    that case; the manifest records the explicit skip.
    """
    record: dict[str, object] = {
        "launcher_argv_prefix": (),
        "launcher_path": None,
        "launcher_sha256": None,
        "ruff_version": None,
        "ruff_invocation_mode": "unresolved",
        "configuration_files": [],
        "configuration_file_sha256": {},
    }
    strategy = _resolve_venv_ruff(repo_root) or _resolve_standalone_ruff(
        repo_root
    )
    if strategy is not None:
        record.update(strategy)

    config_candidates = [
        repo_root / "pyproject.toml",
        repo_root / "ruff.toml",
        repo_root / ".ruff.toml",
    ]
    for path in config_candidates:
        if path.exists():
            sha = _sha256_of_path(path)
            cast("list[object]", record["configuration_files"]).append(
                str(path)
            )
            cast("dict[str, str]", record["configuration_file_sha256"])[
                str(path)
            ] = sha or ""
    return record


def build_ruff_argv_from_identity(
    identity: dict[str, object],
    paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Build the executed argv from the resolved identity.

    The argv is constructed as
    ``(*launcher_argv_prefix, "check", *paths)``.  When the
    identity is ``unresolved`` (no launcher) or ``paths`` is
    empty, the function returns an empty tuple and the caller
    MUST NOT invoke Ruff.
    """
    if not paths:
        return ()
    prefix = cast("tuple[str, ...]", identity.get("launcher_argv_prefix") or ())
    if not prefix:
        return ()
    return (*prefix, "check", *paths)
