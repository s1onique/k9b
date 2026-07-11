"""Per-call-site NewType provenance verification for LLM-safe contracts.

This module hosts the public entry points for the LLM-safe
provenance walker. The walker itself lives in
:mod:`scripts.incident_lifecycle_boundary._llm_safe_walker` so this
module stays under the LLM-friendly file size threshold.

Public surface:

* :func:`check_newtype_provenance` - per-call-site provenance check
  that walks the module body in source order and validates each
  ``NewType(...)`` call against the binding active at that position.
* :func:`build_newtype_bindings` - **auxiliary** final-state binding
  table kept for callers that need a flat map but NOT for per-call-site
  provenance; use :func:`check_newtype_provenance` for that.
* :func:`detect_conditional_provenance_rebindings` - fail-closed detector
  for any rebinding of ``NewType`` or ``typing`` inside module-scope
  ``if``/``try``/``for``/``while``/``with``/``match`` blocks.
* :data:`Binding` - exact (kind, module, level, original_name, local_name)
  provenance record used for the per-call-site check.
* :data:`TRUSTED_BARE_NEWTYPE_BINDING` and
  :data:`TRUSTED_QUALIFIED_TYPING_BINDING` - the two exact bindings
  the verifier accepts.

Pattern-walking primitives (``_iter_target_names``,
``_iter_match_pattern_names``) live in
:mod:`scripts.incident_lifecycle_boundary._llm_safe_traversal`.
Attribute-mutation detection lives in
:mod:`scripts.incident_lifecycle_boundary._llm_safe_attribute_integrity`.
Diagnostic-message formatters live in
:mod:`scripts.incident_lifecycle_boundary._llm_safe_diagnostics`.
"""

from __future__ import annotations

import ast

from scripts.incident_lifecycle_boundary._llm_safe_provenance_types import (
    PROVENANCE_SENSITIVE_NAMES,
    REBINDING_SENTINEL,
    TRUSTED_BARE_NEWTYPE_BINDING,
    TRUSTED_QUALIFIED_TYPING_BINDING,
    Binding,
)
from scripts.incident_lifecycle_boundary._llm_safe_walker import (
    walk_with_source_order as _walk_with_source_order,
)


def build_newtype_bindings(tree: ast.AST) -> dict[str, Binding]:
    """Build a **final-state** binding table for ``NewType`` and ``typing`` imports.

    Returns a mapping ``local_name -> Binding``. Top-level ``Import``
    and ``ImportFrom`` statements are processed in source order so
    later bindings override earlier ones. The ``Binding`` is the
    full 5-tuple ``(kind, module, level, original_name, local_name)``
    so the caller can prove the EXACT identity bound, not merely the
    source module. ``level`` is the relative-import depth captured
    from ``ast.ImportFrom.level``; plain ``Import`` statements always
    encode ``level=0`` because Python does not support relative
    imports for ``import X`` form.

    .. warning::

       This helper is a flat, final-state view of module-scope
       imports. It does **not** capture the binding active at any
       particular source position. Callers that need per-call-site
       provenance MUST use :func:`check_newtype_provenance`, which
       evaluates each ``NewType(...)`` call against the binding
       snapshot active at that call's source position.

    Args:
        tree: Parsed AST (typically an :class:`ast.Module`).

    Returns:
        Dict from local name to a :class:`Binding`. For
        ``from typing import NewType`` the entry is
        ``{"NewType": Binding(kind="from-import", module="typing",
        level=0, original_name="NewType", local_name="NewType")}``.
        For ``import typing`` it is
        ``{"typing": Binding(kind="import", module="typing",
        level=0, original_name="typing", local_name="typing")}``.
    """
    bindings: dict[str, Binding] = {}
    if not isinstance(tree, ast.Module):
        return bindings

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level
            for alias in node.names:
                local_name = alias.asname or alias.name
                bindings[local_name] = Binding(
                    kind="from-import",
                    module=module,
                    level=level,
                    original_name=alias.name,
                    local_name=local_name,
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name
                bindings[local_name] = Binding(
                    kind="import",
                    module=alias.name,
                    level=0,
                    original_name=alias.name,
                    local_name=local_name,
                )

    return bindings


def _validate_newtype_call(
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


# Conditional rebinding detection lives in its own module to keep this
# file under the LLM-friendly threshold. It is re-exported here so
# callers using ``from scripts.incident_lifecycle_boundary
# ._llm_safe_provenance import detect_conditional_provenance_rebindings``
# continue to work without changes.
from scripts.incident_lifecycle_boundary._llm_safe_conditional_rebindings import (
    detect_conditional_provenance_rebindings as detect_conditional_provenance_rebindings,
)
from scripts.incident_lifecycle_boundary._llm_safe_named_expr_walker import (
    scan_module_scope_named_expr_rebindings as scan_module_scope_named_expr_rebindings,
)


def check_newtype_provenance(tree: ast.AST, filepath: str) -> list[str]:
    """Per-call-site ``NewType`` provenance check using a source-order binding snapshot.

    Closes the R9 bypass that the previous final-state-binding
    implementation left open: a late trusted import retroactively
    approved earlier calls that used a fake binding, and a late fake
    import retroactively poisoned earlier trusted calls.

    R10 closes the further bypass where the binding snapshot recorded
    only ``(source_module, original_name)`` and therefore accepted
    same-module imports of unrelated symbols (e.g.
    ``from typing import Any as NewType``). Each binding is now an
    exact 4-tuple ``(kind, module, level, original_name, local_name)``
    and the per-call-site check rejects any call whose binding does not
    match :data:`TRUSTED_BARE_NEWTYPE_BINDING` or
    :data:`TRUSTED_QUALIFIED_TYPING_BINDING` exactly.

    R12 closes the bypass where a module-scope attribute mutation on a
    sensitive name (e.g. ``typing.NewType = fake.NewType``,
    ``del typing.NewType``, ``setattr(typing, "NewType", X)``,
    ``setattr(typing, attr, X)``, ``builtins.setattr(typing, ...)``)
    was only detected as state affecting a later call. The walker now
    emits an immediate diagnostic for every such mutation and also
    rejects dynamic setattr (non-literal attribute name) and any
    ``builtins.setattr`` form outright.

    Algorithm:

    1. **Fail-closed conditional scan**: any rebinding of ``NewType`` or
       ``typing`` inside a module-scope ``if``/``try``/``for``/
       ``while``/``with``/``match`` block is rejected immediately.
    2. **Source-order snapshot walk**: walk ``tree.body`` in order,
       validating each canonical ``Name = NewType(...)`` assignment's
       right-hand call against the binding snapshot that was active
       BEFORE the assignment, and only then applying the binding
       update introduced by the statement. The walk descends into
       module-scope control flow. Sensitive attribute mutations and
       setattr calls emit an immediate diagnostic regardless of
       whether a subsequent call follows.
    """
    errors: list[str] = []
    if not isinstance(tree, ast.Module):
        return errors

    detect_conditional_provenance_rebindings(tree.body, filepath, errors)

    # R17: fail-closed scan for module-scope walrus rebindings
    # of NewType/typing before per-call-site provenance checks run.
    scan_module_scope_named_expr_rebindings(tree, filepath, errors)

    bindings: dict[str, Binding] = {}
    _walk_with_source_order(tree.body, bindings, filepath, errors)

    return errors


__all__ = [
    "PROVENANCE_SENSITIVE_NAMES",
    "REBINDING_SENTINEL",
    "Binding",
    "TRUSTED_BARE_NEWTYPE_BINDING",
    "TRUSTED_QUALIFIED_TYPING_BINDING",
    "build_newtype_bindings",
    "check_newtype_provenance",
    "detect_conditional_provenance_rebindings",
]
