"""Tests for usefulness feedback import/export functionality.

Tests cover:
- Export schema stability
- Feedback JSON validation
- Idempotent import behavior
- Duplicate detection and fan-out behavior
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.export_next_check_usefulness_review import (  # noqa: E402
    _add_duplicate_metadata,
    _build_duplicate_groups_summary,
    _detect_duplicate_groups,
    export_next_check_usefulness_review,
)
from scripts.import_next_check_usefulness_feedback import (  # noqa: E402
    _build_summary,
    _generate_dedupe_key,
    _resolve_artifact_path,
    _set_allowed_roots,
    import_next_check_usefulness_feedback,
)  # noqa: E402


class TestExportSchemaStability(unittest.TestCase):
    """Tests for export schema stability."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True, exist_ok=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_ui_index(self, run_id: str, run_label: str) -> None:
        """Create a minimal ui-index.json for testing."""
        index_data = {
            "run": {
                "run_id": run_id,
                "run_label": run_label,
            }
        }
        (self.health_dir / "ui-index.json").write_text(json.dumps(index_data), encoding="utf-8")

    def _create_execution_artifact(
        self,
        run_id: str,
        index: int,
        command_family: str = "kubectl-logs",
        description: str = "Get pod logs",
        cluster_label: str = "cluster-a",
        status: str = "success",
        usefulness_class: str | None = None,
    ) -> Path:
        """Create a mock execution artifact."""
        artifact_data = {
            "purpose": "next-check-execution",
            "run_id": run_id,
            "run_label": f"{run_id}-label",
            "cluster_label": cluster_label,
            "status": status,
            "tool_name": "test-runner",
            "payload": {
                "candidateIndex": index,
                "candidateId": f"candidate-{index}",
                "command_family": command_family,
                "description": description,
                "command_preview": f"kubectl logs -n default {index}",
            },
            "summary": f"Captured logs for candidate {index}",
        }
        if usefulness_class:
            artifact_data["usefulness_class"] = usefulness_class
        artifact_path = self.external_dir / f"{run_id}-next-check-execution-{index}.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")
        return artifact_path

    def test_export_produces_valid_schema(self) -> None:
        """Test that export produces valid v1 schema."""
        run_id = "test-run-export"
        self._create_ui_index(run_id, "Test Run")
        self._create_execution_artifact(run_id, 0)

        result = export_next_check_usefulness_review(
            self.runs_dir,
            run_id=run_id,
            detect_duplicates=False,
        )

        output_path = result.output_path
        assert output_path is not None
        self.assertTrue(output_path.exists())

        data = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], "next-check-usefulness-review/v1")
        self.assertEqual(data["run_id"], run_id)
        self.assertIn("generated_at", data)
        self.assertIn("entries", data)
        self.assertEqual(data["entry_count"], 1)

    def test_export_preserves_required_fields(self) -> None:
        """Test that export preserves all required fields from source artifacts."""
        run_id = "test-run-fields"
        self._create_ui_index(run_id, "Test Run Fields")
        self._create_execution_artifact(
            run_id,
            0,
            command_family="kubectl-get",
            description="Get deployments",
            cluster_label="cluster-b",
        )

        result = export_next_check_usefulness_review(
            self.runs_dir,
            run_id=run_id,
            detect_duplicates=False,
        )

        output_path = result.output_path
        assert output_path is not None
        data = json.loads(output_path.read_text(encoding="utf-8"))
        entry = data["entries"][0]

        # Required fields per schema
        self.assertIn("artifact_path", entry)
        self.assertIn("run_id", entry)
        self.assertIn("candidate_id", entry)
        self.assertIn("candidate_index", entry)
        self.assertIn("command_family", entry)
        self.assertIn("execution_status", entry)
        self.assertIn("timestamp", entry)
        self.assertIn("usefulness_class", entry)
        self.assertIn("usefulness_summary", entry)

    def test_export_runs_scoped_by_default(self) -> None:
        """Test that export defaults to run-scoped path."""
        run_id = "test-run-scoped"
        self._create_ui_index(run_id, "Test Run Scoped")
        self._create_execution_artifact(run_id, 0)

        result = export_next_check_usefulness_review(
            self.runs_dir,
            run_id=run_id,
        )

        # Use resolved paths to handle macOS /private/var/folders symlink
        assert result.output_path is not None
        expected_path = (self.health_dir / "diagnostic-packs" / run_id / "next_check_usefulness_review.json").resolve()
        self.assertEqual(result.output_path.resolve(), expected_path)

    def test_export_with_run_scoped_false_uses_latest(self) -> None:
        """Test that use_run_scoped_path=False uses latest path."""
        run_id = "test-run-latest"
        self._create_ui_index(run_id, "Test Run Latest")
        self._create_execution_artifact(run_id, 0)

        result = export_next_check_usefulness_review(
            self.runs_dir,
            run_id=run_id,
            use_run_scoped_path=False,
        )

        # Use resolved paths to handle macOS /private/var/folders symlink
        assert result.output_path is not None
        expected_path = (self.health_dir / "diagnostic-packs" / "latest" / "next_check_usefulness_review.json").resolve()
        self.assertEqual(result.output_path.resolve(), expected_path)


class TestFlatExport(unittest.TestCase):
    """Tests for flat reviewer-friendly export functionality."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True, exist_ok=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_ui_index(self, run_id: str, run_label: str) -> None:
        """Create a minimal ui-index.json for testing."""
        index_data = {
            "run": {
                "run_id": run_id,
                "run_label": run_label,
            }
        }
        (self.health_dir / "ui-index.json").write_text(json.dumps(index_data), encoding="utf-8")

    def _create_execution_artifact(
        self,
        run_id: str,
        index: int,
        command_family: str = "kubectl-logs",
        description: str = "Get pod logs",
        cluster_label: str = "cluster-a",
        status: str = "success",
    ) -> Path:
        """Create a mock execution artifact."""
        artifact_data = {
            "purpose": "next-check-execution",
            "run_id": run_id,
            "run_label": f"{run_id}-label",
            "cluster_label": cluster_label,
            "status": status,
            "tool_name": "test-runner",
            "payload": {
                "candidateIndex": index,
                "candidateId": f"candidate-{index}",
                "command_family": command_family,
                "description": description,
                "command_preview": f"kubectl logs -n default {index}",
            },
            "summary": f"Captured logs for candidate {index}",
        }
        artifact_path = self.external_dir / f"{run_id}-next-check-execution-{index}.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")
        return artifact_path

    def test_flat_export_writes_reviewer_friendly_copy(self) -> None:
        """Test that flat export writes a reviewer-friendly copy."""
        run_id = "test-flat-export"
        self._create_ui_index(run_id, "Test Flat Export")
        self._create_execution_artifact(run_id, 0)

        result = export_next_check_usefulness_review(
            self.runs_dir,
            run_id=run_id,
        )

        # Canonical file should still be written
        assert result.output_path is not None
        self.assertTrue(result.output_path.exists())

        # Flat export should also be written
        assert result.flat_output_path is not None
        self.assertTrue(result.flat_output_path.exists())

        # Content should be identical
        canonical_data = json.loads(result.output_path.read_text(encoding="utf-8"))
        flat_data = json.loads(result.flat_output_path.read_text(encoding="utf-8"))
        self.assertEqual(canonical_data, flat_data)

    def test_flat_export_filename_includes_run_id(self) -> None:
        """Test that flat export filename includes run_id for uniqueness."""
        run_id = "unique-run-20240115-001"
        self._create_ui_index(run_id, "Test Run ID in Filename")
        self._create_execution_artifact(run_id, 0)

        result = export_next_check_usefulness_review(
            self.runs_dir,
            run_id=run_id,
        )

        assert result.flat_output_path is not None
        self.assertIn(run_id, result.flat_output_path.name)
        self.assertTrue(result.flat_output_path.name.endswith("-next_check_usefulness_review.json"))

    def test_flat_export_idempotent(self) -> None:
        """Test that repeated export is idempotent - same content, no errors."""
        run_id = "test-idempotent"
        self._create_ui_index(run_id, "Test Idempotent")
        self._create_execution_artifact(run_id, 0)
        self._create_execution_artifact(run_id, 1)

        # First export
        result1 = export_next_check_usefulness_review(
            self.runs_dir,
            run_id=run_id,
        )
        assert result1.flat_output_path is not None
        first_data = json.loads(result1.flat_output_path.read_text(encoding="utf-8"))

        # Second export (should overwrite, be idempotent)
        result2 = export_next_check_usefulness_review(
            self.runs_dir,
            run_id=run_id,
        )
        assert result2.flat_output_path is not None
        second_data = json.loads(result2.flat_output_path.read_text(encoding="utf-8"))

        # Content should be identical except for generated_at and entry timestamps
        # (these change between runs, which is expected)
        self.assertEqual(first_data["run_id"], second_data["run_id"])
        self.assertEqual(first_data["run_label"], second_data["run_label"])
        self.assertEqual(first_data["entry_count"], second_data["entry_count"])
        self.assertEqual(len(first_data["entries"]), len(second_data["entries"]))
        self.assertEqual(first_data["schema_version"], second_data["schema_version"])

        # Entry count should match
        self.assertEqual(result1.entry_count, result2.entry_count)

    def test_flat_export_disabled_by_flag(self) -> None:
        """Test that flat export can be disabled with flag."""
        run_id = "test-no-flat"
        self._create_ui_index(run_id, "Test No Flat")
        self._create_execution_artifact(run_id, 0)

        result = export_next_check_usefulness_review(
            self.runs_dir,
            run_id=run_id,
            export_flat_review_copy=False,
        )

        # Canonical file should still be written
        assert result.output_path is not None
        self.assertTrue(result.output_path.exists())

        # Flat export should NOT be written
        self.assertIsNone(result.flat_output_path)

    def test_flat_export_to_dedicated_directory(self) -> None:
        """Test that flat exports go to dedicated review-exports directory."""
        run_id = "test-review-exports"
        self._create_ui_index(run_id, "Test Review Exports")
        self._create_execution_artifact(run_id, 0)

        result = export_next_check_usefulness_review(
            self.runs_dir,
            run_id=run_id,
        )

        assert result.flat_output_path is not None
        # Should be in review-exports subdirectory
        self.assertIn("review-exports", str(result.flat_output_path))
        # Filename should include run_id
        self.assertTrue(result.flat_output_path.name.startswith(run_id))


class TestDuplicateDetection(unittest.TestCase):
    """Tests for duplicate detection in export."""

    def test_detect_duplicate_groups_same_family(self) -> None:
        """Test detection of duplicates with same command family."""
        entries = [
            {"command_family": "kubectl-logs", "description": "Get logs", "cluster_label": "a"},
            {"command_family": "kubectl-logs", "description": "Get logs", "cluster_label": "a"},
            {"command_family": "kubectl-get", "description": "Get pods", "cluster_label": "a"},
        ]

        groups = _detect_duplicate_groups(entries)
        self.assertEqual(len(groups), 1)
        # The kubectl-logs entries should be grouped
        group_values = list(groups.values())
        self.assertEqual(len(group_values[0]), 2)

    def test_detect_duplicate_groups_different_family(self) -> None:
        """Test that different command families are not grouped."""
        entries = [
            {"command_family": "kubectl-logs", "description": "Get logs", "cluster_label": "a"},
            {"command_family": "kubectl-get", "description": "Get logs", "cluster_label": "a"},
        ]

        groups = _detect_duplicate_groups(entries)
        self.assertEqual(len(groups), 0)

    def test_detect_duplicate_groups_different_cluster(self) -> None:
        """Test that different clusters are not grouped."""
        entries = [
            {"command_family": "kubectl-logs", "description": "Get logs", "cluster_label": "a"},
            {"command_family": "kubectl-logs", "description": "Get logs", "cluster_label": "b"},
        ]

        groups = _detect_duplicate_groups(entries)
        self.assertEqual(len(groups), 0)

    def test_add_duplicate_metadata(self) -> None:
        """Test that duplicate metadata is added correctly."""
        entries = [
            {"artifact_path": "exec-0.json", "command_family": "kubectl-logs"},
            {"artifact_path": "exec-1.json", "command_family": "kubectl-logs"},
            {"artifact_path": "exec-2.json", "command_family": "kubectl-logs"},
        ]
        groups = {"dup-abc123": [0, 1, 2]}

        _add_duplicate_metadata(entries, groups)

        # First entry should be representative
        self.assertEqual(entries[0]["duplicate_group_id"], "dup-abc123")
        self.assertEqual(entries[0]["duplicate_count"], 3)
        self.assertTrue(entries[0]["is_representative"])

        # Others should not be
        self.assertFalse(entries[1]["is_representative"])
        self.assertFalse(entries[2]["is_representative"])

        # All should have siblings
        self.assertEqual(len(entries[0]["duplicate_siblings"]), 3)

    def test_build_duplicate_groups_summary(self) -> None:
        """Test building duplicate groups summary."""
        entries = [
            {"artifact_path": "exec-0.json", "command_family": "kubectl-logs", "description": "Logs", "cluster_label": "a"},
            {"artifact_path": "exec-1.json", "command_family": "kubectl-logs", "description": "Logs", "cluster_label": "a"},
        ]
        groups = {"dup-abc123": [0, 1]}

        summary = _build_duplicate_groups_summary(entries, groups)

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["group_id"], "dup-abc123")
        self.assertEqual(summary[0]["count"], 2)
        self.assertEqual(summary[0]["command_family"], "kubectl-logs")


class TestFeedbackValidation(unittest.TestCase):
    """Tests for feedback JSON validation."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True, exist_ok=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_execution_artifact(self, run_id: str, index: int) -> Path:
        """Create a mock execution artifact."""
        artifact_data = {
            "purpose": "next-check-execution",
            "run_id": run_id,
            "run_label": f"{run_id}-label",
            "cluster_label": "cluster-a",
            "status": "success",
            "tool_name": "test-runner",
            "payload": {"candidateIndex": index},
        }
        artifact_path = self.external_dir / f"{run_id}-next-check-execution-{index}.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")
        return artifact_path

    def _create_feedback_file(self, entries: list[dict]) -> Path:
        """Create a feedback file with given entries."""
        feedback_data = {
            "schema_version": "next-check-usefulness-feedback/v2",
            "run_id": "test-run",
            "run_label": "Test Run",
            "entries": entries,
        }
        feedback_path = self.tmpdir / "feedback.json"
        feedback_path.write_text(json.dumps(feedback_data), encoding="utf-8")
        return feedback_path

    def test_valid_feedback_schema_v2(self) -> None:
        """Test that v2 schema is accepted."""
        run_id = "test-run"
        artifact_path = self._create_execution_artifact(run_id, 0)
        relative_path = str(artifact_path.relative_to(self.health_dir))

        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path,
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found relevant logs",
                }
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
            dry_run=True,
        )

        self.assertEqual(result.error_count, 0)

    def test_invalid_schema_version_rejected(self) -> None:
        """Test that invalid schema version is rejected."""
        feedback_data = {
            "schema_version": "next-check-usefulness-feedback/v42",
            "run_id": "test-run",
            "entries": [],
        }
        feedback_path = self.tmpdir / "feedback.json"
        feedback_path.write_text(json.dumps(feedback_data), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            import_next_check_usefulness_feedback(self.runs_dir, feedback_path)

        self.assertIn("Invalid schema version", str(ctx.exception))

    def test_invalid_usefulness_class_rejected(self) -> None:
        """Test that invalid usefulness_class is rejected."""
        run_id = "test-run"
        artifact_path = self._create_execution_artifact(run_id, 0)
        relative_path = str(artifact_path.relative_to(self.health_dir))

        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path,
                    "run_id": run_id,
                    "usefulness_class": "not-a-real-class",
                    "usefulness_summary": "Test",
                }
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
            dry_run=True,
        )

        self.assertEqual(result.error_count, 1)
        self.assertIn("Invalid usefulness_class", result.errors[0])

    def test_missing_required_fields_rejected(self) -> None:
        """Test that missing required fields are rejected."""
        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": "some/path.json",
                    # Missing: run_id, usefulness_class, usefulness_summary
                }
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
            dry_run=True,
        )

        self.assertEqual(result.error_count, 1)

    def test_all_supported_usefulness_classes(self) -> None:
        """Test that all supported usefulness classes are accepted."""
        run_id = "test-run"
        classes = ["useful", "partial", "noisy", "empty"]

        for cls in classes:
            # Clean up from previous iteration
            for f in self.external_dir.glob("*.json"):
                f.unlink()

            artifact_path = self._create_execution_artifact(run_id, 0)
            relative_path = str(artifact_path.relative_to(self.health_dir))

            feedback_file = self._create_feedback_file(
                [
                    {
                        "artifact_path": relative_path,
                        "run_id": run_id,
                        "usefulness_class": cls,
                        "usefulness_summary": f"Test {cls}",
                    }
                ]
            )

            result = import_next_check_usefulness_feedback(
                self.runs_dir,
                feedback_file,
                dry_run=True,
            )

            self.assertEqual(result.error_count, 0, f"Failed for class: {cls}")


class TestIdempotentImport(unittest.TestCase):
    """Tests for idempotent import behavior."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True, exist_ok=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_execution_artifact(self, run_id: str, index: int) -> Path:
        """Create a mock execution artifact."""
        artifact_data = {
            "purpose": "next-check-execution",
            "run_id": run_id,
            "run_label": f"{run_id}-label",
            "cluster_label": "cluster-a",
            "status": "success",
            "tool_name": "test-runner",
            "payload": {"candidateIndex": index},
        }
        artifact_path = self.external_dir / f"{run_id}-next-check-execution-{index}.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")
        return artifact_path

    def _create_feedback_file(self, entries: list[dict]) -> Path:
        """Create a feedback file with given entries."""
        feedback_data = {
            "schema_version": "next-check-usefulness-feedback/v2",
            "run_id": "test-run",
            "run_label": "Test Run",
            "entries": entries,
        }
        feedback_path = self.tmpdir / "feedback.json"
        feedback_path.write_text(json.dumps(feedback_data), encoding="utf-8")
        return feedback_path

    def _create_feedback_file_with_run_id(self, run_id: str, entries: list[dict]) -> Path:
        """Create a feedback file with given run_id."""
        feedback_data = {
            "schema_version": "next-check-usefulness-feedback/v2",
            "run_id": run_id,
            "run_label": "Test Run",
            "entries": entries,
        }
        feedback_path = self.tmpdir / f"feedback_{run_id}.json"
        feedback_path.write_text(json.dumps(feedback_data), encoding="utf-8")
        return feedback_path

    def test_reimport_same_feedback_skips(self) -> None:
        """Test that reimporting the same feedback skips without changes."""
        run_id = "test-run"
        artifact_path = self._create_execution_artifact(run_id, 0)
        relative_path = str(artifact_path.relative_to(self.health_dir))

        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path,
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found logs",
                }
            ]
        )

        # First import
        result1 = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )
        self.assertEqual(result1.success_count, 1)

        # Get original mtime
        original_mtime = artifact_path.stat().st_mtime

        # Second import (should skip)
        result2 = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )
        self.assertEqual(result2.skipped_count, 1)
        self.assertEqual(result2.updated_count, 0)

        # File should not have been modified
        new_mtime = artifact_path.stat().st_mtime
        self.assertEqual(original_mtime, new_mtime)

    def test_reimport_different_summary_updates(self) -> None:
        """Test that reimporting with different summary updates the artifact."""
        run_id = "test-run"
        artifact_path = self._create_execution_artifact(run_id, 0)
        relative_path = str(artifact_path.relative_to(self.health_dir))

        # First import
        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path,
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "First summary",
                }
            ]
        )

        result1 = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )
        self.assertEqual(result1.success_count, 1)

        # Verify first import
        data1 = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(data1["usefulness_summary"], "First summary")

        # Second import with different summary
        feedback_file2 = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path,
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Updated summary",
                }
            ]
        )

        result2 = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file2,
        )
        self.assertEqual(result2.updated_count, 1)

        # Verify update
        data2 = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(data2["usefulness_summary"], "Updated summary")

    def test_import_creates_summary_artifact(self) -> None:
        """Test that import creates the summary artifact."""
        run_id = "test-run"
        artifact_path = self._create_execution_artifact(run_id, 0)
        relative_path = str(artifact_path.relative_to(self.health_dir))

        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path,
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found logs",
                    "command_family": "kubectl-logs",
                }
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )

        self.assertEqual(result.success_count, 1)
        # Summary contains the schema_version as the top-level key
        self.assertIn("schema_version", result.summary)
        self.assertEqual(result.summary["schema_version"], "usefulness-summary/v1")

        # Check summary artifact exists at run-scoped path
        summary_path = self.health_dir / "diagnostic-packs" / run_id / "usefulness_summary.json"
        self.assertTrue(summary_path.exists())

        summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary_data["schema_version"], "usefulness-summary/v1")
        self.assertEqual(summary_data["usefulness_class_counts"]["useful"], 1)
        # Verify run_id in the summary matches the run_id from entries
        self.assertEqual(summary_data["run_id"], run_id)

    def test_import_multiple_runs_creates_separate_summaries(self) -> None:
        """Test that import with entries for multiple runs creates separate summary artifacts."""
        run_id_1 = "health-run-20260413T153347Z"
        run_id_2 = "health-run-20260415T114432Z"

        # Create artifacts for both runs
        artifact_path_1 = self._create_execution_artifact(run_id_1, 0)
        artifact_path_2 = self._create_execution_artifact(run_id_2, 0)
        relative_path_1 = str(artifact_path_1.relative_to(self.health_dir))
        relative_path_2 = str(artifact_path_2.relative_to(self.health_dir))

        # Create feedback file with entries for multiple runs
        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path_1,
                    "run_id": run_id_1,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found logs for run 1",
                    "command_family": "kubectl-logs",
                },
                {
                    "artifact_path": relative_path_2,
                    "run_id": run_id_2,
                    "usefulness_class": "noisy",
                    "usefulness_summary": "Too many logs for run 2",
                    "command_family": "kubectl-logs",
                },
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )

        self.assertEqual(result.success_count, 2)

        # Check that separate summary artifacts exist for each run
        summary_path_1 = self.health_dir / "diagnostic-packs" / run_id_1 / "usefulness_summary.json"
        summary_path_2 = self.health_dir / "diagnostic-packs" / run_id_2 / "usefulness_summary.json"

        self.assertTrue(summary_path_1.exists(), f"Summary should exist at {summary_path_1}")
        self.assertTrue(summary_path_2.exists(), f"Summary should exist at {summary_path_2}")

        # Verify content of each summary
        summary_data_1 = json.loads(summary_path_1.read_text(encoding="utf-8"))
        self.assertEqual(summary_data_1["run_id"], run_id_1)
        self.assertEqual(summary_data_1["usefulness_class_counts"]["useful"], 1)

        summary_data_2 = json.loads(summary_path_2.read_text(encoding="utf-8"))
        self.assertEqual(summary_data_2["run_id"], run_id_2)
        self.assertEqual(summary_data_2["usefulness_class_counts"]["noisy"], 1)

    def test_import_does_not_create_unknown_bucket_with_valid_run_ids(self) -> None:
        """Test that 'unknown' bucket is NOT created when entries have valid run_ids."""
        run_id_1 = "health-run-20260413T153347Z"
        run_id_2 = "health-run-20260415T114432Z"

        # Create artifacts for both runs
        artifact_path_1 = self._create_execution_artifact(run_id_1, 0)
        artifact_path_2 = self._create_execution_artifact(run_id_2, 0)
        relative_path_1 = str(artifact_path_1.relative_to(self.health_dir))
        relative_path_2 = str(artifact_path_2.relative_to(self.health_dir))

        # Create feedback file with entries for multiple runs (no "unknown" entries)
        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path_1,
                    "run_id": run_id_1,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found logs",
                    "command_family": "kubectl-logs",
                },
                {
                    "artifact_path": relative_path_2,
                    "run_id": run_id_2,
                    "usefulness_class": "partial",
                    "usefulness_summary": "Some logs",
                    "command_family": "kubectl-get",
                },
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )

        self.assertEqual(result.success_count, 2)

        # Verify NO "unknown" bucket was created
        unknown_summary_path = self.health_dir / "diagnostic-packs" / "unknown" / "usefulness_summary.json"
        self.assertFalse(unknown_summary_path.exists(), "Should NOT create 'unknown' bucket when valid run_ids exist")

        # Verify both run-scoped summaries exist
        summary_path_1 = self.health_dir / "diagnostic-packs" / run_id_1 / "usefulness_summary.json"
        summary_path_2 = self.health_dir / "diagnostic-packs" / run_id_2 / "usefulness_summary.json"
        self.assertTrue(summary_path_1.exists())
        self.assertTrue(summary_path_2.exists())

    def test_idempotent_reimport_rebuilds_summaries(self) -> None:
        """Test that idempotent re-import rebuilds summary artifacts."""
        run_id = "test-run-idempotent"

        # Create artifact
        artifact_path = self._create_execution_artifact(run_id, 0)
        relative_path = str(artifact_path.relative_to(self.health_dir))

        # First import
        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path,
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found logs",
                    "command_family": "kubectl-logs",
                }
            ]
        )

        result1 = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )

        self.assertEqual(result1.success_count, 1)

        # Verify summary exists after first import
        summary_path = self.health_dir / "diagnostic-packs" / run_id / "usefulness_summary.json"
        self.assertTrue(summary_path.exists())

        # Store original mtime
        original_mtime = summary_path.stat().st_mtime

        # Second import with identical feedback (idempotent re-import)
        result2 = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )

        # Should be idempotent: skipped_count = 1, success_count = 0
        self.assertEqual(result2.skipped_count, 1)
        self.assertEqual(result2.success_count, 0)

        # Summary should STILL exist after idempotent re-import
        self.assertTrue(summary_path.exists(), "Summary should exist after idempotent re-import")

        # The summary should be rebuilt (mtime should be updated)
        new_mtime = summary_path.stat().st_mtime
        self.assertNotEqual(original_mtime, new_mtime, "Summary should be rebuilt on idempotent re-import")

    def test_delete_summary_and_reimport_recreates(self) -> None:
        """Test that deleting summary and re-importing recreates it."""
        run_id = "test-run-delete-recreate"

        # Create artifact
        artifact_path = self._create_execution_artifact(run_id, 0)
        relative_path = str(artifact_path.relative_to(self.health_dir))

        # First import
        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path,
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found logs",
                    "command_family": "kubectl-logs",
                }
            ]
        )

        result1 = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )

        self.assertEqual(result1.success_count, 1)

        # Verify summary exists
        summary_path = self.health_dir / "diagnostic-packs" / run_id / "usefulness_summary.json"
        self.assertTrue(summary_path.exists())

        # Delete the summary file
        summary_path.unlink()
        self.assertFalse(summary_path.exists())

        # Re-import (idempotent - same feedback)
        result2 = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )

        # Should be skipped (idempotent)
        self.assertEqual(result2.skipped_count, 1)

        # Summary should be recreated
        self.assertTrue(summary_path.exists(), "Summary should be recreated after re-import")

    def test_import_with_context_fields_produces_context_aggregates(self) -> None:
        """Test that feedback with context fields produces context_aggregates in summary."""
        import time
        run_id = f"test-run-context-{int(time.time() * 1000)}"

        # Create artifact
        artifact_path = self._create_execution_artifact(run_id, 0)
        relative_path = str(artifact_path.relative_to(self.health_dir))

        # Create feedback file with context fields (use valid enum values)
        feedback_file = self._create_feedback_file_with_run_id(
            run_id,
            [
                {
                    "artifact_path": relative_path,
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found logs",
                    "command_family": "kubectl-logs",
                    "workstream": "incident",
                    "review_stage": "initial_triage",
                    "problem_class": "crashloop",
                }
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )

        self.assertEqual(result.success_count, 1)

        # Verify summary exists and contains context_aggregates
        summary_path = self.health_dir / "diagnostic-packs" / run_id / "usefulness_summary.json"
        self.assertTrue(summary_path.exists())

        summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertIn("context_aggregates", summary_data)

        # Verify the structure of context_aggregates
        context_aggs = summary_data["context_aggregates"]
        self.assertIn("by_command_family", context_aggs)
        self.assertIn("by_command_family_workstream", context_aggs)
        self.assertIn("by_command_family_review_stage", context_aggs)
        self.assertIn("by_command_family_problem_class", context_aggs)

        # Verify the actual counts
        self.assertEqual(context_aggs["by_command_family"]["kubectl-logs"]["useful"], 1)
        self.assertEqual(context_aggs["by_command_family_workstream"]["kubectl-logs:incident"]["useful"], 1)
        self.assertEqual(context_aggs["by_command_family_review_stage"]["kubectl-logs:initial_triage"]["useful"], 1)
        self.assertEqual(context_aggs["by_command_family_problem_class"]["kubectl-logs:crashloop"]["useful"], 1)

    def test_import_without_context_fields_no_context_aggregates(self) -> None:
        """Test that feedback without context fields does not include context_aggregates."""
        run_id = "test-run-no-context"

        # Create artifact
        artifact_path = self._create_execution_artifact(run_id, 0)
        relative_path = str(artifact_path.relative_to(self.health_dir))

        # Create feedback file WITHOUT context fields
        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path,
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found logs",
                    "command_family": "kubectl-logs",
                    # No workstream, review_stage, or problem_class
                }
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )

        self.assertEqual(result.success_count, 1)

        # Verify summary exists
        summary_path = self.health_dir / "diagnostic-packs" / run_id / "usefulness_summary.json"
        self.assertTrue(summary_path.exists())

        summary_data = json.loads(summary_path.read_text(encoding="utf-8"))

        # by_command_family should exist since command_family is present
        self.assertIn("by_command_family", summary_data["context_aggregates"])
        # But the other rollups should not be present (no context to aggregate)
        self.assertNotIn("by_command_family_workstream", summary_data["context_aggregates"])
        self.assertNotIn("by_command_family_review_stage", summary_data["context_aggregates"])
        self.assertNotIn("by_command_family_problem_class", summary_data["context_aggregates"])

    def test_multi_run_import_produces_per_run_context_aggregates(self) -> None:
        """Test that multi-run import produces separate context_aggregates for each run."""
        run_id_1 = "health-run-A"
        run_id_2 = "health-run-B"

        # Create artifacts for both runs
        artifact_path_1 = self._create_execution_artifact(run_id_1, 0)
        artifact_path_2 = self._create_execution_artifact(run_id_2, 0)
        relative_path_1 = str(artifact_path_1.relative_to(self.health_dir))
        relative_path_2 = str(artifact_path_2.relative_to(self.health_dir))

        # Create feedback file with different context for each run (valid enum values)
        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": relative_path_1,
                    "run_id": run_id_1,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Run A logs",
                    "command_family": "kubectl-logs",
                    "workstream": "incident",
                },
                {
                    "artifact_path": relative_path_2,
                    "run_id": run_id_2,
                    "usefulness_class": "noisy",
                    "usefulness_summary": "Run B noisy",
                    "command_family": "kubectl-get",
                    "workstream": "drift",
                },
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
        )

        self.assertEqual(result.success_count, 2)

        # Check summary for run_id_1
        summary_path_1 = self.health_dir / "diagnostic-packs" / run_id_1 / "usefulness_summary.json"
        self.assertTrue(summary_path_1.exists())
        summary_data_1 = json.loads(summary_path_1.read_text(encoding="utf-8"))

        self.assertIn("context_aggregates", summary_data_1)
        self.assertEqual(summary_data_1["context_aggregates"]["by_command_family"]["kubectl-logs"]["useful"], 1)

        # Check summary for run_id_2
        summary_path_2 = self.health_dir / "diagnostic-packs" / run_id_2 / "usefulness_summary.json"
        self.assertTrue(summary_path_2.exists())
        summary_data_2 = json.loads(summary_path_2.read_text(encoding="utf-8"))

        self.assertIn("context_aggregates", summary_data_2)
        self.assertEqual(summary_data_2["context_aggregates"]["by_command_family"]["kubectl-get"]["noisy"], 1)


class TestDedupeKey(unittest.TestCase):
    """Tests for dedupe key generation."""

    def test_dedupe_key_deterministic(self) -> None:
        """Test that dedupe key is deterministic."""
        entry1 = {
            "run_id": "run-1",
            "candidate_index": 0,
            "artifact_path": "path/to/exec-0.json",
        }
        entry2 = {
            "run_id": "run-1",
            "candidate_index": 0,
            "artifact_path": "path/to/exec-0.json",
        }

        key1 = _generate_dedupe_key(entry1)
        key2 = _generate_dedupe_key(entry2)

        self.assertEqual(key1, key2)

    def test_dedupe_key_different_for_different_entries(self) -> None:
        """Test that different entries produce different keys."""
        entry1 = {
            "run_id": "run-1",
            "candidate_index": 0,
            "artifact_path": "path/to/exec-0.json",
        }
        entry2 = {
            "run_id": "run-1",
            "candidate_index": 1,
            "artifact_path": "path/to/exec-1.json",
        }

        key1 = _generate_dedupe_key(entry1)
        key2 = _generate_dedupe_key(entry2)

        self.assertNotEqual(key1, key2)


class TestSummaryGeneration(unittest.TestCase):
    """Tests for summary artifact generation."""

    def test_build_summary_includes_class_counts(self) -> None:
        """Test that summary includes usefulness class counts."""
        summary = _build_summary(
            run_id="test-run",
            usefulness_class_counts={"useful": 5, "noisy": 2, "empty": 1},
            command_family_counts={"kubectl-logs": 4, "kubectl-get": 4},
            duplicate_groups={"reimport": 1},
            total_entries=8,
            success_count=8,
            error_count=0,
        )

        self.assertEqual(summary["usefulness_class_counts"]["useful"], 5)
        self.assertEqual(summary["usefulness_class_counts"]["noisy"], 2)

    def test_build_summary_identifies_planner_improvements(self) -> None:
        """Test that summary identifies candidates for planner improvement."""
        summary = _build_summary(
            run_id="test-run",
            usefulness_class_counts={"useful": 5, "noisy": 3, "empty": 2, "partial": 1},
            command_family_counts={},
            duplicate_groups={},
            total_entries=11,
            success_count=11,
            error_count=0,
        )

        planner = summary["planner_improvement"]
        self.assertEqual(planner["candidate_count"], 6)  # noisy + empty + partial

        # Check recommendations are present
        recommendations = [c["recommendation"] for c in planner["candidates"]]
        self.assertTrue(any("false positives" in r for r in recommendations))
        self.assertTrue(any("connectivity" in r for r in recommendations))


class TestArtifactResolution(unittest.TestCase):
    """Tests for backward-compatible artifact path resolution."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True, exist_ok=True)

        # Create modern health/external-analysis layout
        self.modern_external_dir = self.health_dir / "external-analysis"
        self.modern_external_dir.mkdir(parents=True, exist_ok=True)

        # Create legacy runs/external-analysis layout
        self.legacy_external_dir = self.runs_dir / "external-analysis"
        self.legacy_external_dir.mkdir(parents=True, exist_ok=True)

        # Set allowed roots for testing
        _set_allowed_roots(self.runs_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_execution_artifact(self, artifact_path: Path) -> None:
        """Create a mock execution artifact at the given path."""
        artifact_data = {
            "purpose": "next-check-execution",
            "run_id": "test-run",
            "run_label": "test-run-label",
            "cluster_label": "cluster-a",
            "status": "success",
            "tool_name": "test-runner",
            "payload": {"candidateIndex": 0},
        }
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

    def test_modern_health_root_artifact_resolution(self) -> None:
        """Test resolution of modern health-root artifact layout."""
        # Create artifact in modern location: runs/health/external-analysis/
        artifact_path = self.modern_external_dir / "test-run-next-check-execution-0.json"
        self._create_execution_artifact(artifact_path)

        # Resolve with relative path from health directory
        result = _resolve_artifact_path(
            "external-analysis/test-run-next-check-execution-0.json",
            self.runs_dir,
            self.health_dir,
        )

        self.assertTrue(result.exists)
        self.assertEqual(result.resolution_mode, "modern")
        self.assertEqual(result.resolved_path, artifact_path)

    def test_legacy_runs_root_artifact_resolution(self) -> None:
        """Test resolution of legacy runs-root artifact layout."""
        # Create artifact in legacy location: runs/external-analysis/
        artifact_path = self.legacy_external_dir / "test-run-next-check-execution-0.json"
        self._create_execution_artifact(artifact_path)

        # Resolve with relative path that was used in legacy layout
        result = _resolve_artifact_path(
            "external-analysis/test-run-next-check-execution-0.json",
            self.runs_dir,
            self.health_dir,
        )

        self.assertTrue(result.exists)
        self.assertEqual(result.resolution_mode, "legacy")
        self.assertEqual(result.resolved_path, artifact_path)

    def test_modern_takes_precedence_over_legacy(self) -> None:
        """Test that modern layout takes precedence when artifact exists in both."""
        # Create artifact in both locations
        modern_artifact = self.modern_external_dir / "test-run-next-check-execution-0.json"
        self._create_execution_artifact(modern_artifact)

        legacy_artifact = self.legacy_external_dir / "test-run-next-check-execution-0.json"
        self._create_execution_artifact(legacy_artifact)

        # Should resolve to modern location first
        result = _resolve_artifact_path(
            "external-analysis/test-run-next-check-execution-0.json",
            self.runs_dir,
            self.health_dir,
        )

        self.assertTrue(result.exists)
        self.assertEqual(result.resolution_mode, "modern")
        self.assertEqual(result.resolved_path, modern_artifact)

    def test_unresolved_artifact_failure(self) -> None:
        """Test that unresolved artifact returns clear error."""
        result = _resolve_artifact_path(
            "external-analysis/nonexistent.json",
            self.runs_dir,
            self.health_dir,
        )

        self.assertFalse(result.exists)
        self.assertEqual(result.resolution_mode, "unresolved")

    def test_absolute_path_within_allowed_root(self) -> None:
        """Test that absolute paths within allowed roots are accepted."""
        # Create artifact in modern location
        artifact_path = self.modern_external_dir / "test-run-next-check-execution-0.json"
        self._create_execution_artifact(artifact_path)

        # Use absolute path
        result = _resolve_artifact_path(
            str(artifact_path),
            self.runs_dir,
            self.health_dir,
        )

        self.assertTrue(result.exists)
        self.assertEqual(result.resolution_mode, "absolute")
        # Use resolved paths to handle macOS /private/var/folders symlink
        self.assertEqual(result.resolved_path.resolve(), artifact_path.resolve())

    def test_absolute_path_outside_allowed_root_rejected(self) -> None:
        """Test that absolute paths outside allowed roots are rejected."""
        # Create artifact in a temporary location outside allowed roots
        other_dir = Path(tempfile.mkdtemp())
        try:
            artifact_path = other_dir / "external-analysis" / "test.json"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            self._create_execution_artifact(artifact_path)

            # Try to resolve absolute path outside allowed roots
            result = _resolve_artifact_path(
                str(artifact_path),
                self.runs_dir,
                self.health_dir,
            )

            self.assertFalse(result.exists)
            self.assertEqual(result.resolution_mode, "unresolved")
        finally:
            shutil.rmtree(other_dir, ignore_errors=True)


class TestImportWithLegacyArtifactLayout(unittest.TestCase):
    """Tests for import with legacy artifact layout."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True, exist_ok=True)

        # Create legacy runs/external-analysis layout (not under health/)
        self.legacy_external_dir = self.runs_dir / "external-analysis"
        self.legacy_external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_execution_artifact(self, artifact_path: Path) -> None:
        """Create a mock execution artifact."""
        artifact_data = {
            "purpose": "next-check-execution",
            "run_id": "test-run",
            "run_label": "test-run-label",
            "cluster_label": "cluster-a",
            "status": "success",
            "tool_name": "test-runner",
            "payload": {"candidateIndex": 0},
        }
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

    def _create_feedback_file(self, entries: list[dict]) -> Path:
        """Create a feedback file with given entries."""
        feedback_data = {
            "schema_version": "next-check-usefulness-feedback/v2",
            "run_id": "test-run",
            "run_label": "Test Run",
            "entries": entries,
        }
        feedback_path = self.tmpdir / "feedback.json"
        feedback_path.write_text(json.dumps(feedback_data), encoding="utf-8")
        return feedback_path

    def test_import_legacy_artifact_path_succeeds(self) -> None:
        """Test that import works with legacy artifact paths."""
        run_id = "test-run"

        # Create artifact in legacy location
        artifact_path = self.legacy_external_dir / f"{run_id}-next-check-execution-0.json"
        self._create_execution_artifact(artifact_path)

        # Feedback file references legacy path
        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": "external-analysis/test-run-next-check-execution-0.json",
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found logs in legacy location",
                }
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
            dry_run=True,
        )

        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.success_count, 1)

    def test_import_modern_artifact_path_succeeds(self) -> None:
        """Test that import still works with modern artifact paths."""
        run_id = "test-run"

        # Create modern health/external-analysis directory
        modern_dir = self.health_dir / "external-analysis"
        modern_dir.mkdir(parents=True, exist_ok=True)

        # Create artifact in modern location
        artifact_path = modern_dir / f"{run_id}-next-check-execution-0.json"
        self._create_execution_artifact(artifact_path)

        # Feedback file references modern path
        feedback_file = self._create_feedback_file(
            [
                {
                    "artifact_path": f"external-analysis/{run_id}-next-check-execution-0.json",
                    "run_id": run_id,
                    "usefulness_class": "useful",
                    "usefulness_summary": "Found logs in modern location",
                }
            ]
        )

        result = import_next_check_usefulness_feedback(
            self.runs_dir,
            feedback_file,
            dry_run=True,
        )

        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.success_count, 1)


if __name__ == "__main__":
    unittest.main()
