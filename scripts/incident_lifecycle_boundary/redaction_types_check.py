"""Type-related checks for evidence privacy-state types.

This module verifies:
1. Required factory functions exist in the privacy-state module
2. Exception type is defined
3. Safe omission constant is defined
4. Projector function uses correct parameter types
"""

from __future__ import annotations

import ast

# Required privacy-state type aliases
REQUIRED_PRIVACY_TYPES = frozenset({
    "RawEvidenceText",
    "RedactedEvidenceText",
    "LLMSafeEvidenceText",
    "SafeEvidenceExcerpt",
})

# Expected hierarchy (derived_type -> base_type)
EXPECTED_HIERARCHY: dict[str, str] = {
    "RawEvidenceText": "str",
    "RedactedEvidenceText": "str",
    "LLMSafeEvidenceText": "RedactedEvidenceText",
    "SafeEvidenceExcerpt": "LLMSafeEvidenceText",
}

# Required production factory functions
REQUIRED_FACTORIES: frozenset[str] = frozenset({
    "redact_evidence_text",
    "approve_redacted_evidence_text",
    "project_raw_evidence_text_for_llm",
    "make_safe_evidence_excerpt",
})

# Required projector function in LLM safe module
REQUIRED_PROJECTOR = "evidence_artifact_to_llm_safe_summary"

# Required exception type
REQUIRED_EXCEPTION = "UnsafeEvidenceTextError"

# Safe omission constant
REQUIRED_SAFE_OMISSION = "SAFE_OMISSION_MARKER"


def extract_function_definitions(filepath: str) -> set[str]:
    """Extract function definition names from a Python file."""
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

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions.add(node.name)

    return functions


def extract_class_definitions(filepath: str) -> set[str]:
    """Extract class definition names from a Python file."""
    classes: set[str] = set()

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return classes

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return classes

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.add(node.name)

    return classes


def check_privacy_state_factories(filepath: str) -> list[str]:
    """Check that required production factory functions exist."""
    errors: list[str] = []

    functions = extract_function_definitions(filepath)

    for factory in REQUIRED_FACTORIES:
        if factory not in functions:
            errors.append(
                f"{filepath}: Missing factory function '{factory}'. "
                f"Required for trusted privacy-state construction."
            )

    return errors


def check_exception_definition(filepath: str) -> list[str]:
    """Check that required exception type is defined."""
    errors: list[str] = []

    classes = extract_class_definitions(filepath)

    if REQUIRED_EXCEPTION not in classes:
        errors.append(
            f"{filepath}: Missing exception class '{REQUIRED_EXCEPTION}'. "
            f"Required for fail-closed validation behavior."
        )

    return errors


def check_safe_omission_constant(filepath: str) -> list[str]:
    """Check that safe omission constant is defined."""
    errors: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return [f"Cannot read {filepath}"]

    # Look for the constant assignment
    if REQUIRED_SAFE_OMISSION not in source:
        errors.append(
            f"{filepath}: Missing constant '{REQUIRED_SAFE_OMISSION}'. "
            f"Required for fail-closed behavior."
        )

    return errors


def _get_annotation_str(annotation: ast.expr) -> str:
    """Extract annotation string from AST node.

    Supports:
    - ast.Name: direct type name (e.g., LLMSafeEvidenceText)
    - ast.Constant: string constant for postponed annotations (e.g., "LLMSafeEvidenceText")
    - ast.Subscript: union types (e.g., str | None)
    """
    if isinstance(annotation, ast.Name):
        return annotation.id
    elif isinstance(annotation, ast.Constant):
        return str(annotation.value)
    elif isinstance(annotation, ast.Subscript):
        # Handle Union types like "str | None"
        left = _get_annotation_str(annotation.value)
        if annotation.slice:
            if isinstance(annotation.slice, ast.Tuple):
                right = " | ".join(_get_annotation_str(e) for e in annotation.slice.elts)
            else:
                right = _get_annotation_str(annotation.slice)
            return f"{left} | {right}"
        return left
    return "<complex>"


def _check_summary_parameter(
    errors: list[str],
    filepath: str,
    projector_name: str,
    param: ast.arg,
    param_source: str,
) -> None:
    """Check a summary parameter for correct annotation and keyword-only position."""
    if param_source != "kwonlyargs":
        errors.append(
            f"{filepath}: Projector '{projector_name}' summary parameter "
            f"must be keyword-only (declared after `*` in {param_source}), "
            f"found '{param_source}'. "
            f"summary must be explicit at every call site."
        )
    if param.annotation:
        annotation_str = _get_annotation_str(param.annotation)
        if annotation_str != "LLMSafeEvidenceText":
            errors.append(
                f"{filepath}: Projector '{projector_name}' summary parameter "
                f"(in {param_source}) must have type annotation 'LLMSafeEvidenceText', "
                f"found '{annotation_str}'."
            )
    else:
        errors.append(
            f"{filepath}: Projector '{projector_name}' summary parameter "
            f"(in {param_source}) is missing type annotation 'LLMSafeEvidenceText'."
        )


def check_projector_parameter_type(filepath: str, projector_name: str = REQUIRED_PROJECTOR) -> list[str]:
    """Check that the projector function uses LLMSafeEvidenceText for summary parameter.

    The summary parameter must be:
    - Named exactly 'summary'
    - Keyword-only (after *)
    - Annotated with LLMSafeEvidenceText

    Supports postponed annotations represented as either ast.Name or string constants.

    Args:
        filepath: Path to the Python file to check
        projector_name: Name of the projector function

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

    # Find the projector function
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == projector_name:
            # Check positional-only, regular, and keyword-only args
            summary_found = False

            # Check positional-only args (before *)
            for arg in node.args.posonlyargs:
                if arg.arg == "summary":
                    summary_found = True
                    _check_summary_parameter(errors, filepath, projector_name, arg, "posonlyargs")
                    break

            # Check regular args (before *)
            if not summary_found:
                for arg in node.args.args:
                    if arg.arg == "summary":
                        summary_found = True
                        _check_summary_parameter(errors, filepath, projector_name, arg, "args")
                        break

            # Check keyword-only args (after *)
            if not summary_found:
                for arg in node.args.kwonlyargs:
                    if arg.arg == "summary":
                        summary_found = True
                        _check_summary_parameter(errors, filepath, projector_name, arg, "kwonlyargs")
                        break

            # Check vararg (*args) and kwarg (**kwargs)
            if not summary_found and node.args.vararg:
                if node.args.vararg.arg == "summary":
                    summary_found = True
                    _check_summary_parameter(errors, filepath, projector_name, node.args.vararg, "vararg")

            if not summary_found:
                errors.append(
                    f"{filepath}: Projector '{projector_name}' missing 'summary' parameter. "
                    f"Required for type-safe boundary crossing."
                )

            return errors

    errors.append(
        f"{filepath}: Missing projector function '{projector_name}'. "
        f"Required for evidence-to-summary projection."
    )

    return errors
