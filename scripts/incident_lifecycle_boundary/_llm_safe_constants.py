"""Contract constants for LLM-safe evidence boundary.

This module contains the type constants and patterns used by the verifier.
"""

from __future__ import annotations

import re

# Contract constants for LLM-safe evidence types
#
# The privacy-state hierarchy lives in ``incident_evidence_redaction.py``,
# the canonical privacy-state module. The facade
# ``incident_evidence_llm_safe.py`` re-exports the canonical identities
# rather than redefining them so that downstream code sees exactly the
# same static types the canonical module exposes.
#
# The verifier enforces (in strict order):
#
# 1. **Exact hierarchy edges**: each canonical alias must declare its
#    EXACT direct supertype, not merely any branded alias whose chain
#    terminates at ``str``. ``LLMSafeEvidenceText -> RawEvidenceText``
#    is forbidden even when both root at ``str``; the privacy-state
#    contract is about the chain itself, not just the terminal primitive.
#
#    Hierarchy (each row must equal ``NewType(<name>, <supertype>)`` in
#    the canonical module):
#
#       RawEvidenceText      -> str
#       RedactedEvidenceText -> str
#       LLMSafeEvidenceText  -> RedactedEvidenceText
#       SafeEvidenceExcerpt  -> LLMSafeEvidenceText
#
# 2. **Facade re-export contract**: the facade must import every
#    canonical name from the canonical module via a top-level
#    ``from canonical import <name>``. ``from somewhere import <name>``
#    and ``from canonical import SomethingElse as <name>`` are rejected
#    because they would mint a statically distinct identity behind
#    the same local name.
#
# 3. **No local NewType in the facade**: the facade must not redefine
#    any canonical alias locally with ``NewType(...)``; doing so would
#    mint a new, structurally identical but statically distinct type.
#
# 4. **Strengthened dataclass contract**:
#    ``RedactedEvidenceSummary.summary`` is typed as ``LLMSafeEvidenceText``,
#    not merely ``RedactedEvidenceText`` (redacted is not LLM-safe).
#
# All four aliases MUST be present in the canonical module and re-exported
# by the facade.
LLM_SAFE_TYPES = frozenset({
    "RawEvidenceText",
    "RedactedEvidenceText",
    "LLMSafeEvidenceText",
    "SafeEvidenceExcerpt",
})

# Expected direct supertype for each canonical alias. The verifier
# enforces each declared supertype EXACTLY: ``LLMSafeEvidenceText``
# must point at ``RedactedEvidenceText`` and NOT at ``RawEvidenceText``
# or ``str``. The chain is rooted at ``str`` by construction.
CANONICAL_NEWTYPE_SUPERTYPES: dict[str, str] = {
    "RawEvidenceText": "str",
    "RedactedEvidenceText": "str",
    "LLMSafeEvidenceText": "RedactedEvidenceText",
    "SafeEvidenceExcerpt": "LLMSafeEvidenceText",
}

# Path to the canonical privacy-state module relative to REPO_ROOT.
# The verifier scans this module for the hierarchy above; the facade
# (LLM_SAFE_FACADE_MODULE) must only re-export from it.
LLM_SAFE_CANONICAL_MODULE = (
    "src/k8s_diag_agent/collect/incident_evidence_redaction.py"
)

# Path to the facade module (re-exports) relative to REPO_ROOT.
LLM_SAFE_FACADE_MODULE = (
    "src/k8s_diag_agent/collect/incident_evidence_llm_safe.py"
)

# Required dataclass
REQUIRED_DATACLASS = "RedactedEvidenceSummary"

# Required helper functions
REQUIRED_HELPERS = frozenset({
    "make_redacted_evidence_text",
    "make_safe_evidence_excerpt",
    "evidence_artifact_to_llm_safe_summary",
})

# Modules that should NOT expose LocalArtifactPath or ExternalStorageRef
# Paths are relative to REPO_ROOT = Path("src") from common.py
LLM_REVIEW_MODULES = [
    "k8s_diag_agent/collect/incident_review_packet.py",
    "k8s_diag_agent/collect/incident_case_file.py",
    "k8s_diag_agent/collect/incident_llm_diagnosis.py",
]

# Unsafe types that should never appear in LLM-safe boundaries
UNSAFE_REF_TYPES = frozenset({
    "LocalArtifactPath",
    "ExternalStorageRef",
})

# Safe types that are allowed in LLM-safe boundaries for safe_ref
SAFE_REF_TYPES = frozenset({
    "LLMSafeArtifactRef",
    "ReviewPacketStorageRef",
    "None",
})

# Names whose module-scope rebinding at any point before a canonical
# ``NewType(...)`` declaration must invalidate the alias contract.
# This set is BROADER than :data:`PROVENANCE_SENSITIVE_NAMES` in
# :mod:`_llm_safe_provenance_types` because it also includes ``str``
# (the trusted primitive supertype) and every canonical alias name.
# R14 invariant: any conditional rebinding of any member of this set
# fails closed, and any post-declaration rebinding of a canonical
# alias name emits an immediate diagnostic.
CANONICAL_ALIAS_SENSITIVE_NAMES: frozenset[str] = frozenset(
    {
        "str",
        "RawEvidenceText",
        "RedactedEvidenceText",
        "LLMSafeEvidenceText",
        "SafeEvidenceExcerpt",
        "NewType",
        "typing",
    }
)

# Patterns that indicate unsafe access patterns in LLM/review modules
# Note: We don't flag raw_content variable names as they're commonly used for sanitization
# context variables. The ACT intent is to prevent RAW artifact content crossing the LLM
# boundary, not to flag legitimate variable naming patterns.
UNSAFE_PATTERNS = [
    # Direct storage_ref access (attribute access on objects)
    (re.compile(r"\w+\.storage_ref\b"), "direct .storage_ref access"),
    # LocalArtifactPath usage
    (re.compile(r"LocalArtifactPath"), "LocalArtifactPath"),
    # ExternalStorageRef usage
    (re.compile(r"ExternalStorageRef"), "ExternalStorageRef"),
    # Raw artifact path strings in dict literals with absolute paths
    (re.compile(r"['\"]artifact_path['\"]\s*:\s*['\"]\/"), "absolute artifact_path"),
]

__all__ = [
    "CANONICAL_ALIAS_SENSITIVE_NAMES",
    "CANONICAL_NEWTYPE_SUPERTYPES",
    "LLM_REVIEW_MODULES",
    "LLM_SAFE_CANONICAL_MODULE",
    "LLM_SAFE_FACADE_MODULE",
    "LLM_SAFE_TYPES",
    "REQUIRED_DATACLASS",
    "REQUIRED_HELPERS",
    "SAFE_REF_TYPES",
    "UNSAFE_PATTERNS",
    "UNSAFE_REF_TYPES",
]
