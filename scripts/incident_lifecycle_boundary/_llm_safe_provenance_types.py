"""Binding dataclass and trusted-binding constants for LLM-safe provenance.

This module hosts the small set of value types and module-level
constants used by the per-call-site ``NewType`` provenance walker.
Keeping these in their own module lets the walker file stay under
the LLM-friendly file size threshold while keeping the type surface
visible.

Public surface:

* :data:`PROVENANCE_SENSITIVE_NAMES` - set of names whose rebinding
  invalidates the per-call-site NewType provenance contract.
* :class:`Binding` - exact 5-tuple ``(kind, module, level,
  original_name, local_name)`` provenance record.
* :data:`REBINDING_SENTINEL` - singleton ``Binding`` instance
  installed when a sensitive name is rebound to an unresolvable
  value.
* :data:`TRUSTED_BARE_NEWTYPE_BINDING` - exact binding accepted for
  ``NewType(...)`` calls.
* :data:`TRUSTED_QUALIFIED_TYPING_BINDING` - exact binding accepted
  for ``typing.NewType(...)`` calls.

This module is intentionally tiny; it has no logic beyond the type
declarations. The walker lives in
:mod:`scripts.incident_lifecycle_boundary._llm_safe_provenance`.
"""

from __future__ import annotations

from dataclasses import dataclass

# Names whose rebinding at module scope invalidates the per-call-site
# NewType provenance contract. A rebinding of ``NewType`` or ``typing``
# (whether by import, assignment, function definition, or class
# definition) means the local name no longer resolves to a trusted
# source. Static analysis cannot always resolve the right-hand side of
# an assignment, so a rebinding is recorded with a sentinel tuple.
PROVENANCE_SENSITIVE_NAMES = frozenset({"NewType", "typing"})


@dataclass(frozen=True)
class Binding:
    """Exact per-binding provenance record.

    Stores the five fields that together identify a top-level import
    result:

    * ``kind`` - either ``"from-import"`` (a ``from X import Y`` form,
      optionally with ``as`` alias) or ``"import"`` (a plain
      ``import X`` form, optionally with ``as`` alias). The sentinel
      binding uses the special kind ``"<rebinding>"``.
    * ``module`` - the source module path the binding was imported
      from. For ``from typing import Any as NewType`` this is
      ``"typing"``. For sentinel bindings it is ``"<unknown>"``.
    * ``level`` - the relative-import depth. ``0`` is an absolute
      import; ``1`` is ``from .X import Y``; ``2`` is ``from ..X
      import Y``. R11 closes the bypass where
      ``from .typing import NewType`` would record ``module ==
      "typing"`` while actually resolving to a different (parent
      package's) ``typing`` module. The trusted bindings REQUIRE
      ``level == 0`` so relative imports cannot smuggle a trusted
      local name from a different package.
    * ``original_name`` - the symbol as it was exported from the
      source module. For ``from typing import NewType`` this is
      ``"NewType"``. For ``from typing import Any as NewType`` this
      is ``"Any"`` - critically different from the local name.
    * ``local_name`` - the name bound in the importing module's
      namespace. For a plain ``import typing`` this is ``"typing"``.
      For ``from typing import NewType as NT`` this is ``"NT"``.

    The R10 invariant is that a ``NewType(...)`` call site is accepted
    ONLY if its binding matches the trusted shape exactly; partial
    matches that share only ``module == "typing"`` are rejected. The
    R11 invariant additionally requires ``level == 0`` for the
    ``from-import`` form.
    """

    kind: str
    module: str
    level: int
    original_name: str
    local_name: str


# Sentinel binding for a name that has been rebound to a non-import
# source (e.g. ``NewType = fake.NewType``, ``def NewType(...)``,
# ``class NewType: ...``). Static analysis cannot follow the value's
# source module, so the per-call-site check rejects any use of the name
# after such a rebinding.
#
# The sentinel is a singleton ``Binding`` instance; callers compare
# with ``is`` rather than via equality so any structurally-distinct
# accidental binding cannot collide with the sentinel.
REBINDING_SENTINEL: Binding = Binding(
    kind="<rebinding>",
    module="<unknown>",
    level=0,
    original_name="<unknown>",
    local_name="<unknown>",
)


# The two exact trusted bindings the per-call-site check accepts. Any
# call whose binding is not one of these (or whose binding has been
# replaced by :data:`REBINDING_SENTINEL`) is rejected.
#
# Bare ``NewType(...)`` form:
#     from typing import NewType
#
# Qualified ``typing.NewType(...)`` form:
#     import typing
#
# Both forms REQUIRE ``level == 0``; the ``from-import`` form encodes
# ``level`` from ``ast.ImportFrom.level`` (0 for absolute imports)
# and the ``import`` form always has ``level == 0`` because Python
# does not support relative imports for plain ``import X``.
TRUSTED_BARE_NEWTYPE_BINDING: Binding = Binding(
    kind="from-import",
    module="typing",
    level=0,
    original_name="NewType",
    local_name="NewType",
)
TRUSTED_QUALIFIED_TYPING_BINDING: Binding = Binding(
    kind="import",
    module="typing",
    level=0,
    original_name="typing",
    local_name="typing",
)


__all__ = [
    "PROVENANCE_SENSITIVE_NAMES",
    "Binding",
    "REBINDING_SENTINEL",
    "TRUSTED_BARE_NEWTYPE_BINDING",
    "TRUSTED_QUALIFIED_TYPING_BINDING",
]
