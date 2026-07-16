"""Source-location primitives for the verifier-core package.

This module is intentionally narrow: it owns only the
:class:`SourceLocation` dataclass and the
:func:`location_of` helper. Both are used by
:mod:`.detectors` to return bounded fact positions, and by
verifier implementations outside the package to locate
specific AST nodes.

The earlier draft of this module declared a
:class:`Diagnostic` dataclass, :func:`format_violation`,
:func:`sort_diagnostics`, and :class:`VerInfrastructureError`.
``Diagnostic`` and ``format_violation`` have been removed
because the production R20 verifier does NOT consume them --
it has its own detector output vocabulary. ``VerInfrastructureError``
now lives in :mod:`.codes` next to the parsing helpers that
raise it. ``sort_diagnostics`` has been removed because no
verifier implementation needs a canonical ordering of
diagnostic records (verifiers emit one violation per source
position in their own ordering).

See ``docs/doctrine/verifier-canonical-syntax.md`` for the
production grammar the canonical R20 verifier recognises.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class SourceLocation:
    """Deterministic 1-indexed ``(line, column)`` source position.

    Lifted to this module so importing :class:`SourceLocation`
    from ``scripts.verifiers.verifier_core`` does not require
    any non-public sub-import. Tests construct positions
    directly; detector returns use :func:`location_of` to
    extract the position from an :mod:`ast` node.
    """

    line: int
    column: int = 0


def location_of(node: ast.AST | None) -> SourceLocation:
    """Return the source location of ``node``, or ``SourceLocation(0, 0)``
    when ``node`` is ``None`` or has no source position."""
    if node is None:
        return SourceLocation(0, 0)
    return SourceLocation(node.lineno or 0, node.col_offset or 0)


__all__ = (
    "SourceLocation",
    "location_of",
)
