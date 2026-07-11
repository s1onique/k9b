"""Protected boundary checks for evidence privacy-state types.

This module verifies that protected LLM/review/case-file/prompt modules do not import
RawEvidenceText or RedactedEvidenceText directly.

Protected boundaries should only use LLMSafeEvidenceText for crossing the LLM boundary.

R7 #4: Extended to detect qualified protected annotations in:
- AnnAssign fields
- Function argument annotations
- Return annotations
- Nested/subscripted annotations
- Qualified attributes
- Postponed string annotations
"""

from __future__ import annotations

import ast
from pathlib import Path

# Modules that should NOT import RawEvidenceText or RedactedEvidenceText
# These are LLM-facing boundaries that should only use LLMSafeEvidenceText
PROTECTED_BOUNDARY_MODULES: frozenset[str] = frozenset({
    "k8s_diag_agent/collect/incident_review_packet.py",
    "k8s_diag_agent/collect/incident_case_file.py",
    "k8s_diag_agent/collect/incident_llm_diagnosis.py",
})

# Types that should not be imported in protected boundary modules
PROTECTED_TYPES: frozenset[str] = frozenset({
    "RawEvidenceText",
    "RedactedEvidenceText",
})


def extract_imports(filepath: str) -> dict[str, list[str]]:
    """Extract import statements from a Python file.

    Returns:
        dict mapping module name -> list of imported names
    """
    imports: dict[str, list[str]] = {}

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return imports

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return imports

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [alias.name for alias in node.names]
            if module not in imports:
                imports[module] = []
            imports[module].extend(names)

    return imports


def _get_annotation_type_names(annotation: ast.expr) -> set[str]:
    """Extract all type names from an annotation including nested types.

    Handles:
    - ast.Name: direct type name (e.g., LLMSafeEvidenceText)
    - ast.Attribute: qualified type names (e.g., module.Type)
    - ast.Subscript: generic types like List[Type]
    - ast.Constant: string constants for postponed annotations

    For postponed annotations, the string is parsed via `ast.parse(mode="eval")`
    and the resulting AST is inspected recursively. This catches nested
    forms such as ``"list[RedactedEvidenceText]"`` and qualified forms
    such as ``"evidence.RawEvidenceText"``.

    Returns:
        Set of all type names found in the annotation
    """
    type_names: set[str] = set()

    if isinstance(annotation, ast.Name):
        type_names.add(annotation.id)
    elif isinstance(annotation, ast.Attribute):
        # Qualified attribute access like evidence.Text
        type_names.add(annotation.attr)
        # Recursively get base types
        type_names.update(_get_annotation_type_names(annotation.value))
    elif isinstance(annotation, ast.Subscript):
        # Generic types like List[Type] or Union[Type1, Type2]
        type_names.update(_get_annotation_type_names(annotation.value))
        if annotation.slice:
            if isinstance(annotation.slice, ast.Tuple):
                for elt in annotation.slice.elts:
                    type_names.update(_get_annotation_type_names(elt))
            else:
                type_names.update(_get_annotation_type_names(annotation.slice))
    elif isinstance(annotation, ast.Constant):
        # Postponed annotations (PEP 563 / ``from __future__ import annotations``)
        # parse the string as a Python expression and inspect the resulting AST.
        if isinstance(annotation.value, str) and annotation.value.strip():
            try:
                parsed = ast.parse(annotation.value, mode="eval").body
            except SyntaxError:
                # Unparseable annotation - fall back to the literal text.
                type_names.add(annotation.value)
                return type_names
            # Recursively inspect the parsed expression so that nested or
            # qualified type references inside the string are caught.
            type_names.update(_get_annotation_type_names(parsed))

    return type_names


def _check_annotation_for_protected_types(
    annotation: ast.expr,
    errors: list[str],
    module_path: str,
    location_desc: str,
) -> None:
    """Check an annotation for protected type usage."""
    type_names = _get_annotation_type_names(annotation)
    for protected_type in PROTECTED_TYPES:
        if protected_type in type_names:
            errors.append(
                f"{module_path}: {location_desc} uses protected type '{protected_type}'. "
                f"Protected LLM boundaries must use LLMSafeEvidenceText only."
            )


def _check_node_for_protected_annotations(
    node: ast.AST,
    errors: list[str],
    module_path: str,
) -> None:
    """Recursively check AST nodes for protected type annotations."""
    # Check AnnAssign (class attribute or variable annotation)
    if isinstance(node, ast.AnnAssign):
        if node.annotation:
            location = "Field annotation"
            if hasattr(node, 'target') and isinstance(node.target, ast.Name):
                location = f"Variable annotation '{node.target.id}'"
            _check_annotation_for_protected_types(
                node.annotation, errors, module_path, location
            )

    # Check FunctionDef arguments
    if isinstance(node, ast.FunctionDef):
        func_name = node.name

        # Check argument annotations
        for arg in node.args.args:
            if arg.annotation:
                _check_annotation_for_protected_types(
                    arg.annotation, errors, module_path,
                    f"Parameter '{arg.arg}' in function '{func_name}'"
                )
        for arg in node.args.posonlyargs:
            if arg.annotation:
                _check_annotation_for_protected_types(
                    arg.annotation, errors, module_path,
                    f"Positional-only parameter '{arg.arg}' in function '{func_name}'"
                )
        for arg in node.args.kwonlyargs:
            if arg.annotation:
                _check_annotation_for_protected_types(
                    arg.annotation, errors, module_path,
                    f"Keyword parameter '{arg.arg}' in function '{func_name}'"
                )
        if node.args.vararg and node.args.vararg.annotation:
            _check_annotation_for_protected_types(
                node.args.vararg.annotation, errors, module_path,
                f"Variadic parameter '{node.args.vararg.arg}' in function '{func_name}'"
            )
        if node.args.kwarg and node.args.kwarg.annotation:
            _check_annotation_for_protected_types(
                node.args.kwarg.annotation, errors, module_path,
                f"Keyword variadic parameter '{node.args.kwarg.arg}' in function '{func_name}'"
            )

        # Check return annotation
        if node.returns:
            _check_annotation_for_protected_types(
                node.returns, errors, module_path,
                f"Return annotation in function '{func_name}'"
            )


def check_protected_boundary_imports(repo_root: Path) -> list[str]:
    """Check that protected boundary modules don't import raw/redacted types.

    Protected modules:
    - incident_review_packet.py
    - incident_case_file.py
    - incident_llm_diagnosis.py

    These modules should only use LLMSafeEvidenceText, SafeEvidenceExcerpt,
    and RedactedEvidenceSummary for crossing the LLM boundary.

    R7 #4: Extended to detect qualified annotations like:
    - import ...incident_evidence as evidence; evidence.RedactedEvidenceText
    - From import with alias; RedactedEvidenceText as Text

    Args:
        repo_root: Root directory of the repository

    Returns:
        List of error messages (empty if all checks pass)
    """
    errors: list[str] = []

    for module_path in PROTECTED_BOUNDARY_MODULES:
        full_path = repo_root / module_path
        if not full_path.exists():
            # Module doesn't exist, skip
            continue

        imports = extract_imports(str(full_path))

        # Check direct imports from incident_evidence_redaction
        redaction_imports = imports.get("k8s_diag_agent.collect.incident_evidence_redaction", [])
        for protected_type in PROTECTED_TYPES:
            if protected_type in redaction_imports:
                errors.append(
                    f"{module_path}: Imports '{protected_type}' from incident_evidence_redaction. "
                    f"Protected LLM boundaries must use LLMSafeEvidenceText only."
                )

        # Check re-exports via incident_evidence facade
        facade_imports = imports.get("k8s_diag_agent.collect.incident_evidence", [])
        for protected_type in PROTECTED_TYPES:
            if protected_type in facade_imports:
                errors.append(
                    f"{module_path}: Imports '{protected_type}' from incident_evidence. "
                    f"Protected LLM boundaries must use LLMSafeEvidenceText only."
                )

        # Check re-exports via incident_evidence_llm_safe
        llm_safe_imports = imports.get("k8s_diag_agent.collect.incident_evidence_llm_safe", [])
        for protected_type in PROTECTED_TYPES:
            if protected_type in llm_safe_imports:
                errors.append(
                    f"{module_path}: Imports '{protected_type}' from incident_evidence_llm_safe. "
                    f"Protected LLM boundaries must use LLMSafeEvidenceText only."
                )

        # R7 #4: Check for qualified annotations in the module body
        try:
            with open(full_path, encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source, filename=str(full_path))

            # Walk the AST and check all annotation usages
            for node in ast.walk(tree):
                _check_node_for_protected_annotations(node, errors, module_path)

        except (OSError, SyntaxError):
            pass  # Skip files that can't be parsed

    return errors
