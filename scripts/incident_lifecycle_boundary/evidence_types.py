"""Evidence type alias checks for the incident lifecycle boundary verifier.

This module verifies that evidence role/kind values crossing the incident
boundary are defined as closed typed aliases.

Context-aware scanning:
- Only flags role/kind in evidence-specific contexts (EvidenceLink, EvidenceArtifact, dicts with evidence keys)
- Ignores LLM/chat roles (system, user) and Kubernetes object kinds (Pod, etc.)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Alias names as they appear in the evidence module
EVIDENCE_ROLE_ALIAS = "EvidenceRoleCode"
EVIDENCE_KIND_ALIAS = "EvidenceKindCode"

# Stable public contract for evidence roles (derived from EvidenceRole enum)
EXPECTED_EVIDENCE_ROLES: frozenset[str] = frozenset({
    "primary",
    "supporting",
    "snapshot",
    "review_packet",
    "debug",
})

# Stable public contract for evidence kinds (derived from EvidenceKind enum)
EXPECTED_EVIDENCE_KINDS: frozenset[str] = frozenset({
    "snapshot_bundle",
    "review_packet",
    "log_excerpt",
    "metric_window",
    "trace",
    "run_summary",
    "external_analysis",
})


# Evidence-adjacent dict keys that indicate this is an evidence payload
EVIDENCE_DICT_KEYS: frozenset[str] = frozenset({
    "artifact_id",
    "evidence_id",
    "incident_id",
    "storage_ref",
    "content_hash",
    "collected_by",
    "redaction_status",
    "evidence_links",
    "evidence_artifacts",
    "evidence_role",
    "evidence_kind",
})

# Known evidence module paths (relative to src/)
EVIDENCE_MODULE_PATTERNS: frozenset[str] = frozenset({
    "k8s_diag_agent/collect/incident_evidence.py",
    "k8s_diag_agent/collect/incident_bundle_promotion.py",
    "k8s_diag_agent/collect/incident_review_packet.py",
    "k8s_diag_agent/collect/incident_store.py",
    "k8s_diag_agent/collect/incident_store_sqlite.py",
})


def _is_literal_subscript(node: ast.Subscript) -> bool:
    """Check if subscript is Literal[...] or typing.Literal[...], not another type."""
    if isinstance(node.value, ast.Name):
        return node.value.id == "Literal"
    if isinstance(node.value, ast.Attribute):
        return node.value.attr == "Literal"
    return False


def _extract_literal_string_args(node: ast.expr) -> set[str]:
    """Extract string literal arguments from a Literal[...] subscript."""
    reasons: set[str] = set()

    if isinstance(node, ast.Subscript):
        if not _is_literal_subscript(node):
            return reasons

        slice_node = node.slice

        if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
            reasons.add(slice_node.value)
        elif isinstance(slice_node, ast.Tuple):
            for elt in slice_node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    reasons.add(elt.value)

    return reasons


def extract_evidence_role_values(filepath: str) -> set[str]:
    """Extract evidence role values from EvidenceRoleCode alias using AST.

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

        # Simple assignment: EvidenceRoleCode = Literal[...]
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id == EVIDENCE_ROLE_ALIAS:
                    target_name = node.targets[0].id
                    value = node.value

        # Annotated assignment: EvidenceRoleCode: TypeAlias = Literal[...]
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                if node.target.id == EVIDENCE_ROLE_ALIAS:
                    target_name = node.target.id
                    value = node.value

        if target_name == EVIDENCE_ROLE_ALIAS and value is not None:
            return _extract_literal_string_args(value)

    return set()


def extract_evidence_kind_values(filepath: str) -> set[str]:
    """Extract evidence kind values from EvidenceKindCode alias using AST.

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

        # Simple assignment: EvidenceKindCode = Literal[...]
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id == EVIDENCE_KIND_ALIAS:
                    target_name = node.targets[0].id
                    value = node.value

        # Annotated assignment: EvidenceKindCode: TypeAlias = Literal[...]
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                if node.target.id == EVIDENCE_KIND_ALIAS:
                    target_name = node.target.id
                    value = node.value

        if target_name == EVIDENCE_KIND_ALIAS and value is not None:
            return _extract_literal_string_args(value)

    return set()


def check_evidence_type_aliases(filepath: str) -> list[str]:
    """Check that EvidenceRoleCode and EvidenceKindCode aliases exist and are properly typed.

    Verifies:
    - EvidenceRoleCode alias exists and contains values
    - EvidenceKindCode alias exists and contains values
    - Alias values match the expected stable public contract
    """
    errors: list[str] = []

    # Extract role values
    extracted_roles = extract_evidence_role_values(filepath)

    if not extracted_roles:
        errors.append(
            f"{filepath}: EvidenceRoleCode alias missing or empty. "
            f"Expected a Literal[...] with evidence role codes."
        )
    else:
        # Check against expected contract
        if extracted_roles != EXPECTED_EVIDENCE_ROLES:
            missing = EXPECTED_EVIDENCE_ROLES - extracted_roles
            extra = extracted_roles - EXPECTED_EVIDENCE_ROLES
            if missing:
                errors.append(
                    f"{filepath}: EvidenceRoleCode missing expected values: {sorted(missing)}"
                )
            if extra:
                errors.append(
                    f"{filepath}: EvidenceRoleCode has unexpected values: {sorted(extra)}"
                )

    # Extract kind values
    extracted_kinds = extract_evidence_kind_values(filepath)

    if not extracted_kinds:
        errors.append(
            f"{filepath}: EvidenceKindCode alias missing or empty. "
            f"Expected a Literal[...] with evidence kind codes."
        )
    else:
        # Check against expected contract
        if extracted_kinds != EXPECTED_EVIDENCE_KINDS:
            missing = EXPECTED_EVIDENCE_KINDS - extracted_kinds
            extra = extracted_kinds - EXPECTED_EVIDENCE_KINDS
            if missing:
                errors.append(
                    f"{filepath}: EvidenceKindCode missing expected values: {sorted(missing)}"
                )
            if extra:
                errors.append(
                    f"{filepath}: EvidenceKindCode has unexpected values: {sorted(extra)}"
                )

    return errors


def check_evidence_dataclass_field_types(filepath: str) -> list[str]:
    """Check that evidence dataclass fields use typed aliases, not widened types.

    Verifies EvidenceLink.role and EvidenceArtifact.kind are NOT typed as:
    - str
    - Any
    - object
    - Sequence, list, etc.
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

    # Track dataclass field pairs that should use typed aliases
    # Format: (class_name, field_name)
    dataclass_field_checks: set[tuple[str, str]] = {
        ("EvidenceLink", "role"),
        ("EvidenceArtifact", "kind"),
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name):
                        field_name = item.target.id
                        # Check if this is one of the fields we're monitoring
                        if (node.name, field_name) in dataclass_field_checks:
                            # Check for widened types
                            if isinstance(item.annotation, ast.Name):
                                wide_types = ("str", "object", "Any")
                                if item.annotation.id in wide_types:
                                    errors.append(
                                        f"{filepath}:{item.lineno}: "
                                        f"{node.name}.{field_name} is typed as '{item.annotation.id}' (too wide), "
                                        f"should be typed alias or enum"
                                    )

                            # Check for Sequence, List, etc.
                            elif isinstance(item.annotation, ast.Subscript):
                                if isinstance(item.annotation.value, ast.Name):
                                    wide_types = ("Sequence", "List", "Iterable", "Collection")
                                    if item.annotation.value.id in wide_types:
                                        errors.append(
                                            f"{filepath}:{item.lineno}: "
                                            f"{node.name}.{field_name} uses {item.annotation.value.id}[...] (too wide), "
                                            f"should be typed alias or enum"
                                        )

    return errors


def _is_evidence_context(filepath: Path, src_root: Path) -> bool:
    """Check if filepath is in an evidence-specific module."""
    try:
        rel_path = filepath.relative_to(src_root)
        return str(rel_path) in EVIDENCE_MODULE_PATTERNS
    except ValueError:
        return False


def _has_evidence_dict_keys(node: ast.Dict) -> bool:
    """Check if dict has evidence-adjacent keys."""
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            if key.value in EVIDENCE_DICT_KEYS:
                return True
    return False


def _is_evidence_constructor(node: ast.Call) -> bool:
    """Check if call is EvidenceLink(...) or EvidenceArtifact(...)."""
    if isinstance(node.func, ast.Name):
        return node.func.id in ("EvidenceLink", "EvidenceArtifact")
    if isinstance(node.func, ast.Attribute):
        return node.func.attr in ("EvidenceLink", "EvidenceArtifact")
    return False


def _check_dict_literal_context_aware(
    node: ast.Dict,
    filepath: Path,
    src_root: Path,
    allowed_roles: frozenset[str],
    allowed_kinds: frozenset[str],
) -> list[str]:
    """Check a dict literal only if it's in an evidence context.

    Context-aware checks:
    - Inside EvidenceLink(...) or EvidenceArtifact(...) calls
    - Dict has evidence-adjacent keys (artifact_id, storage_ref, etc.)
    - In known evidence modules
    """
    errors: list[str] = []

    # Check if dict has evidence-adjacent keys
    has_evidence_keys = _has_evidence_dict_keys(node)

    # If not in evidence context, skip
    if not has_evidence_keys and not _is_evidence_context(filepath, src_root):
        return errors

    for key, value in zip(node.keys, node.values):
        # Check for string keys "role" or "kind"
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            if key.value in ("role", "kind"):
                # Check if value is a string constant
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    str_value = value.value
                    # Skip enum member access patterns like EvidenceRole.SNAPSHOT.value
                    if "." in str_value:
                        continue
                    # Check against allowed values
                    if key.value == "role" and str_value not in allowed_roles:
                        errors.append(
                            f"{filepath}:{key.lineno}: "
                            f"Unknown evidence role literal '{str_value}' "
                            f"(expected one of {sorted(allowed_roles)})"
                        )
                    elif key.value == "kind" and str_value not in allowed_kinds:
                        errors.append(
                            f"{filepath}:{key.lineno}: "
                            f"Unknown evidence kind literal '{str_value}' "
                            f"(expected one of {sorted(allowed_kinds)})"
                        )
    return errors


def _check_call_context_aware(
    node: ast.Call,
    filepath: Path,
    src_root: Path,
    allowed_roles: frozenset[str],
    allowed_kinds: frozenset[str],
) -> list[str]:
    """Check EvidenceLink/EvidenceArtifact calls for unknown role/kind values."""
    errors: list[str] = []

    if not _is_evidence_constructor(node):
        return errors

    for keyword in node.keywords:
        if keyword.arg in ("role", "kind"):
            # Check if value is a string constant
            if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                str_value = keyword.value.value
                # Skip enum member access like EvidenceRole.SNAPSHOT
                if "." in str_value:
                    continue
                # Check against allowed values
                if keyword.arg == "role" and str_value not in allowed_roles:
                    errors.append(
                        f"{filepath}:{keyword.value.lineno}: "
                        f"Unknown evidence role literal '{str_value}' "
                        f"(expected one of {sorted(allowed_roles)})"
                    )
                elif keyword.arg == "kind" and str_value not in allowed_kinds:
                    errors.append(
                        f"{filepath}:{keyword.value.lineno}: "
                        f"Unknown evidence kind literal '{str_value}' "
                        f"(expected one of {sorted(allowed_kinds)})"
                    )
    return errors


def _iter_production_python_files(repo_root: Path) -> list[Path]:
    """Iterate over production Python files in a directory, excluding tests and venvs."""
    return [
        path
        for path in repo_root.rglob("*.py")
        if "__pycache__" not in path.parts
        and ".venv" not in path.parts
        and "tests" not in path.parts
        and "scripts" not in path.parts
    ]


def check_evidence_literal_usage(
    evidence_filepath: str,
    repo_root: Path,
    allowed_roles: frozenset[str],
    allowed_kinds: frozenset[str],
) -> list[str]:
    """Scan evidence-specific contexts for unknown role/kind literals.

    Context-aware scanning:
    - Checks EvidenceLink(...), EvidenceArtifact(...) constructor calls
    - Checks dicts with evidence-adjacent keys (artifact_id, storage_ref, etc.)
    - Only scans known evidence modules OR dicts with evidence keys

    Ignores:
    - LLM/chat roles (system, user) without evidence context
    - Kubernetes object kinds (Pod, etc.) without evidence context
    - Generic role/kind fields without evidence context
    """
    errors: list[str] = []

    import re

    # Pattern: role="value" or role='value' (but not EvidenceRole.X)
    # Only used for constructor calls, not general scanning
    role_pattern = re.compile(r'\brole\s*=\s*["\']([^"\']+)["\']')
    kind_pattern = re.compile(r'\bkind\s*=\s*["\']([^"\']+)["\']')

    # Scan production Python files
    production_files = _iter_production_python_files(repo_root)

    for filepath in production_files:
        try:
            with open(filepath, encoding="utf-8") as f:
                source = f.read()
        except OSError:
            continue

        # Use AST for context-aware detection
        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError:
            continue

        # Check calls and dicts using AST
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                errors.extend(_check_call_context_aware(node, filepath, repo_root, allowed_roles, allowed_kinds))
            elif isinstance(node, ast.Dict):
                errors.extend(_check_dict_literal_context_aware(node, filepath, repo_root, allowed_roles, allowed_kinds))

        # Only check regex patterns in evidence modules or files with evidence dicts
        is_evidence_module = _is_evidence_context(filepath, repo_root)

        if is_evidence_module:
            for lineno, line in enumerate(source.splitlines(), start=1):
                # Skip comments
                if "#" in line:
                    code_part = line.split("#")[0]
                else:
                    code_part = line

                # Check for role assignments in evidence context
                for match in role_pattern.finditer(code_part):
                    value = match.group(1)
                    # Skip enum member access
                    if "." in value:
                        continue
                    if value not in allowed_roles:
                        errors.append(
                            f"{filepath}:{lineno}: "
                            f"Unknown evidence role literal '{value}' "
                            f"(expected one of {sorted(allowed_roles)})"
                        )

                # Check for kind assignments in evidence context
                for match in kind_pattern.finditer(code_part):
                    value = match.group(1)
                    # Skip enum member access
                    if "." in value:
                        continue
                    if value not in allowed_kinds:
                        errors.append(
                            f"{filepath}:{lineno}: "
                            f"Unknown evidence kind literal '{value}' "
                            f"(expected one of {sorted(allowed_kinds)})"
                        )

    return errors


def check_evidence_type_contract(evidence_filepath: str, repo_root: Path) -> list[str]:
    """Run all evidence type contract checks.

    Returns:
        List of error messages (empty if all checks pass).
    """
    errors: list[str] = []

    # Extract actual values from the evidence module
    extracted_roles = extract_evidence_role_values(evidence_filepath)
    extracted_kinds = extract_evidence_kind_values(evidence_filepath)

    # Use extracted values as allowed set for literal usage checks
    allowed_roles = frozenset(extracted_roles) if extracted_roles else EXPECTED_EVIDENCE_ROLES
    allowed_kinds = frozenset(extracted_kinds) if extracted_kinds else EXPECTED_EVIDENCE_KINDS

    # Check 1: Type aliases exist and are properly defined
    alias_errors = check_evidence_type_aliases(evidence_filepath)
    errors.extend(alias_errors)

    # Check 2: Dataclass fields are not widened to str/Any/object
    dataclass_errors = check_evidence_dataclass_field_types(evidence_filepath)
    errors.extend(dataclass_errors)

    # Check 3: Literal usage in evidence contexts (context-aware)
    literal_errors = check_evidence_literal_usage(
        evidence_filepath,
        repo_root,
        allowed_roles,
        allowed_kinds,
    )
    errors.extend(literal_errors)

    return errors


# Allow list of exported names for backward compatibility
if __name__ == "__main__":
    sys.exit(0)
