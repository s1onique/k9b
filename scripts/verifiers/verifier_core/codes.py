"""AST parsing and source-reading helpers for the verifier-core package.

This module is intentionally narrow: it owns only the AST
parsing and IO helpers that have at least one non-test
consumer in the verifier-core package implementation.

The earlier draft of this module declared the canonical-syntax
subcode vocabulary (``CODE_CANONICAL``, 23 ``SUB_*``
constants, ``EXPECTED_PUBLIC_API``, ``all_subcodes()``). That
vocabulary has been removed because the production R20
verifier does NOT emit those subcodes (it has its own
historical detector output vocabulary) and the verifier-core
package must NOT carry speculative public surface.

Public API:

* :func:`read_source` -- UTF-8 source reader with deterministic
  error propagation.
* :func:`parse_path` -- non-raising AST parse returning
  ``None`` on parse or IO failure.
* :func:`parse_strict` -- strict AST parse that raises
  :class:`VerInfrastructureError` on syntax error.
* :class:`VerInfrastructureError` -- the broken-verifier signal
  (parse failure, IO error, etc.).

These primitives are general structural helpers shared across
verifier implementations. The core is policy-free.

See ``docs/doctrine/verifier-canonical-syntax.md`` for the
production grammar the canonical R20 verifier recognises.
"""

from __future__ import annotations

import ast
from pathlib import Path


def read_source(path: Path) -> str:
    """Read ``path`` as UTF-8 with deterministic error propagation.

    IO failures bubble up as :class:`OSError`; the caller decides
    whether that should map to :class:`VerInfrastructureError`.
    """
    return path.read_text(encoding="utf-8")


def parse_path(path: Path) -> ast.Module | None:
    """Parse ``path`` if possible; return ``None`` on parse failure.

    Non-raising: callers that want strict semantics should use
    :func:`parse_strict` which raises
    :class:`VerInfrastructureError` on syntax failure.
    """
    try:
        return ast.parse(read_source(path), filename=str(path))
    except (OSError, SyntaxError):
        return None


def parse_strict(source: str, *, filename: str | None = None) -> ast.Module:
    """Parse ``source`` strictly and raise on syntax error.

    A :class:`SyntaxError` from :mod:`ast` is re-raised as a
    :class:`VerInfrastructureError` whose message preserves the
    original filename, line, column, and parser message.
    """
    try:
        return ast.parse(source, filename=filename or "<source>")
    except SyntaxError as exc:
        location = exc.filename or (filename or "<source>")
        line = exc.lineno or 0
        col = exc.offset or 0
        raise VerInfrastructureError(
            f"syntax error at {location}:{line}:{col}: {exc.msg or exc}"
        ) from exc


class VerInfrastructureError(RuntimeError):
    """The verifier itself is broken (parse failure, IO error, etc.).

    Use this signal for problems the verifier cannot reason about
    -- it is distinct from the user-facing canonical-syntax
    violations that the production R20 verifier emits through
    its own detector output vocabulary.
    """


__all__ = (
    "VerInfrastructureError",
    "read_source",
    "parse_path",
    "parse_strict",
)
