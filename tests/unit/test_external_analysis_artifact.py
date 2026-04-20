"""Tests for external analysis artifact module.

Tests cover:
- Artifact class instantiation and field defaults
- Serialization to/from dict
- Enum field parsing and validation
- Edge cases in artifact handling
- Error handling for invalid inputs
"""

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    JudgmentScope,
    PackRefreshStatus,
    ProblemClass,
    ReviewerConfidence,
    ReviewStage,
    UsefulnessClass,
    Workstream,
    write_external_analysis_artifact,
)


class TestExternalAnalysisArtifactCreation(unittest.TestCase):
    """Tests for creating ExternalAnalysisArtifact instances."""

    def test_create_artifact_with_minimal_fields(self) -> None:
        """Test creating artifact with only required fields."""
        artifact = ExternalAnalysisArtifact(
            tool_name="k8sgpt",
            run_id="run-123",
            cluster_label="cluster-a",
        )

        self.assertEqual(artifact.tool_name, "k8sgpt")
        self.assertEqual(artifact.run_id, "run-123")
        self.assertEqual(artifact.cluster_label, "cluster-a")
        self.assertEqual(artifact.run_label, "")
        self.assertEqual(artifact.status, ExternalAnalysisStatus.PENDING)
        self.assertEqual(artifact.purpose, ExternalAnalysisPurpose.MANUAL)
        self.assertEqual(artifact.findings, ())
        self.assertEqual(artifact.suggested_next_checks, ())
        self.assertIsNone(artifact.summary)
        self.assertIsNone(artifact.raw_output)
        self.assertIsNotNone(artifact.timestamp)

    def test_create_artifact_with_all_fields(self) -> None:
        """Test creating artifact with all fields populated."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        artifact = ExternalAnalysisArtifact(
            tool_name="k8sgpt",
            run_id="run-456",
            cluster_label="cluster-b",
            run_label="analysis-run",
            source_artifact="health-assessment-123",
            summary="Found issues with pod scheduling",
            findings=("crashloop", "insufficient_cpu"),
            suggested_next_checks=("check_node_resources", "review_limits"),
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="Raw analysis output here",
            stdout_truncated=False,
            stderr_truncated=False,
            timed_out=False,
            timestamp=timestamp,
            artifact_path="/path/to/artifact.json",
            provider="k8sgpt",
            duration_ms=1500,
            purpose=ExternalAnalysisPurpose.AUTO_DRILLDOWN,
            payload={"key": "value"},
            error_summary=None,
            skip_reason=None,
            output_bytes_captured=4096,
            pack_refresh_status=PackRefreshStatus.SUCCEEDED,
            pack_refresh_warning=None,
            usefulness_class=UsefulnessClass.USEFUL,
            usefulness_summary="Very helpful for diagnosis",
            review_stage=ReviewStage.INITIAL_TRIAGE,
            workstream=Workstream.INCIDENT,
            problem_class=ProblemClass.CRASHLOOP,
            judgment_scope=JudgmentScope.RUN_CONTEXT,
            reviewer_confidence=ReviewerConfidence.HIGH,
        )

        self.assertEqual(artifact.tool_name, "k8sgpt")
        self.assertEqual(artifact.run_label, "analysis-run")
        self.assertEqual(artifact.source_artifact, "health-assessment-123")
        self.assertEqual(artifact.summary, "Found issues with pod scheduling")
        self.assertEqual(artifact.findings, ("crashloop", "insufficient_cpu"))
        self.assertEqual(artifact.suggested_next_checks, ("check_node_resources", "review_limits"))
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SUCCESS)
        self.assertEqual(artifact.raw_output, "Raw analysis output here")
        self.assertFalse(artifact.stdout_truncated)
        self.assertFalse(artifact.stderr_truncated)
        self.assertFalse(artifact.timed_out)
        self.assertEqual(artifact.timestamp, timestamp)
        self.assertEqual(artifact.artifact_path, "/path/to/artifact.json")
        self.assertEqual(artifact.provider, "k8sgpt")
        self.assertEqual(artifact.duration_ms, 1500)
        self.assertEqual(artifact.purpose, ExternalAnalysisPurpose.AUTO_DRILLDOWN)
        self.assertEqual(artifact.payload, {"key": "value"})
        self.assertEqual(artifact.output_bytes_captured, 4096)
        self.assertEqual(artifact.pack_refresh_status, PackRefreshStatus.SUCCEEDED)
        self.assertEqual(artifact.usefulness_class, UsefulnessClass.USEFUL)
        self.assertEqual(artifact.usefulness_summary, "Very helpful for diagnosis")
        self.assertEqual(artifact.review_stage, ReviewStage.INITIAL_TRIAGE)
        self.assertEqual(artifact.workstream, Workstream.INCIDENT)
        self.assertEqual(artifact.problem_class, ProblemClass.CRASHLOOP)
        self.assertEqual(artifact.judgment_scope, JudgmentScope.RUN_CONTEXT)
        self.assertEqual(artifact.reviewer_confidence, ReviewerConfidence.HIGH)

    def test_create_artifact_with_empty_tuples(self) -> None:
        """Test creating artifact with empty findings and next checks."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-empty",
            cluster_label="cluster-c",
            findings=(),
            suggested_next_checks=(),
        )

        self.assertEqual(artifact.findings, ())
        self.assertEqual(artifact.suggested_next_checks, ())

    def test_create_artifact_with_single_item_tuples(self) -> None:
        """Test creating artifact with single-item tuples."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-single",
            cluster_label="cluster-d",
            findings=("single_finding",),
            suggested_next_checks=("single_check",),
        )

        self.assertEqual(artifact.findings, ("single_finding",))
        self.assertEqual(artifact.suggested_next_checks, ("single_check",))


class TestExternalAnalysisArtifactSerialization(unittest.TestCase):
    """Tests for artifact serialization (to_dict and from_dict)."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_to_dict_includes_all_fields(self) -> None:
        """Test that to_dict includes all fields correctly."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        artifact = ExternalAnalysisArtifact(
            tool_name="k8sgpt",
            run_id="run-789",
            cluster_label="cluster-e",
            run_label="test-run",
            source_artifact="source-123",
            summary="Test summary",
            findings=("finding1", "finding2"),
            suggested_next_checks=("check1",),
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="raw output",
            stdout_truncated=True,
            stderr_truncated=False,
            timed_out=False,
            timestamp=timestamp,
            artifact_path="/path/to/artifact.json",
            provider="provider-x",
            duration_ms=2000,
            purpose=ExternalAnalysisPurpose.DIAGNOSTIC_PACK_REVIEW,
            payload={"data": "value"},
            error_summary=None,
            skip_reason=None,
            output_bytes_captured=5000,
            pack_refresh_status=PackRefreshStatus.SUCCEEDED,
            pack_refresh_warning="minor warning",
            usefulness_class=UsefulnessClass.PARTIAL,
            usefulness_summary="partial usefulness",
            review_stage=ReviewStage.FOCUSED_INVESTIGATION,
            workstream=Workstream.EVIDENCE,
            problem_class=ProblemClass.NETWORKING,
            judgment_scope=JudgmentScope.PATTERN_LEVEL,
            reviewer_confidence=ReviewerConfidence.MEDIUM,
        )

        result = artifact.to_dict()

        self.assertEqual(result["tool_name"], "k8sgpt")
        self.assertEqual(result["run_id"], "run-789")
        self.assertEqual(result["cluster_label"], "cluster-e")
        self.assertEqual(result["run_label"], "test-run")
        self.assertEqual(result["source_artifact"], "source-123")
        self.assertEqual(result["summary"], "Test summary")
        self.assertEqual(result["findings"], ["finding1", "finding2"])
        self.assertEqual(result["suggested_next_checks"], ["check1"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["raw_output"], "raw output")
        self.assertTrue(result["stdout_truncated"])
        self.assertFalse(result["stderr_truncated"])
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["timestamp"], timestamp.isoformat())
        self.assertEqual(result["artifact_path"], "/path/to/artifact.json")
        self.assertEqual(result["provider"], "provider-x")
        self.assertEqual(result["duration_ms"], 2000)
        self.assertEqual(result["purpose"], "diagnostic-pack-review")
        self.assertEqual(result["payload"], {"data": "value"})
        self.assertEqual(result["output_bytes_captured"], 5000)
        self.assertEqual(result["pack_refresh_status"], "succeeded")
        self.assertEqual(result["pack_refresh_warning"], "minor warning")
        self.assertEqual(result["usefulness_class"], "partial")
        self.assertEqual(result["usefulness_summary"], "partial usefulness")
        self.assertEqual(result["review_stage"], "focused_investigation")
        self.assertEqual(result["workstream"], "evidence")
        self.assertEqual(result["problem_class"], "networking")
        self.assertEqual(result["judgment_scope"], "pattern_level")
        self.assertEqual(result["reviewer_confidence"], "medium")

    def test_to_dict_includes_none_values_for_optional_fields(self) -> None:
        """Test that to_dict includes None values for optional fields."""
        artifact = ExternalAnalysisArtifact(
            tool_name="k8sgpt",
            run_id="run-minimal",
            cluster_label="cluster-f",
        )

        result = artifact.to_dict()

        # All fields should be present with None values
        self.assertIn("source_artifact", result)
        self.assertIsNone(result["source_artifact"])
        self.assertIn("summary", result)
        self.assertIsNone(result["summary"])
        self.assertIn("raw_output", result)
        self.assertIsNone(result["raw_output"])
        self.assertIn("error_summary", result)
        self.assertIsNone(result["error_summary"])
        self.assertIn("skip_reason", result)
        self.assertIsNone(result["skip_reason"])
        self.assertIn("pack_refresh_warning", result)
        self.assertIsNone(result["pack_refresh_warning"])
        # Optional enum fields should not be present when None
        self.assertNotIn("usefulness_class", result)
        self.assertNotIn("usefulness_summary", result)
        self.assertNotIn("review_stage", result)
        self.assertNotIn("workstream", result)
        self.assertNotIn("problem_class", result)
        self.assertNotIn("judgment_scope", result)
        self.assertNotIn("reviewer_confidence", result)

    def test_to_dict_converts_tuples_to_lists(self) -> None:
        """Test that to_dict converts tuple fields to lists."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-tuples",
            cluster_label="cluster-g",
            findings=("a", "b", "c"),
            suggested_next_checks=("x", "y"),
        )

        result = artifact.to_dict()

        self.assertIsInstance(result["findings"], list)
        self.assertIsInstance(result["suggested_next_checks"], list)
        self.assertEqual(result["findings"], ["a", "b", "c"])
        self.assertEqual(result["suggested_next_checks"], ["x", "y"])

    def test_from_dict_with_complete_data(self) -> None:
        """Test parsing artifact from dict with all fields."""
        timestamp_str = "2024-01-15T10:30:00+00:00"
        raw = {
            "tool_name": "k8sgpt",
            "run_id": "run-from-dict",
            "cluster_label": "cluster-h",
            "run_label": "parsed-run",
            "source_artifact": "source-artifact",
            "summary": "Parsed summary",
            "findings": ["finding1", "finding2"],
            "suggested_next_checks": ["next1", "next2"],
            "status": "success",
            "raw_output": "raw output content",
            "stdout_truncated": True,
            "stderr_truncated": False,
            "timed_out": False,
            "timestamp": timestamp_str,
            "artifact_path": "/parsed/path.json",
            "provider": "parsed-provider",
            "duration_ms": 3000,
            "purpose": "auto-drilldown",
            "payload": {"key": "parsed_value"},
            "error_summary": None,
            "skip_reason": None,
            "output_bytes_captured": 8000,
            "pack_refresh_status": "succeeded",
            "pack_refresh_warning": None,
            "usefulness_class": "noisy",
            "usefulness_summary": "Too much noise",
            "review_stage": "parity_validation",
            "workstream": "drift",
            "problem_class": "platform_drift",
            "judgment_scope": "run_context",
            "reviewer_confidence": "low",
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertEqual(artifact.tool_name, "k8sgpt")
        self.assertEqual(artifact.run_id, "run-from-dict")
        self.assertEqual(artifact.cluster_label, "cluster-h")
        self.assertEqual(artifact.run_label, "parsed-run")
        self.assertEqual(artifact.source_artifact, "source-artifact")
        self.assertEqual(artifact.summary, "Parsed summary")
        self.assertEqual(artifact.findings, ("finding1", "finding2"))
        self.assertEqual(artifact.suggested_next_checks, ("next1", "next2"))
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SUCCESS)
        self.assertEqual(artifact.raw_output, "raw output content")
        self.assertTrue(artifact.stdout_truncated)
        self.assertFalse(artifact.stderr_truncated)
        self.assertFalse(artifact.timed_out)
        self.assertEqual(artifact.timestamp, datetime.fromisoformat(timestamp_str))
        self.assertEqual(artifact.artifact_path, "/parsed/path.json")
        self.assertEqual(artifact.provider, "parsed-provider")
        self.assertEqual(artifact.duration_ms, 3000)
        self.assertEqual(artifact.purpose, ExternalAnalysisPurpose.AUTO_DRILLDOWN)
        self.assertEqual(artifact.payload, {"key": "parsed_value"})
        self.assertEqual(artifact.output_bytes_captured, 8000)
        self.assertEqual(artifact.pack_refresh_status, PackRefreshStatus.SUCCEEDED)
        self.assertEqual(artifact.usefulness_class, UsefulnessClass.NOISY)
        self.assertEqual(artifact.usefulness_summary, "Too much noise")
        self.assertEqual(artifact.review_stage, ReviewStage.PARITY_VALIDATION)
        self.assertEqual(artifact.workstream, Workstream.DRIFT)
        self.assertEqual(artifact.problem_class, ProblemClass.PLATFORM_DRIFT)
        self.assertEqual(artifact.judgment_scope, JudgmentScope.RUN_CONTEXT)
        self.assertEqual(artifact.reviewer_confidence, ReviewerConfidence.LOW)

    def test_from_dict_with_minimal_data(self) -> None:
        """Test parsing artifact from dict with only required fields."""
        raw = {
            "tool_name": "minimal-tool",
            "run_id": "run-min",
            "cluster_label": "cluster-min",
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertEqual(artifact.tool_name, "minimal-tool")
        self.assertEqual(artifact.run_id, "run-min")
        self.assertEqual(artifact.cluster_label, "cluster-min")
        self.assertEqual(artifact.run_label, "")
        self.assertEqual(artifact.status, ExternalAnalysisStatus.PENDING)
        self.assertEqual(artifact.purpose, ExternalAnalysisPurpose.MANUAL)
        self.assertEqual(artifact.findings, ())
        self.assertEqual(artifact.suggested_next_checks, ())
        self.assertIsNone(artifact.summary)
        self.assertIsNone(artifact.payload)

    def test_from_dict_empty_lists_become_tuples(self) -> None:
        """Test that empty lists in dict become empty tuples."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-empty",
            "cluster_label": "cluster-empty",
            "findings": [],
            "suggested_next_checks": [],
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertEqual(artifact.findings, ())
        self.assertEqual(artifact.suggested_next_checks, ())

    def test_roundtrip_serialization(self) -> None:
        """Test that artifact survives to_dict -> from_dict roundtrip."""
        original = ExternalAnalysisArtifact(
            tool_name="roundtrip-tool",
            run_id="run-roundtrip",
            cluster_label="cluster-rt",
            run_label="roundtrip-run",
            source_artifact="rt-source",
            summary="Roundtrip summary",
            findings=("finding_rt_1", "finding_rt_2"),
            suggested_next_checks=("check_rt",),
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="raw rt output",
            stdout_truncated=False,
            stderr_truncated=True,
            timed_out=False,
            duration_ms=1500,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            payload={"rt_key": "rt_value"},
            output_bytes_captured=1024,
            pack_refresh_status=PackRefreshStatus.TIMED_OUT,
            pack_refresh_warning="timeout occurred",
            usefulness_class=UsefulnessClass.EMPTY,
            usefulness_summary="No data captured",
            review_stage=ReviewStage.FOLLOW_UP,
            workstream=Workstream.UNKNOWN,
            problem_class=ProblemClass.UNKNOWN,
            judgment_scope=JudgmentScope.PATTERN_LEVEL,
            reviewer_confidence=ReviewerConfidence.HIGH,
        )

        # Serialize and deserialize
        serialized = original.to_dict()
        restored = ExternalAnalysisArtifact.from_dict(serialized)

        # Compare all fields
        self.assertEqual(restored.tool_name, original.tool_name)
        self.assertEqual(restored.run_id, original.run_id)
        self.assertEqual(restored.cluster_label, original.cluster_label)
        self.assertEqual(restored.run_label, original.run_label)
        self.assertEqual(restored.source_artifact, original.source_artifact)
        self.assertEqual(restored.summary, original.summary)
        self.assertEqual(restored.findings, original.findings)
        self.assertEqual(restored.suggested_next_checks, original.suggested_next_checks)
        self.assertEqual(restored.status, original.status)
        self.assertEqual(restored.raw_output, original.raw_output)
        self.assertEqual(restored.stdout_truncated, original.stdout_truncated)
        self.assertEqual(restored.stderr_truncated, original.stderr_truncated)
        self.assertEqual(restored.timed_out, original.timed_out)
        self.assertEqual(restored.duration_ms, original.duration_ms)
        self.assertEqual(restored.purpose, original.purpose)
        self.assertEqual(restored.payload, original.payload)
        self.assertEqual(restored.output_bytes_captured, original.output_bytes_captured)
        self.assertEqual(restored.pack_refresh_status, original.pack_refresh_status)
        self.assertEqual(restored.pack_refresh_warning, original.pack_refresh_warning)
        self.assertEqual(restored.usefulness_class, original.usefulness_class)
        self.assertEqual(restored.usefulness_summary, original.usefulness_summary)
        self.assertEqual(restored.review_stage, original.review_stage)
        self.assertEqual(restored.workstream, original.workstream)
        self.assertEqual(restored.problem_class, original.problem_class)
        self.assertEqual(restored.judgment_scope, original.judgment_scope)
        self.assertEqual(restored.reviewer_confidence, original.reviewer_confidence)


class TestExternalAnalysisArtifactEdgeCases(unittest.TestCase):
    """Tests for edge cases in artifact handling."""

    def test_from_dict_with_string_numeric_fields(self) -> None:
        """Test parsing numeric fields that are strings."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-numeric",
            "cluster_label": "cluster-num",
            "duration_ms": "1500",  # String instead of int
            "output_bytes_captured": "4096",  # String instead of int
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertEqual(artifact.duration_ms, 1500)
        self.assertEqual(artifact.output_bytes_captured, 4096)

    def test_from_dict_with_float_numeric_fields(self) -> None:
        """Test parsing numeric fields that are floats."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-float",
            "cluster_label": "cluster-float",
            "duration_ms": 1500.7,  # Float
            "output_bytes_captured": 4096.9,  # Float
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertEqual(artifact.duration_ms, 1500)
        self.assertEqual(artifact.output_bytes_captured, 4096)

    def test_from_dict_with_invalid_numeric_strings(self) -> None:
        """Test parsing invalid numeric strings returns None."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-invalid",
            "cluster_label": "cluster-invalid",
            "duration_ms": "not-a-number",
            "output_bytes_captured": "also-invalid",
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertIsNone(artifact.duration_ms)
        self.assertIsNone(artifact.output_bytes_captured)

    def test_from_dict_with_boolean_fields(self) -> None:
        """Test parsing boolean truncation and timeout fields."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-bool",
            "cluster_label": "cluster-bool",
            "stdout_truncated": "true",  # String "true" - truthy, becomes True
            "stderr_truncated": 1,  # Integer 1 - truthy, becomes True
            "timed_out": "false",  # String "false" - still truthy, becomes True
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        # Note: bool("false") is True because it's a non-empty string
        # The implementation uses bool() which converts any non-empty string to True
        self.assertTrue(artifact.stdout_truncated)
        self.assertTrue(artifact.stderr_truncated)
        self.assertTrue(artifact.timed_out)  # "false" is truthy

    def test_from_dict_with_explicit_boolean_values(self) -> None:
        """Test parsing explicit boolean values (not strings)."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-explicit-bool",
            "cluster_label": "cluster-explicit-bool",
            "stdout_truncated": True,
            "stderr_truncated": False,
            "timed_out": False,
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertTrue(artifact.stdout_truncated)
        self.assertFalse(artifact.stderr_truncated)
        self.assertFalse(artifact.timed_out)

    def test_from_dict_with_missing_boolean_fields(self) -> None:
        """Test that missing boolean fields are None."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-missing-bool",
            "cluster_label": "cluster-missing-bool",
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertIsNone(artifact.stdout_truncated)
        self.assertIsNone(artifact.stderr_truncated)
        self.assertIsNone(artifact.timed_out)

    def test_from_dict_with_invalid_enum_values(self) -> None:
        """Test that invalid enum values result in None for optional fields."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-invalid-enum",
            "cluster_label": "cluster-invalid-enum",
            "usefulness_class": "invalid_class",
            "pack_refresh_status": "invalid_status",
            "review_stage": "invalid_stage",
            "workstream": "invalid_workstream",
            "problem_class": "invalid_problem",
            "judgment_scope": "invalid_scope",
            "reviewer_confidence": "invalid_confidence",
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertIsNone(artifact.usefulness_class)
        self.assertIsNone(artifact.pack_refresh_status)
        self.assertIsNone(artifact.review_stage)
        self.assertIsNone(artifact.workstream)
        self.assertIsNone(artifact.problem_class)
        self.assertIsNone(artifact.judgment_scope)
        self.assertIsNone(artifact.reviewer_confidence)

    def test_from_dict_with_invalid_status_raises_error(self) -> None:
        """Test that invalid status raises ValueError (not defaulting)."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-invalid-status",
            "cluster_label": "cluster-status",
            "status": "invalid_status_value",
        }

        # The implementation uses ExternalAnalysisStatus(status_raw) which raises ValueError
        # for invalid values, unlike optional enums which are caught
        with self.assertRaises(ValueError):
            ExternalAnalysisArtifact.from_dict(raw)

    def test_from_dict_with_invalid_purpose_raises_error(self) -> None:
        """Test that invalid purpose raises ValueError (not defaulting)."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-invalid-purpose",
            "cluster_label": "cluster-purpose",
            "purpose": "invalid_purpose_value",
        }

        # The implementation uses ExternalAnalysisPurpose(purpose_raw) which raises ValueError
        with self.assertRaises(ValueError):
            ExternalAnalysisArtifact.from_dict(raw)

    def test_from_dict_with_missing_timestamp_uses_now(self) -> None:
        """Test that missing timestamp uses current time."""
        before = datetime.now(UTC)
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-no-timestamp",
            "cluster_label": "cluster-no-ts",
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)
        after = datetime.now(UTC)

        self.assertGreaterEqual(artifact.timestamp, before)
        self.assertLessEqual(artifact.timestamp, after)

    def test_from_dict_with_invalid_timestamp_format_raises_error(self) -> None:
        """Test that invalid timestamp format raises ValueError to fail fast on corrupt artifacts."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-invalid-ts",
            "cluster_label": "cluster-invalid-ts",
            "timestamp": "not-a-valid-timestamp",
        }

        # Invalid timestamp formats should raise ValueError, not silently fall back to now()
        with self.assertRaises(ValueError) as ctx:
            ExternalAnalysisArtifact.from_dict(raw)
        self.assertIn("Invalid timestamp format", str(ctx.exception))

    def test_from_dict_with_mapping_payload(self) -> None:
        """Test that Mapping payload is converted to dict."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-payload",
            "cluster_label": "cluster-payload",
            "payload": {"nested": {"key": "value"}},
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertEqual(artifact.payload, {"nested": {"key": "value"}})

    def test_from_dict_with_non_mapping_payload_becomes_none(self) -> None:
        """Test that non-Mapping payload becomes None."""
        raw = {
            "tool_name": "test-tool",
            "run_id": "run-bad-payload",
            "cluster_label": "cluster-bad-payload",
            "payload": "not a mapping",
        }

        artifact = ExternalAnalysisArtifact.from_dict(raw)

        self.assertIsNone(artifact.payload)


class TestWriteExternalAnalysisArtifact(unittest.TestCase):
    """Tests for write_external_analysis_artifact function."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_artifact_creates_json_file(self) -> None:
        """Test that write_external_analysis_artifact creates a JSON file."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-write",
            cluster_label="cluster-write",
            summary="Write test summary",
            findings=("finding_write",),
        )

        output_path = self.tmpdir / "artifact.json"
        result = write_external_analysis_artifact(output_path, artifact)

        self.assertEqual(result, output_path)
        self.assertTrue(output_path.exists())
        self.assertTrue(output_path.is_file())

    def test_write_artifact_creates_parent_directories(self) -> None:
        """Test that write_external_analysis_artifact creates parent directories."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-nested",
            cluster_label="cluster-nested",
        )

        nested_path = self.tmpdir / "nested" / "deep" / "path" / "artifact.json"
        result = write_external_analysis_artifact(nested_path, artifact)

        self.assertTrue(result.exists())
        self.assertTrue(nested_path.parent.exists())

    def test_write_artifact_produces_valid_json(self) -> None:
        """Test that written file contains valid JSON."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-json",
            cluster_label="cluster-json",
            summary="JSON test",
            findings=("a", "b"),
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.MANUAL,
        )

        output_path = self.tmpdir / "artifact.json"
        write_external_analysis_artifact(output_path, artifact)

        # Should be valid JSON
        data = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(data["tool_name"], "test-tool")
        self.assertEqual(data["run_id"], "run-json")
        self.assertEqual(data["cluster_label"], "cluster-json")
        self.assertEqual(data["summary"], "JSON test")
        self.assertEqual(data["findings"], ["a", "b"])
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["purpose"], "manual")

    def test_write_and_read_roundtrip(self) -> None:
        """Test that artifact can be written and read back."""
        original = ExternalAnalysisArtifact(
            tool_name="roundtrip-write-tool",
            run_id="run-rw",
            cluster_label="cluster-rw",
            summary="Roundtrip write test",
            findings=("rw_finding",),
            suggested_next_checks=("rw_check",),
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_APPROVAL,
            usefulness_class=UsefulnessClass.USEFUL,
            usefulness_summary="Very useful",
            review_stage=ReviewStage.INITIAL_TRIAGE,
            workstream=Workstream.INCIDENT,
            problem_class=ProblemClass.CRASHLOOP,
            judgment_scope=JudgmentScope.RUN_CONTEXT,
            reviewer_confidence=ReviewerConfidence.HIGH,
        )

        output_path = self.tmpdir / "roundtrip.json"
        write_external_analysis_artifact(output_path, original)

        # Read back
        data = json.loads(output_path.read_text(encoding="utf-8"))
        restored = ExternalAnalysisArtifact.from_dict(data)

        self.assertEqual(restored.tool_name, original.tool_name)
        self.assertEqual(restored.run_id, original.run_id)
        self.assertEqual(restored.cluster_label, original.cluster_label)
        self.assertEqual(restored.summary, original.summary)
        self.assertEqual(restored.findings, original.findings)
        self.assertEqual(restored.suggested_next_checks, original.suggested_next_checks)
        self.assertEqual(restored.status, original.status)
        self.assertEqual(restored.purpose, original.purpose)
        self.assertEqual(restored.usefulness_class, original.usefulness_class)
        self.assertEqual(restored.usefulness_summary, original.usefulness_summary)
        self.assertEqual(restored.review_stage, original.review_stage)
        self.assertEqual(restored.workstream, original.workstream)
        self.assertEqual(restored.problem_class, original.problem_class)
        self.assertEqual(restored.judgment_scope, original.judgment_scope)
        self.assertEqual(restored.reviewer_confidence, original.reviewer_confidence)


class TestAllEnumValues(unittest.TestCase):
    """Tests verifying all enum values can be used."""

    def test_all_external_analysis_status_values(self) -> None:
        """Test all ExternalAnalysisStatus enum values."""
        statuses = [
            ExternalAnalysisStatus.PENDING,
            ExternalAnalysisStatus.SUCCESS,
            ExternalAnalysisStatus.FAILED,
            ExternalAnalysisStatus.SKIPPED,
        ]
        for status in statuses:
            artifact = ExternalAnalysisArtifact(
                tool_name="test",
                run_id="run-status",
                cluster_label="cluster",
                status=status,
            )
            self.assertEqual(artifact.status, status)

    def test_all_external_analysis_purpose_values(self) -> None:
        """Test all ExternalAnalysisPurpose enum values."""
        purposes = [
            ExternalAnalysisPurpose.MANUAL,
            ExternalAnalysisPurpose.AUTO_DRILLDOWN,
            ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
            ExternalAnalysisPurpose.NEXT_CHECK_APPROVAL,
            ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            ExternalAnalysisPurpose.DIAGNOSTIC_PACK_REVIEW,
        ]
        for purpose in purposes:
            artifact = ExternalAnalysisArtifact(
                tool_name="test",
                run_id="run-purpose",
                cluster_label="cluster",
                purpose=purpose,
            )
            self.assertEqual(artifact.purpose, purpose)

    def test_all_pack_refresh_status_values(self) -> None:
        """Test all PackRefreshStatus enum values."""
        statuses = [
            PackRefreshStatus.SUCCEEDED,
            PackRefreshStatus.FAILED,
            PackRefreshStatus.TIMED_OUT,
        ]
        for status in statuses:
            artifact = ExternalAnalysisArtifact(
                tool_name="test",
                run_id="run-pack-refresh",
                cluster_label="cluster",
                pack_refresh_status=status,
            )
            self.assertEqual(artifact.pack_refresh_status, status)

    def test_all_usefulness_class_values(self) -> None:
        """Test all UsefulnessClass enum values."""
        classes = [
            UsefulnessClass.USEFUL,
            UsefulnessClass.PARTIAL,
            UsefulnessClass.NOISY,
            UsefulnessClass.EMPTY,
        ]
        for cls in classes:
            artifact = ExternalAnalysisArtifact(
                tool_name="test",
                run_id="run-usefulness",
                cluster_label="cluster",
                usefulness_class=cls,
            )
            self.assertEqual(artifact.usefulness_class, cls)

    def test_all_review_stage_values(self) -> None:
        """Test all ReviewStage enum values."""
        stages = [
            ReviewStage.INITIAL_TRIAGE,
            ReviewStage.FOCUSED_INVESTIGATION,
            ReviewStage.PARITY_VALIDATION,
            ReviewStage.FOLLOW_UP,
            ReviewStage.UNKNOWN,
        ]
        for stage in stages:
            artifact = ExternalAnalysisArtifact(
                tool_name="test",
                run_id="run-review-stage",
                cluster_label="cluster",
                review_stage=stage,
            )
            self.assertEqual(artifact.review_stage, stage)

    def test_all_workstream_values(self) -> None:
        """Test all Workstream enum values."""
        workstreams = [
            Workstream.INCIDENT,
            Workstream.EVIDENCE,
            Workstream.DRIFT,
            Workstream.UNKNOWN,
        ]
        for ws in workstreams:
            artifact = ExternalAnalysisArtifact(
                tool_name="test",
                run_id="run-workstream",
                cluster_label="cluster",
                workstream=ws,
            )
            self.assertEqual(artifact.workstream, ws)

    def test_all_problem_class_values(self) -> None:
        """Test all ProblemClass enum values."""
        problems = [
            ProblemClass.WORKLOAD_FAILURE,
            ProblemClass.READINESS_PROBE,
            ProblemClass.LIVENESS_PROBE,
            ProblemClass.CRASHLOOP,
            ProblemClass.IMAGE_PULL,
            ProblemClass.JOB_FAILURE,
            ProblemClass.NODE_CONDITION,
            ProblemClass.PLATFORM_DRIFT,
            ProblemClass.NETWORKING,
            ProblemClass.STORAGE,
            ProblemClass.UNKNOWN,
        ]
        for problem in problems:
            artifact = ExternalAnalysisArtifact(
                tool_name="test",
                run_id="run-problem",
                cluster_label="cluster",
                problem_class=problem,
            )
            self.assertEqual(artifact.problem_class, problem)

    def test_all_judgment_scope_values(self) -> None:
        """Test all JudgmentScope enum values."""
        scopes = [
            JudgmentScope.RUN_CONTEXT,
            JudgmentScope.PATTERN_LEVEL,
        ]
        for scope in scopes:
            artifact = ExternalAnalysisArtifact(
                tool_name="test",
                run_id="run-judgment",
                cluster_label="cluster",
                judgment_scope=scope,
            )
            self.assertEqual(artifact.judgment_scope, scope)

    def test_all_reviewer_confidence_values(self) -> None:
        """Test all ReviewerConfidence enum values."""
        confidences = [
            ReviewerConfidence.LOW,
            ReviewerConfidence.MEDIUM,
            ReviewerConfidence.HIGH,
        ]
        for confidence in confidences:
            artifact = ExternalAnalysisArtifact(
                tool_name="test",
                run_id="run-confidence",
                cluster_label="cluster",
                reviewer_confidence=confidence,
            )
            self.assertEqual(artifact.reviewer_confidence, confidence)


if __name__ == "__main__":
    unittest.main()
