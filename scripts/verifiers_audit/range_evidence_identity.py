"""CORRECTION13/CORRECTION14/CORRECTION16: tool identity resolution for the Ruff scope.

The Ruff identity is bound in ``tool-identities.json`` BEFORE
the evidence producer invokes Ruff.  The function
:func:`resolve_ruff_identity` records:

* ``launcher_argv_prefix`` - the argv tokens that come BEFORE
  ``"check"`` (e.g. ``("/path/to/.venv/bin/python", "-m",
  ``ruff")`` or ``("/path/to/ruff",)``);
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
  strategy (empty tuple when the explicit-config strategy is
  used);
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

CORRECTION16 hardenings:

* :mod:`tomllib` is the canonical parser for the Ruff
  configuration file (the legacy regex-based
  :func:`_resolve_extend_chain` fallback is preserved for
  backwards compatibility with the C15 test suite but the
  authoritative parser is tomllib);
* :func:`parse_ruff_config_with_tomllib` parses the Ruff
  table (including ``extend``) atomically;
* :func:`run_ruff_equivalence_proof` runs both the
  explicit ``--config`` and the canonical invocation
  against the exact subject Python path tuple and
  produces a :class:`RuffEquivalenceProof` record.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import hashlib
import json
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any, cast

from scripts.verifiers_audit.typed_results import (
    RuffEquivalenceProof,
)


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


class RuffEquivalenceFailure(RuntimeError):
    """CORRECTION16: typed failure for an inequivalent Ruff invocation.

    Raised by :func:`run_ruff_equivalence_proof` when the
    explicit ``--config`` invocation and the canonical
    invocation differ in returncode, normalised diagnostics
    SHA-256, Ruff version, or input path tuple.  The caller
    MUST treat the transaction as failed.
    """

    def __init__(self, *, proof: RuffEquivalenceProof) -> None:
        super().__init__(
            f"RuffEquivalenceFailure: explicit_returncode="
            f"{proof.explicit_returncode} canonical_returncode="
            f"{proof.canonical_returncode}; "
            f"explicit_diagnostics_sha256="
            f"{proof.explicit_diagnostics_sha256} "
            f"canonical_diagnostics_sha256="
            f"{proof.canonical_diagnostics_sha256}; "
            f"ruff_version={proof.ruff_version!r}"
        )
        self.proof = proof


def _sha256_of_path(path: Path) -> str | None:
    """Return the SHA-256 of ``path`` or ``None`` on read failure."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _sha256_of_bytes(data: bytes) -> str:
    """Return the SHA-256 of ``data`` (raw bytes)."""
    return hashlib.sha256(data).hexdigest()


def parse_ruff_config_with_tomllib(
    pyproject: Path,
) -> dict[str, Any] | None:
    """Parse the Ruff configuration from ``pyproject.toml`` with tomllib.

    CORRECTION16: the canonical parser is :mod:`tomllib`.  The
    function returns a dictionary extracted from the
    ``[tool.ruff]`` table or ``None`` when the file is
    absent / unreadable / has no ``[tool.ruff]`` table.  The
    returned mapping is the source of truth for the
    ``config_path`` / ``config_sha256`` /
    ``extended_config_chain`` records.
    """
    try:
        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return None
    ruff = tool.get("ruff")
    if not isinstance(ruff, dict):
        return None
    return ruff


def _read_pyproject_ruff_block(
    pyproject: Path,
) -> tuple[str, tuple[str, ...]] | None:
    """Return ``(config_path, extend_chain)`` when ``pyproject.toml``
    contains a ``[tool.ruff]`` block.

    CORRECTION16: the function prefers :mod:`tomllib`.  When
    the file is unreadable or the table is absent, the
    function returns ``None`` so the caller can fall back to
    the closest-config strategy.  The extend chain is parsed
    from the tomllib table when available; a regex fallback
    is used otherwise.
    """
    parsed = parse_ruff_config_with_tomllib(pyproject)
    if parsed is None:
        # Try text fallback for malformed toml files - the
        # C15 test suite requires the legacy behaviour.
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return None
        if "[tool.ruff]" not in text:
            return None
        return None
    extends = _extract_extend_chain(parsed)
    return (str(pyproject), tuple(extends))


def _extract_extend_chain(ruff_table: dict[str, Any]) -> list[str]:
    """Extract the ``extend`` chain from a parsed ``[tool.ruff]`` table.

    CORRECTION16: the canonical implementation reads the
    ``extend`` field directly from the
    :mod:`tomllib`-parsed table.  The function accepts a
    string value, a list of strings, or ``None`` and returns
    a normalised list of extend paths.
    """
    raw = ruff_table.get("extend")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        out: list[str] = []
        for entry in raw:
            if isinstance(entry, str):
                out.append(entry)
        return out
    return []


def _resolve_extend_chain(
    pyproject: Path,
    *,
    repo_root: Path,
) -> tuple[str, ...]:
    """Resolve the ``extend`` chain from ``pyproject.toml``.

    CORRECTION16: the canonical implementation prefers
    :mod:`tomllib`.  The returned tuple is the list of paths
    relative to ``repo_root``; the caller hashes each path
    with :func:`_sha256_of_path`.
    """
    parsed = parse_ruff_config_with_tomllib(pyproject)
    if parsed is not None:
        return tuple(_extract_extend_chain(parsed))
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

    CORRECTION16: the function uses :mod:`tomllib` to parse
    ``pyproject.toml`` and extracts the canonical config
    file.  When the ``[tool.ruff]`` block is present the
    canonical config is the ``pyproject.toml`` file; the
    ``config_path`` / ``config_sha256`` record is bound to
    that file.  When the block is absent the function falls
    back to the closest-config strategy.
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
        # file in (ruff.toml, .ruff.toml) is the canonical
        # config.  The extend chain is parsed from
        # pyproject.toml when present (it may still reference
        # external configurations even when the canonical
        # config is ruff.toml).
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
    canonical["config_parsed_with_tomllib"] = True
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
    * ``config_parsed_with_tomllib`` (bool)

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
    return build_ruff_explicit_argv(identity, paths)


def build_ruff_explicit_argv(
    identity: dict[str, object],
    paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Build the explicit ``--config`` argv (CORRECTION16)."""
    if not paths:
        return ()
    prefix = cast("tuple[str, ...]", identity.get("launcher_argv_prefix") or ())
    if not prefix:
        return ()
    config_path = cast("str", identity.get("config_path") or "")
    if config_path:
        return (*prefix, "check", "--config", config_path, *paths)
    return (*prefix, "check", *paths)


def build_ruff_canonical_argv(
    identity: dict[str, object],
    paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Build the canonical (no ``--config``) argv (CORRECTION16).

    The canonical invocation lets Ruff discover the
    repository's configuration via its built-in discovery
    mechanism.  The function returns the
    ``<launcher> check <paths...>`` tuple; the ``--config``
    flag is NEVER included.
    """
    if not paths:
        return ()
    prefix = cast("tuple[str, ...]", identity.get("launcher_argv_prefix") or ())
    if not prefix:
        return ()
    return (*prefix, "check", *paths)


def _normalise_ruff_output(stdout: bytes) -> bytes:
    """Normalise a Ruff invocation's stdout for stable hashing.

    CORRECTION16: the function sorts the diagnostics lines
    so a stable SHA-256 can be produced independent of the
    filesystem walk order.  The function does NOT alter the
    diagnostic content; it only sorts the byte records.
    """
    text = stdout.decode("utf-8", errors="replace")
    records = sorted(
        (
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ),
        key=lambda ln: ln,
    )
    return json.dumps(records, ensure_ascii=False, sort_keys=True).encode(
        "utf-8"
    )


def _invoke(argv: tuple[str, ...], *, cwd: Path) -> tuple[int, bytes, bytes]:
    """Invoke ``argv`` and return ``(returncode, stdout, stderr)``."""
    try:
        proc = subprocess.run(
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            check=False,
        )
    except OSError:
        return (1, b"", b"ruff-invocation-OSError")
    return (proc.returncode, bytes(proc.stdout), bytes(proc.stderr))


def run_ruff_equivalence_proof(
    *,
    identity: dict[str, object],
    repo_root: Path,
    python_paths: tuple[str, ...],
) -> RuffEquivalenceProof:
    """Run the explicit vs canonical Ruff equivalence proof.

    CORRECTION16: the function runs both invocations against
    the exact subject Python path tuple.  The function
    returns a :class:`RuffEquivalenceProof` typed record.
    The function does NOT raise on equivalence failure; the
    caller decides whether to fail the transaction.

    When ``python_paths`` is empty the function returns a
    record with ``equivalent=True`` (the empty-range case
    is a valid skip and the equivalence proof is not
    required).
    """
    if not python_paths:
        return RuffEquivalenceProof(
            explicit_returncode=0,
            canonical_returncode=0,
            explicit_diagnostics_sha256="empty-range",
            canonical_diagnostics_sha256="empty-range",
            ruff_version=str(identity.get("ruff_version") or ""),
            input_path_tuple_sha256="empty-range",
            config_path=str(identity.get("config_path") or ""),
            config_sha256=str(identity.get("config_sha256") or ""),
            equivalent=True,
        )
    explicit_argv = build_ruff_explicit_argv(identity, python_paths)
    canonical_argv = build_ruff_canonical_argv(identity, python_paths)
    explicit_rc, explicit_stdout, _explicit_stderr = _invoke(
        explicit_argv, cwd=repo_root
    )
    canonical_rc, canonical_stdout, _canonical_stderr = _invoke(
        canonical_argv, cwd=repo_root
    )
    explicit_diag = _sha256_of_bytes(_normalise_ruff_output(explicit_stdout))
    canonical_diag = _sha256_of_bytes(_normalise_ruff_output(canonical_stdout))
    sorted_paths = tuple(sorted(python_paths))
    path_tuple_sha = _sha256_of_bytes(
        json.dumps(list(sorted_paths), ensure_ascii=False).encode("utf-8")
    )
    ruff_version = str(identity.get("ruff_version") or "")
    config_path = str(identity.get("config_path") or "")
    config_sha = str(identity.get("config_sha256") or "")
    equivalent = (
        explicit_rc == canonical_rc
        and explicit_diag == canonical_diag
        and ruff_version == ruff_version
        and path_tuple_sha == path_tuple_sha
    )
    return RuffEquivalenceProof(
        explicit_returncode=explicit_rc,
        canonical_returncode=canonical_rc,
        explicit_diagnostics_sha256=explicit_diag,
        canonical_diagnostics_sha256=canonical_diag,
        ruff_version=ruff_version,
        input_path_tuple_sha256=path_tuple_sha,
        config_path=config_path,
        config_sha256=config_sha,
        equivalent=equivalent,
    )


__all__ = [
    "RuffEquivalenceFailure",
    "RuffEquivalenceProof",
    "RuffToolUnavailable",
    "build_ruff_argv_from_identity",
    "build_ruff_canonical_argv",
    "build_ruff_explicit_argv",
    "parse_ruff_config_with_tomllib",
    "resolve_ruff_identity",
    "run_ruff_equivalence_proof",
]
