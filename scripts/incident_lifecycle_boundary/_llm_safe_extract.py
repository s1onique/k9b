"""AST extraction utilities for LLM-safe evidence boundary verifier.

This module holds small, focused extractors that parse a Python file
and return plain data. Behaviour-heavy checks (provenance, rebinding
detection) live in :mod:`scripts.incident_lifecycle_boundary._llm_safe_traversal`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class ImportedName:
    """Triple of (module, original_name, local_name) for a top-level import.

    ``local_name`` is the name bound in the importing module's
    namespace (either the original imported name or the ``as`` alias).
    ``original_name`` is the symbol actually imported from the source
    module. Preserving both components lets the verifier prove that a
    facade imports the SAME identity as the canonical module, not just a
    same-named alias: ``from canonical import SomethingElse as Foo``
    must be rejected because the original identity is ``SomethingElse``,
    not ``Foo``.
    """

    module: str
    original_name: str
    local_name: str


def extract_newtype_aliases(filepath: str) -> dict[str, str]:
    """Extract NewType aliases from a Python file.

    The extractor:

    * Recognizes ``NewType(...)`` and ``typing.NewType(...)`` qualified
      calls. Arbitrary attribute qualifiers such as ``fake.NewType(...)``
      are REJECTED; the only accepted qualifier is ``typing`` so an
      attacker cannot smuggle a ``NewType`` call through an unrelated
      module reference.
    * Verifies that the assignment target name equals the ``NewType``
      string-name argument (``RedactedEvidenceText = NewType("RedactedEvidenceText", str)``
      is accepted; ``RedactedEvidenceText = NewType("WrongName", str)`` is
      rejected because the two identities must be linked).
    * Returns the declared supertype verbatim, which may be ``"str"``
      (primitive) or another alias declared in the same module
      (branded hierarchy). Callers must resolve transitive references.

    Examples::

        {"RawEvidenceText": "str"}
        {"RedactedEvidenceText": "str"}
        {"LLMSafeEvidenceText": "RedactedEvidenceText"}
        {"SafeEvidenceExcerpt": "LLMSafeEvidenceText"}

    Returns:
        Dict mapping alias name to its declared supertype name. Aliases
        whose ``NewType`` name does not match the assignment target are
        NOT recorded, since they would mint a statically distinct type
        behind a different name.
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
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        if not isinstance(node.targets[0], ast.Name):
            continue
        target_name = node.targets[0].id
        value = node.value
        if not (isinstance(value, ast.Call) and len(value.args) >= 2):
            continue

        # Accept ``NewType(...)`` and the qualified ``typing.NewType(...)``.
        # Arbitrary attribute qualifiers (``fake.NewType(...)``) are
        # REJECTED: the only accepted qualifier is ``typing`` so an
        # attacker cannot smuggle a ``NewType`` call through an
        # unrelated module reference.
        is_newtype = False
        if isinstance(value.func, ast.Name) and value.func.id == "NewType":
            is_newtype = True
        elif (
            isinstance(value.func, ast.Attribute)
            and value.func.attr == "NewType"
            and isinstance(value.func.value, ast.Name)
            and value.func.value.id == "typing"
        ):
            is_newtype = True
        if not is_newtype:
            continue

        # First arg must be a string name and must equal the assignment
        # target. Without this check, ``Foo = NewType("Bar", str)`` would
        # be recorded as ``Foo -> str`` even though ``Foo`` and ``Bar``
        # are statically distinct identities.
        first_arg = value.args[0]
        if not (isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str)):
            continue
        if first_arg.value != target_name:
            continue

        # Supertype may be ``str`` (primitive) or another alias declared
        # in this module (branded hierarchy).
        second_arg = value.args[1]
        if isinstance(second_arg, ast.Name):
            aliases[target_name] = second_arg.id
        elif isinstance(second_arg, ast.Constant) and isinstance(second_arg.value, str):
            aliases[target_name] = second_arg.value

    return aliases


def extract_canonical_imports(filepath: str) -> dict[str, ImportedName]:
    """Extract ``from <module> import <name>`` statements as a canonical-import map.

    Returns:
        Dict mapping imported local name to an :class:`ImportedName`
        triple (module, original_name, local_name). For
        ``from k8s_diag_agent.collect.incident_evidence_redaction import
        LLMSafeEvidenceText`` the result is::

            {
                "LLMSafeEvidenceText": ImportedName(
                    module="k8s_diag_agent.collect.incident_evidence_redaction",
                    original_name="LLMSafeEvidenceText",
                    local_name="LLMSafeEvidenceText",
                )
            }

        For ``from canonical import SomethingElse as Foo`` the result is::

            {
                "Foo": ImportedName(
                    module="canonical",
                    original_name="SomethingElse",
                    local_name="Foo",
                )
            }

        so the verifier can prove the original imported symbol matches
        the local name. Preserving ``original_name`` defeats the
        ``from canonical import SomethingElse as Foo`` bypass.

        Only top-level ``ast.ImportFrom`` nodes are inspected. Imports
        inside functions or conditionals are ignored because they do
        not contribute to the module's public identity surface.
    """
    imports: dict[str, ImportedName] = {}

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
        if not isinstance(node, ast.ImportFrom):
            continue
        # ``module`` is ``None`` for ``from . import name``; skip those.
        module = node.module or ""
        for alias in node.names:
            local_name = alias.asname or alias.name
            imports[local_name] = ImportedName(
                module=module,
                original_name=alias.name,
                local_name=local_name,
            )

    return imports


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


def is_safe_ref_shape(annotation: ast.AST) -> bool:
    """Return True iff the annotation is exactly an allowed safe_ref closed union.

    Recognised shapes (each must contain ``LLMSafeArtifactRef`` and
    optionally ``ReviewPacketStorageRef``; ``None`` is permitted but not
    required):

    * ``LLMSafeArtifactRef | None``
    * ``LLMSafeArtifactRef | ReviewPacketStorageRef | None``
    * ``LLMSafeArtifactRef | ReviewPacketStorageRef``
    * ``LLMSafeArtifactRef``

    Any other annotation (a plain ``str``, ``LLMSafeArtifactRef | str``,
    ``None`` alone, ``LocalArtifactPath``, ``None | LocalArtifactPath``,
    or a generic union containing anything else) returns ``False``.
    """
    members = set(extract_union_members(annotation))
    allowed_members = {"LLMSafeArtifactRef", "ReviewPacketStorageRef", "None"}
    if not members:
        return False
    if not members.issubset(allowed_members):
        return False
    return "LLMSafeArtifactRef" in members


def is_pure_llm_safe_evidence_text_annotation(annotation: ast.AST) -> bool:
    """Return True iff ``annotation`` is exactly ``LLMSafeEvidenceText``.

    Rejects unions, subscripts, qualified names, and any other shape.
    The annotation must be either an ``ast.Name`` with id
    ``LLMSafeEvidenceText`` or a string forward reference equal to
    ``"LLMSafeEvidenceText"``.
    """
    if isinstance(annotation, ast.Name):
        return annotation.id == "LLMSafeEvidenceText"
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value == "LLMSafeEvidenceText"
    return False


__all__ = [
    "ImportedName",
    "extract_canonical_imports",
    "extract_dataclass_names",
    "extract_function_definitions",
    "extract_newtype_aliases",
    "extract_union_members",
    "is_pure_llm_safe_evidence_text_annotation",
    "is_safe_ref_shape",
]