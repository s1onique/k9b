"""Rejection reason type alias checks for the incident lifecycle boundary verifier."""

from __future__ import annotations

import ast
import re
import sys

# Allowed rejection reason codes (derived from TransitionRejectionReason alias)
ALLOWED_REJECTION_REASONS: frozenset[str] = frozenset({
    "terminal_incident",
    "invalid_transition",
    "missing_review_packet",
    "missing_snapshot_bundle",
    "duplicate_self_reference",
})

# Stable public contract for rejection reasons (cross-check against typed alias)
EXPECTED_STABLE_REJECTION_REASONS: frozenset[str] = frozenset({
    "terminal_incident",
    "invalid_transition",
    "missing_review_packet",
    "missing_snapshot_bundle",
    "duplicate_self_reference",
})


def _is_literal_subscript(node: ast.Subscript) -> bool:
    """Check if subscript is Literal[...] or typing.Literal[...], not another type.

    This ensures we only extract from actual Literal types, not from
    incorrectly named types like NotLiteral[...] or Sequence[...].
    """
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

    # Handle subscript: must be Literal[...] specifically
    if isinstance(node, ast.Subscript):
        # REJECT: NotLiteral[...] or other non-Literal subscripts
        if not _is_literal_subscript(node):
            return reasons

        # The slice contains the literal values (e.g., "a", "b")
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


def extract_transition_rejection_reasons(filepath: str) -> set[str]:
    """Extract rejection reason values from TransitionRejectionReason alias using AST.

    Parses the module and finds an assignment named `TransitionRejectionReason`
    with a Literal[...] value.

    Supports:
    - TransitionRejectionReason = Literal["a", "b"]
    - TransitionRejectionReason: TypeAlias = Literal["a", "b"]

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

        # Simple assignment: TransitionRejectionReason = Literal[...]
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id == "TransitionRejectionReason":
                    target_name = node.targets[0].id
                    value = node.value

        # Annotated assignment: TransitionRejectionReason = Literal[...] (no annotation)
        # or TransitionRejectionReason: TypeAlias = Literal[...]
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                if node.target.id == "TransitionRejectionReason":
                    target_name = node.target.id
                    value = node.value

        if target_name == "TransitionRejectionReason" and value is not None:
            return _extract_literal_string_args(value)

    return set()


def check_rejection_reason_type_alias(filepath: str) -> list[str]:
    """Check that TransitionRejectionReason alias exists and is properly typed.

    Verifies:
    - TransitionRejectionReason alias exists
    - Alias contains values (not empty)
    - Alias values match the expected stable public contract
    - TransitionRejected class exists
    - TransitionRejected.reason field exists and is annotated as TransitionRejectionReason
    """
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {filepath}: {e}"]

    # Extract reasons from the alias
    extracted_reasons = extract_transition_rejection_reasons(filepath)

    if not extracted_reasons:
        errors.append(
            f"{filepath}: TransitionRejectionReason alias missing or empty. "
            f"Expected a Literal[...] with rejection reason codes."
        )
        return errors

    # Check that extracted reasons match the expected stable contract
    if extracted_reasons != EXPECTED_STABLE_REJECTION_REASONS:
        missing = EXPECTED_STABLE_REJECTION_REASONS - extracted_reasons
        extra = extracted_reasons - EXPECTED_STABLE_REJECTION_REASONS
        if missing:
            errors.append(
                f"{filepath}: TransitionRejectionReason missing expected values: {sorted(missing)}"
            )
        if extra:
            errors.append(
                f"{filepath}: TransitionRejectionReason has unexpected values: {sorted(extra)}"
            )

    # Check TransitionRejected class and reason field
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return errors

    found_transition_rejected = False
    found_reason_field = False
    reason_correctly_typed = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TransitionRejected":
            found_transition_rejected = True
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name) and item.target.id == "reason":
                        found_reason_field = True
                        # Check if type annotation is exactly TransitionRejectionReason
                        if isinstance(item.annotation, ast.Name):
                            if item.annotation.id == "TransitionRejectionReason":
                                reason_correctly_typed = True
                            elif item.annotation.id in ("str", "object", "Any"):
                                errors.append(
                                    f"{filepath}:{item.lineno}: "
                                    f"TransitionRejected.reason is typed as '{item.annotation.id}' (too wide), "
                                    f"should be 'TransitionRejectionReason'"
                                )
                        # Also check for typing.String, Sequence, etc. (too wide)
                        elif isinstance(item.annotation, ast.Subscript):
                            if isinstance(item.annotation.value, ast.Name):
                                wide_types = ("String", "Sequence", "List", "Iterable", "Collection")
                                if item.annotation.value.id in wide_types:
                                    errors.append(
                                        f"{filepath}:{item.lineno}: "
                                        f"TransitionRejected.reason uses {item.annotation.value.id}[...] (too wide), "
                                        f"should be 'TransitionRejectionReason'"
                                    )

    # Require TransitionRejected class to exist
    if not found_transition_rejected:
        errors.append(
            f"{filepath}: TransitionRejected class is missing. "
            f"Expected a dataclass with reason field typed as TransitionRejectionReason."
        )

    # Require reason field to exist
    if found_transition_rejected and not found_reason_field:
        errors.append(
            f"{filepath}: TransitionRejected.reason field is missing. "
            f"Expected: reason: TransitionRejectionReason"
        )

    # Require reason field to be correctly typed
    if found_reason_field and not reason_correctly_typed:
        errors.append(
            f"{filepath}: TransitionRejected.reason must be annotated as "
            f"'TransitionRejectionReason', not 'str', 'object', or other widened types."
        )

    return errors


def check_reason_allowlist(filepath: str) -> list[str]:
    """Check that rejection reasons are from the allowlist (domain module only).

    Uses AST extraction to derive allowed reasons from TransitionRejectionReason alias.
    """
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {filepath}: {e}"]

    # Derive allowed reasons from the typed alias
    allowed_reasons = extract_transition_rejection_reasons(filepath)

    if not allowed_reasons:
        # Fallback to static allowlist if extraction fails
        allowed_reasons = set(ALLOWED_REJECTION_REASONS)

    # Look for reason assignments
    for lineno, line in enumerate(source.splitlines(), start=1):
        # Match patterns like: reason="..." or reason='...'
        if 'reason="' in line or "reason='" in line:
            # Extract the reason string
            match = re.search(r'reason=["\']([^"\']+)["\']', line)
            if match:
                reason = match.group(1)
                if reason not in allowed_reasons:
                    errors.append(
                        f"{filepath}:{lineno}: Unknown rejection reason '{reason}' "
                        f"(expected one of {sorted(allowed_reasons)})"
                    )

    return errors


# Allow list of exported names for backward compatibility
if __name__ == "__main__":
    sys.exit(0)
