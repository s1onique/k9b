"""LLM-safe dataclass and helper-signature contract verifier.

Validates ``RedactedEvidenceSummary`` and ``evidence_artifact_to_llm_safe_summary``
in the LLM-safe facade. Strengthened contracts:

- ``RedactedEvidenceSummary.summary`` MUST be typed EXACTLY as
  ``LLMSafeEvidenceText`` (a bare name or a string forward reference).
  ``LLMSafeEvidenceText | str``, ``LLMSafeEvidenceText | None``, and
  any union/subscript/qualified alternative are REJECTED. Redacted
  text is not automatically approved for LLM exposure.
- ``RedactedEvidenceSummary.safe_ref`` MUST be one of the closed
  union shapes ``LLMSafeArtifactRef | None`` or
  ``LLMSafeArtifactRef | ReviewPacketStorageRef | None`` (or the
  no-``None`` variant of either). The closed union must contain
  exactly ``LLMSafeArtifactRef`` and optionally
  ``ReviewPacketStorageRef``; ``None`` is permitted but not required.
  Any other annotation (``None`` alone, ``LocalArtifactPath``,
  ``LocalArtifactPath | None``, ``str | None``, ``ReviewPacketStorageRef
  | None``, ``LLMSafeArtifactRef | str``) is rejected.
- ``evidence_artifact_to_llm_safe_summary`` MUST declare a ``summary``
  parameter typed EXACTLY as ``LLMSafeEvidenceText`` and a ``safe_ref``
  of one of the same closed union shapes (positional and keyword-only
  branches both enforced). A missing ``summary`` parameter is
  rejected.
"""

from __future__ import annotations

import ast

from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    REQUIRED_DATACLASS,
)
from scripts.incident_lifecycle_boundary._llm_safe_extract import (
    extract_function_definitions,
    extract_union_members,
    is_pure_llm_safe_evidence_text_annotation,
    is_safe_ref_shape,
)

# The summary field of ``RedactedEvidenceSummary`` must be typed as
# ``LLMSafeEvidenceText`` (not ``RedactedEvidenceText``). Redacted text
# is not inherently safe for LLM exposure; only ``LLMSafeEvidenceText``
# has cleared the residual-secret validation in
# ``incident_evidence_redaction.approve_redacted_evidence_text``.
SUMMARY_REQUIRED_TYPE = "LLMSafeEvidenceText"


def _is_unsafe_safe_ref_annotation(annotation: ast.AST) -> tuple[bool, list[str]]:
    """Return ``(is_unsafe, members)`` for a ``safe_ref`` annotation.

    The annotation is considered unsafe if it contains any prohibited
    type (``LocalArtifactPath`` or ``ExternalStorageRef``) or any
    type outside the closed union ``{LLMSafeArtifactRef,
    ReviewPacketStorageRef, None}``.
    """
    members = extract_union_members(annotation)
    if not members:
        return False, []
    unsafe = {"LocalArtifactPath", "ExternalStorageRef"}
    closed_union = {"LLMSafeArtifactRef", "ReviewPacketStorageRef", "None"}
    for member in members:
        if member in unsafe:
            return True, members
        if member not in closed_union:
            return True, members
    return False, members


def check_llm_safe_dataclass(filepath: str) -> list[str]:
    """Check that ``RedactedEvidenceSummary`` dataclass exists with correct fields.

    Verifies:
    - ``RedactedEvidenceSummary`` dataclass exists
    - ``summary`` field typed EXACTLY as ``LLMSafeEvidenceText`` (NOT
      ``RedactedEvidenceText``). Redacted is not LLM-safe. Unions,
      subscripts, qualified alternatives are all rejected.
    - ``safe_ref`` field typed as a closed union whose members are
      drawn from ``{LLMSafeArtifactRef, ReviewPacketStorageRef,
      None}`` and which must include ``LLMSafeArtifactRef``.
      ``LocalArtifactPath`` / ``ExternalStorageRef`` are prohibited.
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
            f"Expected frozen dataclass with summary: {SUMMARY_REQUIRED_TYPE} field."
        )
        return errors

    # Check for summary field
    has_summary = False
    summary_is_safe_type = False
    has_safe_ref = False
    safe_ref_is_closed_union = False

    for item in dataclass_node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            field_name = item.target.id

            if field_name == "summary":
                has_summary = True
                if is_pure_llm_safe_evidence_text_annotation(item.annotation):
                    summary_is_safe_type = True

            if field_name == "safe_ref":
                has_safe_ref = True
                if is_safe_ref_shape(item.annotation):
                    safe_ref_is_closed_union = True

    if not has_summary:
        errors.append(f"{filepath}: {REQUIRED_DATACLASS} missing 'summary' field.")
    if has_summary and not summary_is_safe_type:
        errors.append(
            f"{filepath}: {REQUIRED_DATACLASS}.summary must be typed EXACTLY as "
            f"the bare name '{SUMMARY_REQUIRED_TYPE}' (or a string forward "
            f"reference). Unions, subscripts, qualified alternatives, and "
            f"any other type are rejected. Redacted text is not automatically "
            f"approved for LLM exposure; only {SUMMARY_REQUIRED_TYPE} crosses "
            f"the LLM boundary."
        )
    if not has_safe_ref:
        errors.append(f"{filepath}: {REQUIRED_DATACLASS} missing 'safe_ref' field.")
    if has_safe_ref and not safe_ref_is_closed_union:
        # Re-fetch the offending members for diagnostic purposes so
        # the operator sees WHICH annotation was rejected (e.g. shows
        # ``SomeOtherRef`` when present in a union).
        offending_members: list[str] = []
        for item in dataclass_node.body:
            if (
                isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
                and item.target.id == "safe_ref"
            ):
                offending_members = extract_union_members(item.annotation)
                break
        errors.append(
            f"{filepath}: {REQUIRED_DATACLASS}.safe_ref annotation is not an "
            f"allowed closed-union shape. Found members: {sorted(offending_members)}. "
            f"Allowed shapes: "
            f"'LLMSafeArtifactRef', 'LLMSafeArtifactRef | None', "
            f"'LLMSafeArtifactRef | ReviewPacketStorageRef', "
            f"'LLMSafeArtifactRef | ReviewPacketStorageRef | None'. "
            f"Prohibited: 'LocalArtifactPath', 'ExternalStorageRef', "
            f"'str', 'None' alone, and any union containing types outside "
            f"the closed set."
        )

    return errors


def check_llm_safe_helpers(filepath: str) -> list[str]:
    """Check that required helper functions exist."""
    errors: list[str] = []
    functions = extract_function_definitions(filepath)

    from scripts.incident_lifecycle_boundary._llm_safe_constants import REQUIRED_HELPERS

    for expected_helper in REQUIRED_HELPERS:
        if expected_helper not in functions:
            errors.append(f"{filepath}: Missing helper function '{expected_helper}'.")

    return errors


def check_llm_safe_helper_signatures(filepath: str) -> list[str]:
    """Check that ``evidence_artifact_to_llm_safe_summary`` declares a
    ``summary`` parameter typed as ``LLMSafeEvidenceText`` and a closed
    ``safe_ref`` union.

    Verifies:
    - ``evidence_artifact_to_llm_safe_summary`` has ``safe_ref`` parameter
      typed as ``LLMSafeArtifactRef | ReviewPacketStorageRef | None``
      (NOT ``LocalArtifactPath`` or any non-closed type).
    - The ``summary`` parameter is typed as ``LLMSafeEvidenceText`` (NOT
      ``RedactedEvidenceText``); this is the static guardrail that mirrors
      the dataclass contract.
    - A missing ``summary`` parameter is rejected (a function with no
      ``summary`` at all leaks raw text to the LLM).
    - No unknown types are allowed in the ``safe_ref`` union.
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

    target_found = False

    def _validate_safe_ref_annotation(annotation: ast.AST | None) -> str | None:
        """Validate a ``safe_ref`` annotation; return an error message or None.

        The annotation must be present and must satisfy the closed-union
        shape requirements: members drawn from
        ``{LLMSafeArtifactRef, ReviewPacketStorageRef, None}`` with at
        least ``LLMSafeArtifactRef`` present. Returns ``None`` on
        success, or a diagnostic string on failure.
        """
        if annotation is None:
            return (
                f"{filepath}: evidence_artifact_to_llm_safe_summary.safe_ref "
                f"parameter must be annotated as a closed union of "
                f"{{LLMSafeArtifactRef, ReviewPacketStorageRef, None}}; "
                f"unannotated safe_ref leaks raw text to the LLM."
            )
        if is_safe_ref_shape(annotation):
            return None
        members = extract_union_members(annotation)
        return (
            f"{filepath}: evidence_artifact_to_llm_safe_summary.safe_ref "
            f"annotation is not an allowed closed-union shape. "
            f"Found members: {sorted(members)}. Allowed shapes: "
            f"'LLMSafeArtifactRef', 'LLMSafeArtifactRef | None', "
            f"'LLMSafeArtifactRef | ReviewPacketStorageRef', "
            f"'LLMSafeArtifactRef | ReviewPacketStorageRef | None'. "
            f"Prohibited: 'LocalArtifactPath', 'ExternalStorageRef', "
            f"'str', 'None' alone, and any union containing types "
            f"outside the closed set."
        )

    def _validate_summary_annotation(annotation: ast.AST | None) -> str | None:
        """Validate a ``summary`` annotation; return an error message or None.

        The annotation must be present and must be EXACTLY
        ``LLMSafeEvidenceText`` (a bare name or a string forward
        reference). Any union, subscript, or qualified alternative is
        rejected. Returns ``None`` on success.
        """
        if annotation is None:
            return (
                f"{filepath}: evidence_artifact_to_llm_safe_summary.summary "
                f"parameter must be annotated as {SUMMARY_REQUIRED_TYPE}; "
                f"unannotated summary leaks raw text to the LLM."
            )
        if is_pure_llm_safe_evidence_text_annotation(annotation):
            return None
        return (
            f"{filepath}: evidence_artifact_to_llm_safe_summary.summary "
            f"parameter must be typed EXACTLY as the bare name "
            f"'{SUMMARY_REQUIRED_TYPE}' (or a string forward reference). "
            f"Found '{ast.unparse(annotation)}'. Unions, subscripts, "
            f"qualified alternatives, and any other type are rejected. "
            f"Redacted text is not automatically approved for LLM "
            f"exposure."
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "evidence_artifact_to_llm_safe_summary":
            target_found = True
            seen_summary_param = False
            seen_safe_ref_param = False

            # Keyword-only ``safe_ref`` and ``summary`` arguments. The
            # closed-union validator runs in this branch.
            for arg in node.args.kwonlyargs:
                if arg.arg == "safe_ref":
                    seen_safe_ref_param = True
                    err = _validate_safe_ref_annotation(arg.annotation)
                    if err is not None:
                        errors.append(err)
                        return errors
                if arg.arg == "summary":
                    seen_summary_param = True
                    err = _validate_summary_annotation(arg.annotation)
                    if err is not None:
                        errors.append(err)
                        return errors

            # Positional ``summary`` and ``safe_ref`` arguments. The
            # closed-union validator runs here too so a positional
            # ``safe_ref`` cannot bypass the exact-shape requirement.
            for arg in node.args.args:
                if arg.arg == "summary":
                    seen_summary_param = True
                    err = _validate_summary_annotation(arg.annotation)
                    if err is not None:
                        errors.append(err)
                        return errors
                if arg.arg == "safe_ref":
                    seen_safe_ref_param = True
                    err = _validate_safe_ref_annotation(arg.annotation)
                    if err is not None:
                        errors.append(err)
                        return errors

            # Final guardrail: a function with no ``summary`` parameter at
            # all leaks raw text to the LLM. Reject.
            if not seen_summary_param:
                errors.append(
                    f"{filepath}: evidence_artifact_to_llm_safe_summary must "
                    f"declare a 'summary' parameter typed as "
                    f"{SUMMARY_REQUIRED_TYPE}; otherwise raw text can leak "
                    f"to the LLM without any privacy-state guard."
                )
                return errors
            if not seen_safe_ref_param:
                errors.append(
                    f"{filepath}: evidence_artifact_to_llm_safe_summary must "
                    f"declare a 'safe_ref' parameter typed as a closed union of "
                    f"{{LLMSafeArtifactRef, ReviewPacketStorageRef, None}}; "
                    f"a missing safe_ref argument exposes an unbounded call-site."
                )
                return errors

    if not target_found:
        errors.append(
            f"{filepath}: missing required function "
            f"'evidence_artifact_to_llm_safe_summary'."
        )

    return errors