"""Contracts for docs_claim_candidates scanner.

Defines constants, enums, and result types.
"""

from __future__ import annotations

from pathlib import Path

# File paths
REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"
GENERATED_CSV_DIR = REPO_ROOT / "docs" / "claims"
GENERATED_CSV = GENERATED_CSV_DIR / "generated_claim_candidates.csv"
INVENTORY_CSV = REPO_ROOT / "docs" / "docs_inventory.csv"

# Minimum prose length to consider
MIN_PROSE_LENGTH = 30

# Claim type patterns
CLAIM_TYPE_PATTERNS: dict[str, dict[str, list[str]]] = {
    "normative": {
        "keywords": [
            r"\bmust\b", r"\bshould\b", r"\bshall\b", r"\brequired\b", r"\brequires\b",
            r"\bnever\b", r"\balways\b", r"\bonly\b", r"\bcannot\b", r"\bdo not\b",
            r"\bMUST\b", r"\bSHOULD\b", r"\bSHALL\b", r"\bREQUIRED\b",
        ],
    },
    "security": {
        "keywords": [
            r"\bauthentication\b", r"\bauthenticated\b", r"\bsession\b", r"\bcookie\b",
            r"\bHttpOnly\b", r"\bSameSite\b", r"\bSecure\b", r"\bpassword hash\b",
            r"\bPBKDF2\b", r"\btoken\b", r"\bRBAC\b", r"\bmutation\b",
            r"\bprotected route\b", r"\bCSRF\b", r"\bXSS\b", r"\binjection\b",
        ],
    },
    "api_contract": {
        "keywords": [
            r"/api/", r"\bGET\b", r"\bPOST\b", r"\bPUT\b", r"\bDELETE\b",
            r"\bendpoint\b", r"\brequest\b", r"\bresponse\b", r"\bpayload\b",
            r"\bGET /", r"\bPOST /", r"\bPUT /", r"\bDELETE /",
        ],
    },
    "config": {
        "keywords": [
            r"\bK9B_[A-Z_]+\b", r"\bHEALTH_UI_\b", r"\bKUBECONFIG\b",
            r"\benvironment variable\b", r"\bHelm value\b", r"\bdefault\b",
            r"\bflag\b", r"\boperator approval\b", r"\bsafeToAutomate\b",
            r"\bworklist\b", r"\brunbook\b", r"\btroubleshooting\b",
            r"\bsession.*timeout\b", r"\bidle.*timeout\b",
        ],
    },
    "data_model": {
        "keywords": [
            r"\blifecycle\b", r"\bstatus\b", r"\bstate\b",
            r"\baggregate root\b", r"\bobject model\b", r"\bfield\b",
            r"\bschema\b", r"\bartifact\b", r"\bEvidenceLink\b",
            r"\bIncident\b", r"\bReviewPacket\b", r"\bSnapshot\b",
            r"\bHealthRun\b", r"\brun_id\b", r"\bcluster_id\b",
            r"\bsource of truth\b", r"\bdurable source\b",
        ],
    },
    "source_of_truth": {
        "keywords": [
            r"\bsource of truth\b", r"\bdurable source\b", r"\bimmutable\b",
            r"\bwrite-once\b", r"\bappend-only\b", r"\bderived projection\b",
            r"\bconvenience alias\b", r"\bnot authoritative\b",
            r"\bimmutable source\b", r"\bderived.*alias\b",
        ],
    },
    "ci_gate": {
        "keywords": [
            r"\bverify_all\.sh\b", r"\bCI\b", r"\bgate\b", r"\bhard-gated\b",
            r"\bblocks merge\b", r"\bthreshold\b", r"\bcoverage\b",
            r"\bworkflow\b", r"\bGitHub Actions\b", r"\bruff\b",
            r"\bmypy\b", r"\bpytest\b", r"\bvitest\b", r"\bhelm lint\b",
            r"\bverification\b", r"\bself-test\b",
        ],
    },
    "performance": {
        "keywords": [
            r"\btimeout\b", r"\binterval\b", r"\bmax age\b", r"\bidle timeout\b",
            r"\bretention\b", r"\bthreshold\b", r"\bduration\b",
            r"\bseconds\b", r"\bminutes\b", r"\bmax.*\d+.*\b",
        ],
    },
}

# Severity scoring
SEVERITY_BY_TYPE: dict[str, str] = {
    "security": "high",
    "source_of_truth": "high",
    "ci_gate": "medium",
    "normative": "medium",
    "api_contract": "medium",
    "data_model": "medium",
    "config": "low",
    "performance": "low",
}

# Registration status values
REGISTRATION_STATUS_VALUES = {
    "registered",
    "unregistered",
    "ignored_historical",
    "ignored_stale",
    "ignored_low_value",
    "ignored_by_policy",
}

# Severity values
SEVERITY_VALUES = {"high", "medium", "low"}


class ScanResult:
    """Result of scanning a document."""

    def __init__(self) -> None:
        self.candidates: list[dict[str, str]] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []