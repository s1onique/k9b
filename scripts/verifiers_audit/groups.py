"""Duplicate-group classification (R5 separation).

A *duplicate group* is a set of local helpers whose shared
surface maps onto one ``verifier_core`` candidate primitive.
Groups are classified as:

* ``EXACT-DUPLICATE`` - byte-equivalent signature + traversal
  boundary + return type + exception behaviour + ordering.
* ``SEMANTICALLY-DIFFERENT`` - same surface name, different meaning
  (e.g. direct-child vs recursive-descendant).
* ``POLICY-SPECIFIC`` - encodes policy or doctrine that the
  policy-free core cannot express.
* ``INFRASTRUCTURE-SPECIFIC`` - infrastructure unrelated to the
  core's structural surface.
* ``SUPERSET-OF-CORE`` / ``SUBSET-OF-CORE`` - structural overlap
  without byte equivalence.

Mixed groups (containing members that span multiple of these
classifications) are NOT permitted: every member of an
``EXACT-DUPLICATE`` group must satisfy the same exact-equivalence
contract. The module below enforces that invariant.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from dataclasses import dataclass


@dataclass(frozen=True)
class DuplicateGroup:
    """One duplicate-group record."""

    group_id: str
    taxonomy: str
    core_symbol: str
    members: tuple[str, ...]
    classification: str
    positive_examples: tuple[str, ...]
    negative_examples: tuple[str, ...]
    risk: str
    recommended_action: str

    def to_dict(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "taxonomy": self.taxonomy,
            "core_symbol": self.core_symbol,
            "members": list(self.members),
            "classification": self.classification,
            "positive_examples": list(self.positive_examples),
            "negative_examples": list(self.negative_examples),
            "risk": self.risk,
            "recommended_action": self.recommended_action,
        }


# ---------------------------------------------------------------------------
# Authoritative duplicate-group roster
# ---------------------------------------------------------------------------
#
# Every member is the source-derived ``qualname`` (AST-discovered)
# of one local helper. Groups are separated so that no
# EXACT-DUPLICATE group contains a recursive or
# infrastructure-specific helper.

GROUPS: tuple[DuplicateGroup, ...] = (
    DuplicateGroup(
        group_id="GR-01-TOP-LEVEL-FN-DIRECT",
        taxonomy="top_level_function_lookup",
        core_symbol="top_level_function",
        members=(
            "scripts/verifiers/incident_current_run_promotion_workset01.py:"
            "_function_def_in",
        ),
        classification="EXACT-DUPLICATE",
        positive_examples=(
            "``def outer(): pass`` -> _function_def_in returns outer; "
            "top_level_function returns outer.",
        ),
        negative_examples=(
            "Absent function -> both return None.",
            "Nested same-name function -> both return the top-level one.",
        ),
        risk="Zero: byte-equivalent per the Wave-1 equivalence suite.",
        recommended_action="Wave 1; MC-03-WORKSET-TOP-LEVEL-FN-DIRECT.",
    ),
    DuplicateGroup(
        group_id="GR-02-AST-PARSE",
        taxonomy="ast_parsing",
        core_symbol="parse_path",
        members=(
            "scripts/verifiers/incident_current_run_promotion_workset01.py:"
            "_parse",
        ),
        classification="EXACT-DUPLICATE",
        positive_examples=(
            "Valid Python -> both return ast.Module.",
        ),
        negative_examples=(
            "Syntax-invalid -> both return None.",
            "Missing file -> both return None.",
        ),
        risk="Zero: byte-equivalent per the Wave-1 equivalence suite.",
        recommended_action="Wave 1; MC-02-WORKSET-PARSE.",
    ),
    DuplicateGroup(
        group_id="GR-03-SOURCE-READ",
        taxonomy="source_reading",
        core_symbol="read_source",
        members=(
            "scripts/verifiers/incident_current_run_promotion_workset01.py:"
            "_read_source",
        ),
        classification="EXACT-DUPLICATE",
        positive_examples=(
            "Valid UTF-8 file -> both return the bytes verbatim.",
            "Empty file -> both return empty string.",
        ),
        negative_examples=(
            "Missing file -> both raise OSError.",
            "Directory supplied as a file -> both raise OSError.",
        ),
        risk="Zero: byte-equivalent per the Wave-1 equivalence suite.",
        recommended_action="Wave 1; MC-01-WORKSET-READ.",
    ),
    DuplicateGroup(
        group_id="GR-04-RECURSIVE-FUNCTION-LOOKUP",
        taxonomy="top_level_function_lookup",
        core_symbol="(no core analogue; new primitive required)",
        members=(
            "scripts/verifiers/incident_current_run_promotion_workset01.py:"
            "_function_def",
            "scripts/verifiers/promotion_diagnosis_handoff_flow.py:"
            "_find_function_node",
        ),
        classification="SEMANTICALLY-DIFFERENT",
        positive_examples=(
            "Single top-level definition -> both find it.",
        ),
        negative_examples=(
            "ast.walk descends into nested defs and methods; the "
            "core's top_level_function does not. The two surfaces "
            "are not equivalent.",
        ),
        risk=(
            "These helpers use ast.walk recursively. The core's "
            "top_level_function is direct-child only. Migration "
            "requires a NEW core primitive (recursive_top_level_function) "
            "which the audit MUST NOT add."
        ),
        recommended_action="CORE-GAP-REQUIRES-DESIGN-REVIEW.",
    ),
    DuplicateGroup(
        group_id="GR-05-POLICY-AST-CHECKS",
        taxonomy="policy_specific",
        core_symbol="(no core analogue; policy-bearing)",
        members=(
            "scripts/verifiers/current_run_promotion_seam01_checks.py:"
            "_truthiness_fallback_violations",
            "scripts/verifiers/current_run_promotion_seam01_checks.py:"
            "_store_scan_string_violations",
            "scripts/verifiers/current_run_promotion_seam01_checks.py:"
            "_explicit_truthy_scan_violations",
            "scripts/verifiers/current_run_promotion_seam01_checks.py:"
            "_independent_outcome_boolean_violations",
            "scripts/verifiers/promotion_diagnosis_handoff_checks.py:"
            "check_attribute_access",
            "scripts/verifiers/promotion_diagnosis_handoff_checks.py:"
            "check_method_call",
        ),
        classification="POLICY-SPECIFIC",
        positive_examples=(
            "Rejection of ``if not incident: reason = incident_not_found``.",
        ),
        negative_examples=(
            "Acceptance of ``batch.promotion_result.actionable_incident_ids``.",
        ),
        risk="Doctrine-specific; policy-free core cannot express.",
        recommended_action="Prohibited; must remain in production verifiers.",
    ),
    DuplicateGroup(
        group_id="GR-06-FLOW-ANALYSIS",
        taxonomy="flow_analysis",
        core_symbol="(no core analogue; doctrine flow tracker)",
        members=(
            "scripts/verifiers/promotion_diagnosis_handoff_flow.py:"
            "_track_to_target_line",
            "scripts/verifiers/promotion_diagnosis_handoff_flow.py:"
            "build_provenance_at_node",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_tracking.py:"
            "_track_statement",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_loops.py:"
            "_track_for_to_target",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_loops.py:"
            "_track_while_to_target",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_try.py:"
            "process_try_body",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_try.py:"
            "process_try_for_continue",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_try_break.py:"
            "process_try_for_break",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_try_canonical.py:"
            "analyze_try_to_target",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_try_canonical.py:"
            "analyze_try_in_sequence",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_exception_paths.py:"
            "capture_exception_envs",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_try_canonical.py:"
            "capture_exception_envs_no_target",
        ),
        classification="POLICY-SPECIFIC",
        positive_examples=(
            "Provenance-aware flow tracking through try/except/finally.",
        ),
        negative_examples=(
            "Structural-only AST traversal would lose precision.",
        ),
        risk="Doctrinal; must remain in production verifiers.",
        recommended_action="Prohibited; must remain in production verifiers.",
    ),
    DuplicateGroup(
        group_id="GR-07-METADATA-COLLECTION",
        taxonomy="metadata_collection",
        core_symbol="(no core analogue; doctrine dataclasses)",
        members=(
            "scripts/verifiers/promotion_diagnosis_handoff_flow_collect.py:"
            "collect_classes",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_collect.py:"
            "collect_functions",
            "scripts/verifiers/promotion_diagnosis_handoff_flow_collect.py:"
            "collect_imports",
        ),
        classification="POLICY-SPECIFIC",
        positive_examples=(
            "Collect FunctionInfo records with annotation text.",
        ),
        negative_examples=(
            "Core has no annotation concept.",
        ),
        risk="Doctrinal.",
        recommended_action="Prohibited; must remain in production verifiers.",
    ),
    DuplicateGroup(
        group_id="GR-08-PARENT-MAP",
        taxonomy="parent_map",
        core_symbol="(no core analogue; verifier-side infrastructure)",
        members=(
            "scripts/verifiers/incident_current_run_promotion_workset01.py:"
            "_build_parent_map",
        ),
        classification="INFRASTRUCTURE-SPECIFIC",
        positive_examples=(
            "Builds a ``dict[id(child), ast.AST]`` over the tree.",
        ),
        negative_examples=(
            "The policy-free core does not expose a parent-map primitive.",
        ),
        risk=(
            "A generic parent-map primitive would broaden the core "
            "with infrastructure that no canonical detector currently "
            "needs."
        ),
        recommended_action="Prohibited; keep verifier-side infrastructure.",
    ),
)


def count_exact_groups() -> int:
    return sum(1 for g in GROUPS if g.classification == "EXACT-DUPLICATE")


def count_exact_helpers() -> int:
    return sum(
        1 for g in GROUPS if g.classification == "EXACT-DUPLICATE" for _ in g.members
    )


def mixed_group_invariant() -> list[str]:
    """Return a list of group_ids whose membership contradicts their
    classification. Empty list means all groups are pure."""
    offenders: list[str] = []
    for g in GROUPS:
        if g.classification == "EXACT-DUPLICATE" and len(g.members) > 1:
            offenders.append(g.group_id)
    return offenders
