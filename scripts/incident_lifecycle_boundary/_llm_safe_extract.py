"""AST extraction utilities for LLM-safe evidence boundary verifier."""

from __future__ import annotations

import ast


def extract_newtype_aliases(filepath: str) -> dict[str, str]:
    """Extract NewType aliases from a Python file.

    Returns:
        Dict mapping alias name to base type (e.g., {"RedactedEvidenceText": "str"}).
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

    for node in tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target_name = node.targets[0].id
                value = node.value
                if isinstance(value, ast.Call):
                    if isinstance(value.func, ast.Name) and value.func.id == "NewType":
                        if len(value.args) >= 2:
                            second_arg = value.args[1]
                            if isinstance(second_arg, ast.Name) and second_arg.id == "str":
                                aliases[target_name] = "str"
                            elif isinstance(second_arg, ast.Constant) and second_arg.value == "str":
                                aliases[target_name] = "str"

    return aliases


def extract_function_definitions(filepath: str) -> set[str]:
    """Extract function definitions from a Python file.

    Returns:
        Set of function names defined in the file.
    """
    functions: set[str] = set()

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return functions

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return functions

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.add(node.name)

    return functions


def extract_dataclass_names(filepath: str) -> set[str]:
    """Extract dataclass names from a Python file.

    Returns:
        Set of dataclass names defined in the file.
    """
    dataclasses: set[str] = set()

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return dataclasses

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return dataclasses

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            # Check if class is a dataclass
            # Handle both @dataclass and @dataclass(frozen=True, ...) forms
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "dataclass":
                    dataclasses.add(node.name)
                    break
                elif isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Name) and decorator.func.id == "dataclass":
                        dataclasses.add(node.name)
                        break

    return dataclasses


def _get_annotation_name(node: ast.AST) -> str | None:
    """Extract the name from a type annotation node.

    For union types (e.g., "LLMSafeArtifactRef | None"), returns only the leftmost
    member. Use extract_union_members() to get all members.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # Handle Union types (e.g., "LLMSafeArtifactRef | None")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # Get the left side name
        return _get_annotation_name(node.left)
    return None


def extract_union_members(node: ast.AST) -> list[str]:
    """Extract all members from a union type annotation recursively.

    For "LLMSafeArtifactRef | ReviewPacketStorageRef | None", returns:
    ["LLMSafeArtifactRef", "ReviewPacketStorageRef", "None"]

    Args:
        node: AST node representing a type annotation

    Returns:
        List of type names in the union (including None for NoneType)
    """
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Constant):
        # Handle None as NoneType
        if node.value is None:
            return ["None"]
        return []
    # Handle Union types (e.g., "LLMSafeArtifactRef | None")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left_members = extract_union_members(node.left)
        right_members = extract_union_members(node.right)
        return left_members + right_members
    return []


__all__ = [
    "extract_dataclass_names",
    "extract_function_definitions",
    "extract_newtype_aliases",
    "extract_union_members",
]
