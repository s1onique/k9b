"""Compatibility tests for model_llm_stats imports via ui.model re-exports.

These tests verify that LLMStatsView, ProviderBreakdownEntry, _build_llm_stats_view,
and _build_optional_llm_stats_view can be imported from both the ui.model module
(for backward compatibility) and the ui.model_llm_stats module (the new canonical location).
"""

from __future__ import annotations

import unittest


class LLMStatsImportCompatibilityTests(unittest.TestCase):
    """Verify LLM stats views and builders are importable from ui.model."""

    def test_llm_stats_view_importable_from_model(self) -> None:
        """LLMStatsView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import LLMStatsView  # noqa: F401

    def test_provider_breakdown_entry_importable_from_model(self) -> None:
        """ProviderBreakdownEntry should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import ProviderBreakdownEntry  # noqa: F401

    def test_build_llm_stats_view_importable_from_model(self) -> None:
        """_build_llm_stats_view should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_llm_stats_view  # noqa: F401

    def test_build_optional_llm_stats_view_importable_from_model(self) -> None:
        """_build_optional_llm_stats_view should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_optional_llm_stats_view  # noqa: F401

    def test_llm_stats_view_importable_from_llm_stats_module(self) -> None:
        """LLMStatsView should be importable from k8s_diag_agent.ui.model_llm_stats."""
        from k8s_diag_agent.ui.model_llm_stats import LLMStatsView  # noqa: F401

    def test_provider_breakdown_entry_importable_from_llm_stats_module(self) -> None:
        """ProviderBreakdownEntry should be importable from k8s_diag_agent.ui.model_llm_stats."""
        from k8s_diag_agent.ui.model_llm_stats import ProviderBreakdownEntry  # noqa: F401

    def test_build_llm_stats_view_importable_from_llm_stats_module(self) -> None:
        """_build_llm_stats_view should be importable from k8s_diag_agent.ui.model_llm_stats."""
        from k8s_diag_agent.ui.model_llm_stats import _build_llm_stats_view  # noqa: F401

    def test_build_optional_llm_stats_view_importable_from_llm_stats_module(self) -> None:
        """_build_optional_llm_stats_view should be importable from k8s_diag_agent.ui.model_llm_stats."""
        from k8s_diag_agent.ui.model_llm_stats import _build_optional_llm_stats_view  # noqa: F401


class LLMStatsViewInstantiationTests(unittest.TestCase):
    """Tests for LLMStatsView instantiation and behavior."""

    def test_provider_breakdown_entry_instantiation(self) -> None:
        """ProviderBreakdownEntry should be instantiable."""
        from k8s_diag_agent.ui.model import ProviderBreakdownEntry

        entry = ProviderBreakdownEntry(
            provider="openai",
            calls=100,
            failed_calls=5,
        )
        self.assertEqual(entry.provider, "openai")
        self.assertEqual(entry.calls, 100)
        self.assertEqual(entry.failed_calls, 5)

    def test_llm_stats_view_instantiation(self) -> None:
        """LLMStatsView should be instantiable."""
        from k8s_diag_agent.ui.model import LLMStatsView, ProviderBreakdownEntry

        entry = ProviderBreakdownEntry(provider="openai", calls=100, failed_calls=5)
        view = LLMStatsView(
            total_calls=100,
            successful_calls=95,
            failed_calls=5,
            last_call_timestamp="2026-01-01T00:00:00Z",
            p50_latency_ms=100,
            p95_latency_ms=200,
            p99_latency_ms=300,
            provider_breakdown=(entry,),
            scope="current_run",
        )
        self.assertEqual(view.total_calls, 100)
        self.assertEqual(view.successful_calls, 95)
        self.assertEqual(len(view.provider_breakdown), 1)

    def test_llm_stats_view_defaults(self) -> None:
        """LLMStatsView should have correct default values."""
        from k8s_diag_agent.ui.model import LLMStatsView

        view = LLMStatsView(
            total_calls=0,
            successful_calls=0,
            failed_calls=0,
            last_call_timestamp=None,
            p50_latency_ms=None,
            p95_latency_ms=None,
            p99_latency_ms=None,
            provider_breakdown=(),
        )
        self.assertEqual(view.scope, "current_run")
        self.assertEqual(view.provider_breakdown, ())


class BuildLLMStatsBuilderTests(unittest.TestCase):
    """Tests for _build_llm_stats_view() builder function behavior."""

    def test_build_llm_stats_view_null_input(self) -> None:
        """_build_llm_stats_view should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_llm_stats_view

        result = _build_llm_stats_view(None)
        self.assertEqual(result.total_calls, 0)
        self.assertEqual(result.provider_breakdown, ())

    def test_build_llm_stats_view_non_mapping_input(self) -> None:
        """_build_llm_stats_view should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_llm_stats_view

        result = _build_llm_stats_view("not a mapping")
        self.assertEqual(result.total_calls, 0)
        self.assertEqual(result.provider_breakdown, ())

    def test_build_llm_stats_view_empty_mapping(self) -> None:
        """_build_llm_stats_view should return defaults for empty mapping."""
        from k8s_diag_agent.ui.model import _build_llm_stats_view

        result = _build_llm_stats_view({})
        self.assertEqual(result.total_calls, 0)
        self.assertEqual(result.scope, "current_run")

    def test_build_llm_stats_view_full_data(self) -> None:
        """_build_llm_stats_view should build with full data."""
        from k8s_diag_agent.ui.model import _build_llm_stats_view

        raw = {
            "totalCalls": 100,
            "successfulCalls": 95,
            "failedCalls": 5,
            "lastCallTimestamp": "2026-01-01T00:00:00Z",
            "p50LatencyMs": 100,
            "p95LatencyMs": 200,
            "p99LatencyMs": 300,
            "providerBreakdown": [
                {"provider": "openai", "calls": 80, "failedCalls": 3},
            ],
            "scope": "current_run",
        }
        result = _build_llm_stats_view(raw)
        self.assertEqual(result.total_calls, 100)
        self.assertEqual(result.successful_calls, 95)
        self.assertEqual(result.failed_calls, 5)
        self.assertEqual(len(result.provider_breakdown), 1)
        self.assertEqual(result.provider_breakdown[0].provider, "openai")

    def test_build_llm_stats_view_missing_scope_defaults(self) -> None:
        """_build_llm_stats_view should default missing scope to 'current_run'."""
        from k8s_diag_agent.ui.model import _build_llm_stats_view

        raw = {"totalCalls": 10, "successfulCalls": 10, "failedCalls": 0}
        result = _build_llm_stats_view(raw)
        self.assertEqual(result.scope, "current_run")


class BuildOptionalLLMStatsBuilderTests(unittest.TestCase):
    """Tests for _build_optional_llm_stats_view() builder function behavior."""

    def test_build_optional_llm_stats_view_null_input(self) -> None:
        """_build_optional_llm_stats_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_optional_llm_stats_view

        result = _build_optional_llm_stats_view(None)
        self.assertIsNone(result)

    def test_build_optional_llm_stats_view_non_mapping_input(self) -> None:
        """_build_optional_llm_stats_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_optional_llm_stats_view

        result = _build_optional_llm_stats_view("not a mapping")
        self.assertIsNone(result)

    def test_build_optional_llm_stats_view_mapping_returns_view(self) -> None:
        """_build_optional_llm_stats_view should return LLMStatsView for mapping."""
        from k8s_diag_agent.ui.model import LLMStatsView, _build_optional_llm_stats_view

        raw = {"totalCalls": 10, "successfulCalls": 10, "failedCalls": 0}
        result = _build_optional_llm_stats_view(raw)
        self.assertIsInstance(result, LLMStatsView)
        assert result is not None
        self.assertEqual(result.total_calls, 10)


class LLMStatsModuleDirectImportTests(unittest.TestCase):
    """Tests for direct imports from model_llm_stats module."""

    def test_build_llm_stats_view_from_llm_stats_module(self) -> None:
        """_build_llm_stats_view should work from model_llm_stats module."""
        from k8s_diag_agent.ui.model_llm_stats import _build_llm_stats_view

        raw = {"totalCalls": 50, "successfulCalls": 48, "failedCalls": 2}
        result = _build_llm_stats_view(raw)
        self.assertEqual(result.total_calls, 50)
        self.assertEqual(result.successful_calls, 48)

    def test_build_optional_llm_stats_view_from_llm_stats_module(self) -> None:
        """_build_optional_llm_stats_view should work from model_llm_stats module."""
        from k8s_diag_agent.ui.model_llm_stats import _build_optional_llm_stats_view

        result = _build_optional_llm_stats_view(None)
        self.assertIsNone(result)

        raw = {"totalCalls": 20, "successfulCalls": 18, "failedCalls": 2}
        result = _build_optional_llm_stats_view(raw)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.total_calls, 20)

    def test_provider_breakdown_entry_from_llm_stats_module(self) -> None:
        """ProviderBreakdownEntry should work from model_llm_stats module."""
        from k8s_diag_agent.ui.model_llm_stats import ProviderBreakdownEntry

        entry = ProviderBreakdownEntry(provider="anthropic", calls=50, failed_calls=2)
        self.assertEqual(entry.provider, "anthropic")
        self.assertEqual(entry.calls, 50)
        self.assertEqual(entry.failed_calls, 2)


if __name__ == "__main__":
    unittest.main()
