"""Tests for content index indexer.

Tests the main indexer orchestrator.
"""

from __future__ import annotations

from pathlib import Path

from k8s_diag_agent.content_index.indexer import (
    ContentIndexer,
    ContentIndexRoots,
    IndexerConfig,
    IndexerSummary,
    discover_sources,
    load_json_file,
    make_content_id,
    rebuild_index,
    update_index,
    validate_index,
)
from k8s_diag_agent.content_index.storage import initialize_database


class TestContentIndexRoots:
    """Test ContentIndexRoots dataclass."""

    def test_get_active_roots(self) -> None:
        """Returns only active roots."""
        roots = ContentIndexRoots(
            lab_root=Path("/lab"),
            perf_baseline_root=Path("/perf"),
        )

        active = roots.get_active_roots()
        assert len(active) == 2
        assert ("lab", Path("/lab")) in active
        assert ("perf_baseline", Path("/perf")) in active

    def test_get_active_roots_empty(self) -> None:
        """Returns empty list when no roots active."""
        roots = ContentIndexRoots()
        active = roots.get_active_roots()
        assert len(active) == 0


class TestIndexerConfig:
    """Test IndexerConfig dataclass."""

    def test_default_config(self) -> None:
        """Default configuration values are correct."""
        config = IndexerConfig()
        assert config.strict_mode is False
        assert config.include_detail_projections is False
        assert config.max_file_size_mb == 100
        assert config.skip_unreadable is True


class TestIndexerSummary:
    """Test IndexerSummary dataclass."""

    def test_to_dict(self) -> None:
        """Converts to dictionary correctly."""
        summary = IndexerSummary(
            command="rebuild",
            items_discovered=10,
            items_indexed=8,
            items_updated=2,
            status="ok",
        )

        result = summary.to_dict()
        assert result["command"] == "rebuild"
        assert result["items_discovered"] == 10
        assert result["items_indexed"] == 8
        assert result["status"] == "ok"


class TestMakeContentId:
    """Test content ID generation."""

    def test_make_content_id(self) -> None:
        """Creates content ID from path kind and relative path."""
        content_id = make_content_id("incident_store", "incidents/123.json")
        assert "incident_store" in content_id
        assert "123" in content_id

    def test_make_content_id_normalizes_paths(self) -> None:
        """Normalizes path separators in content ID."""
        content_id = make_content_id("lab", "lab/pass/lab-result.json")
        assert "\\" not in content_id


class TestLoadJsonFile:
    """Test JSON file loading."""

    def test_load_json_file_success(self, tmp_path: Path) -> None:
        """Loads JSON file successfully."""
        test_file = tmp_path / "test.json"
        test_file.write_text('{"key": "value"}')

        result = load_json_file(test_file)
        assert result is not None
        assert result["key"] == "value"

    def test_load_json_file_missing(self, tmp_path: Path) -> None:
        """Handles missing file."""
        test_file = tmp_path / "nonexistent.json"
        result = load_json_file(test_file)
        assert result is None

    def test_load_json_file_invalid(self, tmp_path: Path) -> None:
        """Handles invalid JSON."""
        test_file = tmp_path / "test.json"
        test_file.write_text("not json {")

        result = load_json_file(test_file)
        assert result is None


class TestDiscoverSources:
    """Test source discovery."""

    def test_discover_sources_lab_result(self, tmp_path: Path) -> None:
        """Discovers lab result files."""
        # Create test structure
        lab_root = tmp_path / "lab"
        lab_root.mkdir()
        (lab_root / "pass").mkdir()
        (lab_root / "pass" / "lab-result.json").write_text('{"ok": true}')

        roots = ContentIndexRoots(lab_root=lab_root)
        discovered = discover_sources(roots)

        assert len(discovered) >= 1
        paths = [str(rel) for _, rel, _ in discovered]
        assert any("lab-result.json" in p for p in paths)

    def test_discover_sources_trace_summary(self, tmp_path: Path) -> None:
        """Discovers trace summary files."""
        trace_root = tmp_path / "trace-capture"
        trace_root.mkdir()
        (trace_root / "trace-summary.json").write_text('{"trace_count": 5}')

        roots = ContentIndexRoots(trace_capture_root=trace_root)
        discovered = discover_sources(roots)

        assert len(discovered) >= 1

    def test_discover_sources_nonexistent_root(self, tmp_path: Path) -> None:
        """Handles nonexistent root gracefully."""
        roots = ContentIndexRoots(lab_root=tmp_path / "nonexistent")
        discovered = discover_sources(roots)
        assert len(discovered) == 0

    def test_discover_sources_skips_large_files(self, tmp_path: Path) -> None:
        """Skips files larger than max size."""
        lab_root = tmp_path / "lab"
        lab_root.mkdir()
        pass_dir = lab_root / "pass"
        pass_dir.mkdir()
        large_file = pass_dir / "lab-result.json"
        large_file.write_bytes(b"x" * (200 * 1024))  # 200KB

        roots = ContentIndexRoots(lab_root=lab_root)
        config = IndexerConfig(max_file_size_mb=0.1)  # 100KB limit
        discovered = discover_sources(roots, config)

        # Large file should be skipped
        paths = [str(rel) for _, rel, _ in discovered]
        assert not any("lab-result.json" in p for p in paths)


class TestRebuildIndex:
    """Test rebuild operation."""

    def test_rebuild_creates_database(self, tmp_path: Path) -> None:
        """Rebuild creates the database."""
        db_path = tmp_path / "content-index.sqlite"

        lab_root = tmp_path / "lab"
        lab_root.mkdir()
        (lab_root / "pass").mkdir()
        (lab_root / "pass" / "lab-result.json").write_text('{"ok": true}')

        roots = ContentIndexRoots(lab_root=lab_root)
        summary = rebuild_index(db_path, roots)

        assert db_path.exists()
        assert summary.items_discovered >= 0
        assert summary.status == "ok"

    def test_rebuild_indexes_content(self, tmp_path: Path) -> None:
        """Rebuild indexes discovered content."""
        db_path = tmp_path / "content-index.sqlite"

        lab_root = tmp_path / "lab"
        lab_root.mkdir()
        (lab_root / "pass").mkdir()
        (lab_root / "pass" / "lab-result.json").write_text(
            '{"ok": true, "scenario": "test"}'
        )

        roots = ContentIndexRoots(lab_root=lab_root)
        summary = rebuild_index(db_path, roots)

        # Should have discovered and indexed
        assert summary.items_discovered >= 1
        assert summary.status == "ok"

    def test_rebuild_validates_schema(self, tmp_path: Path) -> None:
        """Rebuild validates the resulting database."""
        db_path = tmp_path / "content-index.sqlite"

        lab_root = tmp_path / "lab"
        lab_root.mkdir()

        roots = ContentIndexRoots(lab_root=lab_root)
        rebuild_index(db_path, roots)

        # Validate the created database
        result = validate_index(db_path)
        assert result["valid"] is True


class TestUpdateIndex:
    """Test incremental update operation."""

    def test_update_creates_database_if_missing(self, tmp_path: Path) -> None:
        """Update creates database if it doesn't exist."""
        db_path = tmp_path / "content-index.sqlite"

        lab_root = tmp_path / "lab"
        lab_root.mkdir()
        (lab_root / "pass").mkdir()
        (lab_root / "pass" / "lab-result.json").write_text('{"ok": true}')

        roots = ContentIndexRoots(lab_root=lab_root)
        summary = update_index(db_path, roots)

        assert db_path.exists()
        assert summary.status == "ok"

    def test_update_detects_unchanged(self, tmp_path: Path) -> None:
        """Update detects unchanged files."""
        db_path = tmp_path / "content-index.sqlite"

        lab_root = tmp_path / "lab"
        lab_root.mkdir()
        (lab_root / "pass").mkdir()
        (lab_root / "pass" / "lab-result.json").write_text('{"ok": true}')

        roots = ContentIndexRoots(lab_root=lab_root)

        # First run - creates database
        summary1 = update_index(db_path, roots)
        assert summary1.status == "ok"

        # Second run - should detect unchanged
        summary2 = update_index(db_path, roots)
        assert summary2.items_unchanged >= 1


class TestValidateIndex:
    """Test validation operation."""

    def test_validate_missing_database(self, tmp_path: Path) -> None:
        """Returns invalid for missing database."""
        db_path = tmp_path / "nonexistent.sqlite"
        result = validate_index(db_path)

        assert result["valid"] is False
        assert any("does not exist" in e for e in result["errors"])

    def test_validate_valid_database(self, tmp_path: Path) -> None:
        """Returns valid for properly initialized database."""
        db_path = tmp_path / "test.sqlite"
        initialize_database(db_path)

        result = validate_index(db_path)
        assert result["valid"] is True

    def test_validate_returns_counts(self, tmp_path: Path) -> None:
        """Returns item counts in validation result."""
        db_path = tmp_path / "test.sqlite"
        initialize_database(db_path)

        result = validate_index(db_path)
        assert "counts" in result
        assert "total_items" in result["counts"]


class TestContentIndexer:
    """Test ContentIndexer class."""

    def test_indexer_initialization(self, tmp_path: Path) -> None:
        """Indexer initializes correctly."""
        lab_root = tmp_path / "lab"
        lab_root.mkdir()

        roots = ContentIndexRoots(lab_root=lab_root)
        indexer = ContentIndexer(roots)

        assert indexer.roots == roots
        assert indexer.summary.command == ""

    def test_indexer_with_config(self, tmp_path: Path) -> None:
        """Indexer uses configuration."""
        lab_root = tmp_path / "lab"
        lab_root.mkdir()

        roots = ContentIndexRoots(lab_root=lab_root)
        config = IndexerConfig(strict_mode=True)
        indexer = ContentIndexer(roots, config)

        assert indexer.config.strict_mode is True
