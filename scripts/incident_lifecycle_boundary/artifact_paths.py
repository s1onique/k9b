"""Artifact path/reference type checks for the incident lifecycle boundary verifier.

This module verifies that artifact path/reference types crossing the incident boundary
are defined as branded NewType aliases and serialized correctly.

Design:
- SafeRelativeArtifactPath: relative paths safe for review/LLM boundaries
- LocalArtifactPath: local filesystem paths (implementation only)
- ExternalStorageRef: external storage references (s3://, gs://, etc.)
- ReviewPacketStorageRef: storage refs for review packet boundaries
- LLMSafeArtifactRef: artifact refs safe for LLM-facing outputs

Invariant:
- SafeRelativeArtifactPath is the only path-like value allowed in review-packet / LLM-safe artifact references.
- LocalArtifactPath is only used for filesystem read/write implementation details.
- ExternalStorageRef is only used for external object/storage references.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from .ast_imports import iter_import_aliases, resolve_import_source

# Contract constants for path/reference aliases
PATH_ALIASES = frozenset({
    "SafeRelativeArtifactPath",
    "LocalArtifactPath",
    "ExternalStorageRef",
    "ReviewPacketStorageRef",
    "LLMSafeArtifactRef",
})

# Required constructor functions
REQUIRED_CONSTRUCTORS = frozenset({
    "make_safe_relative_artifact_path",
    "make_local_artifact_path",
    "make_external_storage_ref",
    "make_review_packet_storage_ref",
    "make_llm_safe_artifact_ref",
})

# Patterns that indicate unsafe constructor usage
UNSAFE_CONSTRUCTOR_PATTERNS = [
    # make_safe_relative_artifact_path with absolute path
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]\/"), "absolute path"),
    # make_safe_relative_artifact_path with traversal
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]\.\."), "traversal path"),
    # make_safe_relative_artifact_path with URL scheme
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]s3:\/\/"), "URL scheme (s3://)"),
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]gs:\/\/"), "URL scheme (gs://)"),
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]https?:\/\/"), "URL scheme (https://)"),
    # make_safe_relative_artifact_path with home directory
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]~"), "home directory (~)"),
    # LLMSafeArtifactRef from LocalArtifactPath (should not happen)
    (re.compile(r"LLMSafeArtifactRef\s*\(\s*str\s*\(\s*\w*local\w*path"), "LocalArtifactPath to LLMSafeArtifactRef"),
]


def _extract_aliases_from_file(filepath: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Extract NewType aliases and import info from a single file.

    Returns:
        Tuple of (aliases, import_sources, imported_names):
        - aliases: local_name -> base_type
        - import_sources: local_name -> module_path
        - imported_names: local_name -> original_name
    """
    aliases: dict[str, str] = {}
    import_sources: dict[str, str] = {}
    imported_names: dict[str, str] = {}

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return aliases, import_sources, imported_names

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return aliases, import_sources, imported_names

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            resolved = resolve_import_source(node, filepath)
            if resolved:
                for local_name, original_name in iter_import_aliases(node).items():
                    import_sources[local_name] = resolved
                    imported_names[local_name] = original_name

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

    return aliases, import_sources, imported_names


def extract_path_newtype_aliases(
    filepath: str,
    _visited: set[str] | None = None,
    _cache: dict[str, dict[str, str]] | None = None,
) -> dict[str, str]:
    """Extract path/reference NewType aliases from a Python file.

    Recursively follows imports to find definitions in imported modules.
    Uses memoization to avoid re-parsing files.
    Uses separate visited set to prevent infinite recursion on cycles.

    Returns:
        Dict mapping alias name to base type (e.g., {"SafeRelativeArtifactPath": "str"}).
    """
    if _visited is None:
        _visited = set()
    if _cache is None:
        _cache = {}

    real_path = str(Path(filepath).resolve())

    # Return cached result if available
    if real_path in _cache:
        return _cache[real_path]

    # Cycle detection - return empty if already being processed
    if real_path in _visited:
        return {}

    # Mark as being processed (for cycle detection)
    _visited.add(real_path)

    # Extract from this file
    aliases, import_sources, imported_names = _extract_aliases_from_file(filepath)

    # Recursively follow imports for names not found at top level
    for local_name, module_path in import_sources.items():
        if local_name not in aliases:
            # Recursive call - it will use visited set for cycle detection
            # and share the cache for memoization
            mod_aliases = extract_path_newtype_aliases(module_path, _visited, _cache)
            original = imported_names.get(local_name, local_name)
            if original in mod_aliases:
                aliases[local_name] = mod_aliases[original]

    # Cache the completed result.
    _cache[real_path] = aliases

    # Remove from visited set - allow re-entry from different paths
    _visited.discard(real_path)

    return aliases


def _extract_constructors_from_file(filepath: str) -> tuple[set[str], dict[str, str], dict[str, str]]:
    """Extract constructor functions and import info from a single file.

    Returns:
        Tuple of (constructors, import_sources, imported_names):
        - constructors: set of function names
        - import_sources: local_name -> module_path
        - imported_names: local_name -> original_name
    """
    constructors: set[str] = set()
    import_sources: dict[str, str] = {}
    imported_names: dict[str, str] = {}

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return constructors, import_sources, imported_names

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return constructors, import_sources, imported_names

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            resolved = resolve_import_source(node, filepath)
            if resolved:
                for local_name, original_name in iter_import_aliases(node).items():
                    import_sources[local_name] = resolved
                    imported_names[local_name] = original_name

        if isinstance(node, ast.FunctionDef):
            constructors.add(node.name)

    return constructors, import_sources, imported_names


def extract_constructor_functions(
    filepath: str,
    _visited: set[str] | None = None,
    _cache: dict[str, set[str]] | None = None,
) -> set[str]:
    """Extract function definitions that are constructors from a Python file.

    Recursively follows imports to find definitions in imported modules.
    Uses memoization to avoid re-parsing files.
    Uses separate visited set to prevent infinite recursion on cycles.

    Returns:
        Set of function names that are defined in the file.
    """
    if _visited is None:
        _visited = set()
    if _cache is None:
        _cache = {}

    real_path = str(Path(filepath).resolve())

    # Return cached result if available
    if real_path in _cache:
        return _cache[real_path]

    # Cycle detection - return empty if already being processed
    if real_path in _visited:
        return set()

    # Mark as being processed (for cycle detection)
    _visited.add(real_path)

    # Extract from this file
    constructors, import_sources, imported_names = _extract_constructors_from_file(filepath)

    # Recursively follow imports for names not found at top level
    for local_name, module_path in import_sources.items():
        if local_name not in constructors:
            # Recursive call - it will use visited set for cycle detection
            # and share the cache for memoization
            mod_constructors = extract_constructor_functions(module_path, _visited, _cache)
            original = imported_names.get(local_name, local_name)
            if original in mod_constructors:
                constructors.add(local_name)

    # Cache the completed result.
    _cache[real_path] = constructors

    # Remove from visited set - allow re-entry from different paths
    _visited.discard(real_path)

    return constructors


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


def _get_annotation_name(node: ast.AST) -> str | None:
    """Extract the name from a type annotation node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_valid_storage_ref_union(node: ast.AST) -> bool:
    """Check if node is a Union or | operator with valid storage ref types."""
    valid_types = {"SafeRelativeArtifactPath", "LocalArtifactPath", "ExternalStorageRef"}

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
                    if name not in valid_types:
                        return False
                return True

    # Check if this is a direct name in valid_types
    name = _get_annotation_name(node)
    return name in valid_types


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


def check_llm_review_path_boundaries(repo_root: Path) -> list[str]:
    """Scan for violations of LLM/review path boundary rules.

    Checks:
    - No LocalArtifactPath in review/LLM modules
    - No direct safe_relative_artifact_path with unsafe string literals
    - No LocalArtifactPath converted to LLMSafeArtifactRef

    Args:
        repo_root: Root directory of the repository (can be actual repo or fake for testing)

    Returns:
        List of error messages for violations found
    """
    errors: list[str] = []

    # Modules that should NOT expose LocalArtifactPath
    LLM_REVIEW_MODULES = [
        "src/k8s_diag_agent/collect/incident_review_packet.py",
        "src/k8s_diag_agent/collect/incident_case_file.py",
        "src/k8s_diag_agent/collect/incident_llm_diagnosis.py",
    ]

    for module_path in LLM_REVIEW_MODULES:
        # Check within repo_root directly (works for both real repo and fake test repos)
        full_path = repo_root / module_path
        if not full_path.exists():
            continue

        try:
            with open(full_path, encoding="utf-8") as f:
                source = f.read()
        except OSError:
            continue

        # Check for LocalArtifactPath usage in LLM/review modules
        if "LocalArtifactPath" in source:
            errors.append(
                f"{module_path}: LocalArtifactPath used in LLM/review module. "
                f"Use SafeRelativeArtifactPath or ReviewPacketStorageRef instead."
            )

        # Check for unsafe constructor patterns
        for pattern, description in UNSAFE_CONSTRUCTOR_PATTERNS:
            if pattern.search(source):
                errors.append(
                    f"{module_path}: Detected unsafe pattern: {description} in constructor call."
                )

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


def check_artifact_path_contract(evidence_filepath: str, repo_root: Path) -> list[str]:
    """Run all artifact path/reference contract checks.

    Args:
        evidence_filepath: Path to incident_evidence.py
        repo_root: Root directory of the repository

    Returns:
        List of error messages (empty if all checks pass)
    """
    errors: list[str] = []

    # Check 1: Required NewType aliases exist
    alias_errors = check_artifact_path_aliases(evidence_filepath)
    errors.extend(alias_errors)

    # Check 2: Required constructor functions exist
    constructor_errors = check_artifact_path_constructors(evidence_filepath)
    errors.extend(constructor_errors)

    # Check 3: Check for unsafe literal constructor calls in evidence module
    unsafe_errors = check_unsafe_literal_constructor_calls(evidence_filepath)
    errors.extend(unsafe_errors)

    # Check 4: LLM/review boundary violations
    boundary_errors = check_llm_review_path_boundaries(repo_root)
    errors.extend(boundary_errors)

    # Check 5: EvidenceArtifact storage_ref field type usage
    storage_ref_errors = check_storage_ref_field_type(evidence_filepath)
    errors.extend(storage_ref_errors)

    # Check 6: EvidenceArtifact storage_ref serialization
    serialization_errors = check_storage_ref_serialization(evidence_filepath)
    errors.extend(serialization_errors)

    return errors


__all__ = [
    "PATH_ALIASES",
    "REQUIRED_CONSTRUCTORS",
    "check_artifact_path_aliases",
    "check_artifact_path_contract",
    "check_artifact_path_constructors",
    "check_llm_review_path_boundaries",
    "check_storage_ref_field_type",
    "check_storage_ref_serialization",
    "check_unsafe_literal_constructor_calls",
    "extract_constructor_functions",
    "extract_path_newtype_aliases",
]


if __name__ == "__main__":
    # Direct execution shows available aliases
    print("Artifact path/reference aliases required:")
    for alias in sorted(PATH_ALIASES):
        print(f"  - {alias}")
    print("\nRequired constructors:")
    for constructor in sorted(REQUIRED_CONSTRUCTORS):
        print(f"  - {constructor}()")
    sys.exit(0)
