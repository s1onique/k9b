"""Deterministic content quality helper for incident reports.

This module provides deterministic rules for validating incident report content quality.
It is NOT an LLM judge - these are simple, explainable pattern checks.

Quality rules enforced:
1. observed claims do not contain causal/root-cause language
2. derived claims do not contain unsupported causal/root-cause language
3. hypotheses must have non-empty basis
4. unknowns must have whyMissing explanation
5. recommendations are separated from findings (not action verbs in facts/derived)
6. section headings are concise
7. claim statements are reasonably short
8. no generic filler phrases
9. report has full degraded shape (facts, derived, inferences, unknowns, recommendations)

These rules prevent report content from becoming:
- verbose
- causally overconfident
- operator-hostile
- missing critical sections
"""

from __future__ import annotations

from typing import Any, TypedDict

# ============================================================================
# Quality Rule Types
# ============================================================================


class QualityRuleResult(TypedDict):
    """Result of a single quality rule check."""
    rule: str
    passed: bool
    message: str


class ContentQualityReport(TypedDict):
    """Complete quality report for an incident report."""
    passed: bool
    total_rules: int
    passed_rules: int
    failed_rules: int
    results: list[QualityRuleResult]


# ============================================================================
# Forbidden patterns for causal/root-cause language in observed/derived claims
# ============================================================================

CAUSAL_PHRASES = [
    "root cause",
    "caused by",
    "because of",
    "is the cause",
    "the cause of",
    "directly caused",
    "responsible for",
]

FILLER_PHRASES = [
    "the system has identified",
    "potentially relevant diagnostic indicators",
    "it is recommended that",
    "various issues",
    "multiple issues detected",
    "several problems found",
    "numerous concerns",
    "extensive investigation needed",
    "further analysis required",
]

# Action verb prefixes that indicate recommendations should not appear in findings
ACTION_PREFIXES = (
    "check ",
    "collect ",
    "review ",
    "inspect ",
    "investigate ",
    "analyze ",
    "monitor ",
)

# Phrases indicating recommendation-like content that should not be in findings
RECOMMENDATION_PHRASES_IN_FINDINGS = [
    "recommended action",
    "next action",
    "it is recommended that",
    "it is suggested that",
    "recommended next",
    "suggested action",
]


# ============================================================================
# Quality Rules
# ============================================================================


def _check_observed_no_causal_language(
    claims: list[dict[str, Any]],
) -> QualityRuleResult:
    """Rule: observed claims must not contain causal/root-cause language."""
    violations: list[str] = []
    for claim in claims:
        statement = claim.get("statement", "").lower()
        for phrase in CAUSAL_PHRASES:
            if phrase in statement:
                violations.append(f"observed claim contains '{phrase}': {claim.get('statement', '')[:80]}")
    
    passed = len(violations) == 0
    return QualityRuleResult(
        rule="observed_no_causal_language",
        passed=passed,
        message="observed claims contain causal language" if violations else "no causal language in observed claims",
    )


def _check_derived_no_causal_language(
    claims: list[dict[str, Any]],
) -> QualityRuleResult:
    """Rule: derived claims must not contain unsupported causal/root-cause language."""
    violations: list[str] = []
    for claim in claims:
        statement = claim.get("statement", "").lower()
        for phrase in CAUSAL_PHRASES:
            if phrase in statement:
                violations.append(f"derived claim contains '{phrase}': {claim.get('statement', '')[:80]}")
    
    passed = len(violations) == 0
    return QualityRuleResult(
        rule="derived_no_causal_language",
        passed=passed,
        message="derived claims contain causal language" if violations else "no causal language in derived claims",
    )


def _check_hypotheses_have_basis(
    claims: list[dict[str, Any]],
) -> QualityRuleResult:
    """Rule: hypothesis claims must have non-empty basis."""
    violations: list[str] = []
    for claim in claims:
        basis = claim.get("basis", [])
        if not basis or len(basis) == 0:
            violations.append(f"hypothesis lacks basis: {claim.get('statement', '')[:80]}")
    
    passed = len(violations) == 0
    return QualityRuleResult(
        rule="hypotheses_have_basis",
        passed=passed,
        message="some hypotheses lack basis" if violations else "all hypotheses have basis",
    )


def _check_unknowns_have_why_missing(
    claims: list[dict[str, Any]],
) -> QualityRuleResult:
    """Rule: unknown claims must have whyMissing explanation."""
    violations: list[str] = []
    for claim in claims:
        why_missing = claim.get("whyMissing")
        if why_missing is None or why_missing == "":
            violations.append(f"unknown lacks whyMissing: {claim.get('statement', '')[:80]}")
    
    passed = len(violations) == 0
    return QualityRuleResult(
        rule="unknowns_have_why_missing",
        passed=passed,
        message="some unknowns lack whyMissing" if violations else "all unknowns have whyMissing",
    )


def _check_recommendations_separated_from_findings(
    report: dict[str, Any],
) -> QualityRuleResult:
    """Rule: recommendations are under 'Recommended next actions', NOT mixed with findings.
    
    Requirements:
    1. At least one structured recommendation OR legacy recommendedActions must exist
    2. Findings (facts, derived) must NOT contain action-shaped statements
    3. Findings must NOT contain recommendation-like phrasing
    """
    has_structured = bool(report.get("recommendations"))
    has_legacy = bool(report.get("recommendedActions"))
    
    violations: list[str] = []
    
    # Check that recommendations exist
    if not (has_structured or has_legacy):
        violations.append("no recommendations present (structured or legacy)")
    
    # Check that findings don't contain action-shaped content
    for claim in report.get("facts", []) + report.get("derived", []):
        statement = claim.get("statement", "")
        statement_lower = statement.lower()
        
        # Check for action verb prefixes
        if statement_lower.startswith(ACTION_PREFIXES):
            violations.append(
                f"finding contains action verb: '{statement[:60]}...'"
            )
        
        # Check for recommendation phrases
        for phrase in RECOMMENDATION_PHRASES_IN_FINDINGS:
            if phrase in statement_lower:
                violations.append(
                    f"finding contains recommendation phrase '{phrase}': '{statement[:60]}...'"
                )
    
    passed = len(violations) == 0
    return QualityRuleResult(
        rule="recommendations_separated",
        passed=passed,
        message="; ".join(violations) if violations else "recommendations properly separated from findings",
    )


def _check_section_headings_concise(
    report: dict[str, Any],
) -> QualityRuleResult:
    """Rule: section headings remain concise (under 50 characters)."""
    headings = [
        "Observed evidence",
        "Deterministic conclusions",
        "Hypotheses",
        "Unknowns / not proven yet",
        "Recommended next actions",
    ]
    
    violations: list[str] = []
    for heading in headings:
        if len(heading) > 50:
            violations.append(f"heading too long ({len(heading)} chars): {heading}")
    
    passed = len(violations) == 0
    return QualityRuleResult(
        rule="section_headings_concise",
        passed=passed,
        message=f"{len(violations)} headings exceed 50 chars" if violations else "section headings are concise",
    )


def _check_claim_statements_reasonably_short(
    report: dict[str, Any],
) -> QualityRuleResult:
    """Rule: claim statements are reasonably short (under 200 characters).
    
    Checks: facts, derived, inferences, unknowns, recommendations, and legacy recommendedActions.
    """
    MAX_STATEMENT_LENGTH = 200
    
    violations: list[str] = []
    for category in ["facts", "derived", "inferences", "unknowns", "recommendations"]:
        claims = report.get(category, [])
        for claim in claims:
            statement = claim.get("statement", "")
            if len(statement) > MAX_STATEMENT_LENGTH:
                violations.append(
                    f"{category[:-1]} statement too long ({len(statement)} chars): {statement[:80]}..."
                )
    
    # Also check legacy recommendedActions strings
    for i, action in enumerate(report.get("recommendedActions", [])):
        if isinstance(action, str) and len(action) > MAX_STATEMENT_LENGTH:
            violations.append(
                f"legacy action too long ({len(action)} chars): {action[:80]}..."
            )
    
    passed = len(violations) == 0
    return QualityRuleResult(
        rule="claim_statements_short",
        passed=passed,
        message=f"{len(violations)} statements exceed {MAX_STATEMENT_LENGTH} chars" if violations else "all statements reasonably short",
    )


def _check_no_filler_phrases(
    report: dict[str, Any],
) -> QualityRuleResult:
    """Rule: no generic filler phrases in claim statements.
    
    Checks: facts, derived, inferences, unknowns, recommendations, and legacy recommendedActions.
    """
    violations: list[str] = []
    
    for category in ["facts", "derived", "inferences", "unknowns", "recommendations"]:
        claims = report.get(category, [])
        for claim in claims:
            statement = claim.get("statement", "")
            statement_lower = statement.lower()
            for phrase in FILLER_PHRASES:
                if phrase in statement_lower:
                    violations.append(
                        f"{category[:-1]} contains filler phrase '{phrase}': {statement[:80]}"
                    )
    
    # Also check legacy recommendedActions strings
    for i, action in enumerate(report.get("recommendedActions", [])):
        if isinstance(action, str):
            action_lower = action.lower()
            for phrase in FILLER_PHRASES:
                if phrase in action_lower:
                    violations.append(
                        f"legacy action contains filler phrase '{phrase}': {action[:80]}"
                    )
    
    passed = len(violations) == 0
    return QualityRuleResult(
        rule="no_filler_phrases",
        passed=passed,
        message=f"found {len(violations)} filler phrases" if violations else "no filler phrases present",
    )


def _check_report_has_full_degraded_shape(
    report: dict[str, Any],
    require_complete_degraded_shape: bool = True,
) -> QualityRuleResult:
    """Rule: report answers what is observed, derived, hypothesized, unknown, recommended.
    
    For degraded golden fixtures, all five sections must be present.
    For healthy/partial reports, use require_complete_degraded_shape=False.
    """
    has_facts = bool(report.get("facts"))
    has_derived = bool(report.get("derived"))
    has_inferences = bool(report.get("inferences"))
    has_unknowns = bool(report.get("unknowns"))
    has_recommendations = bool(report.get("recommendations")) or bool(report.get("recommendedActions"))
    
    missing_sections: list[str] = []
    if not has_facts:
        missing_sections.append("facts")
    if not has_derived:
        missing_sections.append("derived")
    if not has_inferences:
        missing_sections.append("inferences")
    if not has_unknowns:
        missing_sections.append("unknowns")
    if not has_recommendations:
        missing_sections.append("recommendations")
    
    if require_complete_degraded_shape:
        passed = len(missing_sections) == 0
        return QualityRuleResult(
            rule="report_has_full_degraded_shape",
            passed=passed,
            message=f"missing sections: {', '.join(missing_sections)}" if missing_sections else "report has full degraded shape",
        )
    else:
        # Non-strict mode: report must have at least one section
        has_any_content = has_facts or has_derived or has_inferences or has_unknowns or has_recommendations
        return QualityRuleResult(
            rule="report_has_content",
            passed=has_any_content,
            message="report has content covering core questions" if has_any_content else "report appears empty",
        )


# ============================================================================
# Main quality check function
# ============================================================================


def check_incident_report_quality(
    report: dict[str, Any],
    require_complete_degraded_shape: bool = True,
) -> ContentQualityReport:
    """Run all quality checks on an incident report payload.
    
    Args:
        report: IncidentReportPayload as dict
        require_complete_degraded_shape: If True (default), all five sections must be present.
            Set to False for healthy/partial reports.
        
    Returns:
        ContentQualityReport with all rule results
        
    This function is deterministic - same input always produces same output.
    """
    rules = [
        _check_observed_no_causal_language(report.get("facts", [])),
        _check_derived_no_causal_language(report.get("derived", [])),
        _check_hypotheses_have_basis(report.get("inferences", [])),
        _check_unknowns_have_why_missing(report.get("unknowns", [])),
        _check_recommendations_separated_from_findings(report),
        _check_section_headings_concise(report),
        _check_claim_statements_reasonably_short(report),
        _check_no_filler_phrases(report),
        _check_report_has_full_degraded_shape(report, require_complete_degraded_shape),
    ]
    
    passed_rules = sum(1 for r in rules if r["passed"])
    failed_rules = len(rules) - passed_rules
    
    return ContentQualityReport(
        passed=failed_rules == 0,
        total_rules=len(rules),
        passed_rules=passed_rules,
        failed_rules=failed_rules,
        results=rules,
    )


def check_claim_has_no_causal_language(
    claim_type: str,
    claim: dict[str, Any],
) -> QualityRuleResult:
    """Check if a single claim has causal language (for negative tests).
    
    Args:
        claim_type: Type of claim (observed, derived, hypothesis, etc.)
        claim: The claim dict to check
        
    Returns:
        QualityRuleResult indicating whether causal language was found
    """
    statement = claim.get("statement", "").lower()
    found_phrases = []
    
    for phrase in CAUSAL_PHRASES:
        if phrase in statement:
            found_phrases.append(phrase)
    
    if found_phrases:
        return QualityRuleResult(
            rule="causal_language_check",
            passed=False,
            message=f"claim contains causal language: {found_phrases} - {statement[:80]}",
        )
    
    return QualityRuleResult(
        rule="causal_language_check",
        passed=True,
        message="no causal language found",
    )
