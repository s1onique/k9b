"""Compatibility tests for model_run_status imports via ui.model re-exports.

These tests verify that RunStatsView, PlannerAvailabilityView, _build_run_stats_view,
and _build_planner_availability_view can be imported from both the ui.model module
(for backward compatibility) and the ui.model_run_status module (the new canonical location).
"""

from __future__ import annotations

import unittest


class RunStatusImportCompatibilityTests(unittest.TestCase):
    """Verify run status views and builders are importable from ui.model."""

    def test_run_stats_view_importable_from_model(self) -> None:
        """RunStatsView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import RunStatsView  # noqa: F401

    def test_planner_availability_view_importable_from_model(self) -> None:
        """PlannerAvailabilityView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import PlannerAvailabilityView  # noqa: F401

    def test_build_run_stats_view_importable_from_model(self) -> None:
        """_build_run_stats_view should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_run_stats_view  # noqa: F401

    def test_build_planner_availability_view_importable_from_model(self) -> None:
        """_build_planner_availability_view should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_planner_availability_view  # noqa: F401

    def test_run_stats_view_importable_from_run_status_module(self) -> None:
        """RunStatsView should be importable from k8s_diag_agent.ui.model_run_status."""
        from k8s_diag_agent.ui.model_run_status import RunStatsView  # noqa: F401

    def test_planner_availability_view_importable_from_run_status_module(self) -> None:
        """PlannerAvailabilityView should be importable from k8s_diag_agent.ui.model_run_status."""
        from k8s_diag_agent.ui.model_run_status import PlannerAvailabilityView  # noqa: F401

    def test_build_run_stats_view_importable_from_run_status_module(self) -> None:
        """_build_run_stats_view should be importable from k8s_diag_agent.ui.model_run_status."""
        from k8s_diag_agent.ui.model_run_status import _build_run_stats_view  # noqa: F401

    def test_build_planner_availability_view_importable_from_run_status_module(self) -> None:
        """_build_planner_availability_view should be importable from k8s_diag_agent.ui.model_run_status."""
        from k8s_diag_agent.ui.model_run_status import _build_planner_availability_view  # noqa: F401


class RunStatusViewInstantiationTests(unittest.TestCase):
    """Tests for RunStatsView instantiation and behavior."""

    def test_run_stats_view_instantiation(self) -> None:
        """RunStatsView should be instantiable."""
        from k8s_diag_agent.ui.model import RunStatsView

        view = RunStatsView(
            last_run_duration_seconds=42,
            total_runs=10,
            p50_run_duration_seconds=30,
            p95_run_duration_seconds=40,
            p99_run_duration_seconds=50,
        )
        self.assertEqual(view.last_run_duration_seconds, 42)
        self.assertEqual(view.total_runs, 10)
        self.assertEqual(view.p50_run_duration_seconds, 30)

    def test_run_stats_view_defaults(self) -> None:
        """RunStatsView should have correct default values."""
        from k8s_diag_agent.ui.model import RunStatsView

        view = RunStatsView()
        self.assertIsNone(view.last_run_duration_seconds)
        self.assertEqual(view.total_runs, 0)
        self.assertIsNone(view.p50_run_duration_seconds)
        self.assertIsNone(view.p95_run_duration_seconds)
        self.assertIsNone(view.p99_run_duration_seconds)


class PlannerAvailabilityViewInstantiationTests(unittest.TestCase):
    """Tests for PlannerAvailabilityView instantiation and behavior."""

    def test_planner_availability_view_instantiation(self) -> None:
        """PlannerAvailabilityView should be instantiable."""
        from k8s_diag_agent.ui.model import PlannerAvailabilityView

        view = PlannerAvailabilityView(
            status="available",
            reason="Ready to process",
            hint="Check the queue for pending items",
            artifact_path="/path/to/planner/artifacts",
            next_action_hint="Run the next check",
        )
        self.assertEqual(view.status, "available")
        self.assertEqual(view.reason, "Ready to process")
        self.assertEqual(view.hint, "Check the queue for pending items")
        self.assertEqual(view.artifact_path, "/path/to/planner/artifacts")
        self.assertEqual(view.next_action_hint, "Run the next check")


class BuildRunStatsBuilderTests(unittest.TestCase):
    """Tests for _build_run_stats_view() builder function behavior."""

    def test_build_run_stats_view_null_input(self) -> None:
        """_build_run_stats_view should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_run_stats_view

        result = _build_run_stats_view(None)
        self.assertEqual(result.total_runs, 0)
        self.assertIsNone(result.last_run_duration_seconds)

    def test_build_run_stats_view_non_mapping_input(self) -> None:
        """_build_run_stats_view should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_run_stats_view

        result = _build_run_stats_view("not a mapping")
        self.assertEqual(result.total_runs, 0)
        self.assertIsNone(result.last_run_duration_seconds)

    def test_build_run_stats_view_empty_mapping(self) -> None:
        """_build_run_stats_view should return defaults for empty mapping."""
        from k8s_diag_agent.ui.model import _build_run_stats_view

        result = _build_run_stats_view({})
        self.assertEqual(result.total_runs, 0)
        self.assertIsNone(result.last_run_duration_seconds)

    def test_build_run_stats_view_full_data(self) -> None:
        """_build_run_stats_view should build with full data."""
        from k8s_diag_agent.ui.model import _build_run_stats_view

        raw = {
            "last_run_duration_seconds": 42,
            "total_runs": 10,
            "p50_run_duration_seconds": 30,
            "p95_run_duration_seconds": 40,
            "p99_run_duration_seconds": 50,
        }
        result = _build_run_stats_view(raw)
        self.assertEqual(result.last_run_duration_seconds, 42)
        self.assertEqual(result.total_runs, 10)
        self.assertEqual(result.p50_run_duration_seconds, 30)

    def test_build_run_stats_view_string_int_coerced(self) -> None:
        """_build_run_stats_view should coerce string integers."""
        from k8s_diag_agent.ui.model import _build_run_stats_view

        raw = {
            "last_run_duration_seconds": "42",
            "total_runs": "10",
        }
        result = _build_run_stats_view(raw)
        self.assertEqual(result.last_run_duration_seconds, 42)
        self.assertEqual(result.total_runs, 10)


class BuildPlannerAvailabilityBuilderTests(unittest.TestCase):
    """Tests for _build_planner_availability_view() builder function behavior."""

    def test_build_planner_availability_view_null_input(self) -> None:
        """_build_planner_availability_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_planner_availability_view

        result = _build_planner_availability_view(None)
        self.assertIsNone(result)

    def test_build_planner_availability_view_non_mapping_input(self) -> None:
        """_build_planner_availability_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_planner_availability_view

        result = _build_planner_availability_view("not a mapping")
        self.assertIsNone(result)

    def test_build_planner_availability_view_mapping_returns_view(self) -> None:
        """_build_planner_availability_view should return PlannerAvailabilityView for mapping."""
        from k8s_diag_agent.ui.model import PlannerAvailabilityView, _build_planner_availability_view

        raw = {
            "status": "available",
            "reason": "Ready to process",
        }
        result = _build_planner_availability_view(raw)
        self.assertIsInstance(result, PlannerAvailabilityView)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "available")
        self.assertEqual(result.reason, "Ready to process")

    def test_build_planner_availability_view_camel_case_keys(self) -> None:
        """_build_planner_availability_view should handle camelCase keys."""
        from k8s_diag_agent.ui.model import _build_planner_availability_view

        raw = {
            "status": "unavailable",
            "artifactPath": "/path/to/artifact",
            "nextActionHint": "Wait for next run",
        }
        result = _build_planner_availability_view(raw)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsNotNone(result.artifact_path)
        self.assertEqual(result.artifact_path, "/path/to/artifact")
        self.assertEqual(result.next_action_hint, "Wait for next run")

    def test_build_planner_availability_view_snake_case_keys(self) -> None:
        """_build_planner_availability_view should handle snake_case keys."""
        from k8s_diag_agent.ui.model import _build_planner_availability_view

        raw = {
            "status": "unavailable",
            "artifact_path": "/path/to/artifact",
            "next_action_hint": "Wait for next run",
        }
        result = _build_planner_availability_view(raw)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsNotNone(result.artifact_path)
        self.assertEqual(result.artifact_path, "/path/to/artifact")
        self.assertEqual(result.next_action_hint, "Wait for next run")


class RunStatusModuleDirectImportTests(unittest.TestCase):
    """Tests for direct imports from model_run_status module."""

    def test_build_run_stats_view_from_run_status_module(self) -> None:
        """_build_run_stats_view should work from model_run_status module."""
        from k8s_diag_agent.ui.model_run_status import _build_run_stats_view

        raw = {"total_runs": 50, "last_run_duration_seconds": 120}
        result = _build_run_stats_view(raw)
        self.assertEqual(result.total_runs, 50)
        self.assertEqual(result.last_run_duration_seconds, 120)

    def test_build_planner_availability_view_from_run_status_module(self) -> None:
        """_build_planner_availability_view should work from model_run_status module."""
        from k8s_diag_agent.ui.model_run_status import _build_planner_availability_view

        result = _build_planner_availability_view(None)
        self.assertIsNone(result)

        raw = {"status": "available", "reason": "Ready"}
        result = _build_planner_availability_view(raw)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsNotNone(result.status)
        self.assertEqual(result.status, "available")

    def test_run_stats_view_from_run_status_module(self) -> None:
        """RunStatsView should work from model_run_status module."""
        from k8s_diag_agent.ui.model_run_status import RunStatsView

        view = RunStatsView(total_runs=100, last_run_duration_seconds=60)
        self.assertEqual(view.total_runs, 100)
        self.assertEqual(view.last_run_duration_seconds, 60)

    def test_planner_availability_view_from_run_status_module(self) -> None:
        """PlannerAvailabilityView should work from model_run_status module."""
        from k8s_diag_agent.ui.model_run_status import PlannerAvailabilityView

        view = PlannerAvailabilityView(
            status="available",
            reason="Ready",
            hint=None,
            artifact_path=None,
            next_action_hint=None,
        )
        self.assertEqual(view.status, "available")


if __name__ == "__main__":
    unittest.main()
