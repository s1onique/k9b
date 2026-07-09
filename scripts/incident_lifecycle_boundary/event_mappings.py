"""Event mapping checks for the incident lifecycle boundary verifier.

This module verifies that:
- Domain event types and actors are properly typed as closed Literal aliases
- Store adapter has complete mapping tables for all domain events and actors
- Mapping tables contain no unknown keys
- IncidentLifecycleEvent dataclass fields have correct type annotations
"""

from __future__ import annotations

import ast
import sys

# Expected stable domain event type values (from IncidentLifecycleEventType alias)
EXPECTED_DOMAIN_EVENT_TYPES: frozenset[str] = frozenset({
    "incident_promoted",
    "incident_marked_collecting_evidence",
    "incident_marked_ready_for_review",
    "incident_marked_investigating",
    "incident_suppressed",
    "incident_marked_duplicate",
    "incident_resolved",
})

# Expected stable domain actor values (from IncidentLifecycleActor alias)
EXPECTED_DOMAIN_ACTORS: frozenset[str] = frozenset({
    "system",
    "user",
    "diagnosis_loop",
    "test",
})


def _is_literal_subscript(node: ast.Subscript) -> bool:
    """Check if subscript is Literal[...] or typing.Literal[...], not another type."""
    if isinstance(node.value, ast.Name):
        return node.value.id == "Literal"
    if isinstance(node.value, ast.Attribute):
        # Handle: typing.Literal[...]
        return node.value.attr == "Literal"
    return False


def _extract_literal_string_args(node: ast.expr) -> set[str]:
    """Extract string literal arguments from a Literal[...] subscript.

    Handles:
    - Literal["a", "b"]
    - Literal["a"]  (single element)
    - typing.Literal["a", "b"]

    Returns empty set if node is not a Literal subscript.
    """
    reasons: set[str] = set()

    if isinstance(node, ast.Subscript):
        if not _is_literal_subscript(node):
            return reasons

        slice_node = node.slice

        # Single element: Literal["a"]
        if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
            reasons.add(slice_node.value)
        # Tuple of elements: Literal["a", "b"]
        elif isinstance(slice_node, ast.Tuple):
            for elt in slice_node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    reasons.add(elt.value)

    return reasons


def extract_literal_alias_values(filepath: str, alias_name: str) -> set[str]:
    """Extract values from a Literal type alias using AST.

    Parses the module and finds an assignment named `alias_name`
    with a Literal[...] value.

    Supports:
    - AliasName = Literal["a", "b"]
    - AliasName: TypeAlias = Literal["a", "b"]

    Returns:
        Set of string literal values from the alias, or empty set if not found.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return set()

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return set()

    for node in tree.body:
        target_name: str | None = None
        value: ast.expr | None = None

        # Simple assignment: AliasName = Literal[...]
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id == alias_name:
                    target_name = node.targets[0].id
                    value = node.value

        # Annotated assignment: AliasName = Literal[...] (no annotation)
        # or AliasName: TypeAlias = Literal[...]
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                if node.target.id == alias_name:
                    target_name = node.target.id
                    value = node.value

        if target_name == alias_name and value is not None:
            return _extract_literal_string_args(value)

    return set()


def extract_domain_event_types(domain_filepath: str) -> set[str]:
    """Extract IncidentLifecycleEventType values from domain module."""
    return extract_literal_alias_values(domain_filepath, "IncidentLifecycleEventType")


def extract_domain_actors(domain_filepath: str) -> set[str]:
    """Extract IncidentLifecycleActor values from domain module."""
    return extract_literal_alias_values(domain_filepath, "IncidentLifecycleActor")


def _extract_dict_keys(node: ast.Dict) -> set[str]:
    """Extract string keys from an ast.Dict node."""
    result: set[str] = set()
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            result.add(key.value)
    return result


def extract_adapter_mapping_keys(
    adapter_filepath: str,
    mapping_var_name: str,
) -> set[str]:
    """Extract keys from a module-level dict variable.

    Looks for a variable like:
        _DOMAIN_EVENT_TO_STORE_EVENT = {
            "key1": ...,
            "key2": ...,
        }
    """
    try:
        with open(adapter_filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return set()

    try:
        tree = ast.parse(source, filename=adapter_filepath)
    except SyntaxError:
        return set()

    for node in tree.body:
        # Handle simple assignment: _VAR = {...}
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == mapping_var_name:
                    if isinstance(node.value, ast.Dict):
                        return _extract_dict_keys(node.value)

        # Handle annotated assignment: _VAR: dict[str, str] = {...}
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == mapping_var_name:
                if isinstance(node.value, ast.Dict):
                    return _extract_dict_keys(node.value)

    return set()


def check_event_dataclass_field_types(filepath: str) -> list[str]:
    """Check that IncidentLifecycleEvent has correctly typed event_type and actor fields.

    Verifies:
    - IncidentLifecycleEvent exists
    - event_type field is annotated as IncidentLifecycleEventType (not str, not Any)
    - actor field is annotated as IncidentLifecycleActor (not str, not Any)
    """
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {filepath}: {e}"]

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return errors

    found_event_class = False
    event_type_correctly_typed = False
    actor_correctly_typed = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "IncidentLifecycleEvent":
            found_event_class = True
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name):
                        if item.target.id == "event_type":
                            # Check if type is IncidentLifecycleEventType
                            if isinstance(item.annotation, ast.Name):
                                if item.annotation.id == "IncidentLifecycleEventType":
                                    event_type_correctly_typed = True
                                elif item.annotation.id in ("str", "object", "Any"):
                                    errors.append(
                                        f"{filepath}:{item.lineno}: "
                                        f"IncidentLifecycleEvent.event_type is typed as '{item.annotation.id}' (too wide), "
                                        f"should be 'IncidentLifecycleEventType'"
                                    )
                        elif item.target.id == "actor":
                            # Check if type is IncidentLifecycleActor
                            if isinstance(item.annotation, ast.Name):
                                if item.annotation.id == "IncidentLifecycleActor":
                                    actor_correctly_typed = True
                                elif item.annotation.id in ("str", "object", "Any"):
                                    errors.append(
                                        f"{filepath}:{item.lineno}: "
                                        f"IncidentLifecycleEvent.actor is typed as '{item.annotation.id}' (too wide), "
                                        f"should be 'IncidentLifecycleActor'"
                                    )

    # Require IncidentLifecycleEvent class to exist
    if not found_event_class:
        errors.append(
            f"{filepath}: IncidentLifecycleEvent class is missing. "
            f"Expected a dataclass with event_type and actor fields."
        )

    # Require event_type field to be correctly typed
    if found_event_class and not event_type_correctly_typed:
        errors.append(
            f"{filepath}: IncidentLifecycleEvent.event_type must be annotated as "
            f"'IncidentLifecycleEventType', not 'str', 'object', or other widened types."
        )

    # Require actor field to be correctly typed
    if found_event_class and not actor_correctly_typed:
        errors.append(
            f"{filepath}: IncidentLifecycleEvent.actor must be annotated as "
            f"'IncidentLifecycleActor', not 'str', 'object', or other widened types."
        )

    return errors


def check_lifecycle_event_mappings(
    domain_filepath: str,
    adapter_filepath: str,
) -> list[str]:
    """Check that adapter mapping tables cover all domain event types and actors.

    Verifies:
    - Domain event types match expected values
    - Domain actors match expected values
    - Adapter event mapping contains all domain event types (no missing, no extra)
    - Adapter actor mapping contains all domain actors (no missing, no extra)
    - IncidentLifecycleEvent dataclass fields are correctly typed
    """
    errors: list[str] = []

    # Step 1: Extract domain event types
    domain_event_types = extract_domain_event_types(domain_filepath)
    if not domain_event_types:
        errors.append(
            f"{domain_filepath}: IncidentLifecycleEventType alias missing or empty"
        )
    elif domain_event_types != EXPECTED_DOMAIN_EVENT_TYPES:
        missing = EXPECTED_DOMAIN_EVENT_TYPES - domain_event_types
        extra = domain_event_types - EXPECTED_DOMAIN_EVENT_TYPES
        if missing:
            errors.append(
                f"{domain_filepath}: IncidentLifecycleEventType missing expected values: {sorted(missing)}"
            )
        if extra:
            errors.append(
                f"{domain_filepath}: IncidentLifecycleEventType has unexpected values: {sorted(extra)}"
            )

    # Step 2: Extract domain actors
    domain_actors = extract_domain_actors(domain_filepath)
    if not domain_actors:
        errors.append(
            f"{domain_filepath}: IncidentLifecycleActor alias missing or empty"
        )
    elif domain_actors != EXPECTED_DOMAIN_ACTORS:
        missing = EXPECTED_DOMAIN_ACTORS - domain_actors
        extra = domain_actors - EXPECTED_DOMAIN_ACTORS
        if missing:
            errors.append(
                f"{domain_filepath}: IncidentLifecycleActor missing expected values: {sorted(missing)}"
            )
        if extra:
            errors.append(
                f"{domain_filepath}: IncidentLifecycleActor has unexpected values: {sorted(extra)}"
            )

    # Step 3: Extract adapter event mapping keys
    adapter_event_keys = extract_adapter_mapping_keys(
        adapter_filepath, "_DOMAIN_EVENT_TO_STORE_EVENT"
    )
    if not adapter_event_keys and domain_event_types:
        errors.append(
            f"{adapter_filepath}: _DOMAIN_EVENT_TO_STORE_EVENT mapping is missing or empty"
        )
    elif domain_event_types and adapter_event_keys != domain_event_types:
        event_missing: set[str] = set(domain_event_types) - adapter_event_keys
        event_extra: set[str] = adapter_event_keys - set(domain_event_types)
        if event_missing:
            errors.append(
                f"{adapter_filepath}: _DOMAIN_EVENT_TO_STORE_EVENT missing domain events: {sorted(event_missing)}"
            )
        if event_extra:
            errors.append(
                f"{adapter_filepath}: _DOMAIN_EVENT_TO_STORE_EVENT has unknown extra keys: {sorted(event_extra)}"
            )

    # Step 4: Extract adapter actor mapping keys
    adapter_actor_keys = extract_adapter_mapping_keys(
        adapter_filepath, "_DOMAIN_ACTOR_TO_STORE_ACTOR"
    )
    if not adapter_actor_keys and domain_actors:
        errors.append(
            f"{adapter_filepath}: _DOMAIN_ACTOR_TO_STORE_ACTOR mapping is missing or empty"
        )
    elif domain_actors and adapter_actor_keys != domain_actors:
        actor_missing: set[str] = set(domain_actors) - adapter_actor_keys
        actor_extra: set[str] = adapter_actor_keys - set(domain_actors)
        if actor_missing:
            errors.append(
                f"{adapter_filepath}: _DOMAIN_ACTOR_TO_STORE_ACTOR missing domain actors: {sorted(actor_missing)}"
            )
        if actor_extra:
            errors.append(
                f"{adapter_filepath}: _DOMAIN_ACTOR_TO_STORE_ACTOR has unknown extra keys: {sorted(actor_extra)}"
            )

    # Step 5: Check dataclass field types
    field_type_errors = check_event_dataclass_field_types(domain_filepath)
    errors.extend(field_type_errors)

    return errors


# Allow list of exported names for backward compatibility
if __name__ == "__main__":
    sys.exit(0)
