"""Structural-helper taxonomy constants.

The audit classifies every discovered local helper into one of the
following structural families. Policy-specific helpers are
classified as ``NON-STRUCTURAL`` and reported separately so they do
not pollute the structural helper ledger.

The taxonomy is intentionally narrow and policy-free; the
verifier_core package has no ``ast`` policy primitives.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"

# Structural families (the 20 named in the ACT scope, reduced to
# the families that actually appear in the verifier estate).
STRUCTURAL_FAMILIES: tuple[str, ...] = (
    "source_reading",
    "ast_parsing",
    "top_level_function_lookup",
    "class_method_lookup",
    "function_body_extraction",
    "direct_name_load_detection",
    "direct_call_detection",
    "keyword_argument_extraction",
    "source_location_extraction",
    "immediate_statement_value_extraction",
    "nested_function_detection",
    "lambda_detection",
    "compound_statement_inspection",
    "star_argument_detection",
    "dynamic_lookup_detection",
    "partial_application_detection",
    "callable_in_collection_detection",
    "diagnostic_ordering",
    "violation_formatting",
    "cli_source_loading",
)

# Non-structural helpers are not migration candidates. They are
# policy-bearing or doctrine-specific and must stay in their
# production verifier files.
NON_STRUCTURAL_FAMILIES: tuple[str, ...] = (
    "policy_specific",
    "infrastructure_specific",
    "doctrine_specific",
    "flow_analysis",
    "parent_map",
    "metadata_collection",
    "provenance_tracking",
    "exception_flow",
    "type_identity_check",
    "non_structural_helper",
)
