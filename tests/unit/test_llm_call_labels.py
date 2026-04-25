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
        from k8s_diag_agent.llm.prompt_diagnostics import PromptDiagnostics, log_prompt_diagnostics

        diagnostics = PromptDiagnostics(
            provider="llamacpp",
            operation="auto-drilldown",
            actual_prompt_chars=1000,
            actual_prompt_tokens_estimate=250,
            prompt_chars=900,
            prompt_tokens_estimate=225,
            prompt_section_count=5,
            prompt_sections=[],
            top_prompt_sections=[],
        )

        result = log_prompt_diagnostics(diagnostics)

        self.assertTrue(result.get("llm_call"))
        self.assertEqual(result.get("llm_provider"), "llamacpp")
        self.assertEqual(result.get("llm_operation"), "auto-drilldown")
        self.assertEqual(result.get("llm_phase"), "diagnostics")
        # Existing fields should remain
        self.assertEqual(result.get("operation"), "auto-drilldown")
        self.assertEqual(result.get("provider"), "llamacpp")

    def test_log_prompt_diagnostics_preserves_existing_fields(self) -> None:
        """Existing fields are still present in output."""
        from k8s_diag_agent.llm.prompt_diagnostics import PromptDiagnostics, log_prompt_diagnostics

        diagnostics = PromptDiagnostics(
            provider="llamacpp",
            operation="review-enrichment",
            actual_prompt_chars=2000,
            actual_prompt_tokens_estimate=500,
            prompt_chars=1900,
            prompt_tokens_estimate=475,
            prompt_section_count=8,
            prompt_sections=[],
            top_prompt_sections=[],
            elapsed_ms=1500,
            failure_class="llm_client_read_timeout",
        )

        result = log_prompt_diagnostics(diagnostics)

        self.assertEqual(result.get("elapsed_ms"), 1500)
        self.assertEqual(result.get("failure_class"), "llm_client_read_timeout")
        self.assertIn("actual_prompt_chars", result)


class ReviewEnrichmentFailureMetadataTest(unittest.TestCase):
    """Tests for review-enrichment failure metadata including llm_* fields."""

    def test_llamacpp_adapter_adds_llm_fields_to_failure_metadata(self) -> None:
        """LlamaCppAdapter._run_http adds llm_call, llm_call_id, llm_provider, llm_operation to failure_metadata."""
        import inspect
        from k8s_diag_agent.external_analysis.llamacpp_adapter import LlamaCppAdapter

        source = inspect.getsource(LlamaCppAdapter._run_http)

        # Check that the adapter includes llm_* fields in failure_metadata
        self.assertIn('failure_metadata["llm_call"] = True', source)
        self.assertIn('failure_metadata["llm_call_id"]', source)
        self.assertIn('failure_metadata["llm_provider"]', source)
        self.assertIn('failure_metadata["llm_operation"] = "review-enrichment"', source)

    def test_llamacpp_adapter_uses_build_llm_call_id(self) -> None:
        """LlamaCppAdapter uses build_llm_call_id helper."""
        import inspect
        from k8s_diag_agent.external_analysis.llamacpp_adapter import LlamaCppAdapter

        source = inspect.getsource(LlamaCppAdapter._run_http)

        # Check that the adapter uses the helper
        self.assertIn("build_llm_call_id(request.run_id, \"review-enrichment\", self.name)", source)


class AutoDrilldownLogsTest(unittest.TestCase):
    """Tests for auto-drilldown LLM logging in loop.py."""

    def test_auto_drilldown_uses_build_llm_call_id(self) -> None:
        """_run_auto_drilldown_analysis uses build_llm_call_id helper."""
        import inspect
        from k8s_diag_agent.health.loop import HealthLoopRunner

        source = inspect.getsource(HealthLoopRunner._run_auto_drilldown_analysis)

        # Check that the method uses the helper
        self.assertIn("build_llm_call_id(self.run_id, \"auto-drilldown\", provider_name, cluster_label=drilldown.label)", source)

    def test_auto_drilldown_has_start_log(self) -> None:
        """_run_auto_drilldown_analysis includes LLM call start log."""
        import inspect
        from k8s_diag_agent.health.loop import HealthLoopRunner

        source = inspect.getsource(HealthLoopRunner._run_auto_drilldown_analysis)

        # Check for start log with llm_* fields
        self.assertIn('"llm-call"', source)
        self.assertIn("llm_call=True", source)
        self.assertIn('llm_phase="start"', source)
        self.assertIn('llm_operation="auto-drilldown"', source)

    def test_auto_drilldown_has_result_log(self) -> None:
        """_run_auto_drilldown_analysis includes LLM call result log."""
        import inspect
        from k8s_diag_agent.health.loop import HealthLoopRunner

        source = inspect.getsource(HealthLoopRunner._run_auto_drilldown_analysis)

        # Check for result log with llm_* fields
        self.assertIn('"llm-call"', source)
        self.assertIn("llm_call=True", source)
        self.assertIn('llm_phase="result"', source)
        self.assertIn("LLM call completed", source)

    def test_auto_drilldown_has_diagnostics_log(self) -> None:
        """_run_auto_drilldown_analysis includes LLM diagnostics log with llm_* fields."""
        import inspect
        from k8s_diag_agent.health.loop import HealthLoopRunner

        source = inspect.getsource(HealthLoopRunner._run_auto_drilldown_analysis)

        # Check for diagnostics log with llm_* fields
        self.assertIn('"llm-prompt-diagnostics"', source)
        self.assertIn("llm_call=True", source)
        self.assertIn('llm_phase="diagnostics"', source)
        self.assertIn('llm_operation="auto-drilldown"', source)

    def test_auto_drilldown_result_log_uses_failure_metadata_helper(self) -> None:
        """Result log uses _failure_metadata_field helper to extract failure_class and exception_type."""
        import inspect
        from k8s_diag_agent.health.loop import HealthLoopRunner

        source = inspect.getsource(HealthLoopRunner._run_auto_drilldown_analysis)

        # Check that the helper is used to extract failure_class and exception_type
        self.assertIn("_failure_metadata_field(failure_metadata, \"failure_class\")", source)
        self.assertIn("_failure_metadata_field(failure_metadata, \"exception_type\")", source)

    def test_auto_drilldown_result_log_includes_max_tokens(self) -> None:
        """Result log includes max_tokens for llama.cpp provider."""
        import inspect
        from k8s_diag_agent.health.loop import HealthLoopRunner

        source = inspect.getsource(HealthLoopRunner._run_auto_drilldown_analysis)

        # Check that max_tokens is resolved and included
        self.assertIn("resolve_drilldown_max_tokens", source)
        self.assertIn("max_tokens=result_max_tokens", source)

    def test_auto_drilldown_start_log_includes_max_tokens(self) -> None:
        """Start log includes max_tokens for llama.cpp provider."""
        import inspect
        from k8s_diag_agent.health.loop import HealthLoopRunner

        source = inspect.getsource(HealthLoopRunner._run_auto_drilldown_analysis)

        # Check that max_tokens is resolved and included in start log
        self.assertIn("start_max_tokens", source)
        self.assertIn("max_tokens=start_max_tokens", source)


class FailureMetadataFieldHelperTest(unittest.TestCase):
    """Tests for _failure_metadata_field helper."""

    def test_helper_exists_on_health_loop_runner(self) -> None:
        """HealthLoopRunner has _failure_metadata_field static method."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        self.assertTrue(hasattr(HealthLoopRunner, "_failure_metadata_field"))

    def test_helper_extracts_from_top_level(self) -> None:
        """Helper extracts failure_class from top-level failure_metadata."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        metadata = {"failure_class": "llm_response_parse_error_length_capped", "exception_type": "LLMResponseParseError"}
        result = HealthLoopRunner._failure_metadata_field(metadata, "failure_class")
        self.assertEqual(result, "llm_response_parse_error_length_capped")

        result = HealthLoopRunner._failure_metadata_field(metadata, "exception_type")
        self.assertEqual(result, "LLMResponseParseError")

    def test_helper_extracts_from_nested_prompt_diagnostics(self) -> None:
        """Helper extracts failure_class from nested prompt_diagnostics."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        metadata = {
            "prompt_diagnostics": {
                "failure_class": "llm_client_read_timeout",
                "exception_type": "requests.Timeout",
            }
        }
        result = HealthLoopRunner._failure_metadata_field(metadata, "failure_class")
        self.assertEqual(result, "llm_client_read_timeout")

        result = HealthLoopRunner._failure_metadata_field(metadata, "exception_type")
        self.assertEqual(result, "requests.Timeout")

    def test_helper_prefers_top_level_over_nested(self) -> None:
        """Helper prefers top-level field over nested when both present."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        metadata = {
            "failure_class": "top_level_class",
            "prompt_diagnostics": {
                "failure_class": "nested_class",
            }
        }
        result = HealthLoopRunner._failure_metadata_field(metadata, "failure_class")
        self.assertEqual(result, "top_level_class")

    def test_helper_returns_none_when_missing(self) -> None:
        """Helper returns None when field not found anywhere."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        metadata = {"other_field": "value"}
        result = HealthLoopRunner._failure_metadata_field(metadata, "failure_class")
        self.assertIsNone(result)

    def test_helper_returns_none_for_empty_metadata(self) -> None:
        """Helper returns None for None or empty metadata."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        result = HealthLoopRunner._failure_metadata_field(None, "failure_class")
        self.assertIsNone(result)

        result = HealthLoopRunner._failure_metadata_field({}, "failure_class")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()