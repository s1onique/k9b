"""Tests for LLM-safe evidence boundary checks.

ACT-K9B-HULK-LLM-SAFE-EVIDENCE-BOUNDARY01.
"""

from __future__ import annotations

from pathlib import Path

from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
    LLM_SAFE_TYPES,
    REQUIRED_DATACLASS,
    REQUIRED_HELPERS,
    extract_dataclass_names,
    extract_function_definitions,
    extract_newtype_aliases,
)

REPO_ROOT = Path(__file__).parent.parent.parent
# EVIDENCE_LLM_SAFE_MODULE is the actual defining module for LLM-safe types
EVIDENCE_LLM_SAFE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_llm_safe.py"


class TestExtractNewTypeAliases:
    """Tests for NewType alias extraction."""

    def test_extracts_from_actual_llm_safe_module(self) -> None:
        """Extracts values from actual incident_evidence_llm_safe.py."""
        aliases = extract_newtype_aliases(str(EVIDENCE_LLM_SAFE_MODULE))
        assert "RedactedEvidenceText" in aliases
        assert aliases["RedactedEvidenceText"] == "str"

    def test_extracts_all_expected_aliases(self) -> None:
        """Extracts all expected NewType aliases."""
        aliases = extract_newtype_aliases(str(EVIDENCE_LLM_SAFE_MODULE))
        for expected_alias in LLM_SAFE_TYPES:
            assert expected_alias in aliases, f"Missing alias: {expected_alias}"
            assert aliases[expected_alias] == "str"

    def test_returns_empty_for_missing_file(self) -> None:
        """Returns empty dict for missing file."""
        aliases = extract_newtype_aliases("/nonexistent/file.py")
        assert aliases == {}


class TestExtractDataclassNames:
    """Tests for dataclass extraction."""

    def test_extracts_from_actual_llm_safe_module(self) -> None:
        """Extracts dataclass names from actual incident_evidence_llm_safe.py."""
        dataclasses = extract_dataclass_names(str(EVIDENCE_LLM_SAFE_MODULE))
        assert REQUIRED_DATACLASS in dataclasses


class TestExtractFunctionDefinitions:
    """Tests for function definition extraction."""

    def test_extracts_from_actual_llm_safe_module(self) -> None:
        """Extracts function names from actual incident_evidence_llm_safe.py."""
        functions = extract_function_definitions(str(EVIDENCE_LLM_SAFE_MODULE))
        for expected_helper in REQUIRED_HELPERS:
            assert expected_helper in functions, f"Missing function: {expected_helper}"


