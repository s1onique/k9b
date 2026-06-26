"""Contract definitions for LLM security requirements verification.

This module contains constants, patterns, and the REQCheckResult class.
Keeping these separate allows check functions to remain focused on logic.
"""

from __future__ import annotations

import re
from pathlib import Path

# File paths (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent
REGISTRY_CSV = REPO_ROOT / "docs" / "requirements" / "llm_security_requirements.csv"

# Allowed values
ALLOWED_CLAIM_CATEGORY = {"llm_security", "security", "privacy", "prompt_security"}
ALLOWED_SECURITY_DOMAIN = {
    "threat_model", "governance", "provider_boundary", "trust_levels",
    "prompt_injection", "secret_scanning", "output_handling", "data_handling",
    "data_masking", "agent_boundary", "resource_management", "audit", "ai_bom",
    "rag", "mcp", "self_hosted", "ci_gate"
}
ALLOWED_ASSURANCE_LEVEL = {"MUST", "SHOULD", "N/A"}
ALLOWED_STATUS = {"current", "planned", "deprecated", "superseded"}

# REQ ID pattern: REQ-LLMSEC-0001
REQ_ID_PATTERN = re.compile(r"^REQ-LLMSEC-\d{3,}$")

# Doc scan pattern for REQ ID references
REQ_REF_PATTERN = re.compile(r"REQ-LLMSEC-\d{3,}")

# Required columns in exact order
REQUIRED_COLUMNS = [
    "req_id", "title", "requirement_text", "claim_category", "security_domain",
    "assurance_level", "source_doc", "source_section", "status", "implementation_refs",
    "verification_refs", "owner", "freshness_policy", "notes"
]


class REQCheckResult:
    """Result of a single REQ check."""

    def __init__(self) -> None:
        self.passed = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def merge(self, other: REQCheckResult) -> None:
        if not other.passed:
            self.passed = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
