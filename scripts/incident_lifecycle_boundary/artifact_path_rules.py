"""Validation rules for artifact path verification.

This module contains:
- check_artifact_path_aliases(): Verify required NewType aliases exist
- check_artifact_path_constructors(): Verify required constructor functions exist
- check_storage_ref_field_type(): Verify EvidenceArtifact.storage_ref field type
- check_storage_ref_serialization(): Verify to_dict() serializes storage_ref correctly
- check_unsafe_literal_constructor_calls(): Detect suspicious constructor calls
- _get_annotation_name(): Helper to extract type annotation name
- _is_valid_storage_ref_union(): Helper to validate storage ref union type
- _is_str_self_storage_ref(): Helper to check str(self.storage_ref) pattern
- _is_direct_self_storage_ref(): Helper to check self.storage_ref pattern
"""

from __future__ import annotations

import ast

from .artifact_path_constants import (
    PATH_ALIASES,
    REQUIRED_CONSTRUCTORS,
    UNSAFE_CONSTRUCTOR_PATTERNS,
    VALID_STORAGE_REF_TYPES,
)
from .artifact_path_scan import (
    extract_constructor_functions,
    extract_path_newtype_aliases,
)


def _get_annotation_name(node: ast.AST) -> str | None:
    """Extract the name from a type annotation node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_valid_storage_ref_union(node: ast.AST) -> bool:
    """Check if node is a Union or | operator with valid storage ref types."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # Recursively check both sides of the | operator
        left_valid = _is_valid_storage_ref_union(node.left)
        right_valid = _is_valid_storage_ref_union(node.right)
        return left_valid and right_valid

    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Name) and node.value.id == "Union":
            # Check union members
            if isinstance(node.slice, ast.Tuple):
                for elt in node.slice.elts:
                    name = _get_annotation_name(elt)
                    if name not in VALID_STORAGE_REF_TYPES:
                        return False
                return True

    # Check if this is a direct name in valid_types
    name = _get_annotation_name(node)
    return name in VALID_STORAGE_REF_TYPES


def _is_str_self_storage_ref(value: ast.AST) -> bool:
    """Check if value is str(self.storage_ref)."""
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "str"
        and len(value.args) == 1
        and isinstance(value.args[0], ast.Attribute)
        and value.args[0].attr == "storage_ref"
        and isinstance(value.args[0].value, ast.Name)
        and value.args[0].value.id == "self"
    )


def _is_direct_self_storage_ref(value: ast.AST) -> bool:
    """Check if value is self.storage_ref (without str())."""
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "storage_ref"
        and isinstance(value.value, ast.Name)
        and value.value.id == "self"
    )


def check_artifact_path_aliases(filepath: str) -> list[str]:
    """Check that required NewType aliases exist for artifact paths/references.

    Verifies:
    - All PATH_ALIASES exist
    - All aliases are based on str
    """
    errors: list[str] = []

    aliases = extract_path_newtype_aliases(filepath)

    for expected_alias in PATH_ALIASES:
        if expected_alias not in aliases:
            errors.append(
                f"{filepath}: Missing NewType alias '{expected_alias}'. "
                f"Expected NewType('{expected_alias}', str)."
            )
        elif aliases[expected_alias] != "str":
            errors.append(
                f"{filepath}: NewType alias '{expected_alias}' is based on "
                f"'{aliases[expected_alias]}', expected 'str'."
            )

    return errors


def check_artifact_path_constructors(filepath: str) -> list[str]:
    """Check that required constructor functions exist.

    Verifies:
    - All REQUIRED_CONSTRUCTORS are defined
    """
    errors: list[str] = []

    constructors = extract_constructor_functions(filepath)

    for expected_constructor in REQUIRED_CONSTRUCTORS:
        if expected_constructor not in constructors:
            errors.append(
                f"{filepath}: Missing constructor function '{expected_constructor}'."
            )

    return errors


def check_storage_ref_field_type(filepath: str) -> list[str]:
    """Check that EvidenceArtifact.storage_ref is typed as ArtifactStorageRef.

    This check verifies that:
    - EvidenceArtifact class has storage_ref field
    - storage_ref is typed as ArtifactStorageRef (union of branded path types)
    - storage_ref is NOT typed as raw str, Any, object, int, or missing

    The field annotation must be ArtifactStorageRef to enforce branded type usage
    at the evidence boundary.
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

    # Find EvidenceArtifact class definition
    evidence_artifact_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "EvidenceArtifact":
            evidence_artifact_node = node
            break

    if evidence_artifact_node is None:
        return errors  # Not an evidence module, skip

    # Check storage_ref field annotation
    storage_ref_ann_node = None

    for item in evidence_artifact_node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            if item.target.id == "storage_ref":
                storage_ref_ann_node = item.annotation
                break

    if storage_ref_ann_node is None:
        errors.append(
            f"{filepath}: EvidenceArtifact.storage_ref is missing type annotation. "
            f"Expected: storage_ref: ArtifactStorageRef"
        )
        return errors

    # Check the annotation type
    # ArtifactStorageRef = SafeRelativeArtifactPath | LocalArtifactPath | ExternalStorageRef
    # Acceptable forms: "ArtifactStorageRef", Union[X, Y, Z], | operator

    annotation_name = _get_annotation_name(storage_ref_ann_node)

    if annotation_name is None:
        # Could be Union[...] or | operator - check for union pattern
        if not _is_valid_storage_ref_union(storage_ref_ann_node):
            errors.append(
                f"{filepath}: EvidenceArtifact.storage_ref has invalid type annotation. "
                f"Expected: ArtifactStorageRef (union of SafeRelativeArtifactPath | "
                f"LocalArtifactPath | ExternalStorageRef)"
            )
    elif annotation_name in ("str", "Any", "object", "int", "float", "bytes"):
        errors.append(
            f"{filepath}: EvidenceArtifact.storage_ref is typed as '{annotation_name}'. "
            f"Must be: ArtifactStorageRef (union of SafeRelativeArtifactPath | "
            f"LocalArtifactPath | ExternalStorageRef)"
        )
    elif annotation_name != "ArtifactStorageRef":
        errors.append(
            f"{filepath}: EvidenceArtifact.storage_ref is typed as '{annotation_name}'. "
            f"Must be: ArtifactStorageRef"
        )

    return errors


def check_storage_ref_serialization(filepath: str) -> list[str]:
    """Check that to_dict() serializes storage_ref correctly.

    Verifies:
    - storage_ref is emitted as str(self.storage_ref) for branded types
    - Direct self.storage_ref is flagged when field is typed as ArtifactStorageRef
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

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.name == "EvidenceArtifact":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "to_dict":
                        # Check storage_ref serialization in dict literal
                        for stmt in ast.walk(item):
                            if isinstance(stmt, ast.Dict):
                                for key, value in zip(stmt.keys, stmt.values):
                                    if isinstance(key, ast.Constant) and key.value == "storage_ref":
                                        if _is_direct_self_storage_ref(value):
                                            errors.append(
                                                f"{filepath}: EvidenceArtifact.to_dict() returns "
                                                f"{{'storage_ref': self.storage_ref}} directly. "
                                                f"Must be: {{'storage_ref': str(self.storage_ref)}}"
                                            )
                                        elif _is_str_self_storage_ref(value):
                                            # Valid: str(self.storage_ref)
                                            pass

    return errors


def check_unsafe_literal_constructor_calls(filepath: str) -> list[str]:
    """Detect suspicious constructor calls with obvious unsafe string literals.

    Checks for patterns like:
    - make_safe_relative_artifact_path("/absolute/path")
    - make_safe_relative_artifact_path("../secret")
    - make_safe_relative_artifact_path("s3://bucket/key")

    Args:
        filepath: Path to the file to check

    Returns:
        List of error messages for suspicious calls
    """
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [f"Cannot read {filepath}: {e}"]

    for pattern, description in UNSAFE_CONSTRUCTOR_PATTERNS:
        matches = pattern.findall(source)
        if matches:
            # Find line numbers for error reporting
            for i, line in enumerate(source.splitlines(), 1):
                if pattern.search(line):
                    errors.append(
                        f"{filepath}:{i}: Suspicious pattern: {description} detected in source."
                    )

    return errors


__all__ = [
    "check_artifact_path_aliases",
    "check_artifact_path_constructors",
    "check_storage_ref_field_type",
    "check_storage_ref_serialization",
    "check_unsafe_literal_constructor_calls",
]
