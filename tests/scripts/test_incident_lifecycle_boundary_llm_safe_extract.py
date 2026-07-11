"""Tests for LLM-safe evidence boundary checks.

ACT-K9B-HULK-LLM-SAFE-EVIDENCE-BOUNDARY01.

The extractor tests verify that ``extract_newtype_aliases`` correctly
captures the canonical privacy-state hierarchy, that
``extract_canonical_imports`` captures the facade re-export
provenance, and that the extractors reject malformed declarations
that would silently mint statically distinct identities.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scripts.incident_lifecycle_boundary._llm_safe_extract import (
    ImportedName,
    extract_canonical_imports,
    extract_newtype_aliases,
)
from scripts.incident_lifecycle_boundary.llm_safe_evidence import (
    REQUIRED_DATACLASS,
    REQUIRED_HELPERS,
    extract_dataclass_names,
    extract_function_definitions,
)

REPO_ROOT = Path(__file__).parent.parent.parent
# EVIDENCE_REDACTION_MODULE is the canonical privacy-state module - it
# declares all four aliases as top-level NewType assignments.
EVIDENCE_REDACTION_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_redaction.py"
# EVIDENCE_LLM_SAFE_MODULE is the facade (re-export) - it should NOT
# declare any NewType aliases locally; it re-exports canonical identities.
EVIDENCE_LLM_SAFE_MODULE = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_evidence_llm_safe.py"


class TestExtractNewTypeAliases:
    """Tests for NewType alias extraction."""

    def test_extracts_from_actual_canonical_redaction_module(self) -> None:
        """Extracts the canonical hierarchy from incident_evidence_redaction.py.

        The canonical module declares each alias with its declared supertype:
        RawEvidenceText -> str, RedactedEvidenceText -> str,
        LLMSafeEvidenceText -> RedactedEvidenceText,
        SafeEvidenceExcerpt -> LLMSafeEvidenceText.
        """
        aliases = extract_newtype_aliases(str(EVIDENCE_REDACTION_MODULE))
        assert aliases.get("RawEvidenceText") == "str"
        assert aliases.get("RedactedEvidenceText") == "str"
        assert aliases.get("LLMSafeEvidenceText") == "RedactedEvidenceText"
        assert aliases.get("SafeEvidenceExcerpt") == "LLMSafeEvidenceText"

    def test_extracts_branded_supertype_chains(self) -> None:
        """Branded-alias chains (NewType -> another NewType) are captured verbatim.

        Verifies the extractor no longer assumes every alias directly wraps ``str``.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Branded chain fixture."""\n')
            f.write("from typing import NewType\n\n")
            f.write("Foo = NewType('Foo', str)\n")
            f.write("Bar = NewType('Bar', Foo)\n")
            f.write("Baz = NewType('Baz', Bar)\n")
            temp_path = f.name
        try:
            aliases = extract_newtype_aliases(temp_path)
            assert aliases == {
                "Foo": "str",
                "Bar": "Foo",
                "Baz": "Bar",
            }, f"Expected branded chain capture; got {aliases}"
        finally:
            Path(temp_path).unlink()

    def test_extracts_qualified_typing_newtype(self) -> None:
        """Recognizes ``typing.NewType(...)`` qualified calls."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Qualified typing.NewType fixture."""\n')
            f.write("import typing\n\n")
            f.write("Foo = typing.NewType('Foo', str)\n")
            temp_path = f.name
        try:
            aliases = extract_newtype_aliases(temp_path)
            assert aliases == {"Foo": "str"}, (
                f"Expected qualified typing.NewType to be recognized; got {aliases}"
            )
        finally:
            Path(temp_path).unlink()

    def test_rejects_qualified_non_typing_newtype(self) -> None:
        """``fake.NewType(...)`` is rejected because the only accepted qualifier is ``typing``."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Smuggled fake.NewType fixture."""\n')
            f.write("import fake\n\n")
            f.write("RawEvidenceText = fake.NewType('RawEvidenceText', str)\n")
            temp_path = f.name
        try:
            aliases = extract_newtype_aliases(temp_path)
            assert aliases == {}, (
                f"fake.NewType must NOT be recognized as a canonical NewType; "
                f"got {aliases}"
            )
        finally:
            Path(temp_path).unlink()

    def test_drops_alias_when_newtype_name_does_not_match_target(self) -> None:
        """``Foo = NewType(\"Bar\", str)`` is dropped because the NewType
        string name is not the same as the assignment target; doing so
        would mint a statically distinct type behind a different name.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Mismatched name."""\n')
            f.write("from typing import NewType\n\n")
            f.write("Foo = NewType('Bar', str)\n")
            temp_path = f.name
        try:
            aliases = extract_newtype_aliases(temp_path)
            assert aliases == {}, (
                f"Aliases whose NewType name does not match the target must "
                f"be dropped; got {aliases}"
            )
        finally:
            Path(temp_path).unlink()

    def test_extracts_facade_with_no_local_newtypes(self) -> None:
        """A facade that only re-exports (no local NewType) returns empty dict."""
        aliases = extract_newtype_aliases(str(EVIDENCE_LLM_SAFE_MODULE))
        assert aliases == {}, (
            f"Facade should declare no local NewType aliases; got {aliases}. "
            "If the facade accidentally re-declares canonical aliases, this "
            "test catches the privacy-state-identity regression."
        )

    def test_returns_empty_for_missing_file(self) -> None:
        """Returns empty dict for missing file."""
        aliases = extract_newtype_aliases("/nonexistent/file.py")
        assert aliases == {}

    def test_returns_empty_for_module_with_no_newtypes(self) -> None:
        """Returns empty dict for a module that defines no NewType aliases."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""No NewTypes here."""\n')
            f.write("x = 1\n")
            temp_path = f.name
        try:
            aliases = extract_newtype_aliases(temp_path)
            assert aliases == {}
        finally:
            Path(temp_path).unlink()


class TestExtractCanonicalImports:
    """Tests for canonical-import extraction."""

    def test_extracts_canonical_imports_from_actual_facade(self) -> None:
        """Extracts the canonical-import map from the actual facade."""
        imports = extract_canonical_imports(str(EVIDENCE_LLM_SAFE_MODULE))
        # Every canonical privacy-state alias must come from the
        # canonical module with itself as the original imported symbol.
        for canonical_name in (
            "LLMSafeEvidenceText",
            "RawEvidenceText",
            "RedactedEvidenceText",
            "SafeEvidenceExcerpt",
        ):
            assert canonical_name in imports, (
                f"Expected {canonical_name} in facade imports; got {imports}"
            )
            imported = imports[canonical_name]
            assert imported.module == (
                "k8s_diag_agent.collect.incident_evidence_redaction"
            ), (
                f"Expected {canonical_name} from canonical module; got "
                f"{imported.module}"
            )
            assert imported.original_name == canonical_name, (
                f"Expected original_name to equal {canonical_name}; "
                f"got {imported.original_name}"
            )
            assert imported.local_name == canonical_name, (
                f"Expected local_name to equal {canonical_name}; "
                f"got {imported.local_name}"
            )

    def test_extracts_empty_for_module_without_imports(self) -> None:
        """Returns empty dict for a module with no top-level imports."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""No imports."""\n')
            f.write("x = 1\n")
            temp_path = f.name
        try:
            imports = extract_canonical_imports(temp_path)
            assert imports == {}
        finally:
            Path(temp_path).unlink()

    def test_extracts_imports_with_asname(self) -> None:
        """``from x import Y as Z`` records the (module, Y, Z) triple."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Imports with asname."""\n')
            f.write("from somewhere import Foo as Bar\n")
            temp_path = f.name
        try:
            imports = extract_canonical_imports(temp_path)
            assert imports == {
                "Bar": ImportedName(module="somewhere", original_name="Foo", local_name="Bar"),
            }, f"Expected ImportedName triple; got {imports}"
        finally:
            Path(temp_path).unlink()

    def test_returns_empty_for_missing_file(self) -> None:
        """Returns empty dict for a missing file."""
        imports = extract_canonical_imports("/nonexistent/file.py")
        assert imports == {}

    def test_extracts_chained_imports(self) -> None:
        """Multi-line import statements are scanned."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Multi-line imports."""\n')
            f.write(
                "from canonical import (\n"
                "    Foo,\n"
                "    Bar,\n"
                ")\n"
            )
            temp_path = f.name
        try:
            imports = extract_canonical_imports(temp_path)
            assert "Foo" in imports
            assert "Bar" in imports
            assert imports["Foo"] == ImportedName(
                module="canonical", original_name="Foo", local_name="Foo"
            )
            assert imports["Bar"] == ImportedName(
                module="canonical", original_name="Bar", local_name="Bar"
            )
        finally:
            Path(temp_path).unlink()


class TestExtractDataclassNames:
    """Tests for dataclass extraction."""

    def test_extracts_from_actual_facade(self) -> None:
        """Extracts the RedactedEvidenceSummary dataclass from the facade."""
        dataclasses = extract_dataclass_names(str(EVIDENCE_LLM_SAFE_MODULE))
        assert REQUIRED_DATACLASS in dataclasses


class TestExtractFunctionDefinitions:
    """Tests for function definition extraction."""

    def test_extracts_from_actual_facade(self) -> None:
        """Extracts all required helper function names from the facade."""
        functions = extract_function_definitions(str(EVIDENCE_LLM_SAFE_MODULE))
        for expected_helper in REQUIRED_HELPERS:
            assert expected_helper in functions, f"Missing function: {expected_helper}"