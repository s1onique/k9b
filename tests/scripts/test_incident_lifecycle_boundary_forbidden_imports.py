"""Tests for the forbidden imports checks in the incident lifecycle boundary verifier."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Import the verifier package
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from incident_lifecycle_boundary.forbidden_imports import (
    _is_forbidden_module,
    check_forbidden_imports,
)


class TestForbiddenModuleMatching:
    """Tests for forbidden module matching."""

    def test_exact_match_subprocess(self) -> None:
        """_is_forbidden_module should detect exact matches for subprocess."""
        assert _is_forbidden_module("subprocess") is True

    def test_exact_match_logging(self) -> None:
        """_is_forbidden_module should detect exact matches for logging."""
        assert _is_forbidden_module("logging") is True

    def test_exact_match_random(self) -> None:
        """_is_forbidden_module should detect exact matches for random."""
        assert _is_forbidden_module("random") is True

    def test_exact_match_os(self) -> None:
        """_is_forbidden_module should detect exact matches for os."""
        assert _is_forbidden_module("os") is True

    def test_exact_match_requests(self) -> None:
        """_is_forbidden_module should detect exact matches for requests."""
        assert _is_forbidden_module("requests") is True

    def test_dotted_match_incident_store(self) -> None:
        """_is_forbidden_module should detect dotted module matches."""
        assert (
            _is_forbidden_module("k8s_diag_agent.collect.incident_store")
            is True
        )

    def test_dotted_match_incident_store_provider(self) -> None:
        """_is_forbidden_module should detect dotted store provider matches."""
        assert (
            _is_forbidden_module("k8s_diag_agent.collect.incident_store_provider")
            is True
        )

    def test_prefix_match_kubernetes_client(self) -> None:
        """_is_forbidden_module should detect submodule matches."""
        assert _is_forbidden_module("kubernetes.client") is True

    def test_prefix_match_incident_store_submodule(self) -> None:
        """_is_forbidden_module should detect incident_store submodules."""
        assert (
            _is_forbidden_module("k8s_diag_agent.collect.incident_store.foo")
            is True
        )

    def test_prefix_match_httpx_submodule(self) -> None:
        """_is_forbidden_module should detect httpx submodules."""
        assert _is_forbidden_module("httpx.client") is True

    def test_no_match_datetime(self) -> None:
        """_is_forbidden_module should return False for allowed modules."""
        assert _is_forbidden_module("datetime") is False

    def test_no_match_typing(self) -> None:
        """_is_forbidden_module should return False for typing module."""
        assert _is_forbidden_module("typing") is False

    def test_no_match_domain_module(self) -> None:
        """_is_forbidden_module should return False for domain module."""
        assert _is_forbidden_module("k8s_diag_agent.domain") is False

    def test_no_match_dataclass(self) -> None:
        """_is_forbidden_module should return False for dataclasses module."""
        assert _is_forbidden_module("dataclasses") is False


class TestForbiddenImportCheck:
    """Tests for the check_forbidden_imports function."""

    def test_domain_module_has_no_forbidden_imports(self) -> None:
        """Domain module should not import forbidden dependencies."""
        domain_module = (
            Path(__file__).parent.parent.parent
            / "src"
            / "k8s_diag_agent"
            / "domain"
            / "incident_lifecycle.py"
        )
        errors = check_forbidden_imports(str(domain_module))
        assert errors == [], f"Domain module has forbidden imports: {errors}"

    def test_detects_forbidden_import(self) -> None:
        """Should detect forbidden import statements."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("import subprocess\n")
            temp_path = f.name

        try:
            errors = check_forbidden_imports(temp_path)
            assert len(errors) == 1
            assert "Forbidden import 'subprocess'" in errors[0]
        finally:
            Path(temp_path).unlink()

    def test_detects_forbidden_from_import(self) -> None:
        """Should detect forbidden from-import statements."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("from logging import getLogger\n")
            temp_path = f.name

        try:
            errors = check_forbidden_imports(temp_path)
            assert len(errors) == 1
            assert "Forbidden import 'logging'" in errors[0]
        finally:
            Path(temp_path).unlink()

    def test_detects_dotted_forbidden_import(self) -> None:
        """Should detect dotted forbidden imports like incident_store."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("from k8s_diag_agent.collect.incident_store import IncidentStore\n")
            temp_path = f.name

        try:
            errors = check_forbidden_imports(temp_path)
            assert len(errors) == 1
            assert "Forbidden import 'k8s_diag_agent.collect.incident_store'" in errors[0]
        finally:
            Path(temp_path).unlink()

    def test_allows_clean_module(self) -> None:
        """Should allow modules with no forbidden imports."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("""
from dataclasses import dataclass
from typing import Literal
import datetime
""")
            temp_path = f.name

        try:
            errors = check_forbidden_imports(temp_path)
            assert errors == [], f"Expected no errors for clean module: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_handles_missing_file(self) -> None:
        """Should handle missing files gracefully."""
        errors = check_forbidden_imports("/nonexistent/file.py")
        assert len(errors) == 1
        assert "Cannot read" in errors[0]

    def test_handles_syntax_error(self) -> None:
        """Should handle syntax errors gracefully."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write("def broken(\n")  # Syntax error
            temp_path = f.name

        try:
            errors = check_forbidden_imports(temp_path)
            assert len(errors) == 1
            assert "Syntax error" in errors[0]
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    import unittest
    unittest.main()
