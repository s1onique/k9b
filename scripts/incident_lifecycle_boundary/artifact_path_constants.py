"""Artifact path/reference type constants for the incident lifecycle boundary verifier.

This module contains:
- PATH_ALIASES: Required NewType alias names for artifact paths/references
- REQUIRED_CONSTRUCTORS: Required constructor function names
- UNSAFE_CONSTRUCTOR_PATTERNS: Regex patterns for detecting unsafe constructor usage
- LLM_REVIEW_MODULES: Modules that should NOT expose LocalArtifactPath
- VALID_STORAGE_REF_TYPES: Valid types for ArtifactStorageRef union

Design:
- SafeRelativeArtifactPath: relative paths safe for review/LLM boundaries
- LocalArtifactPath: local filesystem paths (implementation only)
- ExternalStorageRef: external storage references (s3://, gs://, etc.)
- ReviewPacketStorageRef: storage refs for review packet boundaries
- LLMSafeArtifactRef: artifact refs safe for LLM-facing outputs

Invariant:
- SafeRelativeArtifactPath is the only path-like value allowed in review-packet / LLM-safe artifact references.
- LocalArtifactPath is only used for filesystem read/write implementation details.
- ExternalStorageRef is only used for external object/storage references.
"""

from __future__ import annotations

import re

# Contract constants for path/reference aliases
PATH_ALIASES = frozenset({
    "SafeRelativeArtifactPath",
    "LocalArtifactPath",
    "ExternalStorageRef",
    "ReviewPacketStorageRef",
    "LLMSafeArtifactRef",
})

# Required constructor functions
REQUIRED_CONSTRUCTORS = frozenset({
    "make_safe_relative_artifact_path",
    "make_local_artifact_path",
    "make_external_storage_ref",
    "make_review_packet_storage_ref",
    "make_llm_safe_artifact_ref",
})

# Patterns that indicate unsafe constructor usage
UNSAFE_CONSTRUCTOR_PATTERNS = [
    # make_safe_relative_artifact_path with absolute path
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]\/"), "absolute path"),
    # make_safe_relative_artifact_path with traversal
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]\.\."), "traversal path"),
    # make_safe_relative_artifact_path with URL scheme
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]s3:\/\/"), "URL scheme (s3://)"),
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]gs:\/\/"), "URL scheme (gs://)"),
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]https?:\/\/"), "URL scheme (https://)"),
    # make_safe_relative_artifact_path with home directory
    (re.compile(r"make_safe_relative_artifact_path\s*\(\s*['\"]~"), "home directory (~)"),
    # LLMSafeArtifactRef from LocalArtifactPath (should not happen)
    (re.compile(r"LLMSafeArtifactRef\s*\(\s*str\s*\(\s*\w*local\w*path"), "LocalArtifactPath to LLMSafeArtifactRef"),
]

# Modules that should NOT expose LocalArtifactPath
LLM_REVIEW_MODULES = [
    "src/k8s_diag_agent/collect/incident_review_packet.py",
    "src/k8s_diag_agent/collect/incident_case_file.py",
    "src/k8s_diag_agent/collect/incident_llm_diagnosis.py",
]

# Valid types for ArtifactStorageRef union
VALID_STORAGE_REF_TYPES = frozenset({
    "SafeRelativeArtifactPath",
    "LocalArtifactPath",
    "ExternalStorageRef",
})

__all__ = [
    "PATH_ALIASES",
    "REQUIRED_CONSTRUCTORS",
    "UNSAFE_CONSTRUCTOR_PATTERNS",
    "LLM_REVIEW_MODULES",
    "VALID_STORAGE_REF_TYPES",
]
