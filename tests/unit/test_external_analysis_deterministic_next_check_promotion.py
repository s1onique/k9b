"""Tests for deterministic next check promotion module.

Tests cover:
- Promotion decision logic and candidate ID generation
- Edge cases in coercion functions
- Error handling in collection functions
- Default values in queue entry building
- Missing field handling
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.deterministic_next_check_promotion import (
    DeterministicNextCheckPromotionPayload,
    _build_queue_entry,
    _coerce_optional_int,
    _coerce_optional_str,
    _coerce_str,
    _normalize_command_hint,
    _priority_label,
    build_promoted_candidate_id,
    collect_promoted_next_check_payloads,
    collect_promoted_queue_entries,
    write_deterministic_next_check_promotion,
)


class TestBuildPromotedCandidateId(unittest.TestCase):
    """Tests for build_promoted_candidate_id function."""

    def test_basic_candidate_id_generation(self) -> None:
        """Test basic candidate ID generation with description, cluster, and run_id."""
        result = build_promoted_candidate_id("Check pod logs", "cluster-a", "run-123")
        
        # Result should be a SHA256 hex string (64 characters)
        self.assertEqual(len(result), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_same_inputs_produce_same_id(self) -> None:
        """Test that same inputs produce the same candidate ID."""
        id1 = build_promoted_candidate_id("Check events", "cluster-b", "run-456")
        id2 = build_promoted_candidate_id("Check events", "cluster-b", "run-456")
        
        self.assertEqual(id1, id2)

    def test_different_inputs_produce_different_ids(self) -> None:
        """Test that different inputs produce different candidate IDs."""
        id1 = build_promoted_candidate_id("Check events", "cluster-a", "run-1")
        id2 = build_promoted_candidate_id("Different check", "cluster-a", "run-1")
        
        self.assertNotEqual(id1, id2)

    def test_description_whitespace_is_normalized(self) -> None:
        """Test that description whitespace is normalized."""
        id1 = build_promoted_candidate_id("  Check logs  ", "cluster", "run")
        id2 = build_promoted_candidate_id("Check logs", "cluster", "run")
        
        self.assertEqual(id1, id2)

    def test_empty_description(self) -> None:
        """Test handling of empty description."""
        result = build_promoted_candidate_id("", "cluster", "run")
        
        # Should still produce valid hash
        self.assertEqual(len(result), 64)


class TestCoerceStr(unittest.TestCase):
    """Tests for _coerce_str function."""

    def test_returns_string_unchanged(self) -> None:
        """Test that string values are returned unchanged."""
        result = _coerce_str("test string")
        self.assertEqual(result, "test string")

    def test_none_returns_empty_string(self) -> None:
        """Test that None returns empty string."""
        result = _coerce_str(None)
        self.assertEqual(result, "")

    def test_other_types_converted_to_string(self) -> None:
        """Test that non-string types are converted to strings."""
        self.assertEqual(_coerce_str(123), "123")
        self.assertEqual(_coerce_str(45.67), "45.67")
        self.assertEqual(_coerce_str(["a", "b"]), "['a', 'b']")
        self.assertEqual(_coerce_str({"key": "value"}), "{'key': 'value'}")


class TestCoerceOptionalStr(unittest.TestCase):
    """Tests for _coerce_optional_str function."""

    def test_returns_string_unchanged(self) -> None:
        """Test that string values are returned unchanged."""
        result = _coerce_optional_str("test string")
        self.assertEqual(result, "test string")

    def test_none_returns_none(self) -> None:
        """Test that None returns None."""
        result = _coerce_optional_str(None)
        self.assertIsNone(result)

    def test_other_types_converted_to_string(self) -> None:
        """Test that non-string types are converted to strings."""
        self.assertEqual(_coerce_optional_str(123), "123")
        self.assertEqual(_coerce_optional_str(True), "True")
        self.assertEqual(_coerce_optional_str(45.67), "45.67")


class TestCoerceOptionalInt(unittest.TestCase):
    """Tests for _coerce_optional_int function."""

    def test_returns_int_unchanged(self) -> None:
        """Test that integer values are returned unchanged."""
        result = _coerce_optional_int(42)
        self.assertEqual(result, 42)

    def test_float_converted_to_int(self) -> None:
        """Test that float values are converted to int."""
        result = _coerce_optional_int(42.9)
        self.assertEqual(result, 42)

    def test_none_returns_none(self) -> None:
        """Test that None returns None."""
        result = _coerce_optional_int(None)
        self.assertIsNone(result)

    def test_valid_string_converted(self) -> None:
        """Test that valid numeric strings are converted."""
        result = _coerce_optional_int("123")
        self.assertEqual(result, 123)

    def test_invalid_string_returns_none(self) -> None:
        """Test that invalid numeric strings return None."""
        result = _coerce_optional_int("not a number")
        self.assertIsNone(result)

    def test_empty_string_returns_none(self) -> None:
        """Test that empty string returns None."""
        result = _coerce_optional_int("")
        self.assertIsNone(result)


class TestNormalizeCommandHint(unittest.TestCase):
    """Tests for _normalize_command_hint function."""

    def test_method_takes_precedence(self) -> None:
        """Test that method field takes precedence over description."""
        payload = {"method": "kubectl get pods", "description": "Get pods"}
        result = _normalize_command_hint(payload)
        self.assertEqual(result, "kubectl get pods")

    def test_description_used_when_method_empty(self) -> None:
        """Test that description is used when method is empty."""
        payload = {"method": "", "description": "Get services"}
        result = _normalize_command_hint(payload)
        self.assertEqual(result, "Get services")

    def test_whitespace_is_normalized(self) -> None:
        """Test that whitespace in method is normalized."""
        payload = {"method": "  kubectl get pods  ", "description": "test"}
        result = _normalize_command_hint(payload)
        self.assertEqual(result, "kubectl get pods")

    def test_missing_fields_return_empty(self) -> None:
        """Test that missing fields return empty string."""
        payload: dict[str, object] = {}
        result = _normalize_command_hint(payload)
        self.assertEqual(result, "")


class TestPriorityLabel(unittest.TestCase):
    """Tests for _priority_label function."""

    def test_none_returns_secondary(self) -> None:
        """Test that None priority score returns 'secondary'."""
        result = _priority_label(None)
        self.assertEqual(result, "secondary")

    def test_high_priority_80_plus(self) -> None:
        """Test that score >= 80 returns 'primary'."""
        self.assertEqual(_priority_label(80), "primary")
        self.assertEqual(_priority_label(100), "primary")
        self.assertEqual(_priority_label(90), "primary")

    def test_medium_priority_50_to_79(self) -> None:
        """Test that score 50-79 returns 'secondary'."""
        self.assertEqual(_priority_label(50), "secondary")
        self.assertEqual(_priority_label(79), "secondary")
        self.assertEqual(_priority_label(75), "secondary")

    def test_low_priority_below_50(self) -> None:
        """Test that score < 50 returns 'fallback'."""
        self.assertEqual(_priority_label(49), "fallback")
        self.assertEqual(_priority_label(0), "fallback")
        self.assertEqual(_priority_label(-10), "fallback")


class TestBuildQueueEntry(unittest.TestCase):
    """Tests for _build_queue_entry function."""

    def test_basic_queue_entry_creation(self) -> None:
        """Test basic queue entry creation with all fields."""
        payload: DeterministicNextCheckPromotionPayload = {
            "description": "Check pod logs",
            "method": "kubectl logs",
            "evidenceNeeded": ["log_output"],
            "workstream": "incident",
            "urgency": "high",
            "whyNow": "Recent issue",
            "topProblem": "CrashLoopBackOff",
            "priorityScore": 85,
            "clusterLabel": "cluster-a",
            "targetContext": "default",
            "runId": "run-123",
            "candidateId": "candidate-abc",
            "promotionIndex": 0,
        }
        artifact_path = "external-analysis/test.json"
        
        result = _build_queue_entry(payload, artifact_path)
        
        self.assertEqual(result["candidateId"], "candidate-abc")
        self.assertEqual(result["candidateIndex"], 0)
        self.assertEqual(result["description"], "Check pod logs")
        self.assertEqual(result["targetCluster"], "cluster-a")
        self.assertEqual(result["targetContext"], "default")
        self.assertEqual(result["sourceReason"], "Recent issue")
        # expectedSignal is derived from command detection
        self.assertIsNotNone(result["expectedSignal"])
        self.assertFalse(result["safeToAutomate"])
        self.assertTrue(result["requiresOperatorApproval"])
        self.assertEqual(result["approvalState"], "approval-required")
        self.assertEqual(result["executionState"], "unexecuted")
        self.assertEqual(result["outcomeStatus"], "approval-required")
        self.assertEqual(result["latestArtifactPath"], artifact_path)
        self.assertEqual(result["queueStatus"], "approval-needed")
        self.assertEqual(result["planArtifactPath"], artifact_path)
        self.assertEqual(result["sourceType"], "deterministic")
        self.assertEqual(result["priorityLabel"], "primary")
        self.assertEqual(result["normalizationReason"], "deterministic-promoted")
        self.assertEqual(result["safetyReason"], "deterministic-promoted")
        self.assertEqual(result["approvalReason"], "deterministic-promoted")
        self.assertEqual(result["blockingReason"], "awaiting-review")
        self.assertEqual(result["workstream"], "incident")

    def test_priority_label_fallback(self) -> None:
        """Test queue entry with low priority score."""
        payload: DeterministicNextCheckPromotionPayload = {
            "description": "Low priority check",
            "priorityScore": 30,
            "clusterLabel": "cluster-b",
            "runId": "run-456",
            "candidateId": "candidate-def",
            "promotionIndex": 1,
        }
        
        result = _build_queue_entry(payload, "test.json")
        
        self.assertEqual(result["priorityLabel"], "fallback")

    def test_source_reason_fallback_chain(self) -> None:
        """Test source reason fallback chain: whyNow -> topProblem -> default."""
        # No whyNow or topProblem
        payload: DeterministicNextCheckPromotionPayload = {
            "description": "Test check",
            "clusterLabel": "cluster",
            "runId": "run",
            "candidateId": "candidate",
            "promotionIndex": 0,
        }
        
        result = _build_queue_entry(payload, "test.json")
        
        self.assertEqual(result["sourceReason"], "Deterministic next check")

    def test_source_reason_uses_top_problem_when_why_now_missing(self) -> None:
        """Test source reason uses topProblem when whyNow is missing."""
        payload: DeterministicNextCheckPromotionPayload = {
            "description": "Test check",
            "topProblem": "Pod crash",
            "clusterLabel": "cluster",
            "runId": "run",
            "candidateId": "candidate",
            "promotionIndex": 0,
        }
        
        result = _build_queue_entry(payload, "test.json")
        
        self.assertEqual(result["sourceReason"], "Pod crash")

    def test_description_fallback_to_default(self) -> None:
        """Test that empty description falls back to default."""
        payload: DeterministicNextCheckPromotionPayload = {
            "description": "",
            "clusterLabel": "cluster",
            "runId": "run",
            "candidateId": "candidate",
            "promotionIndex": 0,
        }
        
        result = _build_queue_entry(payload, "test.json")
        
        self.assertEqual(result["description"], "Deterministic next check")

    def test_empty_cluster_label(self) -> None:
        """Test handling of empty cluster label."""
        payload: DeterministicNextCheckPromotionPayload = {
            "description": "Test check",
            "clusterLabel": "",
            "runId": "run",
            "candidateId": "candidate",
            "promotionIndex": 0,
        }
        
        result = _build_queue_entry(payload, "test.json")
        
        self.assertEqual(result["targetCluster"], "")

    def test_workstream_preserved_when_present(self) -> None:
        """Test that workstream is preserved when present in payload."""
        payload: DeterministicNextCheckPromotionPayload = {
            "description": "Test check",
            "workstream": "evidence",
            "clusterLabel": "cluster",
            "runId": "run",
            "candidateId": "candidate",
            "promotionIndex": 0,
        }
        
        result = _build_queue_entry(payload, "test.json")
        
        self.assertEqual(result["workstream"], "evidence")

    def test_workstream_not_included_when_missing(self) -> None:
        """Test that workstream key is not included when missing."""
        payload: DeterministicNextCheckPromotionPayload = {
            "description": "Test check",
            "clusterLabel": "cluster",
            "runId": "run",
            "candidateId": "candidate",
            "promotionIndex": 0,
        }
        
        result = _build_queue_entry(payload, "test.json")
        
        self.assertNotIn("workstream", result)

    def test_workstream_not_included_when_empty_string(self) -> None:
        """Test that workstream key is not included when empty string."""
        payload: DeterministicNextCheckPromotionPayload = {
            "description": "Test check",
            "workstream": "",
            "clusterLabel": "cluster",
            "runId": "run",
            "candidateId": "candidate",
            "promotionIndex": 0,
        }
        
        result = _build_queue_entry(payload, "test.json")
        
        self.assertNotIn("workstream", result)

    def test_workstream_not_included_when_none(self) -> None:
        """Test that workstream key is not included when None."""
        payload: DeterministicNextCheckPromotionPayload = {
            "description": "Test check",
            "clusterLabel": "cluster",
            "runId": "run",
            "candidateId": "candidate",
            "promotionIndex": 0,
        }
        
        result = _build_queue_entry(payload, "test.json")
        
        self.assertNotIn("workstream", result)


class TestWriteDeterministicNextCheckPromotion(unittest.TestCase):
    """Tests for write_deterministic_next_check_promotion function."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_artifact_to_disk(self) -> None:
        """Test that promotion writes artifact to disk."""
        artifact, payload = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-001",
            run_label="test-run",
            cluster_label="cluster-x",
            target_context="default",
            summary={"description": "Test promotion"},
        )
        
        self.assertIsNotNone(artifact)
        self.assertEqual(artifact.tool_name, "deterministic-promoter")
        self.assertEqual(artifact.run_id, "run-001")
        self.assertEqual(artifact.cluster_label, "cluster-x")
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SUCCESS)
        self.assertEqual(artifact.purpose, ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION)
        
        # Check file exists
        self.assertIsNotNone(artifact.artifact_path)
        assert artifact.artifact_path is not None
        artifact_path_str: str = artifact.artifact_path
        artifact_path = self.tmpdir / artifact_path_str
        self.assertTrue(artifact_path.exists())

    def test_payload_contains_expected_fields(self) -> None:
        """Test that returned payload contains all expected fields."""
        _, payload = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-002",
            run_label="test-run",
            cluster_label="cluster-y",
            target_context="production",
            summary={
                "description": "Pod logs check",
                "method": "kubectl logs",
                "evidenceNeeded": ["logs"],
                "urgency": "high",
                "whyNow": "Crash detected",
                "topProblem": "CrashLoopBackOff",
                "priorityScore": 90,
                "workstream": "incident",
            },
        )
        
        self.assertEqual(payload["description"], "Pod logs check")
        self.assertEqual(payload["method"], "kubectl logs")
        self.assertEqual(payload["evidenceNeeded"], ["logs"])
        self.assertEqual(payload["urgency"], "high")
        self.assertEqual(payload["whyNow"], "Crash detected")
        self.assertEqual(payload["topProblem"], "CrashLoopBackOff")
        self.assertEqual(payload["priorityScore"], 90)
        self.assertEqual(payload["workstream"], "incident")
        self.assertEqual(payload["clusterLabel"], "cluster-y")
        self.assertEqual(payload["targetContext"], "production")
        self.assertEqual(payload["runId"], "run-002")
        self.assertEqual(payload["promotionIndex"], 0)
        self.assertIn("candidateId", payload)
        self.assertTrue(len(payload["candidateId"]) > 0)

    def test_increments_promotion_index(self) -> None:
        """Test that promotion index increments for same run."""
        # First promotion
        _, payload1 = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-003",
            run_label="test-run",
            cluster_label="cluster-z",
            target_context=None,
            summary={"description": "First check"},
        )
        
        # Second promotion
        _, payload2 = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-003",
            run_label="test-run",
            cluster_label="cluster-z",
            target_context=None,
            summary={"description": "Second check"},
        )
        
        self.assertEqual(payload1["promotionIndex"], 0)
        self.assertEqual(payload2["promotionIndex"], 1)

    def test_empty_description_normalized(self) -> None:
        """Test that empty description is normalized to empty string."""
        _, payload = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-004",
            run_label="test-run",
            cluster_label="cluster",
            target_context=None,
            summary={},
        )
        
        self.assertEqual(payload["description"], "")

    def test_description_whitespace_trimmed(self) -> None:
        """Test that description whitespace is trimmed."""
        _, payload = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-005",
            run_label="test-run",
            cluster_label="cluster",
            target_context=None,
            summary={"description": "  Check logs  "},
        )
        
        self.assertEqual(payload["description"], "Check logs")

    def test_missing_evidence_needed_defaults_to_empty_list(self) -> None:
        """Test that missing evidenceNeeded defaults to empty list."""
        _, payload = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-006",
            run_label="test-run",
            cluster_label="cluster",
            target_context=None,
            summary={},
        )
        
        self.assertEqual(payload["evidenceNeeded"], [])

    def test_evidence_needed_filters_non_strings(self) -> None:
        """Test that evidenceNeeded filters out non-string items."""
        _, payload = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-007",
            run_label="test-run",
            cluster_label="cluster",
            target_context=None,
            summary={"evidenceNeeded": ["valid", 123, "also_valid", None, "final"]},
        )
        
        self.assertEqual(payload["evidenceNeeded"], ["valid", "also_valid", "final"])

    def test_priority_score_coerced_from_string(self) -> None:
        """Test that priorityScore is coerced from string."""
        _, payload = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-008",
            run_label="test-run",
            cluster_label="cluster",
            target_context=None,
            summary={"priorityScore": "75"},
        )
        
        self.assertEqual(payload["priorityScore"], 75)

    def test_priority_score_coerced_from_float(self) -> None:
        """Test that priorityScore is coerced from float."""
        _, payload = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-009",
            run_label="test-run",
            cluster_label="cluster",
            target_context=None,
            summary={"priorityScore": 75.9},
        )
        
        self.assertEqual(payload["priorityScore"], 75)

    def test_written_artifact_is_valid_json(self) -> None:
        """Test that written artifact is valid JSON and can be parsed."""
        artifact, _ = write_deterministic_next_check_promotion(
            runs_dir=self.tmpdir,
            run_id="run-010",
            run_label="test-run",
            cluster_label="cluster",
            target_context=None,
            summary={"description": "JSON test"},
        )
        
        self.assertIsNotNone(artifact.artifact_path)
        assert artifact.artifact_path is not None
        artifact_path_str: str = artifact.artifact_path
        artifact_path = self.tmpdir / artifact_path_str
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        
        self.assertEqual(data["tool_name"], "deterministic-promoter")
        self.assertEqual(data["purpose"], "next-check-promotion")
        self.assertIsInstance(data["payload"], dict)


class TestCollectPromotedNextCheckPayloads(unittest.TestCase):
    """Tests for collect_promoted_next_check_payloads function."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_promotion_artifact(
        self,
        run_id: str,
        promotion_index: int,
        description: str = "Test check",
        cluster_label: str = "cluster",
        **extra_payload: Any,
    ) -> None:
        """Helper to create a promotion artifact file."""
        from k8s_diag_agent.external_analysis.artifact import write_external_analysis_artifact
        
        artifact = ExternalAnalysisArtifact(
            tool_name="deterministic-promoter",
            run_id=run_id,
            run_label="test",
            cluster_label=cluster_label,
            summary="Test",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
            payload={
                "description": description,
                "method": "kubectl get pods",
                "evidenceNeeded": [],
                "clusterLabel": cluster_label,
                "targetContext": None,
                "runId": run_id,
                "candidateId": f"candidate-{run_id}-{promotion_index}",
                "promotionIndex": promotion_index,
                **extra_payload,
            },
        )
        external_dir = self.tmpdir / "external-analysis"
        external_dir.mkdir(exist_ok=True)
        artifact_path = external_dir / f"{run_id}-next-check-promotion-{promotion_index}.json"
        write_external_analysis_artifact(artifact_path, artifact)

    def test_returns_empty_list_for_nonexistent_directory(self) -> None:
        """Test that function returns empty list when directory doesn't exist."""
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-nonexistent")
        self.assertEqual(result, [])

    def test_collects_promotions_for_specific_run(self) -> None:
        """Test that function collects promotions for a specific run."""
        self._create_promotion_artifact("run-a", 0)
        self._create_promotion_artifact("run-a", 1)
        self._create_promotion_artifact("run-b", 0)
        
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-a")
        
        self.assertEqual(len(result), 2)
        payloads = [p[0] for p in result]
        self.assertTrue(all(p["runId"] == "run-a" for p in payloads))

    def test_filters_out_other_run_ids(self) -> None:
        """Test that function filters out promotions from other runs."""
        self._create_promotion_artifact("run-other", 0)
        
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-target")
        
        self.assertEqual(len(result), 0)

    def test_returns_sorted_by_promotion_index(self) -> None:
        """Test that results are sorted by promotion index."""
        self._create_promotion_artifact("run-sort", 2)
        self._create_promotion_artifact("run-sort", 0)
        self._create_promotion_artifact("run-sort", 1)
        
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-sort")
        
        self.assertEqual(len(result), 3)
        payloads = [p[0] for p in result]
        self.assertEqual(payloads[0]["promotionIndex"], 0)
        self.assertEqual(payloads[1]["promotionIndex"], 1)
        self.assertEqual(payloads[2]["promotionIndex"], 2)

    def test_handles_corrupted_json_files(self) -> None:
        """Test that function handles corrupted JSON files gracefully."""
        external_dir = self.tmpdir / "external-analysis"
        external_dir.mkdir(exist_ok=True)
        (external_dir / "corrupted.json").write_text("not valid json{", encoding="utf-8")
        
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-any")
        
        self.assertEqual(result, [])

    def test_handles_missing_payload(self) -> None:
        """Test that function handles artifacts without payload."""
        external_dir = self.tmpdir / "external-analysis"
        external_dir.mkdir(exist_ok=True)
        artifact_path = external_dir / "no-payload.json"
        artifact_path.write_text(json.dumps({
            "tool_name": "test",
            "run_id": "run-test",
            "cluster_label": "cluster",
        }), encoding="utf-8")
        
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-test")
        
        self.assertEqual(result, [])

    def test_handles_invalid_run_id_in_payload(self) -> None:
        """Test that function handles artifacts with mismatched run_id in payload."""
        self._create_promotion_artifact("run-actual", 0)
        
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-expected")
        
        self.assertEqual(len(result), 0)

    def test_includes_artifact_path_in_result(self) -> None:
        """Test that result includes artifact path."""
        self._create_promotion_artifact("run-path", 0)
        
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-path")
        
        self.assertEqual(len(result), 1)
        _, rel_path = result[0]
        self.assertIn("external-analysis", rel_path)
        self.assertIn("run-path", rel_path)

    def test_coerces_payload_fields(self) -> None:
        """Test that payload fields are coerced correctly."""
        self._create_promotion_artifact(
            "run-coerce",
            0,
            description="Test",
            priorityScore="85",  # String instead of int
        )
        
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-coerce")
        
        self.assertEqual(len(result), 1)
        payload = result[0][0]
        self.assertEqual(payload["priorityScore"], 85)

    def test_handles_non_string_evidence_items(self) -> None:
        """Test that non-string evidence items are filtered."""
        self._create_promotion_artifact(
            "run-evidence",
            0,
            evidenceNeeded=[42, "valid", None, "item"],
        )
        
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-evidence")
        
        self.assertEqual(len(result), 1)
        payload = result[0][0]
        self.assertEqual(payload["evidenceNeeded"], ["valid", "item"])

    def test_returns_empty_for_non_matching_purpose(self) -> None:
        """Test that non-promotion purpose artifacts are filtered out."""
        from k8s_diag_agent.external_analysis.artifact import write_external_analysis_artifact
        
        external_dir = self.tmpdir / "external-analysis"
        external_dir.mkdir(exist_ok=True)
        artifact_path = external_dir / "other-purpose.json"
        
        artifact = ExternalAnalysisArtifact(
            tool_name="test",
            run_id="run-other-purpose",
            cluster_label="cluster",
            purpose=ExternalAnalysisPurpose.MANUAL,
            payload={
                "runId": "run-other-purpose",
                "description": "Test",
                "clusterLabel": "cluster",
                "candidateId": "c1",
                "promotionIndex": 0,
            },
        )
        write_external_analysis_artifact(artifact_path, artifact)
        
        result = collect_promoted_next_check_payloads(self.tmpdir, "run-other-purpose")
        
        self.assertEqual(len(result), 0)


class TestCollectPromotedQueueEntries(unittest.TestCase):
    """Tests for collect_promoted_queue_entries function."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_promotion_artifact(
        self,
        run_id: str,
        promotion_index: int,
        **payload_fields: Any,
    ) -> None:
        """Helper to create a promotion artifact file."""
        from k8s_diag_agent.external_analysis.artifact import write_external_analysis_artifact
        
        artifact = ExternalAnalysisArtifact(
            tool_name="deterministic-promoter",
            run_id=run_id,
            run_label="test",
            cluster_label="cluster",
            summary="Test",
            status=ExternalAnalysisStatus.SUCCESS,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PROMOTION,
            payload={
                "description": "Test check",
                "method": "kubectl get pods",
                "evidenceNeeded": [],
                "clusterLabel": "cluster",
                "targetContext": None,
                "runId": run_id,
                "candidateId": f"candidate-{promotion_index}",
                "promotionIndex": promotion_index,
                **payload_fields,
            },
        )
        external_dir = self.tmpdir / "external-analysis"
        external_dir.mkdir(exist_ok=True)
        artifact_path = external_dir / f"{run_id}-next-check-promotion-{promotion_index}.json"
        write_external_analysis_artifact(artifact_path, artifact)

    def test_returns_empty_list_for_nonexistent_run(self) -> None:
        """Test that function returns empty list for nonexistent run."""
        result = collect_promoted_queue_entries(self.tmpdir, "nonexistent")
        self.assertEqual(result, [])

    def test_collects_queue_entries_for_run(self) -> None:
        """Test that function collects queue entries for a run."""
        self._create_promotion_artifact("run-queue", 0)
        self._create_promotion_artifact("run-queue", 1)
        
        result = collect_promoted_queue_entries(self.tmpdir, "run-queue")
        
        self.assertEqual(len(result), 2)
        self.assertTrue(all("candidateId" in entry for entry in result))
        self.assertTrue(all(entry["sourceType"] == "deterministic" for entry in result))

    def test_queue_entries_have_correct_structure(self) -> None:
        """Test that queue entries have the correct structure."""
        self._create_promotion_artifact("run-struct", 0)
        
        result = collect_promoted_queue_entries(self.tmpdir, "run-struct")
        
        self.assertEqual(len(result), 1)
        entry = result[0]
        
        # Check required fields
        self.assertIn("candidateId", entry)
        self.assertIn("candidateIndex", entry)
        self.assertIn("description", entry)
        self.assertIn("targetCluster", entry)
        self.assertIn("sourceReason", entry)
        self.assertIn("expectedSignal", entry)
        self.assertIn("safeToAutomate", entry)
        self.assertIn("requiresOperatorApproval", entry)
        self.assertIn("approvalState", entry)
        self.assertIn("executionState", entry)
        self.assertIn("outcomeStatus", entry)
        self.assertIn("latestArtifactPath", entry)
        self.assertIn("queueStatus", entry)
        self.assertIn("sourceType", entry)
        self.assertIn("priorityLabel", entry)
        self.assertIn("normalizationReason", entry)
        self.assertIn("safetyReason", entry)
        self.assertIn("approvalReason", entry)
        self.assertIn("blockingReason", entry)

    def test_priority_score_affects_priority_label(self) -> None:
        """Test that priority score in payload affects priority label."""
        self._create_promotion_artifact("run-priority", 0, priorityScore=85)
        
        result = collect_promoted_queue_entries(self.tmpdir, "run-priority")
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["priorityLabel"], "primary")


if __name__ == "__main__":
    unittest.main()
