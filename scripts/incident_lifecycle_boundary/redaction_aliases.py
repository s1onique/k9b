"""Alias declaration checks for evidence privacy-state types.

This module verifies that:
1. Variable names match expected names (alias_name == expected_name)
2. NewType first string argument matches expected name
"""

from __future__ import annotations

import ast


def extract_newtype_aliases(filepath: str) -> dict[str, str]:
    """Extract NewType alias definitions from a Python file.

    Returns:
        dict mapping alias name -> base type name
    """
    aliases: dict[str, str] = {}

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return aliases

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return aliases

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    if isinstance(node.value, ast.Call):
                        if isinstance(node.value.func, ast.Name):
                            if node.value.func.id == "NewType":
                                # NewType('Name', BaseType) - first arg is the type name
                                if len(node.value.args) >= 1:
                                    first_arg = node.value.args[0]
                                    if isinstance(first_arg, ast.Constant):
                                        type_name = str(first_arg.value)
                                        # Verify the type name matches the variable name
                                        if type_name != name:
                                            # Record with mismatch marker
                                            aliases[f"__MISMATCH__{name}"] = type_name
                                        else:
                                            # Extract base type
                                            if len(node.value.args) >= 2:
                                                base_type = node.value.args[1]
                                                if isinstance(base_type, ast.Name):
                                                    aliases[name] = base_type.id
                                                elif isinstance(base_type, ast.Constant):
                                                    aliases[name] = str(base_type.value)
                                                else:
                                                    aliases[name] = "<complex>"

    return aliases


def check_alias_declarations(filepath: str, expected_aliases: set[str]) -> list[str]:
    """Verify both variable name and NewType string argument match expected names.

    Rejects:
        LLMSafeEvidenceText = NewType("SomethingElse", RedactedEvidenceText)

    Args:
        filepath: Path to the Python file to check
        expected_aliases: Set of expected type alias names

    Returns:
        List of error messages (empty if all checks pass)
    """
    errors: list[str] = []
    aliases = extract_newtype_aliases(filepath)
    found_aliases = set(aliases.keys()) - {"__MISMATCH__"}

    # Check for mismatched NewType string argument
    for name, base_type in aliases.items():
        if name.startswith("__MISMATCH__"):
            actual_name = name[len("__MISMATCH__"):]
            expected_name = base_type  # In mismatch case, base_type holds the actual NewType string
            errors.append(
                f"{filepath}: NewType declares '{expected_name}' but variable is '{actual_name}'. "
                f"NewType first string argument must match variable name."
            )

    # Check for missing expected aliases
    for expected in expected_aliases:
        if expected not in found_aliases:
            errors.append(
                f"{filepath}: Missing expected NewType alias '{expected}'. "
                f"Expected NewType('{expected}', <base_type>)."
            )


    return errors


def check_type_hierarchy(filepath: str, expected_hierarchy: dict[str, str]) -> list[str]:
    """Verify the type hierarchy is correct.

    Args:
        filepath: Path to the Python file to check
        expected_hierarchy: dict mapping alias name -> expected base type name

    Returns:
        List of error messages (empty if all checks pass)
    """
    errors: list[str] = []
    aliases = extract_newtype_aliases(filepath)

    for alias_name, expected_base in expected_hierarchy.items():
        if alias_name.startswith("__MISMATCH__"):
            continue  # Already reported in check_alias_declarations

        if alias_name in aliases:
            actual_base = aliases[alias_name]
            if actual_base != expected_base:
                errors.append(
                    f"{filepath}: NewType '{alias_name}' has base type '{actual_base}', "
                    f"expected '{expected_base}' for correct privacy-state hierarchy."
                )

    return errors
