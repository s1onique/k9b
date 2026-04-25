"""Tests for auto-drilldown failure metadata propagation and prompt bounds."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.health.drilldown import DrilldownArtifact
from k8s_diag_agent.llm.drilldown_prompts import build_drilldown_prompt
from k8s_diag_agent.llm.llamacpp_provider import DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN, LLMFailureMetadata, LLMResponseParseError


def _make_drilldown() -> DrilldownArtifact:
    """Create a minimal DrilldownArtifact for auto-drilldown testing."""
    return DrilldownArtifact(
        run_label="test-cluster",
        run_id="run-001",
        timestamp=datetime.now(UTC),
        snapshot_timestamp=datetime.now(UTC),
        context="test-context",
        label="test-cluster",
        cluster_id="test-cluster-id",
        trigger_reasons=("test-reason",),
        missing_evidence=(),
        evidence_summary={"test": "data"},
        affected_namespaces=("default",),
        affected_workloads=(),
        warning_events=(),
        non_running_pods=(),
        pod_descriptions={},
        rollout_status=(),
        collection_timestamps={},
        artifact_path="test.json",
    )


class TestLLMResponseParseErrorDiagnostics(unittest.TestCase):
    """Test LLMResponseParseError carries structured diagnostics."""

    def test_error_with_length_finish_reason(self) -> None:
        """Test that LLMResponseParseError from length-capped response has correct metadata."""
        exc = LLMResponseParseError(
            "llama.cpp response text content is not valid JSON",
            finish_reason="length",
            response_content_chars=1500,
            response_content_prefix='{"observed',
            completion_stopped_by_length=True,
            max_tokens=768,
        )
        diags = exc.to_diagnostics()
        self.assertEqual(diags["finish_reason"], "length")
        self.assertTrue(diags["completion_stopped_by_length"])
        self.assertEqual(diags["response_content_chars"], 1500)
        self.assertEqual(diags["response_content_prefix"], '{"observed')
        self.assertEqual(diags["max_tokens"], 768)

    def test_error_without_length_is_not_capped(self) -> None:
        """Test that LLMResponseParseError without length finish_reason is not capped."""
        exc = LLMResponseParseError(
            "invalid JSON syntax",
            finish_reason="stop",
            response_content_chars=500,
            response_content_prefix="{",
            completion_stopped_by_length=False,
            max_tokens=768,
        )
        diags = exc.to_diagnostics()
        self.assertEqual(diags["finish_reason"], "stop")
        self.assertFalse(diags["completion_stopped_by_length"])


class TestPromptContainsBoundsConstraints(unittest.TestCase):
    """Test auto-drilldown prompt contains explicit bounded item counts."""

    def test_prompt_contains_max_3_items_constraint(self) -> None:
        """Test prompt contains max 3 items constraint."""
        prompt = build_drilldown_prompt(_make_drilldown())
        self.assertIn("max 3 items each", prompt)

    def test_prompt_contains_under_80_chars_constraint(self) -> None:
        """Test prompt contains description length constraint."""
        prompt = build_drilldown_prompt(_make_drilldown())
        self.assertIn("80 characters", prompt)

    def test_prompt_contains_no_exhaustive_events_constraint(self) -> None:
        """Test prompt contains no exhaustive event listings constraint."""
        prompt = build_drilldown_prompt(_make_drilldown())
        self.assertIn("exhaustive event listings", prompt)

    def test_prompt_contains_observed_signals(self) -> None:
        """Test prompt contains observed_signals in schema."""
        prompt = build_drilldown_prompt(_make_drilldown())
        self.assertIn("observed_signals", prompt)

    def test_prompt_contains_findings(self) -> None:
        """Test prompt contains findings in schema."""
        prompt = build_drilldown_prompt(_make_drilldown())
        self.assertIn("findings", prompt)

    def test_prompt_contains_hypotheses(self) -> None:
        """Test prompt contains hypotheses in schema."""
        prompt = build_drilldown_prompt(_make_drilldown())
        self.assertIn("hypotheses", prompt)

    def test_prompt_contains_next_evidence_to_collect(self) -> None:
        """Test prompt contains next_evidence_to_collect in schema."""
        prompt = build_drilldown_prompt(_make_drilldown())
        self.assertIn("next_evidence_to_collect", prompt)

    def test_constraint_section_present(self) -> None:
        """Test prompt contains Constraint: directive."""
        prompt = build_drilldown_prompt(_make_drilldown())
        self.assertIn("Constraint:", prompt)


class TestPromptContainsRequiredSchemaFields(unittest.TestCase):
    """Test auto-drilldown prompt schema reminder includes all required fields."""

    def test_prompt_contains_evidence_id_in_observed_signals(self) -> None:
        """Test prompt schema reminder includes evidence_id for observed_signals."""
        prompt = build_drilldown_prompt(_make_drilldown())
        # evidence_id is required for AssessorSignal.from_dict()
        self.assertIn("evidence_id", prompt)

    def test_prompt_contains_supporting_signals_in_findings(self) -> None:
        """Test prompt schema reminder includes supporting_signals for findings."""
        prompt = build_drilldown_prompt(_make_drilldown())
        # supporting_signals is included to keep the model output aligned with the compact schema and stable shape
        self.assertIn("supporting_signals", prompt)

    def test_prompt_contains_owner_in_next_evidence_to_collect(self) -> None:
        """Test prompt schema reminder includes owner for next_evidence_to_collect."""
        prompt = build_drilldown_prompt(_make_drilldown())
        # owner is required for AssessorNextCheck.from_dict()
        self.assertIn("owner", prompt)

    def test_prompt_contains_evidence_needed_in_next_evidence_to_collect(self) -> None:
        """Test prompt schema reminder includes evidence_needed for next_evidence_to_collect."""
        prompt = build_drilldown_prompt(_make_drilldown())
        # evidence_needed is included to keep the model output aligned with the compact schema and stable shape
        self.assertIn("evidence_needed", prompt)

    def test_prompt_contains_references_in_recommended_action(self) -> None:
        """Test prompt schema reminder includes references for recommended_action."""
        prompt = build_drilldown_prompt(_make_drilldown())
        # references is included to keep the model output aligned with the compact schema and stable shape
        self.assertIn("references", prompt)


class TestDefaultMaxTokens(unittest.TestCase):
    """Test max_tokens configuration for auto-drilldown."""

    def test_default_max_tokens_is_768(self) -> None:
        """Verify default max_tokens_auto_drilldown is 768."""
        self.assertEqual(DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN, 768)


class TestLLMFailureMetadataStructure(unittest.TestCase):
    """Test LLMFailureMetadata structure for auto-drilldown."""

    def test_metadata_has_core_failure_fields(self) -> None:
        """Test LLMFailureMetadata dataclass has core failure fields.

        Note: llm_call_id and llm_call are added by the builder function in loop.py,
        not by the LLMFailureMetadata dataclass itself.
        """
        from dataclasses import fields

        field_names = [f.name for f in fields(LLMFailureMetadata)]
        required = [
            "failure_class",
            "exception_type",
            "finish_reason",
            "completion_stopped_by_length",
            "response_content_chars",
            "response_content_prefix",
            "max_tokens",
            "provider",
            "operation",
        ]
        for req in required:
            self.assertIn(req, field_names, f"Missing required field: {req}")


if __name__ == "__main__":
    unittest.main()
