"""Constructor provenance checks for evidence privacy-state types.

This module enforces that trusted constructors (RedactedEvidenceText, LLMSafeEvidenceText,
SafeEvidenceExcerpt) are only called from the designated projection module.

AST-scan production Python files and reject direct calls to:
- RedactedEvidenceText(...)
- LLMSafeEvidenceText(...)
- SafeEvidenceExcerpt(...)

Also handles:
- Module-qualified calls: redaction.LLMSafeEvidenceText(value)
- Aliased imports: Safe = LLMSafeEvidenceText; Safe(value)

Trusted locations:
- The canonical privacy projection module (incident_evidence_redaction.py)
- NewType(...) declarations themselves
"""

from __future__ import annotations

import ast
from pathlib import Path

# Trusted module where constructor calls are allowed
TRUSTED_PROJECTION_MODULE = "k8s_diag_agent/collect/incident_evidence_redaction.py"

# Trusted types whose constructors should NOT be called outside the projection module
TRUSTED_CONSTRUCTOR_TYPES: frozenset[str] = frozenset({
    "RedactedEvidenceText",
    "LLMSafeEvidenceText",
    "SafeEvidenceExcerpt",
})

# Trusted source modules
TRUSTED_SOURCE_MODULES: frozenset[str] = frozenset({
    "k8s_diag_agent.collect.incident_evidence_redaction",
    "incident_evidence_redaction",
})


def _extract_imports(tree: ast.AST) -> tuple[dict[str, str], dict[str, str]]:
    """Extract import information from AST.

    Returns:
        - local_name -> qualified_name mapping for direct imports
        - module_alias -> qualified_module mapping for module imports
    """
    local_to_qualified: dict[str, str] = {}
    module_aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local_name = alias.asname if alias.asname else alias.name
                qualified_name = f"{module}.{alias.name}" if module else alias.name
                local_to_qualified[local_name] = qualified_name
                # Also record the unqualified name
                local_to_qualified[alias.name] = qualified_name

        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                alias_name = alias.asname if alias.asname else alias.name
                module_aliases[alias_name] = module
                # Also map the unqualified module name
                parts = module.rsplit(".", 1)
                if len(parts) > 1:
                    module_aliases[parts[-1]] = module

    return local_to_qualified, module_aliases


def _resolve_call_target(func: ast.expr, local_to_qualified: dict[str, str], module_aliases: dict[str, str]) -> str | None:
    """Resolve a call expression to its qualified name.

    Handles:
    - Direct calls: LLMSafeEvidenceText(value)
    - Module-qualified: redaction.LLMSafeEvidenceText(value)
    - Aliased imports: Safe(value) where Safe = LLMSafeEvidenceText

    Returns:
        The fully qualified name of the call target, or None if not a trusted constructor
    """
    # Direct call: Name
    if isinstance(func, ast.Name):
        local_name = func.id
        if local_name in TRUSTED_CONSTRUCTOR_TYPES:
            # Could be from any source, we need to check if it's the trusted type
            # We'll return the simple name and check later
            return local_name
        if local_name in local_to_qualified:
            qualified = local_to_qualified[local_name]
            # Check if this is an alias for a trusted constructor
            if any(t in qualified for t in TRUSTED_CONSTRUCTOR_TYPES):
                return qualified
        return None

    # Module-qualified call: Attribute
    if isinstance(func, ast.Attribute):
        # Handle module.attr calls like redaction.LLMSafeEvidenceText
        value = func.value
        attr_name = func.attr

        if attr_name not in TRUSTED_CONSTRUCTOR_TYPES:
            return None

        # Check if it's from a trusted module
        if isinstance(value, ast.Name):
            module_name = value.id
            # Check if this is a module alias
            if module_name in module_aliases:
                return f"{module_aliases[module_name]}.{attr_name}"
            # Could be a direct import like `import incident_evidence_redaction as redaction`
            if module_name in TRUSTED_SOURCE_MODULES or any(
                t in module_name for t in ("incident_evidence_redaction", "redaction")
            ):
                return f"incident_evidence_redaction.{attr_name}"

        return attr_name

    return None


def extract_call_sites(filepath: str) -> tuple[dict[str, list[dict[str, object]]], dict[str, str], dict[str, str]]:
    """Extract function and constructor call sites from a Python file.

    Returns:
        Tuple of:
        - dict mapping type/function name -> list of call site info dicts
        - local_name -> qualified_name mapping
        - module_alias -> qualified_module mapping
    """
    call_sites: dict[str, list[dict[str, object]]] = {}

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return call_sites, {}, {}

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return call_sites, {}, {}

    local_to_qualified, module_aliases = _extract_imports(tree)

    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            resolved = _resolve_call_target(node.func, local_to_qualified, module_aliases)
            if resolved:
                context = ""
                if 0 <= node.lineno - 1 < len(lines):
                    context = lines[node.lineno - 1].strip()
                call_sites.setdefault(resolved, []).append({
                    "module": filepath,
                    "lineno": node.lineno,
                    "col_offset": node.col_offset,
                    "context": context,
                })

    return call_sites, local_to_qualified, module_aliases


def check_trusted_constructor_usage(
    repo_root: Path,
    source_dir: str = "k8s_diag_agent",
) -> list[str]:
    """Check that trusted constructors are only called from designated projection module.

    This function scans production Python files and rejects direct calls to:
    - RedactedEvidenceText(...)
    - LLMSafeEvidenceText(...)
    - SafeEvidenceExcerpt(...)

    outside the trusted projection module.

    Excludes:
    - Test modules (files matching test_*.py or *_test.py)
    - The verifier fixture source strings
    - The NewType(...) declarations themselves

    Args:
        repo_root: Root directory of the repository
        source_dir: Source directory to scan (relative to repo_root)

    Returns:
        List of error messages (empty if all checks pass)
    """
    errors: list[str] = []

    src_path = repo_root / source_dir if source_dir else repo_root

    if not src_path.exists():
        return [f"Source directory not found: {src_path}"]

    # Scan all Python files in the source directory
    for py_file in src_path.rglob("*.py"):
        rel_path = py_file.relative_to(repo_root)

        # Skip test modules
        if py_file.name.startswith("test_") or py_file.name.endswith("_test.py"):
            continue

        # Skip the verifier itself
        if "incident_lifecycle_boundary" in str(rel_path):
            continue

        # Scan every production Python file
        # Use the import map only to resolve whether a call targets trusted types
        try:
            with open(py_file, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue

        call_sites, local_to_qualified, module_aliases = extract_call_sites(str(py_file))

        for type_name, calls in call_sites.items():
            for call in calls:
                # Check if this file is the trusted projection module
                if str(rel_path).replace("\\", "/") == TRUSTED_PROJECTION_MODULE:
                    # Inside the trusted module, only allow in function bodies, not at module level
                    # Check if this is a NewType declaration (the declaration itself)
                    source_lines = content.splitlines()
                    call_lineno: int = call["lineno"]  # type: ignore[assignment]
                    if call_lineno <= len(source_lines):
                        line = source_lines[call_lineno - 1]
                        # Check if this is a NewType declaration line
                        if "NewType" in line or "=" not in line:
                            continue

                # REJECT if this file is NOT the trusted projection module
                # The call site is in an importing module (external to trusted projection)
                is_trusted_module = str(rel_path).replace("\\", "/") == TRUSTED_PROJECTION_MODULE
                if not is_trusted_module:
                    errors.append(
                        f"{rel_path}:{call['lineno']}: "
                        f"Direct constructor call to {type_name}(...) found outside "
                        f"trusted projection module. Use the projection pipeline functions "
                        f"(redact_evidence_text, approve_redacted_evidence_text, "
                        f"project_raw_evidence_text_for_llm) instead."
                    )

    return errors
