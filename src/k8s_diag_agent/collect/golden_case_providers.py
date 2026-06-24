"""Golden-case offline providers for testing production diagnosis machinery.

This module re-exports from the split modules for backward compatibility.
See the individual modules for full implementation details:
- golden_case_providers_constants: Shared constants and patterns
- golden_case_evidence_provider: GoldenCaseEvidenceProvider class
- golden_case_fake_handlers: Fake handlers for golden-case evidence
- golden_case_deterministic_diagnosis: DeterministicDiagnosisProvider
"""

from __future__ import annotations

from .golden_case_deterministic_diagnosis import (
    DeterministicDiagnosisProvider,
    build_deterministic_diagnosis,
)
from .golden_case_evidence_provider import GoldenCaseEvidenceProvider
from .golden_case_fake_handlers import (
    GoldenCaseFakeHandlers,
    create_golden_case_fake_handlers,
)

__all__ = [
    "GoldenCaseEvidenceProvider",
    "GoldenCaseFakeHandlers",
    "create_golden_case_fake_handlers",
    "DeterministicDiagnosisProvider",
    "build_deterministic_diagnosis",
]
