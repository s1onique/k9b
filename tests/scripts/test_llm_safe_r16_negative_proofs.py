"""R16 negative-proof tests for the LLM-safe evidence boundary verifier.

R16 closes the R15 bypass where the conditional supertype-shadowing
walker only inspected binding targets when a construct was hidden
inside another conditional (``inside_conditional == True``). At
module scope (``inside_conditional == False``), the walker
previously let binding targets on ``for``/``with``/``match``/``except``
constructs slip through. R16 fires the scanner on binding targets
regardless of nesting depth and ALSO routes every rebinding form
(including BINDING TARGETS) through the source-order walker so the
per-call-site supertype-identity check sees the rebind.

Negative proofs (each MUST reject the offending source):

* ``for str in (int,): pass`` BEFORE declarations.
* ``with manager as str: pass`` BEFORE declarations.
* ``match v: case int() as str: pass`` BEFORE declarations.
* ``for RawEvidenceText in (int,): pass`` AFTER declarations.
* ``with nullcontext() as RawEvidenceText: pass`` AFTER declarations.
* ``match v: case int() as RawEvidenceText: pass`` AFTER declarations.
* ``except Exception as RawEvidenceText`` rebinds exception handler name.

Sanity proofs:

* All R10-R15 negative-proof tests still pass.
* Legitimate canonical module still passes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary._llm_safe_alias_supertypes import (
    validate_canonical_alias_super_types,
)

REPO_ROOT = Path(__file__).parent.parent.parent
EXPECTED_ALIASES = frozenset(
    {
        "RawEvidenceText",
        "RedactedEvidenceText",
        "LLMSafeEvidenceText",
        "SafeEvidenceExcerpt",
    }
)


def _parse(source: str):
    return ast.parse(source)


def _supertype_errors(source: str) -> list[str]:
    return validate_canonical_alias_super_types(
        _parse(source), "<synthetic>", EXPECTED_ALIASES
    )


class TestTopLevelForTargetIsForbidden:
    """R16: top-level ``for <sensitive>`` rebinds the module name."""

    def test_top_level_for_str_before_declarations_is_rejected(self) -> None:
        source = (
            '"""Top-level for str before declarations."""\n'
            "from typing import NewType\n"
            "for str in (int,):\n"
            "    pass\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "str" in e.lower()
            and ("rebound" in e.lower() or "sentinel" in e.lower())
            for e in errors
        ), f"Expected top-level for-target str rebinding rejection; got: {errors}"

    def test_top_level_for_raw_evidence_text_after_declarations_is_rejected(self) -> None:
        source = (
            '"""Top-level for canonical-alias after declarations."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            "for RawEvidenceText in (int,):\n"
            "    pass\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "raw" in e.lower() and "rebound" in e.lower()
            for e in errors
        ), f"Expected top-level for-target Raw rebinding rejection; got: {errors}"


class TestTopLevelWithAsTargetIsForbidden:
    """R16: top-level ``with ... as <sensitive>`` rebinds the module name."""

    def test_top_level_with_as_str_before_declarations_is_rejected(self) -> None:
        source = (
            '"""Top-level with-as str before declarations."""\n'
            "from contextlib import nullcontext\n"
            "from typing import NewType\n"
            "with nullcontext() as str:\n"
            "    pass\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "str" in e.lower()
            and ("rebound" in e.lower() or "sentinel" in e.lower())
            for e in errors
        ), f"Expected top-level with-as str rebinding rejection; got: {errors}"

    def test_top_level_with_as_redacted_after_declarations_is_rejected(self) -> None:
        source = (
            '"""Top-level with-as canonical-alias after declarations."""\n'
            "from contextlib import nullcontext\n"
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "with nullcontext() as RedactedEvidenceText:\n"
            "    pass\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "redacted" in e.lower() and "rebound" in e.lower()
            for e in errors
        ), f"Expected top-level with-as Redacted rebinding rejection; got: {errors}"


class TestTopLevelMatchCaptureIsForbidden:
    """R16: top-level ``match v: case int() as <sensitive>`` rebinds the module name."""

    def test_top_level_match_as_str_before_declarations_is_rejected(self) -> None:
        source = (
            '"""Top-level match capture str before declarations."""\n'
            "from typing import NewType\n"
            "match 0:\n"
            "    case int() as str:\n"
            "        pass\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "str" in e.lower()
            and ("rebound" in e.lower() or "sentinel" in e.lower())
            for e in errors
        ), f"Expected top-level match-capture str rebinding rejection; got: {errors}"

    def test_top_level_match_as_llm_safe_after_declarations_is_rejected(self) -> None:
        source = (
            '"""Top-level match capture canonical-alias after declarations."""\n'
            "from typing import NewType\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
            "match 0:\n"
            "    case int() as LLMSafeEvidenceText:\n"
            "        pass\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "llm" in e.lower() and "rebound" in e.lower()
            for e in errors
        ), f"Expected top-level match-capture LLMSafe rebinding rejection; got: {errors}"


class TestExceptAsTargetIsForbidden:
    """R16: ``except Exception as <sensitive>`` rebinds the module name."""

    def test_top_level_except_as_redacted_before_declarations_is_rejected(self) -> None:
        source = (
            '"""Top-level except alias redacted before declarations."""\n'
            "from typing import NewType\n"
            "try:\n"
            "    raise OSError()\n"
            "except Exception as RedactedEvidenceText:\n"
            "    pass\n"
            "RawEvidenceText = NewType('RawEvidenceText', str)\n"
            "RedactedEvidenceText = NewType('RedactedEvidenceText', str)\n"
            "LLMSafeEvidenceText = NewType('LLMSafeEvidenceText', RedactedEvidenceText)\n"
            "SafeEvidenceExcerpt = NewType('SafeEvidenceExcerpt', LLMSafeEvidenceText)\n"
        )
        errors = _supertype_errors(source)
        assert any(
            "redacted" in e.lower() and ("rebound" in e.lower() or "rebinding" in e.lower())
            for e in errors
        ), f"Expected top-level except-as Redacted rebinding rejection; got: {errors}"


class TestR16SanityRegressions:
    """Sanity proofs: R16 does not regress legitimate modules."""

    def test_legitimate_canonical_module_still_passes(self) -> None:
        """The actual canonical module passes under R16."""
        from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
            check_canonical_redaction_aliases,
        )

        path = (
            Path(__file__)
            .resolve()
            .parents[2]
            .joinpath(
                "src",
                "k8s_diag_agent",
                "collect",
                "incident_evidence_redaction.py",
            )
        )
        errors = check_canonical_redaction_aliases(str(path))
        assert errors == [], (
            f"Legitimate canonical module must pass under R16: {errors}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
