"""Compatibility tests for model_llm_activity imports via ui.model re-exports.

These tests verify that LLMActivityView, LLMActivityEntryView, LLMActivitySummaryView,
and their builder functions can be imported from both the ui.model module (for backward
compatibility) and the ui.model_llm_activity module (the new canonical location).
"""

import unittest


class LLMActivityImportCompatibilityTests(unittest.TestCase):
    """Verify LLM activity views and builders are importable from ui.model."""

    def test_llm_activity_view_importable_from_model(self) -> None:
        """LLMActivityView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import LLMActivityView  # noqa: F401

    def test_llm_activity_entry_view_importable_from_model(self) -> None:
        """LLMActivityEntryView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import LLMActivityEntryView  # noqa: F401

    def test_llm_activity_summary_view_importable_from_model(self) -> None:
        """LLMActivitySummaryView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import LLMActivitySummaryView  # noqa: F401

    def test_build_llm_activity_importable_from_model(self) -> None:
        """_build_llm_activity should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_llm_activity  # noqa: F401

    def test_build_llm_activity_entry_importable_from_model(self) -> None:
        """_build_llm_activity_entry should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_llm_activity_entry  # noqa: F401

    def test_build_llm_activity_summary_importable_from_model(self) -> None:
        """_build_llm_activity_summary should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_llm_activity_summary  # noqa: F401

    def test_llm_activity_view_importable_from_llm_activity_module(self) -> None:
        """LLMActivityView should be importable from k8s_diag_agent.ui.model_llm_activity."""
        from k8s_diag_agent.ui.model_llm_activity import LLMActivityView  # noqa: F401

    def test_llm_activity_entry_view_importable_from_llm_activity_module(self) -> None:
        """LLMActivityEntryView should be importable from k8s_diag_agent.ui.model_llm_activity."""
        from k8s_diag_agent.ui.model_llm_activity import LLMActivityEntryView  # noqa: F401

    def test_llm_activity_summary_view_importable_from_llm_activity_module(self) -> None:
        """LLMActivitySummaryView should be importable from k8s_diag_agent.ui.model_llm_activity."""
        from k8s_diag_agent.ui.model_llm_activity import LLMActivitySummaryView  # noqa: F401

    def test_build_llm_activity_importable_from_llm_activity_module(self) -> None:
        """_build_llm_activity should be importable from k8s_diag_agent.ui.model_llm_activity."""
        from k8s_diag_agent.ui.model_llm_activity import _build_llm_activity  # noqa: F401

    def test_build_llm_activity_entry_importable_from_llm_activity_module(self) -> None:
        """_build_llm_activity_entry should be importable from k8s_diag_agent.ui.model_llm_activity."""
        from k8s_diag_agent.ui.model_llm_activity import _build_llm_activity_entry  # noqa: F401

    def test_build_llm_activity_summary_importable_from_llm_activity_module(self) -> None:
        """_build_llm_activity_summary should be importable from k8s_diag_agent.ui.model_llm_activity."""
        from k8s_diag_agent.ui.model_llm_activity import _build_llm_activity_summary  # noqa: F401


class LLMActivityViewInstantiationTests(unittest.TestCase):
    """Tests for LLM activity view instantiation and behavior."""

    def test_llm_activity_entry_view_instantiation(self) -> None:
        """LLMActivityEntryView should be instantiable."""
        from k8s_diag_agent.ui.model import LLMActivityEntryView

        entry = LLMActivityEntryView(
            timestamp="2026-01-01T00:00:00Z",
            run_id="run-1",
            run_label="test run",
            cluster_label="cluster-a",
            tool_name="k8sgpt",
            provider="openai",
            purpose="analysis",
            status="success",
            latency_ms=100,
            artifact_path="artifacts/run-1-llm.json",
            summary="Analysis complete",
            error_summary=None,
            skip_reason=None,
        )
        self.assertEqual(entry.timestamp, "2026-01-01T00:00:00Z")
        self.assertEqual(entry.run_id, "run-1")
        self.assertEqual(entry.status, "success")
        self.assertEqual(entry.latency_ms, 100)

    def test_llm_activity_entry_view_default_values(self) -> None:
        """LLMActivityEntryView should have correct defaults."""
        from k8s_diag_agent.ui.model import LLMActivityEntryView

        entry = LLMActivityEntryView(
            timestamp=None,
            run_id=None,
            run_label=None,
            cluster_label=None,
            tool_name=None,
            provider=None,
            purpose=None,
            status=None,
            latency_ms=None,
            artifact_path=None,
            summary=None,
            error_summary=None,
            skip_reason=None,
        )
        self.assertIsNone(entry.timestamp)
        self.assertIsNone(entry.run_id)
        self.assertIsNone(entry.status)
        self.assertIsNone(entry.latency_ms)

    def test_llm_activity_summary_view_instantiation(self) -> None:
        """LLMActivitySummaryView should be instantiable."""
        from k8s_diag_agent.ui.model import LLMActivitySummaryView

        summary = LLMActivitySummaryView(retained_entries=10)
        self.assertEqual(summary.retained_entries, 10)

    def test_llm_activity_summary_view_default_values(self) -> None:
        """LLMActivitySummaryView should have correct defaults."""
        from k8s_diag_agent.ui.model import LLMActivitySummaryView

        summary = LLMActivitySummaryView(retained_entries=0)
        self.assertEqual(summary.retained_entries, 0)

    def test_llm_activity_view_instantiation(self) -> None:
        """LLMActivityView should be instantiable."""
        from k8s_diag_agent.ui.model import LLMActivityEntryView, LLMActivitySummaryView, LLMActivityView

        entry = LLMActivityEntryView(
            timestamp="2026-01-01T00:00:00Z",
            run_id="run-1",
            run_label=None,
            cluster_label=None,
            tool_name=None,
            provider=None,
            purpose=None,
            status="success",
            latency_ms=None,
            artifact_path=None,
            summary=None,
            error_summary=None,
            skip_reason=None,
        )
        summary = LLMActivitySummaryView(retained_entries=1)
        view = LLMActivityView(entries=(entry,), summary=summary)
        self.assertEqual(len(view.entries), 1)
        self.assertEqual(view.summary.retained_entries, 1)


class BuildLLMActivityBuilderTests(unittest.TestCase):
    """Tests for _build_llm_activity() builder function behavior."""

    def test_build_llm_activity_null_input(self) -> None:
        """_build_llm_activity should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model import LLMActivityView, _build_llm_activity

        result = _build_llm_activity(None)
        self.assertIsInstance(result, LLMActivityView)
        self.assertEqual(result.entries, ())
        self.assertEqual(result.summary.retained_entries, 0)

    def test_build_llm_activity_non_mapping_input(self) -> None:
        """_build_llm_activity should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model import LLMActivityView, _build_llm_activity

        result = _build_llm_activity("not a mapping")
        self.assertIsInstance(result, LLMActivityView)
        self.assertEqual(result.entries, ())
        self.assertEqual(result.summary.retained_entries, 0)

    def test_build_llm_activity_empty_mapping(self) -> None:
        """_build_llm_activity should handle empty mapping."""
        from k8s_diag_agent.ui.model import LLMActivityView, _build_llm_activity

        result = _build_llm_activity({})
        self.assertIsInstance(result, LLMActivityView)
        self.assertEqual(result.entries, ())
        self.assertEqual(result.summary.retained_entries, 0)

    def test_build_llm_activity_with_entries(self) -> None:
        """_build_llm_activity should build LLMActivityView with entries."""
        from k8s_diag_agent.ui.model import LLMActivityView, _build_llm_activity

        raw = {
            "entries": [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "run_id": "run-1",
                    "run_label": "test",
                    "cluster_label": "cluster-a",
                    "tool_name": "k8sgpt",
                    "provider": "openai",
                    "purpose": "analysis",
                    "status": "success",
                    "latency_ms": 100,
                    "artifact_path": "artifacts/run-1-llm.json",
                    "summary": "Analysis complete",
                    "error_summary": None,
                    "skip_reason": None,
                },
            ],
            "summary": {
                "retained_entries": 1,
            },
        }
        result = _build_llm_activity(raw)
        self.assertIsInstance(result, LLMActivityView)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].run_id, "run-1")
        self.assertEqual(result.entries[0].status, "success")
        self.assertEqual(result.summary.retained_entries, 1)

    def test_build_llm_activity_filters_invalid_entries(self) -> None:
        """_build_llm_activity should filter out non-Mapping entries."""
        from k8s_diag_agent.ui.model import _build_llm_activity

        raw = {
            "entries": [
                {"run_id": "valid-entry", "status": "success"},
                "not a mapping",
                42,
                None,
                {"run_id": "another-valid", "status": "failed"},
            ],
        }
        result = _build_llm_activity(raw)
        self.assertEqual(len(result.entries), 2)
        self.assertEqual(result.entries[0].run_id, "valid-entry")
        self.assertEqual(result.entries[1].run_id, "another-valid")

    def test_build_llm_activity_null_entries(self) -> None:
        """_build_llm_activity should handle null entries."""
        from k8s_diag_agent.ui.model import LLMActivityView, _build_llm_activity

        raw = {"entries": None, "summary": {"retained_entries": 0}}
        result = _build_llm_activity(raw)
        self.assertIsInstance(result, LLMActivityView)
        self.assertEqual(result.entries, ())


class BuildLLMActivityEntryBuilderTests(unittest.TestCase):
    """Tests for _build_llm_activity_entry() builder function behavior."""

    def test_build_llm_activity_entry_full_data(self) -> None:
        """_build_llm_activity_entry should build entry with all fields."""
        from k8s_diag_agent.ui.model import LLMActivityEntryView, _build_llm_activity_entry

        raw = {
            "timestamp": "2026-01-01T00:00:00Z",
            "run_id": "run-1",
            "run_label": "test run",
            "cluster_label": "cluster-a",
            "tool_name": "k8sgpt",
            "provider": "openai",
            "purpose": "analysis",
            "status": "success",
            "latency_ms": 100,
            "artifact_path": "artifacts/run-1-llm.json",
            "summary": "Analysis complete",
            "error_summary": "some error",
            "skip_reason": "skipped for testing",
        }
        result = _build_llm_activity_entry(raw)
        self.assertIsInstance(result, LLMActivityEntryView)
        self.assertEqual(result.timestamp, "2026-01-01T00:00:00Z")
        self.assertEqual(result.run_id, "run-1")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.latency_ms, 100)
        self.assertEqual(result.error_summary, "some error")
        self.assertEqual(result.skip_reason, "skipped for testing")

    def test_build_llm_activity_entry_all_none(self) -> None:
        """_build_llm_activity_entry should handle all None/missing fields."""
        from k8s_diag_agent.ui.model import LLMActivityEntryView, _build_llm_activity_entry

        raw: dict[str, None] = {
            "timestamp": None,
            "run_id": None,
            "run_label": None,
            "cluster_label": None,
            "tool_name": None,
            "provider": None,
            "purpose": None,
            "status": None,
            "latency_ms": None,
            "artifact_path": None,
            "summary": None,
            "error_summary": None,
            "skip_reason": None,
        }
        result = _build_llm_activity_entry(raw)
        self.assertIsInstance(result, LLMActivityEntryView)
        for field in result.__dataclass_fields__.values():
            self.assertIsNone(getattr(result, field.name))

    def test_build_llm_activity_entry_missing_keys(self) -> None:
        """_build_llm_activity_entry should treat missing keys as None."""
        from k8s_diag_agent.ui.model import LLMActivityEntryView, _build_llm_activity_entry

        raw = {}
        result = _build_llm_activity_entry(raw)
        self.assertIsInstance(result, LLMActivityEntryView)
        self.assertIsNone(result.timestamp)
        self.assertIsNone(result.run_id)
        self.assertIsNone(result.status)

    def test_build_llm_activity_entry_int_coercion(self) -> None:
        """_build_llm_activity_entry should coerce latency_ms from string."""
        from k8s_diag_agent.ui.model import _build_llm_activity_entry

        raw = {"latency_ms": "150"}
        result = _build_llm_activity_entry(raw)
        self.assertEqual(result.latency_ms, 150)


class BuildLLMActivitySummaryBuilderTests(unittest.TestCase):
    """Tests for _build_llm_activity_summary() builder function behavior."""

    def test_build_llm_activity_summary_null_input(self) -> None:
        """_build_llm_activity_summary should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model import LLMActivitySummaryView, _build_llm_activity_summary

        result = _build_llm_activity_summary(None)
        self.assertIsInstance(result, LLMActivitySummaryView)
        self.assertEqual(result.retained_entries, 0)

    def test_build_llm_activity_summary_non_mapping_input(self) -> None:
        """_build_llm_activity_summary should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model import LLMActivitySummaryView, _build_llm_activity_summary

        result = _build_llm_activity_summary("not a mapping")
        self.assertIsInstance(result, LLMActivitySummaryView)
        self.assertEqual(result.retained_entries, 0)

    def test_build_llm_activity_summary_full_data(self) -> None:
        """_build_llm_activity_summary should build with data."""
        from k8s_diag_agent.ui.model import LLMActivitySummaryView, _build_llm_activity_summary

        raw = {"retained_entries": 25}
        result = _build_llm_activity_summary(raw)
        self.assertIsInstance(result, LLMActivitySummaryView)
        self.assertEqual(result.retained_entries, 25)

    def test_build_llm_activity_summary_missing_key(self) -> None:
        """_build_llm_activity_summary should default retained_entries to 0 for missing key."""
        from k8s_diag_agent.ui.model import LLMActivitySummaryView, _build_llm_activity_summary

        raw: dict[str, object] = {}
        result = _build_llm_activity_summary(raw)
        self.assertIsInstance(result, LLMActivitySummaryView)
        self.assertEqual(result.retained_entries, 0)

    def test_build_llm_activity_summary_int_coercion(self) -> None:
        """_build_llm_activity_summary should coerce retained_entries from string."""
        from k8s_diag_agent.ui.model import LLMActivitySummaryView, _build_llm_activity_summary

        raw = {"retained_entries": "42"}
        result = _build_llm_activity_summary(raw)
        self.assertIsInstance(result, LLMActivitySummaryView)
        self.assertEqual(result.retained_entries, 42)


if __name__ == "__main__":
    unittest.main()
