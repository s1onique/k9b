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

        # Check summary artifact exists
        summary_path = self.health_dir / "diagnostic-packs" / run_id / "usefulness_summary.json"
        self.assertTrue(summary_path.exists())

        summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary_data["schema_version"], "usefulness-summary/v1")
        self.assertEqual(summary_data["usefulness_class_counts"]["useful"], 1)


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


if __name__ == "__main__":
    unittest.main()
