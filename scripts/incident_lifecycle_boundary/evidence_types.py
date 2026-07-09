"""Evidence type alias checks for the incident lifecycle boundary verifier.

This module verifies that evidence role/kind values crossing the incident
boundary are defined as closed typed aliases.

Thin compatibility facade; implementation lives in focused modules.

Context-aware scanning:
- Only flags role/kind in evidence-specific contexts (EvidenceLink, EvidenceArtifact, dicts with evidence keys)
- Ignores LLM/chat roles (system, user) and Kubernetes object kinds (Pod, etc.)
"""

from __future__ import annotations

import sys

from .evidence_types_contract import (  # noqa: I001
    EVIDENCE_DICT_KEYS,
    EVIDENCE_KIND_ALIAS,
    EVIDENCE_MODULE_PATTERNS,
    EVIDENCE_ROLE_ALIAS,
    EXPECTED_EVIDENCE_KINDS,
    EXPECTED_EVIDENCE_ROLES,
)
from .evidence_types_rules import (  # noqa: I001
    check_evidence_type_aliases,
    check_evidence_type_contract,
)
from .evidence_types_scan import (  # noqa: I001
    check_evidence_dataclass_field_types,
    check_evidence_literal_usage,
    extract_evidence_kind_values,
    extract_evidence_role_values,
)

__all__ = [
    # Contract constants
    "EVIDENCE_DICT_KEYS",
    "EVIDENCE_KIND_ALIAS",
    "EVIDENCE_MODULE_PATTERNS",
    "EVIDENCE_ROLE_ALIAS",
    "EXPECTED_EVIDENCE_KINDS",
    "EXPECTED_EVIDENCE_ROLES",
    # Scan functions
    "extract_evidence_role_values",
    "extract_evidence_kind_values",
    "check_evidence_dataclass_field_types",
    "check_evidence_literal_usage",
    # Rules functions
    "check_evidence_type_aliases",
    "check_evidence_type_contract",
]


if __name__ == "__main__":
    # Direct execution of this file is a no-op; use evidence_types_cli for actual verification.
    # This file is a public compatibility facade for importing the verification functions.
    sys.exit(0)
