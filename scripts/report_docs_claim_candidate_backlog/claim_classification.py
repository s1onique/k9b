"""Claim classification logic for documentation claim candidate backlog reporter."""

from __future__ import annotations

import re

# =============================================================================
# High-confidence claim signals
# =============================================================================

# High-confidence claim signals (strong indicators of real behavioral claims)
# These can classify as claim_candidate if no exclusion marker applies
HIGH_CONFIDENCE_SIGNALS: list[str] = [
    "must not",
    "cannot",
    "no mutation",
    "read-only",
    "append-only",
    "immutable",
    "source of truth",
    "authenticated",
    "authorization",
    "production evidence",
    "verifier",
    "gate",
    "reject",
    "must reject",
    "must validate",
    "must sanitize",
    "must redact",
    "must block",
    "must deny",
    "must forbid",
]


# =============================================================================
# Broad normative signals
# =============================================================================

# Broad normative signals (common words that alone are NOT enough)
# These require claim-shaped context AND no exclusion markers
BROAD_NORMATIVE_SIGNALS: list[str] = [
    "must",
    "required",
    "never",
    "only",
    "invariant",
    "append-only",
    "immutable",
    "read-only",
]


# =============================================================================
# Claim shape terms
# =============================================================================

# System behavior subjects that give prose "claim shape"
# A broad signal near these terms suggests a real behavioral claim
SYSTEM_SUBJECT_TERMS: list[str] = [
    "system",
    "agent",
    "backend",
    "server",
    "api",
    "ui",
    "artifact",
    "incident",
    "run",
    "snapshot",
    "review packet",
    "evidence",
    "cluster",
    "operator",
    "authentication",
    "authorization",
    "checks",
    "validation",
    "verifier",
    "gate",
    "pipeline",
    "workflow",
    "queue",
    "job",
    "task",
    "request",
    "response",
    "payload",
    "credential",
    "token",
    "secret",
    "config",
    "manifest",
]

# Enforceable action terms that give prose "claim shape"
ACTION_TERMS: list[str] = [
    "reject",
    "require",
    "validate",
    "redact",
    "sanitize",
    "persist",
    "store",
    "emit",
    "serve",
    "block",
    "forbid",
    "allow",
    "deny",
    "verify",
    "fail",
    "pass",
    "generate",
    "load",
    "write",
    "read",
    "delete",
    "create",
    "update",
    "submit",
    "process",
    "check",
    "enforce",
    "ensure",
    "guarantee",
    "protect",
    "secure",
    "authenticate",
    "authorize",
]


# =============================================================================
# Exclusion marker patterns
# =============================================================================

# Exclusion marker patterns (meta-documentation, policy, design/future, etc.)
# If any of these apply, the row should NOT be claim_candidate
EXCLUSION_MARKER_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    # Meta-documentation about the claims system itself
    ("meta:truthfulness_doc", "meta-documentation about claims system", re.compile(
        r"documentation-truthfulness", re.IGNORECASE
    )),
    ("meta:claim_scanner", "meta-documentation about claim scanner", re.compile(
        r"claim\s*scanner|claim\s*candidate|claim\s*disposition|claim\s*registry|"
        r"claim\s*traceability|claim\s*backlog|claim\s*verifier", re.IGNORECASE
    )),
    ("meta:evidence_status", "meta-documentation about evidence status", re.compile(
        r"evidence[_ ]status|docs[_ ]claim", re.IGNORECASE
    )),
    # Policy/process/backlog notes
    ("policy:backlog", "backlog or worklist item", re.compile(
        r"backlog|worklist|pending|todo|deferred|deprecated", re.IGNORECASE
    )),
    ("policy:acceptance", "acceptance criteria or policy statement", re.compile(
        r"acceptance\s*criteria|acceptance\s*criterion", re.IGNORECASE
    )),
    ("policy:priority", "priority or severity indicator", re.compile(
        r"priority|p[0-4]|severity|critical|major|minor|blocker", re.IGNORECASE
    )),
    ("policy:process", "process or guidance note", re.compile(
        r"guidance|guideline|playbook|process|procedure|workflow\s*note", re.IGNORECASE
    )),
    # Design/future/deferred statements
    ("design:future", "design note or future consideration", re.compile(
        r"design\s*note|design\s*intent|future\s*note|optional|planned|"
        r"nice\s*to\s*have|not\s*implemented|deferred|roadmap", re.IGNORECASE
    )),
    ("design:impact", "impact scan or design review item", re.compile(
        r"impact[_\-]?scan|behavior\s*risk|design\s*review|impact-scan-ledger", re.IGNORECASE
    )),
    # Schema/table/field structural fragments
    ("schema:table", "table cell or row", re.compile(
        r"table\s*cell|table\s*row|table\s*header|column\s*label", re.IGNORECASE
    )),
    ("schema:field", "schema field or enum value", re.compile(
        r"schema\s*field|field\s*label|enum\s*value|column|header", re.IGNORECASE
    )),
    # Example/exemplar content
    ("example:exemplar", "example or exemplar content", re.compile(
        r"example|exemplar|sample|illustrative|for\s*instance", re.IGNORECASE
    )),
    # Implementation details
    ("impl:detail", "implementation detail", re.compile(
        r"implementation\s*detail|internal\s*note|internal\s*comment", re.IGNORECASE
    )),
    # CI/gate drift documentation (meta about the gate system)
    ("ci:gate_doc", "CI gate drift documentation", re.compile(
        r"gate.*not\s*represented|gate.*covered\s*by|gate.*purpose|"
        r"cigatemapping|requiredgates|ci-gate-drift|gate-timings", re.IGNORECASE
    )),
    # Path security doctrine (meta-documentation about security gates)
    ("doctrine:path_security", "path security doctrine", re.compile(
        r"path-security-doctrine", re.IGNORECASE
    )),
    # Reviewer guidance/process documents
    ("doctrine:reviewer_guidance", "reviewer guidance", re.compile(
        r"reviewer\s*check|reviewer\s*guidance|seed\s*rules|blockstor-derived", re.IGNORECASE
    )),
]


# =============================================================================
# Classification helpers
# =============================================================================

def _has_high_confidence_signal(candidate_text: str) -> list[str]:
    """Check if candidate text contains high-confidence claim signals.
    
    Returns list of signal tags found.
    """
    text_lower = candidate_text.lower()
    signals: list[str] = []
    
    for signal in HIGH_CONFIDENCE_SIGNALS:
        # Multi-word signals need exact match
        if " " in signal:
            if signal in text_lower:
                signals.append(f"high_conf_signal:{signal}")
        else:
            # Single word - use word boundary
            if re.search(rf"\b{re.escape(signal)}\b", text_lower):
                signals.append(f"high_conf_signal:{signal}")
    
    return signals


def _has_broad_normative_signal(candidate_text: str) -> list[str]:
    """Check if candidate text contains broad normative signals.
    
    Returns list of signal tags found.
    
    NOTE: These signals alone are NOT enough to classify as claim_candidate.
    They require claim-shaped context and no exclusion markers.
    """
    text_lower = candidate_text.lower()
    signals: list[str] = []
    
    for signal in BROAD_NORMATIVE_SIGNALS:
        # Use word boundary for single words
        if re.search(rf"\b{re.escape(signal)}\b", text_lower):
            signals.append(f"broad_signal:{signal}")
    
    return signals


def _has_claim_shape(candidate_text: str) -> tuple[bool, list[str]]:
    """Check if candidate text has claim-shaped context.
    
    Returns (has_shape, shape_tags).
    
    Claim shape means the prose describes system behavior rather than
    documentation policy, schema semantics, or generic principles.
    """
    text_lower = candidate_text.lower()
    shape_tags: list[str] = []
    
    # Check for system subject terms
    for term in SYSTEM_SUBJECT_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", text_lower):
            shape_tags.append(f"subject:{term}")
    
    # Check for enforceable action terms
    for term in ACTION_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", text_lower):
            shape_tags.append(f"action:{term}")
    
    return len(shape_tags) > 0, shape_tags


def _has_exclusion_marker(
    notes: str,
    candidate_text: str,
    doc_path: str,
) -> tuple[bool, list[str]]:
    """Check if candidate has an exclusion marker.
    
    Returns (has_exclusion, exclusion_tags).
    
    Exclusion markers indicate the row is structural, meta-documentation,
    policy/process, design/future, example, or implementation detail.
    """
    combined = f"{notes} {candidate_text} {doc_path}".lower()
    exclusion_tags: list[str] = []
    
    for pattern_id, description, pattern in EXCLUSION_MARKER_PATTERNS:
        if pattern.search(combined):
            exclusion_tags.append(f"excluded:{pattern_id}")
    
    return len(exclusion_tags) > 0, exclusion_tags


def classify_claim_candidate(
    candidate_text: str,
    notes: str,
    doc_path: str,
) -> tuple[bool, list[str]]:
    """Determine if a candidate should be classified as claim_candidate.
    
    Returns (is_claim_candidate, reason_tags).
    
    Rules:
    1. High-confidence signal + no exclusion = claim_candidate
    2. Broad signal + claim shape + no exclusion = claim_candidate
    3. Otherwise = not claim_candidate
    """
    # Check for exclusion markers first (they override everything)
    has_exclusion, exclusion_tags = _has_exclusion_marker(notes, candidate_text, doc_path)
    
    # Check high-confidence signals
    high_conf_signals = _has_high_confidence_signal(candidate_text)
    
    if high_conf_signals:
        # High-confidence signal found
        if has_exclusion:
            # Exclusion overrides even high-confidence signals
            return False, exclusion_tags + high_conf_signals + ["blocked:exclusion_overrides_high_conf"]
        else:
            # High-confidence signal without exclusion = claim_candidate
            return True, high_conf_signals
    
    # Check broad normative signals
    broad_signals = _has_broad_normative_signal(candidate_text)
    
    if broad_signals:
        # Broad signal found - need claim shape and no exclusion
        has_shape, shape_tags = _has_claim_shape(candidate_text)
        
        if has_exclusion:
            return False, exclusion_tags + broad_signals + ["blocked:exclusion"]
        
        if has_shape:
            # Broad signal + claim shape + no exclusion = claim_candidate
            return True, broad_signals + shape_tags
        else:
            # Broad signal without claim shape = not claim_candidate
            return False, broad_signals + ["blocked:no_claim_shape"]
    
    # No claim signals found
    return False, ["no_claim_signal"]