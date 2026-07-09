"""Evidence type contract: stable constants and expected values.

This module defines the stable public contract for evidence role/kind codes.
These values are derived from the EvidenceRole and EvidenceKind enums.
"""

from __future__ import annotations

# Alias names as they appear in the evidence module
EVIDENCE_ROLE_ALIAS = "EvidenceRoleCode"
EVIDENCE_KIND_ALIAS = "EvidenceKindCode"

# Stable public contract for evidence roles (derived from EvidenceRole enum)
EXPECTED_EVIDENCE_ROLES: frozenset[str] = frozenset({
    "primary",
    "supporting",
    "snapshot",
    "review_packet",
    "debug",
})

# Stable public contract for evidence kinds (derived from EvidenceKind enum)
EXPECTED_EVIDENCE_KINDS: frozenset[str] = frozenset({
    "snapshot_bundle",
    "review_packet",
    "log_excerpt",
    "metric_window",
    "trace",
    "run_summary",
    "external_analysis",
})

# Evidence-adjacent dict keys that indicate this is an evidence payload
EVIDENCE_DICT_KEYS: frozenset[str] = frozenset({
    "artifact_id",
    "evidence_id",
    "incident_id",
    "storage_ref",
    "content_hash",
    "collected_by",
    "redaction_status",
    "evidence_links",
    "evidence_artifacts",
    "evidence_role",
    "evidence_kind",
})

# Known evidence module paths (relative to src/)
EVIDENCE_MODULE_PATTERNS: frozenset[str] = frozenset({
    "k8s_diag_agent/collect/incident_evidence.py",
    "k8s_diag_agent/collect/incident_bundle_promotion.py",
    "k8s_diag_agent/collect/incident_review_packet.py",
    "k8s_diag_agent/collect/incident_store.py",
    "k8s_diag_agent/collect/incident_store_sqlite.py",
})

__all__ = [
    "EVIDENCE_ROLE_ALIAS",
    "EVIDENCE_KIND_ALIAS",
    "EXPECTED_EVIDENCE_ROLES",
    "EXPECTED_EVIDENCE_KINDS",
    "EVIDENCE_DICT_KEYS",
    "EVIDENCE_MODULE_PATTERNS",
]
