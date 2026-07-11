"""LLM-safe canonical privacy-state hierarchy verifier.

Verifies that ``incident_evidence_redaction.py`` declares the exact
hierarchy declared in
:data:`scripts.incident_lifecycle_boundary._llm_safe_constants.CANONICAL_NEWTYPE_SUPERTYPES`
and that no extra or reshuffled aliases are present. The hierarchy is
part of the privacy-state contract, not just its terminal primitive
``str``.

Per-call-site ``NewType`` provenance is also enforced via a
source-order binding table (see
:mod:`scripts.incident_lifecycle_boundary._llm_safe_traversal`). Each
accepted ``NewType(...)`` call form (bare ``NewType(...)`` or qualified
``typing.NewType(...)``) must connect to a trusted import resolved at
the call site. The binding table closes two bypasses that the
previous module-wide boolean left open:

* ``from fake import NewType`` with no other ``NewType`` import was
  accepted because the boolean stayed ``False`` and no error was
  raised.
* ``from typing import NewType`` followed by ``from fake import
  NewType`` was accepted because the boolean was set to ``True`` by
  the first import and never invalidated.
"""

from __future__ import annotations

import ast

from scripts.incident_lifecycle_boundary._llm_safe_alias_supertypes import (
    validate_canonical_alias_super_types,
)
from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    CANONICAL_NEWTYPE_SUPERTYPES,
    LLM_SAFE_TYPES,
)
from scripts.incident_lifecycle_boundary._llm_safe_extract import (
    extract_newtype_aliases,
)
from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
    check_newtype_provenance,
)


def resolve_alias_base(
    name: str,
    aliases: dict[str, str],
    *,
    _seen: set[str] | None = None,
) -> str | None:
    """Resolve ``name`` to its primitive root by following the alias chain.

    For ``LLMSafeEvidenceText`` -> ``RedactedEvidenceText`` -> ``str``,
    returns ``"str"``. Returns ``None`` if the chain does not terminate
    in ``str`` (cycle or unknown supertype).
    """
    seen = set(_seen or ())
    if name in seen:
        # Cycle detected: alias chain does not terminate cleanly.
        return None
    seen.add(name)
    supertype = aliases.get(name)
    if supertype is None:
        return None
    if supertype == "str":
        return "str"
    # Recurse: supertype is another alias declared in this module.
    return resolve_alias_base(supertype, aliases, _seen=seen)


def check_canonical_redaction_aliases(
    canonical_filepath: str,
    *,
    expected_supertypes: dict[str, str] | None = None,
    expected_aliases: frozenset[str] | None = None,
) -> list[str]:
    """Verify the canonical privacy-state module declares the expected hierarchy.

    Enforcement is strict: every expected alias MUST declare its exact
    expected direct supertype. Reshuffling the branded chain (for example
    ``LLMSafeEvidenceText -> RawEvidenceText`` instead of
    ``LLMSafeEvidenceText -> RedactedEvidenceText``) is rejected, even
    when the chain still terminates at ``str``. The privacy-state
    hierarchy is part of the contract, not just its terminal primitive.

    Checks:

    - Every expected alias is declared as a top-level ``NewType(...)``
      assignment in ``canonical_filepath`` whose string name equals
      the assignment target.
    - The direct supertype for each alias matches ``expected_supertypes``
      exactly. Aliases whose resolved primitive root is ``str`` but whose
      immediate supertype is the wrong branded alias are rejected.
    - The alias chain is acyclic; cycles are surfaced.
    - No extra ``NewType`` aliases are allowed in the canonical module.
    - Per-call-site ``NewType`` provenance is enforced via a
      source-order binding table: bare ``NewType(...)`` requires the
      call-site name to be bound from ``typing`` at that source
      position; ``typing.NewType(...)`` requires ``import typing`` at
      that source position. ``from fake import NewType`` is rejected
      even when ``from typing import NewType`` is also present, and
      ``from fake import NewType`` alone is also rejected.

    Args:
        canonical_filepath: Path to the canonical redaction module.
        expected_supertypes: Optional override of expected supertypes map.
        expected_aliases: Optional override of expected alias set.

    Returns:
        List of error messages. Empty list means the canonical module
        declares the expected hierarchy with trusted NewType provenance.
    """
    errors: list[str] = []
    supertypes = expected_supertypes if expected_supertypes is not None else CANONICAL_NEWTYPE_SUPERTYPES
    aliases_set = expected_aliases if expected_aliases is not None else LLM_SAFE_TYPES

    actual = extract_newtype_aliases(canonical_filepath)
    if not actual:
        return [
            f"{canonical_filepath}: canonical privacy-state module declares "
            f"no NewType aliases; expected at least: {sorted(aliases_set)}."
        ]

    for alias in aliases_set:
        if alias not in actual:
            errors.append(
                f"{canonical_filepath}: canonical privacy-state module is "
                f"missing required NewType alias '{alias}'."
            )
            continue

        declared_supertype = actual[alias]
        expected_direct = supertypes.get(alias)
        if expected_direct is None:
            # No expected direct supertype registered; only require
            # the alias be present and its name match.
            continue

        if declared_supertype != expected_direct:
            errors.append(
                f"{canonical_filepath}: canonical privacy-state alias '{alias}' "
                f"declared as NewType('{alias}', '{declared_supertype}'), "
                f"expected NewType('{alias}', '{expected_direct}'). "
                f"Reshuffling the branded-alias chain is forbidden: "
                f"the privacy-state hierarchy must match the contract exactly."
            )

    # Reject extra aliases so the canonical module does not silently
    # mint new privacy-state types.
    extras = sorted(set(actual) - aliases_set)
    if extras:
        errors.append(
            f"{canonical_filepath}: canonical privacy-state module declares "
            f"unexpected NewType aliases: {extras}. The expected set is "
            f"{sorted(aliases_set)}."
        )

    # Detect cycles or ungrounded chains in the declared aliases.
    for alias in aliases_set:
        if alias in actual and not resolve_alias_base(alias, actual):
            errors.append(
                f"{canonical_filepath}: canonical privacy-state alias '{alias}' "
                f"does not resolve to a primitive 'str' root. The branded chain "
                f"either cycles or references an unknown supertype."
            )

    # Per-call-site ``NewType`` provenance using a source-order binding
    # table. Catches cases like ``from fake import NewType`` (alone or
    # after a trusted import) because the binding table records the
    # LAST binding for the local name ``NewType`` and rejects any
    # call whose binding is not from a trusted source.
    try:
        with open(canonical_filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return errors
    try:
        tree = ast.parse(source, filename=canonical_filepath)
    except SyntaxError:
        return errors
    errors.extend(check_newtype_provenance(tree, canonical_filepath))

    # R12 invariant: each canonical alias's declared supertype must be a
    # ``Name`` referencing a real binding identity that has NOT been
    # rebound at module scope. This closes the bypass where
    # ``str = int`` followed by ``NewType(..., str)`` passed the
    # lexical check, and where ``NewType("Foo", "str")`` passed
    # because no Name resolution was attempted.
    errors.extend(
        validate_canonical_alias_super_types(tree, canonical_filepath, aliases_set)
    )

    return errors
