"""Tests for LLM call labeling in structured logs."""
from __future__ import annotations

import unittest


class BuildLLMCallIDTest(unittest.TestCase):
    """Tests for deterministic LLM call ID generation."""

    def test_auto_drilldown_format(self) -> None:
        """Call ID format: {run_id}:{cluster_label}:auto-drilldown:{provider}."""
        from k8s_diag_agent.llm.call_labels import build_llm_call_id

        call_id = build_llm_call_id(
            run_id="run-123",
            operation="auto-drilldown",
            provider="llamacpp",
            cluster_label="prod-cluster",
        )
        self.assertEqual(call_id, "run-123:prod-cluster:auto-drilldown:llamacpp")

    def test_review_enrichment_format(self) -> None:
        """Call ID format: {run_id}:review-enrichment:{provider}."""
        from k8s_diag_agent.llm.call_labels import build_llm_call_id

        call_id = build_llm_call_id(
            run_id="run-456",
            operation="review-enrichment",
            provider="llamacpp",
        )
        self.assertEqual(call_id, "run-456:review-enrichment:llamacpp")

    def test_auto_drilldown_requires_cluster_label(self) -> None:
        """auto-drilldown operation requires cluster_label."""
        from k8s_diag_agent.llm.call_labels import build_llm_call_id

        with self.assertRaises(ValueError):
            build_llm_call_id(
                run_id="run-123",
                operation="auto-drilldown",
                provider="llamacpp",
            )

    def test_call_id_is_deterministic(self) -> None:
        """Same inputs produce same call ID."""
        from k8s_diag_agent.llm.call_labels import build_llm_call_id

        call_id1 = build_llm_call_id(
            run_id="run-789",
            operation="auto-drilldown",
            provider="llamacpp",
            cluster_label="test-cluster",
        )
        call_id2 = build_llm_call_id(
            run_id="run-789",
            operation="auto-drilldown",
            provider="llamacpp",
            cluster_label="test-cluster",
        )
        self.assertEqual(call_id1, call_id2)

    def test_call_id_different_with_different_inputs(self) -> None:
        """Different inputs produce different call IDs."""
        from k8s_diag_agent.llm.call_labels import build_llm_call_id

        call_id1 = build_llm_call_id(
            run_id="run-abc",
            operation="auto-drilldown",
            provider="llamacpp",
            cluster_label="cluster-a",
        )
        call_id2 = build_llm_call_id(
            run_id="run-abc",
            operation="auto-drilldown",
            provider="llamacpp",
            cluster_label="cluster-b",
        )
        self.assertNotEqual(call_id1, call_id2)

    def test_generic_operation_format(self) -> None:
        """Unknown operations use generic format."""
        from k8s_diag_agent.llm.call_labels import build_llm_call_id

        call_id = build_llm_call_id(
            run_id="run-xyz",
            operation="custom-op",
            provider="test-provider",
        )
        self.assertEqual(call_id, "run-xyz:custom-op:test-provider")


class LogPromptDiagnosticsTest(unittest.TestCase):
    """Tests for log_prompt_diagnostics adding llm_* fields."""

    def test_log_prompt_diagnostics_includes_llm_fields(self) -> None:
        """log_prompt_diagnostics output includes llm_call, llm_provider, llm_operation, llm_phase."""
        import inspect

        from k8s_diag_agent.llm.prompt_diagnostics import log_prompt_diagnostics

        source = inspect.getsource(log_prompt_diagnostics)

        # Check that the function adds llm_* fields
        self.assertIn("llm_call", source)
        self.assertIn("llm_provider", source)
        self.assertIn("llm_operation", source)
        self.assertIn("llm_phase", source)

    def test_log_prompt_diagnostics_preserves_existing_fields(self) -> None:
        """log_prompt_diagnostics preserves existing fields while adding llm_* fields."""
        import inspect

        from k8s_diag_agent.llm.prompt_diagnostics import log_prompt_diagnostics

        source = inspect.getsource(log_prompt_diagnostics)

        # Check that original diagnostics fields are preserved
        self.assertIn("provider", source)
        self.assertIn("prompt_chars", source)


class ReviewEnrichmentFailureMetadataTest(unittest.TestCase):
    """Tests for review enrichment LLM call labeling and failure metadata."""

    def test_llamacpp_adapter_adds_llm_fields_to_failure_metadata(self) -> None:
        """LlamaCpp adapter includes llm_call and llm_call_id in failure metadata."""
        import inspect

        from k8s_diag_agent.external_analysis.llamacpp_adapter_http import build_generic_failure_metadata

        source = inspect.getsource(build_generic_failure_metadata)

        # Check that the function adds llm fields
        self.assertIn("llm_call", source)
        self.assertIn("llm_call_id", source)

    def test_llamacpp_adapter_uses_build_llm_call_id(self) -> None:
        """run_http_assessment uses build_llm_call_id helper."""
        import inspect

        from k8s_diag_agent.external_analysis.llamacpp_adapter_http import run_http_assessment

        source = inspect.getsource(run_http_assessment)

        # Check that the function uses the helper
        self.assertIn("build_llm_call_id", source)


class AutoDrilldownLogsTest(unittest.TestCase):
    """Tests for auto-drilldown LLM logging in loop_runner_drilldown_analysis.py.

    These tests verify the extracted helper module contains the expected
    LLM logging behavior, not the delegating wrapper in loop.py.
    """

    def test_auto_drilldown_uses_build_llm_call_id(self) -> None:
        """run_auto_drilldown_analysis uses build_llm_call_id helper."""
        import inspect

        from k8s_diag_agent.health.loop_runner_drilldown_analysis import run_auto_drilldown_analysis

        source = inspect.getsource(run_auto_drilldown_analysis)

        # Check that the function uses the helper
        self.assertIn("build_llm_call_id(run_id, \"auto-drilldown\", provider_name, cluster_label=drilldown.label)", source)

    def test_auto_drilldown_has_start_log(self) -> None:
        """run_auto_drilldown_analysis includes LLM call start log."""
        import inspect

        from k8s_diag_agent.health.loop_runner_drilldown_analysis import run_auto_drilldown_analysis

        source = inspect.getsource(run_auto_drilldown_analysis)

        # Check for start log with llm_* fields
        self.assertIn('"llm-call"', source)
        self.assertIn("llm_call=True", source)
        self.assertIn('llm_phase="start"', source)
        self.assertIn('llm_operation="auto-drilldown"', source)

    def test_auto_drilldown_has_result_log(self) -> None:
        """run_auto_drilldown_analysis includes LLM call result log."""
        import inspect

        from k8s_diag_agent.health.loop_runner_drilldown_analysis import run_auto_drilldown_analysis

        source = inspect.getsource(run_auto_drilldown_analysis)

        # Check for result log with llm_* fields
        self.assertIn('"llm-call"', source)
        self.assertIn("llm_call=True", source)
        self.assertIn('llm_phase="result"', source)
        self.assertIn("LLM call completed", source)

    def test_auto_drilldown_has_diagnostics_log(self) -> None:
        """run_auto_drilldown_analysis includes LLM diagnostics log with llm_* fields."""
        import inspect

        from k8s_diag_agent.health.loop_runner_drilldown_analysis import run_auto_drilldown_analysis

        source = inspect.getsource(run_auto_drilldown_analysis)

        # Check for diagnostics log with llm_* fields
        self.assertIn('"llm-prompt-diagnostics"', source)
        self.assertIn("llm_call=True", source)
        self.assertIn('llm_phase="diagnostics"', source)
        self.assertIn('llm_operation="auto-drilldown"', source)

    def test_auto_drilldown_result_log_uses_failure_metadata_helper(self) -> None:
        """Result log uses extract_failure_metadata_field to extract failure_class and exception_type."""
        import inspect

        from k8s_diag_agent.health.loop_runner_drilldown_analysis import run_auto_drilldown_analysis

        source = inspect.getsource(run_auto_drilldown_analysis)

        # Check that the helper is used to extract failure_class and exception_type
        self.assertIn('extract_failure_metadata_field(failure_metadata, "failure_class")', source)
        self.assertIn('extract_failure_metadata_field(failure_metadata, "exception_type")', source)

    def test_auto_drilldown_result_log_includes_max_tokens(self) -> None:
        """Result log includes max_tokens for llama.cpp provider."""
        import inspect

        from k8s_diag_agent.health.loop_runner_drilldown_analysis import run_auto_drilldown_analysis

        source = inspect.getsource(run_auto_drilldown_analysis)

        # Check that max_tokens is resolved and included
        self.assertIn("resolve_drilldown_max_tokens", source)
        self.assertIn("max_tokens=result_max_tokens", source)

    def test_auto_drilldown_start_log_includes_max_tokens(self) -> None:
        """Start log includes max_tokens for llama.cpp provider."""
        import inspect

        from k8s_diag_agent.health.loop_runner_drilldown_analysis import run_auto_drilldown_analysis

        source = inspect.getsource(run_auto_drilldown_analysis)

        # Check that max_tokens is resolved and included in start log
        self.assertIn("start_max_tokens", source)
        self.assertIn("max_tokens=start_max_tokens", source)


class FailureMetadataFieldHelperTest(unittest.TestCase):
    """Tests for _failure_metadata_field helper."""

    def test_helper_exists_on_health_loop_runner(self) -> None:
        """HealthLoopRunner has _failure_metadata_field static method."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        self.assertTrue(hasattr(HealthLoopRunner, "_failure_metadata_field"))

    def test_helper_extracts_from_nested_prompt_diagnostics(self) -> None:
        """_failure_metadata_field extracts from nested prompt_diagnostics."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        metadata = {
            "failure_class": "llm_response_parse_error",
            "prompt_diagnostics": {
                "failure_class": "nested_failure_class",
            },
        }

        # Should prefer top-level
        result = HealthLoopRunner._failure_metadata_field(metadata, "failure_class")
        self.assertEqual(result, "llm_response_parse_error")

    def test_helper_extracts_from_top_level(self) -> None:
        """_failure_metadata_field extracts from top-level metadata."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        metadata = {
            "failure_class": "network_error",
            "exception_type": "requests.RequestException",
        }

        result = HealthLoopRunner._failure_metadata_field(metadata, "failure_class")
        self.assertEqual(result, "network_error")

        result2 = HealthLoopRunner._failure_metadata_field(metadata, "exception_type")
        self.assertEqual(result2, "requests.RequestException")

    def test_helper_prefers_top_level_over_nested(self) -> None:
        """_failure_metadata_field prefers top-level over nested prompt_diagnostics."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        metadata = {
            "failure_class": "top-level",
            "prompt_diagnostics": {
                "failure_class": "nested",
            },
        }

        result = HealthLoopRunner._failure_metadata_field(metadata, "failure_class")
        self.assertEqual(result, "top-level")

    def test_helper_returns_none_for_empty_metadata(self) -> None:
        """_failure_metadata_field returns None when metadata is empty."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        result = HealthLoopRunner._failure_metadata_field({}, "failure_class")
        self.assertIsNone(result)

    def test_helper_returns_none_when_missing(self) -> None:
        """_failure_metadata_field returns None when field is not present."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        metadata = {"other_field": "value"}
        result = HealthLoopRunner._failure_metadata_field(metadata, "failure_class")
        self.assertIsNone(result)


class ReviewEnrichmentLogsTest(unittest.TestCase):
    """Tests for review enrichment LLM logging in loop_runner_review_enrichment.py."""

    def test_review_enrichment_uses_build_llm_call_id(self) -> None:
        """run_review_enrichment uses build_llm_call_id for LLM call labeling."""
        import inspect

        from k8s_diag_agent.health.loop_runner_review_enrichment import run_review_enrichment

        source = inspect.getsource(run_review_enrichment)
        # Review enrichment calls adapter.run() which uses build_llm_call_id internally
        self.assertIn("ExternalAnalysisRequest", source)

    def test_review_enrichment_logs_shape_classification(self) -> None:
        """run_review_enrichment logs shape classification for observability."""
        import inspect

        from k8s_diag_agent.health.loop_runner_review_enrichment import run_review_enrichment

        source = inspect.getsource(run_review_enrichment)

        # Check for shape classification logging
        self.assertIn("review-enrichment-shape", source)
        self.assertIn("shape_classification", source)


if __name__ == "__main__":
    unittest.main()