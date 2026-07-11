"""LLM-safe facade re-export verifier.

The facade (``incident_evidence_llm_safe.py``) re-exports canonical
privacy-state identities rather than redefining them. This module
enforces three independent contracts:

1. No local ``NewType(...)`` redeclaration of any canonical alias. The
   bare ``NewType`` name must trace to a trusted import (``typing``)
   per call-site via a source-order binding table (see
   :mod:`scripts.incident_lifecycle_boundary._llm_safe_traversal`).
2. Top-level ``from <canonical> import <name>`` re-export for every
   canonical name. ``from somewhere import <name>`` and
   ``from canonical import SomethingElse as <name>`` are rejected.
3. No module-scope rebinding of any protected canonical name. The
   facade must NOT rebind ``RawEvidenceText = str`` (or via
   ``FunctionDef``, ``ClassDef``, ``AugAssign``, ``for``, ``with``,
   ``except``, ``match`` cases, or later ``Import``/``ImportFrom``
   statements) after a correct canonical import, including rebindings
   hidden inside ``if``/``try``/``for``/``while``/``with``/``match``
   blocks that execute at import time: doing so would replace the
   privacy-state identity with an arbitrary Python object and
   silently leak raw text.
"""

from __future__ import annotations

import ast

from scripts.incident_lifecycle_boundary._llm_safe_constants import LLM_SAFE_TYPES
from scripts.incident_lifecycle_boundary._llm_safe_extract import (
    extract_canonical_imports,
    extract_newtype_aliases,
)
from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
    check_newtype_provenance,
)
from scripts.incident_lifecycle_boundary._llm_safe_traversal import (
    collect_module_scope_rebindings,
)


def _has_trusted_newtype_import(tree: ast.AST) -> bool:
    """Return True if the module has any trusted ``NewType`` binding.

    A trusted binding is either:
    - ``from typing import NewType``
    - ``from typing import NewType as <other>``
    - ``import typing`` (qualifies the ``typing.NewType`` form)

    A bare ``from fake import NewType`` is NOT trusted because the
    extracted ``NewType`` name does not connect to a known
    privacy-state constructor. Note: this only checks whether ANY
    trusted binding exists; the per-call-site check in
    :func:`check_newtype_provenance` validates that the binding is
    actually active at each call site.
    """
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module == "typing":
                for alias in node.names:
                    if alias.name == "NewType":
                        return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "typing":
                    return True
    return False


def check_llm_safe_type_aliases(facade_filepath: str) -> list[str]:
    """Verify the facade does NOT define any canonical alias as a local NewType.

    Duplicating a ``NewType`` with the same name would create two
    structurally identical but statically distinct types behind the
    identical name, weakening privacy guarantees.

    The canonical module is required to import ``NewType`` from a
    trusted source (``typing``). A bare ``from fake import NewType``
    is NOT trusted; the facade verifier rejects any local ``NewType``
    declaration if the facade cannot prove the provenance of its
    ``NewType`` name.

    Args:
        facade_filepath: Path to the LLM-safe facade module.

    Returns:
        List of error messages. Empty list means the facade does not
        redefine any canonical alias locally.
    """
    errors: list[str] = []

    try:
        with open(facade_filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {facade_filepath}: {e}"]
    try:
        tree = ast.parse(source, filename=facade_filepath)
    except SyntaxError:
        return errors

    facade_aliases = extract_newtype_aliases(facade_filepath)
    has_trusted_newtype = _has_trusted_newtype_import(tree)

    for canonical_alias in LLM_SAFE_TYPES:
        if canonical_alias in facade_aliases:
            errors.append(
                f"{facade_filepath}: facade must NOT redefine '{canonical_alias}' "
                f"as a local NewType. The canonical identity lives in the "
                f"canonical redaction module; re-export it via 'from ... "
                f"import {canonical_alias}' instead. Declared as: "
                f"NewType('{canonical_alias}', '{facade_aliases[canonical_alias]}')."
            )

    # Reject local ``NewType`` declarations when the module did not
    # import ``NewType`` from a trusted source. This catches
    # ``from fake import NewType`` smuggling even when the alias name
    # matches a non-canonical identity.
    if facade_aliases and not has_trusted_newtype:
        smuggled = sorted(facade_aliases)
        errors.append(
            f"{facade_filepath}: module declares local NewType aliases "
            f"({smuggled}) but does not import ``NewType`` from a trusted "
            f"source (typing or typing.NewType). Refusing to accept "
            f"untrusted NewType provenance."
        )

    # Per-call-site provenance: each ``NewType(...)`` call must connect
    # to a trusted import resolved at the call site. Uses the
    # source-order binding table so a later ``from fake import
    # NewType`` invalidates an earlier trusted import.
    errors.extend(check_newtype_provenance(tree, facade_filepath))

    return errors


def _collect_canonical_rebindings(
    facade_filepath: str,
    protected_names: frozenset[str],
    *,
    canonical_module: str | None = None,
) -> set[str]:
    """Collect every module-scope rebinding of a protected canonical name.

    Rebindings can take many forms beyond ``Assign``:

    * ``Assign`` and ``AnnAssign`` (most common forms)
    * ``AugAssign`` (``name += other``, ``name -= other``)
    * ``FunctionDef`` / ``AsyncFunctionDef`` (a function with the
      same name as the protected alias)
    * ``ClassDef`` (a class with the same name)
    * ``Import`` / ``ImportFrom`` (a later import that rebinds the
      protected name to a different module; the canonical
      ``from canonical import ...`` is excluded via
      ``canonical_module``)
    * ``for`` / ``async for`` / ``while`` / ``with`` / ``async with``
      / ``except`` / ``match`` case targets that bind the protected
      name at module scope

    The walker descends into module-scope control flow (``if``,
    ``try``/``except``/``else``/``finally``, ``for``, ``while``,
    ``with``, ``match``) so rebindings that execute at import time
    inside such blocks are surfaced.

    The invariant: each protected name has exactly one top-level
    binding, and that binding must be the canonical ``ImportFrom`` we
    already collected via ``extract_canonical_imports``.

    Note: rebindings inside a function or class body are intentionally
    NOT scanned because the privacy-state identity surface is the
    module's public namespace, not its local frame.
    """
    try:
        with open(facade_filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return set()
    try:
        tree = ast.parse(source, filename=facade_filepath)
    except SyntaxError:
        return set()

    # The canonical ``from <canonical_module> import ...`` statement is
    # the ONE allowed top-level binding for each canonical name. The
    # walker skips ImportFrom rebindings whose ``module`` matches
    # ``canonical_module`` via the ``exclude_imports_from`` parameter.
    return collect_module_scope_rebindings(
        tree, protected_names, exclude_imports_from=canonical_module,
    )


def check_llm_safe_canonical_imports(
    facade_filepath: str,
    *,
    canonical_module: str | None = None,
    expected_names: frozenset[str] | None = None,
) -> list[str]:
    """Verify the facade imports every canonical privacy-state name from the
    canonical redaction module.

    The facade module MUST bind each canonical privacy-state name to a
    top-level ``from <canonical_module> import <canonical_name>`` statement.
    Both the source module and the original imported symbol must match:
    ``from canonical import SomethingElse as Foo`` is rejected because the
    original identity is ``SomethingElse``, not ``Foo``. The facade must
    also avoid rebinding any protected canonical name to an arbitrary
    Python object (e.g. ``RawEvidenceText = str``, ``def RawEvidenceText()``,
    ``class RawEvidenceText``, ``RawEvidenceText += other``): doing so
    would replace the privacy-state identity and silently leak raw text.
    Rebindings hidden inside module-scope control flow (``if``,
    ``try``/``finally``, ``for``, ``while``, ``with``, ``match``) are
    also rejected.

    Args:
        facade_filepath: Path to the facade module.
        canonical_module: Fully-qualified module path that must supply
            the canonical aliases.
        expected_names: Override of the canonical alias set.

    Returns:
        List of error messages. Empty list means the facade imports
        every canonical alias from the canonical module with the
        correct original symbol and no rebinding has occurred.
    """
    errors: list[str] = []
    module = (
        canonical_module
        if canonical_module is not None
        else "k8s_diag_agent.collect.incident_evidence_redaction"
    )
    names = expected_names if expected_names is not None else LLM_SAFE_TYPES

    imports = extract_canonical_imports(facade_filepath)
    rebindings = _collect_canonical_rebindings(
        facade_filepath, names, canonical_module=module,
    )

    for canonical_name in names:
        if canonical_name not in imports:
            errors.append(
                f"{facade_filepath}: facade does not re-export '{canonical_name}' "
                f"via a top-level 'from {module} import {canonical_name}'. "
                f"Without this import the facade would expose a different "
                f"identity than the canonical privacy-state module."
            )
            continue
        imported = imports[canonical_name]
        if imported.module != module:
            errors.append(
                f"{facade_filepath}: facade imports '{canonical_name}' from "
                f"'{imported.module}', expected canonical source "
                f"'{module}'. The privacy-state identity must be sourced from "
                f"the canonical redaction module."
            )
            continue
        if imported.original_name != canonical_name:
            errors.append(
                f"{facade_filepath}: facade binds '{canonical_name}' to "
                f"the result of 'from {imported.module} import "
                f"{imported.original_name} as {imported.local_name}'. The "
                f"original imported symbol must equal the local name; "
                f"otherwise the facade exposes a same-named but "
                f"statically distinct identity."
            )
            continue
        if imported.local_name != canonical_name:
            errors.append(
                f"{facade_filepath}: facade binds the canonical symbol to a "
                f"different local name: '{imported.local_name}'. The "
                f"local name must equal '{canonical_name}'."
            )
        if canonical_name in rebindings:
            errors.append(
                f"{facade_filepath}: facade rebinds protected canonical "
                f"name '{canonical_name}' after the canonical import. "
                f"Each canonical privacy-state name must have exactly one "
                f"top-level binding, and that binding must be the "
                f"canonical ImportFrom. Rebinding (Assign, AnnAssign, "
                f"AugAssign, FunctionDef, ClassDef, Import, ImportFrom, "
                f"for/while/with/except/match targets, including those "
                f"inside module-scope if/try/for/while/with/match "
                f"blocks) exposes a different identity than the "
                f"privacy-state module declares."
            )

    return errors
