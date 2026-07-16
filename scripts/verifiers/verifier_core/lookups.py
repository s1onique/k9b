"""Top-level function lookups.

This module owns the small set of ``ast.Module``-level lookup
helpers a verifier needs to locate a canonical chain's target
function:

* :func:`top_level_function` -- first-match lookup returning
  ``None`` when absent.
* :func:`function_body_statements` -- cheap alias kept for
  symmetry with the historical R20 fixture contract.
* :func:`parse_function_body` -- public alias for
  :func:`function_body_statements` matching the documented
  ``docs/doctrine/verifier-canonical-syntax.md`` contract.

These helpers do NOT descend into nested scopes -- that policy
is enforced intentionally so a verifier cannot accidentally
re-introduce a call-graph search.

The earlier draft of this module declared
:func:`unique_top_level_function`, which used
:func:`diagnostics.format_violation` and the
``SUB_DUPLICATE_TARGET_DEFINITION`` constant. Both of those
symbols have been removed (the production R20 verifier does
not consume them), so the duplicate-detecting variant is
intentionally absent. Verifier implementations that need
duplicate detection should iterate
:func:`top_level_function` over the candidate name or use the
parser-level primitives directly.

See ``docs/doctrine/verifier-canonical-syntax.md`` for the
production grammar the canonical R20 verifier recognises.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence


def top_level_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    """Top-level ``name`` lookup.

    Returns ``None`` when the name is absent. If multiple
    definitions exist, returns the first by source order; the
    verifier-core package does not currently ship a duplicate
    detector (see module docstring for the rationale).
    """
    return next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ),
        None,
    )


def function_body_statements(func: ast.FunctionDef) -> list[ast.stmt]:
    """Return ``func.body`` as a list.

    Cheap alias kept for symmetry with the historical R20
    fixture contract; consumers should prefer
    :func:`parse_function_body` for new code per the
    ``docs/doctrine/verifier-canonical-syntax.md`` grammar.
    """
    return list(func.body)


def parse_function_body(func: ast.FunctionDef) -> Sequence[ast.stmt]:
    """Return the canonical body statements of ``func``.

    This is the public alias mandated by the canonical-syntax
    doctrine: ``parse_function_body(func)`` returns the bounded
    list of statements the verifier should walk. It deliberately
    does not perform any ownership inference -- nested defs and
    lambdas are detected by the dedicated detectors, not by
    recursive AST walking here.
    """
    return function_body_statements(func)


__all__ = (
    "top_level_function",
    "function_body_statements",
    "parse_function_body",
)
