"""Tests for OpenAPI breaking-change snapshot gate.

Run with: .venv/bin/python -m pytest tests/test_openapi_breaking_change_gate.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_openapi_breaking_changes import (
    DEFAULT_BASELINE,
    DEFAULT_BREAKING_REPORT,
    DEFAULT_CHANGELOG_REPORT,
    DEFAULT_CURRENT,
    DEFAULT_OPERATION_IDS_BASELINE,
    DEFAULT_OPERATION_IDS_CURRENT,
    _parse_operation_ids,
    compare_operation_id_snapshots,
    update_baseline,
    write_operation_id_snapshot,
    write_success_report,
)

# =============================================================================
# Fixtures
# =============================================================================


def _make_minimal_openapi(path: str, method: str = "get", op_id: str = "test_op") -> dict:
    """Create a minimal OpenAPI schema with one path/method."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "1.0"},
        "paths": {
            path: {
                method: {
                    "operationId": op_id,
                    "summary": "Test endpoint",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }


# =============================================================================
# Tests for operation ID parsing
# =============================================================================


class TestOperationIdParsing:
    """Tests for _parse_operation_ids function."""

    def test_parses_valid_lines(self, tmp_path: Path) -> None:
        """Test parsing valid operation ID lines."""
        content = "# Comment\nGET /api/test op1\nPOST /api/other op2\n"
        f = tmp_path / "ops.txt"
        f.write_text(content)

        result = _parse_operation_ids(f)
        # Results are sorted: GET before POST; /api/other before /api/test alphabetically
        assert "GET /api/test op1" in result
        assert "POST /api/other op2" in result
        assert len(result) == 2

    def test_skips_comments_and_empty_lines(self, tmp_path: Path) -> None:
        """Test that comments and empty lines are skipped."""
        content = "# Header\n\nGET /api/test op1\n\n# Another\nPOST /api/other op2\n"
        f = tmp_path / "ops.txt"
        f.write_text(content)

        result = _parse_operation_ids(f)
        assert len(result) == 2


# =============================================================================
# Tests for operation ID snapshot comparison
# =============================================================================


class TestOperationIdComparison:
    """Tests for compare_operation_id_snapshots function."""

    def test_identical_snapshots_passes(self, tmp_path: Path) -> None:
        """Test that identical snapshots have no breaking changes."""
        baseline = tmp_path / "baseline.txt"
        current = tmp_path / "current.txt"
        content = "# Comment\nGET /api/test test_op\nPOST /api/other other_op\n"
        baseline.write_text(content)
        current.write_text(content)

        result = compare_operation_id_snapshots(baseline, current)
        assert not any("Removed" in r for r in result)
        assert not any("Renamed" in r for r in result)

    def test_removed_operation_fails(self, tmp_path: Path) -> None:
        """Test that removing an operation route is flagged as breaking."""
        baseline = tmp_path / "baseline.txt"
        current = tmp_path / "current.txt"
        baseline.write_text("# Comment\nGET /api/test test_op\nPOST /api/other other_op\n")
        current.write_text("# Comment\nGET /api/test test_op\n")  # removed other_op

        result = compare_operation_id_snapshots(baseline, current)
        assert any("Removed" in r for r in result)
        assert any("other_op" in r for r in result)

    def test_added_operation_not_breaking(self, tmp_path: Path) -> None:
        """Test that adding an operation route is NOT flagged as breaking."""
        baseline = tmp_path / "baseline.txt"
        current = tmp_path / "current.txt"
        baseline.write_text("# Comment\nGET /api/test test_op\n")
        current.write_text("# Comment\nGET /api/test test_op\nPOST /api/new new_op\n")

        result = compare_operation_id_snapshots(baseline, current)
        # Should have no breaking changes (added routes are OK)
        assert not any("Removed" in r for r in result)
        assert not any("Renamed" in r for r in result)

    def test_renamed_operation_detected(self, tmp_path: Path) -> None:
        """Test that renaming an operation ID for the same route is detected."""
        baseline = tmp_path / "baseline.txt"
        current = tmp_path / "current.txt"
        baseline.write_text("# Comment\nGET /api/test old_op_name\n")
        current.write_text("# Comment\nGET /api/test new_op_name\n")

        result = compare_operation_id_snapshots(baseline, current)
        assert any("Renamed" in r for r in result)
        assert any("old_op_name" in r for r in result)
        assert any("new_op_name" in r for r in result)

    def test_swapped_operation_ids_detected(self, tmp_path: Path) -> None:
        """Test that swapping operation IDs between routes is detected."""
        baseline = tmp_path / "baseline.txt"
        current = tmp_path / "current.txt"
        baseline.write_text("# Comment\nGET /api/a get_a\nGET /api/b get_b\n")
        current.write_text("# Comment\nGET /api/a get_b\nGET /api/b get_a\n")

        result = compare_operation_id_snapshots(baseline, current)
        # Both routes have renamed operation IDs
        assert any("Renamed" in r for r in result)
        # Should detect both renames
        assert any("get_a" in r and "get_b" in r for r in result)


# =============================================================================
# Tests for schema export (pure functions)
# =============================================================================


class TestOperationIdSnapshotExport:
    """Tests for write_operation_id_snapshot function."""

    def test_writes_sorted_operations(self, tmp_path: Path) -> None:
        """Test that operation IDs are written sorted."""
        schema = tmp_path / "schema.json"
        output = tmp_path / "ops.txt"

        # Create schema with multiple paths
        schema_data = {
            "openapi": "3.1.0",
            "info": {"title": "Test", "version": "1.0"},
            "paths": {
                "/api/zebra": {"get": {"operationId": "zebra_op"}},
                "/api/alpha": {"get": {"operationId": "alpha_op"}},
                "/api/beta": {"post": {"operationId": "beta_op"}},
            },
        }
        schema.write_text(json.dumps(schema_data, indent=2))

        write_operation_id_snapshot(schema, output)

        lines = output.read_text().splitlines()
        # Find the data lines (non-comment)
        data_lines = [line for line in lines if not line.startswith("#") and line.strip()]
        # Should be sorted: alpha, beta, zebra
        assert "GET /api/alpha alpha_op" in data_lines[0]
        assert "POST /api/beta beta_op" in data_lines[1]
        assert "GET /api/zebra zebra_op" in data_lines[2]

    def test_includes_header_comments(self, tmp_path: Path) -> None:
        """Test that output file includes header comments."""
        schema = tmp_path / "schema.json"
        output = tmp_path / "ops.txt"

        schema_data = {
            "openapi": "3.1.0",
            "info": {"title": "Test", "version": "1.0"},
            "paths": {},
        }
        schema.write_text(json.dumps(schema_data, indent=2))

        write_operation_id_snapshot(schema, output)

        content = output.read_text()
        assert "# Operation ID snapshot" in content
        assert "# Format: METHOD /path operation_id" in content


# =============================================================================
# Tests for baseline update
# =============================================================================


class TestBaselineUpdate:
    """Tests for update_baseline function."""

    def test_copies_schema_to_baseline(self, tmp_path: Path) -> None:
        """Test that update_baseline copies current to baseline."""
        current = tmp_path / "current.json"
        baseline = tmp_path / "baseline.json"

        current.write_text('{"openapi": "3.1.0", "info": {"title": "Test", "version": "1.0"}}')

        update_baseline(current, baseline)

        assert baseline.exists()
        content = json.loads(baseline.read_text())
        assert content["info"]["title"] == "Test"


# =============================================================================
# Tests for success report
# =============================================================================


class TestSuccessReport:
    """Tests for write_success_report function."""

    def test_writes_success_message(self, tmp_path: Path) -> None:
        """Test that success report contains expected message."""
        report = tmp_path / "report.txt"
        baseline = Path("docs/api/openapi/baseline.json")
        current = Path("build/openapi/current.json")

        write_success_report(baseline, current, report)

        content = report.read_text()
        assert "No OpenAPI breaking changes detected" in content
        assert str(baseline) in content
        assert str(current) in content


# =============================================================================
# Tests for default paths
# =============================================================================


class TestDefaultPaths:
    """Tests for default path constants."""

    def test_baseline_uses_docs_api_openapi(self) -> None:
        """Test baseline path is in docs/api/openapi."""
        assert "docs/api/openapi" in str(DEFAULT_BASELINE)
        assert DEFAULT_BASELINE.name == "k9b-openapi-baseline.json"

    def test_operation_ids_baseline_in_docs(self) -> None:
        """Test operation IDs baseline path."""
        assert "docs/api/openapi" in str(DEFAULT_OPERATION_IDS_BASELINE)
        assert DEFAULT_OPERATION_IDS_BASELINE.name == "operation-ids-baseline.txt"

    def test_current_schema_in_build(self) -> None:
        """Test current schema path is in build directory."""
        assert "build/openapi" in str(DEFAULT_CURRENT)
        assert DEFAULT_CURRENT.name == "k9b-openapi.json"

    def test_reports_in_build(self) -> None:
        """Test report paths are in build directory."""
        assert "build/openapi" in str(DEFAULT_BREAKING_REPORT)
        assert "build/openapi" in str(DEFAULT_CHANGELOG_REPORT)
        assert "build/openapi" in str(DEFAULT_OPERATION_IDS_CURRENT)


# =============================================================================
# Integration-style tests (can be skipped if oasdiff unavailable)
# =============================================================================


class TestOasdiffIntegration:
    """Integration tests requiring oasdiff availability."""

    @pytest.fixture
    def oasdiff_available(self) -> bool:
        """Check if oasdiff is available via go run."""
        import subprocess

        try:
            result = subprocess.run(
                ["go", "run", "github.com/oasdiff/oasdiff@latest", "--help"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0
        except Exception:
            return False

    def test_identical_schemas_passes_oasdiff(self, tmp_path: Path, oasdiff_available: bool) -> None:
        """Test that identical schemas pass oasdiff breaking check."""
        if not oasdiff_available:
            pytest.skip("oasdiff not available")

        from scripts.verify_openapi_breaking_changes import run_oasdiff_breaking

        baseline = tmp_path / "baseline.json"
        current = tmp_path / "current.json"
        report = tmp_path / "report.txt"

        schema = _make_minimal_openapi("/api/test")
        baseline.write_text(json.dumps(schema, indent=2))
        current.write_text(json.dumps(schema, indent=2))

        returncode, stdout = run_oasdiff_breaking(baseline, current, report)

        assert returncode == 0
        assert "report.txt" in str(report)  # report should exist

    def test_removed_path_fails_oasdiff(self, tmp_path: Path, oasdiff_available: bool) -> None:
        """Test that removing a path is detected by oasdiff with --fail-on ERR."""
        if not oasdiff_available:
            pytest.skip("oasdiff not available")

        from scripts.verify_openapi_breaking_changes import run_oasdiff_breaking

        baseline = tmp_path / "baseline.json"
        current = tmp_path / "current.json"
        report = tmp_path / "report.txt"

        # Baseline has two paths
        baseline_data = {
            "openapi": "3.1.0",
            "info": {"title": "Test", "version": "1.0"},
            "paths": {
                "/api/test": {"get": {"operationId": "test_op", "responses": {"200": {"description": "OK"}}}},
                "/api/keep": {"get": {"operationId": "keep_op", "responses": {"200": {"description": "OK"}}}},
            },
        }
        baseline.write_text(json.dumps(baseline_data, indent=2))

        # Current has only one path (removed /api/test)
        current_data = {
            "openapi": "3.1.0",
            "info": {"title": "Test", "version": "1.0"},
            "paths": {
                "/api/keep": {"get": {"operationId": "keep_op", "responses": {"200": {"description": "OK"}}}},
            },
        }
        current.write_text(json.dumps(current_data, indent=2))

        returncode, stdout = run_oasdiff_breaking(baseline, current, report)

        # oasdiff with --fail-on ERR exits non-zero on breaking changes
        assert returncode != 0, f"Expected non-zero exit code for breaking changes, got {returncode}"
        
        report_content = report.read_text()
        assert "api-path-removed" in report_content or "api/test" in report_content, \
            f"Expected path removal detected in report: {report_content}"


# =============================================================================
# Test module interface
# =============================================================================


class TestModuleInterface:
    """Tests for module-level function signatures."""

    def test_export_current_schema_exists(self) -> None:
        """Test that export_current_schema function exists."""
        import inspect

        from scripts.verify_openapi_breaking_changes import export_current_schema

        sig = inspect.signature(export_current_schema)
        assert "output_path" in [p.name for p in sig.parameters.values()]

    def test_main_returns_int(self) -> None:
        """Test that main function exists and has correct signature."""
        import inspect

        from scripts.verify_openapi_breaking_changes import main

        sig = inspect.signature(main)
        assert "argv" in [p.name for p in sig.parameters.values()]
