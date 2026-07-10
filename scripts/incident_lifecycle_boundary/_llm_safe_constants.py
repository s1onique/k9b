"""Contract constants for LLM-safe evidence boundary.

This module contains the type constants and patterns used by the verifier.
"""

from __future__ import annotations

import re

# Contract constants for LLM-safe evidence types
LLM_SAFE_TYPES = frozenset({
    "RedactedEvidenceText",
    "SafeEvidenceExcerpt",
})

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
    "LLM_REVIEW_MODULES",
    "LLM_SAFE_TYPES",
    "REQUIRED_DATACLASS",
    "REQUIRED_HELPERS",
    "SAFE_REF_TYPES",
    "UNSAFE_REF_TYPES",
    "UNSAFE_PATTERNS",
]
