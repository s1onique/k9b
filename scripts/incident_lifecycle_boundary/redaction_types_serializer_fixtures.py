"""Serializer-specific test fixtures for redaction_types verifier.

R8 split from redaction_types_fixtures.py to keep file sizes bounded.
"""

from __future__ import annotations

# ==============================================================================
# SERIALIZER NEGATIVE TEST CASES - Missing explicit str() conversion
# R8 #4: Missing summary key now causes failure
# ==============================================================================

SERIALIZER_NEGATIVE_TEST_CASES: list[dict[str, object]] = [
    # Missing summary field in to_dict (has field but doesn't include it)
    # R8 #4: Expected to FAIL because summary key is missing from returned dict
    {
        "name": "to_dict missing summary key",
        "content": '''\
from dataclasses import dataclass

@dataclass
class RedactedEvidenceSummary:
    artifact_id: str
    kind: str
    summary: str

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            # Missing summary field entirely
        }
''',
        "expected_pass": False,
        "expected_errors_containing": ["summary", "Missing"],
    },
    # self.summary without str() conversion
    {
        "name": "to_dict uses self.summary without str() conversion",
        "content": '''\
from dataclasses import dataclass

@dataclass
class RedactedEvidenceSummary:
    artifact_id: str
    kind: str
    summary: str

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "summary": self.summary,  # Missing str() conversion
        }
''',
        "expected_pass": False,
        "expected_errors_containing": ["must use"],
    },
    # Unrelated str(self.artifact_id) only
    {
        "name": "to_dict uses unrelated str(self.artifact_id) but not str(self.summary)",
        "content": '''\
from dataclasses import dataclass

@dataclass
class RedactedEvidenceSummary:
    artifact_id: str
    kind: str
    summary: str

    def to_dict(self):
        return {
            "artifact_id": str(self.artifact_id),
            "kind": self.kind,
            "summary": self.summary,  # Missing str() conversion
        }
''',
        "expected_pass": False,
        "expected_errors_containing": ["must use"],
    },
    # R8 #4: Only artifact_id returned, no summary at all
    {
        "name": "to_dict returns only artifact_id (no summary)",
        "content": '''\
from dataclasses import dataclass

@dataclass
class RedactedEvidenceSummary:
    artifact_id: str
    kind: str
    summary: str

    def to_dict(self):
        return {"artifact_id": str(self.artifact_id)}
''',
        "expected_pass": False,
        "expected_errors_containing": ["summary", "Missing"],
    },
    # R8 #4: str(self.summary) after the return statement (outside dict)
    {
        "name": "to_dict has bare str(self.summary) outside dict",
        "content": '''\
from dataclasses import dataclass

@dataclass
class RedactedEvidenceSummary:
    artifact_id: str
    kind: str
    summary: str

    def to_dict(self):
        result = {"artifact_id": self.artifact_id}
        unused = str(self.summary)
        return result
''',
        "expected_pass": False,
        "expected_errors_containing": ["summary", "Missing"],
    },
]
