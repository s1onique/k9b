"""Tests for LLM-safe evidence boundary check functions.

ACT-K9B-HULK-LLM-SAFE-EVIDENCE-BOUNDARY01.

The verifier enforces three independent contracts:

1. **Canonical privacy-state hierarchy** lives in
   ``incident_evidence_redaction.py``. The four canonical aliases
   (RawEvidenceText, RedactedEvidenceText, LLMSafeEvidenceText,
   SafeEvidenceExcerpt) MUST be declared there as NewType assignments
   with the exact expected supertype chain. Edge reshuffling (e.g.
   ``LLMSafeEvidenceText -> RawEvidenceText``) is rejected even when
   the chain still terminates at ``str``.

2. **Facade re-export contract**: ``incident_evidence_llm_safe.py``
   re-exports the canonical identities rather than redefining them.
   Duplicating a ``NewType`` with the same name would mint a new,
   statically distinct type and weaken privacy guarantees. The facade
   MUST also import each canonical name from the canonical module via
   a top-level ``from <canonical_module> import <name>`` statement.

3. **Strengthened dataclass contract**:
   ``RedactedEvidenceSummary.summary`` MUST be typed as
   ``LLMSafeEvidenceText`` (not ``RedactedEvidenceText``). Redacted
   text is not automatically approved for LLM exposure.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
    check_canonical_redaction_aliases,
)

REPO_ROOT = Path(__file__).parent.parent.parent
# EVIDENCE_MODULE is the facade (re-export module) - used for backward-compat tests
EVIDENCE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence.py"
# EVIDENCE_LLM_SAFE_MODULE is the facade that re-exports canonical identities.
EVIDENCE_LLM_SAFE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_llm_safe.py"
# EVIDENCE_REDACTION_MODULE is the canonical privacy-state hierarchy source.
EVIDENCE_REDACTION_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_redaction.py"


class TestCheckCanonicalRedactionAliases:
    """Tests for the canonical privacy-state hierarchy verifier."""

    def test_passes_for_actual_canonical_module(self) -> None:
        """The actual incident_evidence_redaction.py declares the full hierarchy."""
        errors = check_canonical_redaction_aliases(str(EVIDENCE_REDACTION_MODULE))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_fails_if_alias_missing_from_canonical_module(self) -> None:
        """Negative proof: a missing canonical alias surfaces an error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0
            missing_aliases = {"RawEvidenceText", "LLMSafeEvidenceText", "SafeEvidenceExcerpt"}
            surfaced = {name for name in missing_aliases if any(name in e for e in errors)}
            assert surfaced == missing_aliases, (
                f"Expected errors for {missing_aliases}; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_if_canonical_supertype_is_wrong_primitive(self) -> None:
        """Negative proof: canonical alias rooted at non-str primitive is rejected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', int)\n")
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert len(errors) > 0
            assert any("RedactedEvidenceText" in e for e in errors)
        finally:
            Path(temp_path).unlink()

    def test_fails_if_canonical_module_declares_unexpected_extra_alias(self) -> None:
        """Negative proof: extra aliases (silently minting new types) are rejected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n")
            f.write("SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n")
            f.write("SecretSquirrelAlias = NewType('SecretSquirrelAlias', str)\n")
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert any("SecretSquirrelAlias" in e for e in errors), (
                f"Expected error about SecretSquirrelAlias; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_accepts_branded_alias_chain_rooted_at_str(self) -> None:
        """Branded supertype chain rooted at str is accepted (no exact-shape coupling)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Test module."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n")
            f.write("SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n")
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert errors == [], f"Branded chain rooted at str should pass: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_when_llm_safe_evidence_text_chains_to_raw_evidence_text(self) -> None:
        """Negative proof: reshuffling ``LLMSafeEvidenceText -> RawEvidenceText``
        is forbidden even when the chain still terminates at ``str``.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Reshuffled chain."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            # LLMSafeEvidenceText mistakenly points at RawEvidenceText instead of
            # RedactedEvidenceText. The chain still terminates at str, but the
            # branded-alias edge is wrong.
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RawEvidenceText)\n")
            f.write("SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n")
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert any(
                "LLMSafeEvidenceText" in e and "RawEvidenceText" in e for e in errors
            ), f"Expected reshuffling error about LLMSafeEvidenceText edge; got: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_fails_when_llm_safe_evidence_text_chains_directly_to_str(self) -> None:
        """Negative proof: ``LLMSafeEvidenceText -> str`` bypasses the
        privacy-state transition chain.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Skip-chain bypass."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', str)\n")
            f.write("SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n")
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert any("LLMSafeEvidenceText" in e for e in errors), (
                f"Expected edge mismatch for LLMSafeEvidenceText; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_when_safe_evidence_excerpt_chains_to_redacted_evidence_text(self) -> None:
        """Negative proof: ``SafeEvidenceExcerpt -> RedactedEvidenceText``
        skips the LLMSafeEvidenceText transition.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Skip-chain bypass on excerpt."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n")
            f.write("SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', RedactedEvidenceText)\n")
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert any("SafeEvidenceExcerpt" in e for e in errors), (
                f"Expected edge mismatch for SafeEvidenceExcerpt; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_when_safe_evidence_excerpt_chains_directly_to_str(self) -> None:
        """Negative proof: ``SafeEvidenceExcerpt -> str`` skips both
        LLMSafeEvidenceText and RedactedEvidenceText.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Double skip-chain bypass."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            f.write("RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n")
            f.write("SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', str)\n")
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            assert any("SafeEvidenceExcerpt" in e for e in errors), (
                f"Expected edge mismatch for SafeEvidenceExcerpt; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()

    def test_fails_when_alias_name_does_not_match_newtype_string(self) -> None:
        """Negative proof: ``RedactedEvidenceText = NewType(\"WrongName\", str)``
        is rejected by the extractor (assignment target must match the
        NewType string name).
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Mismatched NewType string name."""\n')
            f.write("from typing import NewType\n\n")
            f.write("RawEvidenceText = NewType('RawEvidenceText', str)\n")
            # Note: the NewType string name is 'WrongName', not 'RedactedEvidenceText'
            f.write("RedactedEvidenceText = NewType('WrongName', str)\n")
            f.write("LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n")
            f.write("SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n")
            temp_path = f.name
        try:
            errors = check_canonical_redaction_aliases(temp_path)
            # The mismatched alias should be missing from the canonical
            # hierarchy (the extractor drops it), so RedactedEvidenceText
            # surfaces as missing.
            assert any("RedactedEvidenceText" in e for e in errors), (
                f"Expected RedactedEvidenceText to surface as missing; got: {errors}"
            )
        finally:
            Path(temp_path).unlink()




if __name__ == "__main__":
    pytest.main([__file__, "-v"])
