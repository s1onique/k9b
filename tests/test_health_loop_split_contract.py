"""Contract tests for health loop split into LLM-friendly modules.

These tests verify that the public API contract from k8s_diag_agent.health.loop
is preserved after splitting the implementation across multiple modules.

Tests are intentionally minimal and focused on import contracts only.
"""

from __future__ import annotations

import k8s_diag_agent.health.loop as loop_module


class TestHealthLoopPublicAPIImports:
    """Verify that key public API symbols can be imported from loop.py."""

    def test_health_loop_runner_imports(self) -> None:
        """HealthLoopRunner should be importable from loop.py."""
        from k8s_diag_agent.health.loop import HealthLoopRunner

        assert HealthLoopRunner is not None

    def test_health_run_config_imports(self) -> None:
        """HealthRunConfig should be importable from loop.py."""
        from k8s_diag_agent.health.loop import HealthRunConfig

        assert HealthRunConfig is not None

    def test_health_target_imports(self) -> None:
        """HealthTarget should be importable from loop.py."""
        from k8s_diag_agent.health.loop import HealthTarget

        assert HealthTarget is not None

    def test_health_snapshot_record_imports(self) -> None:
        """HealthSnapshotRecord should be importable from loop.py."""
        from k8s_diag_agent.health.loop import HealthSnapshotRecord

        assert HealthSnapshotRecord is not None

    def test_baseline_registry_imports(self) -> None:
        """BaselineRegistry should be importable from loop.py."""
        from k8s_diag_agent.health.loop import BaselineRegistry

        assert BaselineRegistry is not None

    def test_trigger_policy_imports(self) -> None:
        """TriggerPolicy should be importable from loop.py."""
        from k8s_diag_agent.health.loop import TriggerPolicy

        assert TriggerPolicy is not None

    def test_comparison_peer_imports(self) -> None:
        """ComparisonPeer should be importable from loop.py."""
        from k8s_diag_agent.health.loop import ComparisonPeer

        assert ComparisonPeer is not None

    def test_health_loop_scheduler_imports(self) -> None:
        """HealthLoopScheduler should be importable from loop.py."""
        from k8s_diag_agent.health.loop import HealthLoopScheduler

        assert HealthLoopScheduler is not None


class TestHealthLoopFacadeExports:
    """Verify that loop.py __all__ contains expected public symbols."""

    def test_loop_all_contains_expected_symbols(self) -> None:
        """The __all__ list should contain all key public symbols."""
        expected = {
            "HealthLoopRunner",
            "HealthRunConfig",
            "HealthTarget",
            "HealthSnapshotRecord",
            "BaselineRegistry",
            "TriggerPolicy",
            "ComparisonPeer",
            "HealthLoopScheduler",
            "HealthAssessmentArtifact",
            "HealthHistoryEntry",
            "HealthRating",
            "run_health_loop",
        }

        assert hasattr(loop_module, "__all__")
        actual = set(loop_module.__all__)
        missing = expected - actual
        assert not missing, f"Missing from __all__: {missing}"

    def test_loop_all_is_subset_of_module_dict(self) -> None:
        """All symbols in __all__ should exist in the module."""
        assert hasattr(loop_module, "__all__")
        for name in loop_module.__all__:
            assert hasattr(loop_module, name), f"__all__ contains '{name}' but module lacks it"


class TestHealthLoopModuleStructure:
    """Verify the split module structure is correct."""

    def test_loop_runner_module_exists(self) -> None:
        """loop_runner module should exist and contain HealthLoopRunner."""
        from k8s_diag_agent.health import loop_runner

        assert hasattr(loop_runner, "HealthLoopRunner")
        assert hasattr(loop_runner, "HealthRunConfig")

    def test_loop_models_module_exists(self) -> None:
        """loop_models module should exist and contain model classes."""
        from k8s_diag_agent.health import loop_models

        assert hasattr(loop_models, "ManualComparison")
        assert hasattr(loop_models, "HealthLoopStatus")
        assert hasattr(loop_models, "HealthLoopResult")

    def test_facade_class_is_same_as_runner_class(self) -> None:
        """The facade should expose the same class as loop_runner."""
        from k8s_diag_agent.health.loop import HealthLoopRunner
        from k8s_diag_agent.health.loop_runner import HealthLoopRunner as RunnerClass

        assert HealthLoopRunner is RunnerClass

    def test_facade_config_is_same_as_runner_config(self) -> None:
        """The facade should expose the same HealthRunConfig as loop_runner."""
        from k8s_diag_agent.health.loop import HealthRunConfig
        from k8s_diag_agent.health.loop_runner import HealthRunConfig as ConfigClass

        assert HealthRunConfig is ConfigClass

    def test_facade_config_is_same_as_run_config_owner(self) -> None:
        """The facade should expose the same HealthRunConfig as loop_run_config."""
        from k8s_diag_agent.health.loop import HealthRunConfig
        from k8s_diag_agent.health.loop_run_config import HealthRunConfig as OwnerConfig

        assert HealthRunConfig is OwnerConfig
        assert HealthRunConfig.__module__ == "k8s_diag_agent.health.loop_run_config"


class TestRunnerExecutionModules:
    """Verify that extracted execution modules can be imported."""

    def test_runner_execution_modules_import(self) -> None:
        """Verify execution modules can be imported cleanly."""
        from k8s_diag_agent.health.loop_runner_execute import execute_health_loop_run
        from k8s_diag_agent.health.loop_runner_monitoring import run_alertmanager_discovery

        assert execute_health_loop_run is not None
        assert run_alertmanager_discovery is not None
