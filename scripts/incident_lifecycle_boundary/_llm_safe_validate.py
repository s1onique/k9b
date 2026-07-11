"""Per-call-site ``NewType(...)`` validation helper for LLM-safe walker.

R10 invariant: each canonical ``NewType(...)`` call must match
exactly one of two trusted bindings
(:data:`TRUSTED_BARE_NEWTYPE_BINDING` or
:data:`TRUSTED_QUALIFIED_TYPING_BINDING`). This module hosts the
validation helper so the walker (in :mod:`_llm_safe_walker`) and the
public entry point (in :mod:`_llm_safe_provenance`) can share the
same logic without creating a circular import.

Public surface:

* :func:`validate_newtype_call` - validate that a single
  ``NewType(...)`` call's binding snapshot at its source position
  matches the canonical trusted identity.
"""

from __future__ import annotations

import ast

from scripts.incident_lifecycle_boundary._llm_safe_provenance_types import (
    REBINDING_SENTINEL,
    TRUSTED_BARE_NEWTYPE_BINDING,
    TRUSTED_QUALIFIED_TYPING_BINDING,
    Binding,
)


def validate_newtype_call(
    call: ast.Call,
    bindings: dict[str, Binding],
    filepath: str,
    errors: list[str],
) -> None:
    """Validate a single ``NewType(...)`` call against the active binding snapshot.

    Appends to ``errors`` if the call's binding is untrusted or absent
    at the call's source position. The binding snapshot MUST reflect the
    state immediately after processing every prior module-level statement
    in source order; the walker in :func:`check_newtype_provenance`
    maintains that invariant.

    R10 requires an EXACT 4-tuple match against one of the two trusted
    bindings (:data:`TRUSTED_BARE_NEWTYPE_BINDING` or
    :data:`TRUSTED_QUALIFIED_TYPING_BINDING`). Sharing only
    ``module == "typing"`` with a trusted binding is NOT sufficient;
    same-module imports of a different symbol (e.g.
    ``from typing import Any as NewType``) are rejected.
    """
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "NewType":
        value = func.value
        if not isinstance(value, ast.Name) or value.id != "typing":
            errors.append(
                f"{filepath}: qualified 'NewType(...)' call must use the "
                f"'typing' qualifier; got '{ast.unparse(func)}'."
            )
            return
        binding = bindings.get("typing")
        if binding is None:
            errors.append(
                f"{filepath}: 'typing.NewType(...)' call requires a top-level "
                f"'import typing' before the call site; no binding found at "
                f"the call's source position."
            )
            return
        if binding is REBINDING_SENTINEL:
            errors.append(
                f"{filepath}: 'typing.NewType(...)' call at source position "
                f"uses a name that has been rebound at module scope; "
                f"the local name 'typing' no longer resolves to the "
                f"'typing' package at that source position."
            )
            return
        if binding != TRUSTED_QUALIFIED_TYPING_BINDING:
            errors.append(
                f"{filepath}: 'typing.NewType(...)' call resolves to a "
                f"non-trusted binding at its source position. The local "
                f"name 'typing' must be bound exactly as 'import typing' "
                f"(kind='import', module='typing', "
                f"original_name='typing', local_name='typing'); got "
                f"kind={binding.kind!r}, module={binding.module!r}, "
                f"original_name={binding.original_name!r}, "
                f"local_name={binding.local_name!r}. Same-module imports "
                f"of unrelated symbols (e.g. 'from typing import Any as "
                f"typing', 'from typing import NewType as typing') are "
                f"rejected."
            )
            return
        return

    if isinstance(func, ast.Name) and func.id == "NewType":
        binding = bindings.get("NewType")
        if binding is None:
            errors.append(
                f"{filepath}: bare 'NewType(...)' call is not connected to any "
                f"import at its source position. Add 'from typing import NewType' "
                f"or 'import typing' before the call; do not rely on a later "
                f"import to retroactively bind the name."
            )
            return
        if binding is REBINDING_SENTINEL:
            errors.append(
                f"{filepath}: bare 'NewType(...)' call at source position "
                f"uses a name that has been rebound at module scope; "
                f"the local name 'NewType' no longer resolves to the "
                f"trusted import at that source position."
            )
            return
        if binding != TRUSTED_BARE_NEWTYPE_BINDING:
            errors.append(
                f"{filepath}: bare 'NewType(...)' call resolves to a "
                f"non-trusted binding at its source position. The local "
                f"name 'NewType' must be bound exactly as 'from typing "
                f"import NewType' (kind='from-import', module='typing', "
                f"original_name='NewType', local_name='NewType'); got "
                f"kind={binding.kind!r}, module={binding.module!r}, "
                f"original_name={binding.original_name!r}, "
                f"local_name={binding.local_name!r}. Same-module imports "
                f"of unrelated symbols (e.g. 'from typing import Any as "
                f"NewType', 'import typing as NewType') are rejected."
            )


__all__ = ["validate_newtype_call"]
