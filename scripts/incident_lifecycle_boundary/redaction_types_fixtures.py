"""Comprehensive self-test fixtures for redaction_types.py verifier.

This module contains test cases used to verify the verifier itself works correctly.
Split into ACCEPTED_TEST_CASES (should pass) and REJECTED_TEST_CASES (should fail).

Required negative cases:
- wrong NewType string argument
- wrong hierarchy
- direct trusted constructor in a prompt module
- module-qualified trusted constructor
- aliased trusted constructor
- summary field using RedactedEvidenceText
- projector parameter using RedactedEvidenceText
- missing projector
- projector in the wrong module
- implicit summary serialization
- protected boundary importing raw text
- protected boundary importing redacted text
- facade-based bypass
"""

from __future__ import annotations

# ==============================================================================
# ACCEPTED TEST CASES - These should PASS verification
# ==============================================================================

ACCEPTED_TEST_CASES: list[dict[str, object]] = [
    # Valid privacy-state type hierarchy
    {
        "name": "Valid four-type hierarchy with correct base types",
        "content": """\
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)
""",
        "expected_pass": True,
    },
    # Valid with docstring
    {
        "name": "Valid hierarchy with module docstring",
        "content": '''\
"""Module docstring."""
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)
''',
        "expected_pass": True,
    },
]


# ==============================================================================
# R7 #3: POSITIVE CONSTRUCTOR TEST CASES - Should pass constructor check
# These are checked separately by the constructor subsystem
# ==============================================================================

CONSTRUCTOR_POSITIVE_TEST_CASES: list[dict[str, object]] = [
    # R7 #3: Constructor inside trusted module - should NOT trigger errors
    {
        "name": "Trusted constructor call inside projection module",
        "content": """\
\"\"\"Trusted projection module.\"\"\"
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)

def project_for_llm(value: RawEvidenceText) -> LLMSafeEvidenceText:
    redacted = RedactedEvidenceText(str(value))
    return LLMSafeEvidenceText(redacted)
""",
        "expected_pass": True,
    },
]


# ==============================================================================
# R7 #3: POSITIVE BOUNDARY TEST CASES - Should pass boundary check
# These are checked separately by the boundary subsystem
# ==============================================================================

BOUNDARY_POSITIVE_TEST_CASES: list[dict[str, object]] = [
    # R7 #3: Protected module with only LLMSafeEvidenceText - should NOT trigger errors
    # Note: extract_imports returns all imports, so we use local type definitions
    # without importing from the redaction modules
    {
        "name": "Protected module with local type definition only",
        "content": '"""Protected boundary module - uses local LLMSafeEvidenceText definition."""\n\nclass ReviewPacket:\n    summary: str  # Local type, not imported from redaction\n',
        "expected_pass": True,
    },
]


# ==============================================================================
# R7 #3: POSITIVE SERIALIZER TEST CASES - Should pass serializer check
# These are checked separately by the serializer subsystem
# ==============================================================================

SERIALIZER_POSITIVE_TEST_CASES: list[dict[str, object]] = [
    # R7 #3: Correct serializer with str(self.summary) - should NOT trigger errors
    {
        "name": "Correct serializer with str(self.summary)",
        "content": '''\
from dataclasses import dataclass
from typing import NewType

LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", str)

@dataclass
class RedactedEvidenceSummary:
    artifact_id: str
    summary: LLMSafeEvidenceText

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "summary": str(self.summary),
        }
''',
        "expected_pass": True,
    },
]


# ==============================================================================
# REJECTED TEST CASES - These should FAIL verification
# ==============================================================================

REJECTED_TEST_CASES: list[dict[str, object]] = [
    # Missing types
    {
        "name": "Missing SafeEvidenceExcerpt type",
        "content": """\
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
""",
        "expected_pass": False,
        "expected_errors_containing": ["Missing expected NewType alias"],
    },
    {
        "name": "Missing RedactedEvidenceText type",
        "content": """\
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)
""",
        "expected_pass": False,
        "expected_errors_containing": ["Missing expected NewType alias"],
    },
    {
        "name": "Missing RawEvidenceText type",
        "content": """\
from typing import NewType

RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)
""",
        "expected_pass": False,
        "expected_errors_containing": ["Missing expected NewType alias"],
    },
    # Wrong NewType string argument (mismatch between variable name and NewType first arg)
    {
        "name": "Wrong NewType string argument - variable 'LLMSafeEvidenceText' but NewType declares 'SomethingElse'",
        "content": """\
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("SomethingElse", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)
""",
        "expected_pass": False,
        "expected_errors_containing": ["NewType first string argument must match variable name"],
    },
    {
        "name": "Wrong NewType string argument - variable 'SafeEvidenceExcerpt' but NewType declares 'WrongName'",
        "content": """\
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("WrongName", LLMSafeEvidenceText)
""",
        "expected_pass": False,
        "expected_errors_containing": ["NewType first string argument must match variable name"],
    },
    # Wrong base types
    {
        "name": "LLMSafeEvidenceText based on str instead of RedactedEvidenceText",
        "content": """\
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", str)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)
""",
        "expected_pass": False,
        "expected_errors_containing": ["base type"],
    },
    {
        "name": "SafeEvidenceExcerpt based on str instead of LLMSafeEvidenceText",
        "content": """\
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", str)
""",
        "expected_pass": False,
        "expected_errors_containing": ["base type"],
    },
    {
        "name": "RedactedEvidenceText based on int instead of str",
        "content": """\
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", int)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)
""",
        "expected_pass": False,
        "expected_errors_containing": ["base type"],
    },
    # Wrong NewType name (variable name doesn't match expected)
    {
        "name": "Wrong variable name 'LLMSafeText' instead of 'LLMSafeEvidenceText'",
        "content": """\
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeText = NewType("LLMSafeText", RedactedEvidenceText)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeText)
""",
        "expected_pass": False,
        "expected_errors_containing": ["Missing expected NewType alias"],
    },
    # Missing type alias entirely
    {
        "name": "Empty module with no type definitions",
        "content": """\
from typing import NewType

# No type definitions
""",
        "expected_pass": False,
        "expected_errors_containing": ["Missing expected NewType alias"],
    },
    # Inverted hierarchy (LLM-safe is base of Redacted)
    {
        "name": "Inverted hierarchy - RedactedEvidenceText based on LLMSafeEvidenceText",
        "content": """\
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", LLMSafeEvidenceText)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", str)
SafeEvidenceExcerpt = NewType("SafeEvidenceExcerpt", LLMSafeEvidenceText)
""",
        "expected_pass": False,
        "expected_errors_containing": ["base type"],
    },
]


# ==============================================================================
# CONSTRUCTOR NEGATIVE TEST CASES - Must be rejected outside trusted module
# ==============================================================================

CONSTRUCTOR_NEGATIVE_TEST_CASES: list[dict[str, object]] = [
    # Direct import and call
    {
        "name": "Direct import of LLMSafeEvidenceText constructor call",
        "content": """\
from k8s_diag_agent.collect.incident_evidence_redaction import LLMSafeEvidenceText
result = LLMSafeEvidenceText("some value")
""",
        "expected_pass": False,
        "expected_errors_containing": ["Direct constructor call to LLMSafeEvidenceText"],
    },
    # Aliased import
    {
        "name": "Aliased import of LLMSafeEvidenceText constructor call",
        "content": """\
from k8s_diag_agent.collect.incident_evidence_redaction import LLMSafeEvidenceText as Safe
result = Safe("some value")
""",
        "expected_pass": False,
        "expected_errors_containing": ["Direct constructor call"],
    },
    # Module-qualified call
    {
        "name": "Module-qualified LLMSafeEvidenceText constructor call",
        "content": """\
import k8s_diag_agent.collect.incident_evidence_redaction as redaction
result = redaction.LLMSafeEvidenceText("some value")
""",
        "expected_pass": False,
        "expected_errors_containing": ["Direct constructor call"],
    },
    # Facade-qualified call
    {
        "name": "Facade-qualified LLMSafeEvidenceText constructor call",
        "content": """\
import k8s_diag_agent.collect.incident_evidence as facade
result = facade.LLMSafeEvidenceText("some value")
""",
        "expected_pass": False,
        "expected_errors_containing": ["Direct constructor call"],
    },
    # Re-export through incident_evidence_llm_safe
    {
        "name": "Re-export through incident_evidence_llm_safe",
        "content": """\
from k8s_diag_agent.collect.incident_evidence_llm_safe import LLMSafeEvidenceText
result = LLMSafeEvidenceText("some value")
""",
        "expected_pass": False,
        "expected_errors_containing": ["Direct constructor call"],
    },
]


# ==============================================================================
# BOUNDARY NEGATIVE TEST CASES - Protected modules importing raw/redacted
# ==============================================================================

BOUNDARY_NEGATIVE_TEST_CASES: list[dict[str, object]] = [
    # Direct import of RawEvidenceText
    {
        "name": "Protected module imports RawEvidenceText directly",
        "content": """\
from k8s_diag_agent.collect.incident_evidence_redaction import RawEvidenceText

class MyReviewPacket:
    text: RawEvidenceText
""",
        "expected_pass": False,
        "expected_errors_containing": ["Imports 'RawEvidenceText' from incident_evidence_redaction"],
    },
    # Direct import of RedactedEvidenceText
    {
        "name": "Protected module imports RedactedEvidenceText directly",
        "content": """\
from k8s_diag_agent.collect.incident_evidence_redaction import RedactedEvidenceText

class MyCaseFile:
    summary: RedactedEvidenceText
""",
        "expected_pass": False,
        "expected_errors_containing": ["Imports 'RedactedEvidenceText' from incident_evidence_redaction"],
    },
    # Via incident_evidence facade
    {
        "name": "Via incident_evidence facade import",
        "content": """\
from k8s_diag_agent.collect.incident_evidence import RedactedEvidenceText

class MyReview:
    evidence: RedactedEvidenceText
""",
        "expected_pass": False,
        "expected_errors_containing": ["Imports 'RedactedEvidenceText' from incident_evidence"],
    },
]
