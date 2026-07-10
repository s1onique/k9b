"""LLM-safe evidence boundary verifier for the incident lifecycle.

This module verifies that LLM/case-file/review-packet builders accept only:
- LLMSafeArtifactRef
- ReviewPacketStorageRef
- RedactedEvidenceSummary
- RedactedEvidenceText
- SafeEvidenceExcerpt

And reject:
- LocalArtifactPath
- ExternalStorageRef
- raw artifact content
- direct EvidenceArtifact.storage_ref access

Invariant: Raw artifact paths, storage refs, and unredacted content
must NOT cross the LLM boundary without explicit redacted projection.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    LLM_REVIEW_MODULES,
    LLM_SAFE_TYPES,
    REQUIRED_DATACLASS,
    REQUIRED_HELPERS,
    SAFE_REF_TYPES,
    UNSAFE_PATTERNS,
    UNSAFE_REF_TYPES,
)
from scripts.incident_lifecycle_boundary._llm_safe_extract import (
    extract_dataclass_names,
    extract_function_definitions,
    extract_newtype_aliases,
    extract_union_members,
)


def check_llm_safe_type_aliases(filepath: str) -> list[str]:
    """Check that required NewType aliases exist for LLM-safe evidence.

    Verifies:
    - RedactedEvidenceText exists
    - SafeEvidenceExcerpt exists
    - All are based on str
    """
    errors: list[str] = []

    aliases = extract_newtype_aliases(filepath)

    for expected_type in LLM_SAFE_TYPES:
        if expected_type not in aliases:
            errors.append(
                f"{filepath}: Missing NewType alias '{expected_type}'. "
                f"Expected NewType('{expected_type}', str)."
            )
        elif aliases[expected_type] != "str":
            errors.append(
                f"{filepath}: NewType alias '{expected_type}' is based on "
                f"'{aliases[expected_type]}', expected 'str'."
            )

    return errors


def _get_annotation_name(node: ast.AST) -> str | None:
    """Extract the name from a type annotation node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _get_annotation_name(node.left)
    return None


def check_llm_safe_dataclass(filepath: str) -> list[str]:
    """Check that RedactedEvidenceSummary dataclass exists with correct fields.

    Verifies:
    - RedactedEvidenceSummary dataclass exists
    - It has 'summary' field typed as RedactedEvidenceText
    - It has 'safe_ref' field typed as safe reference (NOT LocalArtifactPath/ExternalStorageRef)
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

    # Find RedactedEvidenceSummary class
    dataclass_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == REQUIRED_DATACLASS:
            dataclass_node = node
            break

    if dataclass_node is None:
        errors.append(
            f"{filepath}: Missing dataclass '{REQUIRED_DATACLASS}'. "
            f"Expected frozen dataclass with summary: RedactedEvidenceText field."
        )
        return errors

    # Check for summary field
    has_summary = False
    summary_is_safe_type = False
    has_safe_ref = False
    safe_ref_has_unsafe_type = False
    safe_ref_members: list[str] = []

    for item in dataclass_node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            field_name = item.target.id

            if field_name == "summary":
                has_summary = True
                annotation_name = _get_annotation_name(item.annotation)
                if annotation_name == "RedactedEvidenceText":
                    summary_is_safe_type = True

            if field_name == "safe_ref":
                has_safe_ref = True
                safe_ref_members = extract_union_members(item.annotation)
                for member in safe_ref_members:
                    if member in UNSAFE_REF_TYPES:
                        safe_ref_has_unsafe_type = True
                        break

    if not has_summary:
        errors.append(f"{filepath}: RedactedEvidenceSummary missing 'summary' field.")
    if has_summary and not summary_is_safe_type:
        errors.append(f"{filepath}: RedactedEvidenceSummary.summary must be typed as RedactedEvidenceText.")
    if not has_safe_ref:
        errors.append(f"{filepath}: RedactedEvidenceSummary missing 'safe_ref' field.")
    if safe_ref_has_unsafe_type:
        errors.append(
            f"{filepath}: RedactedEvidenceSummary.safe_ref contains unsafe type. "
            f"Found: {safe_ref_members}. Allowed: LLMSafeArtifactRef, ReviewPacketStorageRef, None. "
            f"Prohibited: LocalArtifactPath, ExternalStorageRef."
        )
    for member in safe_ref_members:
        if member != "None" and member not in SAFE_REF_TYPES:
            errors.append(
                f"{filepath}: RedactedEvidenceSummary.safe_ref contains unknown type. "
                f"Found: {member}. Allowed: LLMSafeArtifactRef, ReviewPacketStorageRef, None."
            )

    return errors


def check_llm_safe_helpers(filepath: str) -> list[str]:
    """Check that required helper functions exist."""
    errors: list[str] = []
    functions = extract_function_definitions(filepath)

    for expected_helper in REQUIRED_HELPERS:
        if expected_helper not in functions:
            errors.append(f"{filepath}: Missing helper function '{expected_helper}'.")

    return errors


def check_llm_review_unsafe_access(repo_root: Path) -> list[str]:
    """Scan LLM/review modules for unsafe access patterns."""
    errors: list[str] = []

    for module_path in LLM_REVIEW_MODULES:
        full_path = repo_root / module_path
        if not full_path.exists():
            continue

        try:
            with open(full_path, encoding="utf-8") as f:
                source = f.read()
        except OSError:
            continue

        for pattern, description in UNSAFE_PATTERNS:
            if pattern.search(source):
                for i, line in enumerate(source.splitlines(), 1):
                    if pattern.search(line):
                        errors.append(f"{module_path}:{i}: Detected unsafe pattern: {description}")

    return errors


def check_llm_safe_evidence_contract(
    evidence_filepath: str,
    repo_root: Path,
) -> list[str]:
    """Run all LLM-safe evidence contract checks."""
    errors: list[str] = []

    alias_errors = check_llm_safe_type_aliases(evidence_filepath)
    errors.extend(alias_errors)

    dataclass_errors = check_llm_safe_dataclass(evidence_filepath)
    errors.extend(dataclass_errors)

    helper_errors = check_llm_safe_helpers(evidence_filepath)
    errors.extend(helper_errors)

    unsafe_errors = check_llm_review_unsafe_access(repo_root)
    errors.extend(unsafe_errors)

    return errors


def check_llm_safe_helper_signatures(filepath: str) -> list[str]:
    """Check that helper function signatures are type-safe.

    Verifies:
    - evidence_artifact_to_llm_safe_summary has safe_ref parameter typed as
      LLMSafeArtifactRef | ReviewPacketStorageRef | None (NOT LocalArtifactPath)
    - No unknown types are allowed in the safe_ref union
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
        if isinstance(node, ast.FunctionDef) and node.name == "evidence_artifact_to_llm_safe_summary":
            for arg in node.args.kwonlyargs:
                if arg.arg == "safe_ref":
                    if arg.annotation is None:
                        continue
                    members = extract_union_members(arg.annotation)
                    for member in members:
                        if member in UNSAFE_REF_TYPES:
                            errors.append(
                                f"{filepath}: evidence_artifact_to_llm_safe_summary has unsafe safe_ref type. "
                                f"Found: {members}. Allowed: LLMSafeArtifactRef, ReviewPacketStorageRef, None. "
                                f"Prohibited: LocalArtifactPath, ExternalStorageRef."
                            )
                            return errors
                    for member in members:
                        if member != "None" and member not in SAFE_REF_TYPES:
                            errors.append(
                                f"{filepath}: evidence_artifact_to_llm_safe_summary has unknown safe_ref type. "
                                f"Found: {member}. Allowed: LLMSafeArtifactRef, ReviewPacketStorageRef, None."
                            )
                            return errors

    return errors


__all__ = [
    "check_llm_safe_dataclass",
    "check_llm_safe_evidence_contract",
    "check_llm_safe_helper_signatures",
    "check_llm_safe_helpers",
    "check_llm_safe_type_aliases",
    "check_llm_review_unsafe_access",
    "extract_dataclass_names",
    "extract_function_definitions",
    "extract_newtype_aliases",
    "extract_union_members",
]


if __name__ == "__main__":
    print("LLM-safe evidence types required:")
    for alias in sorted(LLM_SAFE_TYPES):
        print(f"  - {alias} = NewType('{alias}', str)")
    print("\nRequired dataclass:")
    print(f"  - {REQUIRED_DATACLASS} (frozen, slots, kw_only)")
    print("\nRequired helpers:")
    for helper in sorted(REQUIRED_HELPERS):
        print(f"  - {helper}()")
    print("\nLLM/review modules to check:")
    for module in LLM_REVIEW_MODULES:
        print(f"  - {module}")
    sys.exit(0)
