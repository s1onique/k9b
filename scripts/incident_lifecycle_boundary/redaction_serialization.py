"""Serialization checks for evidence privacy-state types.

This module verifies that dataclass serializers explicitly convert branded text to str
using the correct pattern: "summary": str(self.summary)

R7 #5: Requires exact pattern matching via AST to reject:
- Missing summary field entirely
- self.summary without str() conversion
- str(other_value) instead of str(self.summary)
- str(self.summary) after the return statement
"""

from __future__ import annotations

import ast


def extract_class_methods(filepath: str) -> dict[str, dict[str, list[str]]]:
    """Extract class methods from a Python file.

    Returns:
        dict mapping class name -> dict mapping method name -> list of source lines
    """
    class_methods: dict[str, dict[str, list[str]]] = {}

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return class_methods

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return class_methods

    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name
            class_methods[class_name] = {}
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    method_name = item.name
                    # Extract method source lines
                    if item.lineno <= len(lines):
                        method_lines = lines[item.lineno - 1 : item.end_lineno or item.lineno]
                        class_methods[class_name][method_name] = method_lines

    return class_methods


def check_serializer_explicit_conversion(filepath: str, class_name: str = "RedactedEvidenceSummary") -> list[str]:
    """Check that dataclass serializers explicitly convert branded text to str.

    R7 #5: Uses AST parsing to require EXACTLY:
    "summary": str(self.summary)

    Rejects:
    - Missing summary field entirely
    - "summary": self.summary (no str() conversion)
    - "summary": str(other_value) (wrong source)
    - Any str(self.summary) after the return statement

    Args:
        filepath: Path to the Python file to check
        class_name: Name of the class containing the to_dict method

    Returns:
        List of error messages (empty if all checks pass)
    """
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return [f"Cannot read {filepath}"]

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return errors

    # Find the class and to_dict method
    to_dict_method: ast.FunctionDef | None = None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "to_dict":
                    to_dict_method = item
                    break

    if to_dict_method is None:
        errors.append(f"{filepath}: Missing to_dict() method in class '{class_name}'.")
        return errors

    return_nodes = [node for node in ast.walk(to_dict_method) if isinstance(node, ast.Return)]
    if not return_nodes:
        errors.append(f"{filepath}: to_dict() in class '{class_name}' must return a literal dict containing \"summary\": str(self.summary). No return statement found.")
        return errors

    for return_node in return_nodes:
        if not isinstance(return_node.value, ast.Dict):
            errors.append(f"{filepath}: to_dict() in class '{class_name}' must return a literal dict containing \"summary\": str(self.summary). Indirect variable returns are rejected.")
            continue

        summary_values = [value for key, value in zip(return_node.value.keys, return_node.value.values) if isinstance(key, ast.Constant) and key.value == "summary"]
        if not summary_values:
            errors.append(f"{filepath}: every to_dict() return in class '{class_name}' must include \"summary\": str(self.summary). Missing summary field.")
            continue
        if len(summary_values) != 1:
            errors.append(f"{filepath}: every to_dict() return in class '{class_name}' must include exactly one \"summary\": str(self.summary) field.")
            continue

        value = summary_values[0]
        exact = (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "str"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Attribute)
            and isinstance(value.args[0].value, ast.Name)
            and value.args[0].value.id == "self"
            and value.args[0].attr == "summary"
            and not value.keywords
        )
        if not exact:
            errors.append(f"{filepath}: every to_dict() return in class '{class_name}' must use \"summary\": str(self.summary). Bare self.summary or other expressions are unsafe.")

    return errors
