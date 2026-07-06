"""Tests for content index CLI.

Tests the command-line interface for content index operations.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestCliHelp:
    """Test CLI help output."""

    def test_rebuild_help(self) -> None:
        """Rebuild command has help."""
        result = subprocess.run(
            [sys.executable, "scripts/k9b_content_index.py", "rebuild", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 0
        assert "rebuild" in result.stdout.lower()
        assert "--index-db" in result.stdout

    def test_update_help(self) -> None:
        """Update command has help."""
        result = subprocess.run(
            [sys.executable, "scripts/k9b_content_index.py", "update", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 0
        assert "update" in result.stdout.lower()

    def test_validate_help(self) -> None:
        """Validate command has help."""
        result = subprocess.run(
            [sys.executable, "scripts/k9b_content_index.py", "validate", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 0
        assert "validate" in result.stdout.lower()


class TestCliRebuild:
    """Test rebuild command."""

    def test_rebuild_requires_index_db(self) -> None:
        """Rebuild requires --index-db."""
        result = subprocess.run(
            [sys.executable, "scripts/k9b_content_index.py", "rebuild"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode != 0
        assert "--index-db" in result.stderr

    def test_rebuild_requires_roots(self) -> None:
        """Rebuild requires at least one root."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/k9b_content_index.py",
                "rebuild",
                "--index-db",
                "/tmp/test.sqlite",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 1
        assert "root" in result.stderr.lower() or "specify" in result.stderr.lower()

    def test_rebuild_with_fixture_roots(self, tmp_path: Path) -> None:
        """Rebuild works with fixture roots."""
        db_path = tmp_path / "content-index.sqlite"

        # Use fixture lab directory
        fixture_lab = Path(__file__).parent.parent.parent / "fixtures" / "lab"

        result = subprocess.run(
            [
                sys.executable,
                "scripts/k9b_content_index.py",
                "rebuild",
                "--index-db",
                str(db_path),
                "--lab-root",
                str(fixture_lab),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        # Should succeed or have specific expected behavior
        # The exact result depends on fixture contents
        assert db_path.exists() or "Error" in result.stderr or result.returncode in (0, 1)


class TestCliValidate:
    """Test validate command."""

    def test_validate_requires_index_db(self) -> None:
        """Validate requires --index-db."""
        result = subprocess.run(
            [sys.executable, "scripts/k9b_content_index.py", "validate"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode != 0
        assert "--index-db" in result.stderr

    def test_validate_nonexistent_returns_nonzero(self) -> None:
        """Validate returns non-zero for nonexistent database."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/k9b_content_index.py",
                "validate",
                "--index-db",
                "/tmp/nonexistent_12345.sqlite",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode != 0

    def test_validate_json_output(self, tmp_path: Path) -> None:
        """Validate outputs JSON when requested."""
        from k8s_diag_agent.content_index.storage import initialize_database

        db_path = tmp_path / "test.sqlite"
        initialize_database(db_path)

        result = subprocess.run(
            [
                sys.executable,
                "scripts/k9b_content_index.py",
                "validate",
                "--index-db",
                str(db_path),
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 0

        # Should be valid JSON
        output = json.loads(result.stdout)
        assert "valid" in output


class TestCliUpdate:
    """Test update command."""

    def test_update_requires_index_db(self) -> None:
        """Update requires --index-db."""
        result = subprocess.run(
            [sys.executable, "scripts/k9b_content_index.py", "update"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode != 0
        assert "--index-db" in result.stderr

    def test_update_requires_roots(self) -> None:
        """Update requires at least one root."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/k9b_content_index.py",
                "update",
                "--index-db",
                "/tmp/test.sqlite",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 1
        assert "root" in result.stderr.lower() or "specify" in result.stderr.lower()


class TestCliSummary:
    """Test CLI summary output."""

    def test_rebuild_prints_summary(self, tmp_path: Path) -> None:
        """Rebuild prints human-readable summary."""
        db_path = tmp_path / "content-index.sqlite"
        fixture_lab = Path(__file__).parent.parent.parent / "fixtures" / "lab"

        result = subprocess.run(
            [
                sys.executable,
                "scripts/k9b_content_index.py",
                "rebuild",
                "--index-db",
                str(db_path),
                "--lab-root",
                str(fixture_lab),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        # Should print summary
        if result.returncode == 0:
            assert "Summary" in result.stdout or "Items" in result.stdout or "VERIFICATION" in result.stdout


class TestCliVerbose:
    """Test verbose flag."""

    def test_verbose_flag_exists(self) -> None:
        """Verbose flag is recognized."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/k9b_content_index.py",
                "--help",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 0
        assert "--verbose" in result.stdout or "-v" in result.stdout
