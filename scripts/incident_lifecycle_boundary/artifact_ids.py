"""Artifact ID type checks for the incident lifecycle boundary verifier.

This module verifies that evidence/artifact IDs crossing the incident boundary
are defined as branded NewType aliases and serialized correctly.

Context-aware scanning:
- Only flags artifact_id in evidence-specific contexts (EvidenceLink, EvidenceArtifact)
- Ignores generic ID fields (incident_id, candidate_id, etc.)

R2 Stricter enforcement:
- EvidenceArtifact.artifact_id must be typed as ArtifactId
- EvidenceLink.artifact_id must be typed as ArtifactId
- to_dict() must use str(self.artifact_id), not self.artifact_id directly
"""

from __future__ import annotations

import ast
import sys

# Contract constants for artifact ID aliases
ARTIFACT_ID_ALIASES = frozenset({
    "ArtifactId",
    "EvidenceLinkId",
    "SnapshotBundleId",
    "ReviewPacketId",
    "DiagnosisLoopPassId",
    "ExternalAnalysisArtifactId",
})

# Dataclass fields that MUST use ArtifactId specifically (R2: stricter check)
# Format: (class_name, field_name) -> allowed type names
ALLOWED_ARTIFACT_ID_FIELD_TYPES: dict[tuple[str, str], frozenset[str]] = {
    ("EvidenceArtifact", "artifact_id"): frozenset({"ArtifactId"}),
    ("EvidenceLink", "artifact_id"): frozenset({"ArtifactId"}),
}

# Classes that need serialization checks for artifact_id
CLASSES_WITH_ARTIFACT_ID_SERIALIZATION: frozenset[str] = frozenset({
    "EvidenceArtifact",
    "EvidenceLink",
})


def _is_newtype_alias(node: ast.Assign | ast.AnnAssign, source: str) -> tuple[bool, str | None]:
    """Check if assignment is a NewType alias based on str.

    Returns (is_newtype, base_type).
    """
    value = None
    if isinstance(node, ast.Assign):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            value = node.value
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name):
            value = node.value

    if value is None:
        return False, None

    # Check for NewType("Name", str) pattern
    if isinstance(value, ast.Call):
        if isinstance(value.func, ast.Name) and value.func.id == "NewType":
            if len(value.args) >= 2:
                # Check if second argument is "str"
                second_arg = value.args[1]
                if isinstance(second_arg, ast.Name) and second_arg.id == "str":
                    return True, "str"
                if isinstance(second_arg, ast.Constant) and second_arg.value == "str":
                    return True, "str"
    return False, None


def extract_newtype_aliases(filepath: str) -> dict[str, str]:
    """Extract NewType aliases from a Python file.

    Returns:
        Dict mapping alias name to base type (e.g., {"ArtifactId": "str"}).
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
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            is_newtype, base_type = _is_newtype_alias(node, source)
            if is_newtype:
                target_name = None
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    target_name = node.targets[0].id
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    target_name = node.target.id
                if target_name and base_type:
                    aliases[target_name] = base_type

    return aliases


def check_artifact_id_aliases(filepath: str) -> list[str]:
    """Check that required NewType aliases exist for artifact IDs.

    Verifies:
    - ArtifactId alias exists
    - Alias is based on str
    """
    errors: list[str] = []

    aliases = extract_newtype_aliases(filepath)

    for expected_alias in ARTIFACT_ID_ALIASES:
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


def check_artifact_id_field_types(filepath: str) -> list[str]:
    """Check that artifact ID fields use the exact required branded type.

    R2 stricter enforcement:
    - EvidenceArtifact.artifact_id must be ArtifactId
    - EvidenceLink.artifact_id must be ArtifactId
    - Rejects str, Any, object, int, CandidateId, or any other non-ArtifactId type
    - Fails if field is missing
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

    # First pass: collect all class field definitions
    class_fields: dict[tuple[str, str], tuple[str, int]] = {}  # (class, field) -> (type_name, lineno)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_name = item.target.id
                    # Get the type name
                    type_name = _get_annotation_name(item.annotation)
                    if type_name:
                        class_fields[(class_name, field_name)] = (type_name, item.lineno)

    # Second pass: check required fields exist and have correct types
    for (class_name, field_name), allowed_types in ALLOWED_ARTIFACT_ID_FIELD_TYPES.items():
        key = (class_name, field_name)
        if key not in class_fields:
            errors.append(
                f"{filepath}: Missing required field '{class_name}.{field_name}'. "
                f"Must be typed as one of: {', '.join(sorted(allowed_types))}."
            )
        else:
            actual_type, lineno = class_fields[key]
            if actual_type not in allowed_types:
                errors.append(
                    f"{filepath}:{lineno}: "
                    f"{class_name}.{field_name} is typed as '{actual_type}'. "
                    f"Must be: {', '.join(sorted(allowed_types))}."
                )

    return errors


def _get_annotation_name(annotation: ast.expr) -> str | None:
    """Extract the type name from an annotation node."""
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Subscript):
        # Handle Optional[X], List[X], etc. - extract base type
        return _get_annotation_name(annotation.value)
    if isinstance(annotation, ast.Constant):
        # Literal types
        return None
    return None


def check_artifact_id_serialization(filepath: str) -> list[str]:
    """Check that to_dict() uses str() for artifact_id serialization.

    R2 enforcement:
    - to_dict() must use str(self.artifact_id), not self.artifact_id directly
    - Direct attribute access like {"artifact_id": self.artifact_id} is an error
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
            class_name = node.name
            # Only check classes that have artifact_id fields
            if class_name not in CLASSES_WITH_ARTIFACT_ID_SERIALIZATION:
                continue

            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "to_dict":
                    # Check the body for artifact_id serialization
                    class_errors = _check_to_dict_artifact_id_serialization(
                        item, class_name, filepath
                    )
                    errors.extend(class_errors)

    return errors


def _check_to_dict_artifact_id_serialization(
    to_dict_node: ast.FunctionDef,
    class_name: str,
    filepath: str,
) -> list[str]:
    """Check a to_dict method for correct artifact_id serialization."""
    errors: list[str] = []

    for stmt in ast.walk(to_dict_node):
        if isinstance(stmt, ast.Dict):
            for key, value in zip(stmt.keys, stmt.values):
                if isinstance(key, ast.Constant) and key.value == "artifact_id":
                    # Found artifact_id in the dict
                    # Check if it's str(self.artifact_id) or self.artifact_id directly
                    if isinstance(value, ast.Call):
                        # str(self.artifact_id) - this is CORRECT
                        if isinstance(value.func, ast.Name) and value.func.id == "str":
                            # Check that the arg is self.artifact_id
                            if len(value.args) == 1:
                                arg = value.args[0]
                                if isinstance(arg, ast.Attribute) and arg.attr == "artifact_id":
                                    # This is correct: str(self.artifact_id)
                                    pass
                                else:
                                    # str() with something other than self.artifact_id
                                    errors.append(
                                        f"{filepath}:{to_dict_node.lineno}: "
                                        f"{class_name}.to_dict() calls str() with unexpected argument. "
                                        f"Expected str(self.artifact_id)."
                                    )
                        else:
                            # Some other function call
                            errors.append(
                                f"{filepath}:{to_dict_node.lineno}: "
                                f"{class_name}.to_dict() artifact_id uses '{value.func.id}()' instead of str(). "
                                f"Expected str(self.artifact_id)."
                            )
                    elif isinstance(value, ast.Attribute) and value.attr == "artifact_id":
                        # Direct self.artifact_id - this is WRONG
                        errors.append(
                            f"{filepath}:{to_dict_node.lineno}: "
                            f"{class_name}.to_dict() returns self.artifact_id directly. "
                            f"Must wrap with str(): str(self.artifact_id)."
                        )

    return errors


def check_artifact_id_contract(evidence_filepath: str) -> list[str]:
    """Run all artifact ID contract checks.

    R2 includes:
    - Required NewType aliases exist
    - Field types use exact branded aliases (ArtifactId)
    - Serialization uses str() wrapper (R2)
    """
    errors: list[str] = []

    # Check 1: Required NewType aliases exist
    alias_errors = check_artifact_id_aliases(evidence_filepath)
    errors.extend(alias_errors)

    # Check 2: Field types use EXACT branded aliases, not raw str or other types
    field_errors = check_artifact_id_field_types(evidence_filepath)
    errors.extend(field_errors)

    # Check 3: Serialization uses str() for branded IDs (R2)
    serialization_errors = check_artifact_id_serialization(evidence_filepath)
    errors.extend(serialization_errors)

    return errors


__all__ = [
    "ALLOWED_ARTIFACT_ID_FIELD_TYPES",
    "ARTIFACT_ID_ALIASES",
    "CLASSES_WITH_ARTIFACT_ID_SERIALIZATION",
    "check_artifact_id_aliases",
    "check_artifact_id_contract",
    "check_artifact_id_field_types",
    "check_artifact_id_serialization",
    "extract_newtype_aliases",
]


if __name__ == "__main__":
    # Direct execution shows available aliases
    print("Artifact ID aliases required:")
    for alias in sorted(ARTIFACT_ID_ALIASES):
        print(f"  - {alias}")
    print("\nDataclass fields with required types:")
    for (class_name, field_name), allowed_types in sorted(ALLOWED_ARTIFACT_ID_FIELD_TYPES.items()):
        print(f"  - {class_name}.{field_name}: {', '.join(sorted(allowed_types))}")
    sys.exit(0)
