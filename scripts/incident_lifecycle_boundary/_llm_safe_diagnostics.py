"""Diagnostic message formatters for the LLM-safe provenance walker.

R12 invariant: the walker emits an immediate diagnostic for every
module-scope attribute mutation on a provenance-sensitive name and
for every sensitive ``setattr`` call. The formatters here centralise
the diagnostic wording so the walker stays focused on walker
mechanics while the messages stay consistent.

Public surface:

* :func:`describe_attribute_mutation` - single-line diagnostic for
  ``typing.<attr> = X`` (and the symmetric AnnAssign, AugAssign,
  Delete forms).
* :func:`describe_setattr` - single-line diagnostic for
  ``setattr(typing, "NewType", X)`` (literal) and
  ``setattr(typing, attr_var, X)`` (dynamic) plus the
  ``builtins.setattr`` / ``__builtins__.setattr`` variants.
"""

from __future__ import annotations

import ast

from scripts.incident_lifecycle_boundary._llm_safe_attribute_integrity import (
    classify_sensitive_attribute_mutation as _classify_sensitive_attribute_mutation,
)


def attribute_mutation_targets(stmt: ast.stmt) -> list[ast.AST]:
    """Return the attribute-target list for attribute mutation forms."""
    if isinstance(stmt, ast.Assign):
        return list(stmt.targets)
    if isinstance(stmt, ast.Delete):
        return list(stmt.targets)
    return [stmt.target]


def describe_attribute_mutation(stmt: ast.stmt, *, filepath: str) -> str:
    """Return a single-line diagnostic for a sensitive attribute mutation."""
    form = _classify_sensitive_attribute_mutation(stmt) or "mutation"
    targets = attribute_mutation_targets(stmt)
    rendered = ", ".join(ast.unparse(t) for t in targets)
    return (
        f"{filepath}: forbidden module-scope attribute {form} on a "
        f"provenance-sensitive target ({rendered}). The sensitive "
        f"attribute can no longer be statically resolved to the "
        f"trusted import; subsequent calls to "
        f"typing.NewType(...) would resolve to the mutated value. "
        f"R10 fail-closed: attribute mutation forms are rejected "
        f"immediately, regardless of whether a call follows."
    )


def describe_setattr(stmt: ast.stmt, form: str, *, filepath: str) -> str:
    """Return a single-line diagnostic for a sensitive setattr call."""
    call = stmt.value
    assert isinstance(call, ast.Call)
    rendered = ast.unparse(call)
    if form == "literal":
        return (
            f"{filepath}: forbidden module-scope setattr on a "
            f"provenance-sensitive target ({rendered}). A literal "
            f"attribute name (or ``builtins.setattr``) on a sensitive "
            f"base cannot be statically resolved to a trusted "
            f"module; the call would let an attacker swap the "
            f"trusted NewType constructor. R10 fail-closed: rejected "
            f"immediately, regardless of whether a call follows."
        )
    return (
        f"{filepath}: forbidden module-scope dynamic setattr on a "
        f"provenance-sensitive target ({rendered}). The attribute "
        f"name is not a string literal so the verifier cannot "
        f"determine which attribute is being mutated. R10 "
        f"fail-closed: every dynamic setattr on a sensitive base "
        f"is rejected; use a literal attribute name with a non-"
        f"sensitive target instead."
    )


__all__ = [
    "attribute_mutation_targets",
    "describe_attribute_mutation",
    "describe_setattr",
]
