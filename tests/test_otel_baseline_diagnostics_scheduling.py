#!/usr/bin/env python3
"""Tests for scheduling constraint helpers.

These tests verify the scheduling constraint detection logic extracted from
k9b_otel_demo_lab_baseline_diagnostics.py.

Run with: python -m pytest tests/test_otel_baseline_diagnostics_scheduling.py -v
"""

from __future__ import annotations

import pytest

from scripts.k9b_otel_demo_lab_baseline_diagnostics_scheduling import (
    has_scheduling_constraints,
    is_scenario_specific_toleration,
)


class TestIsScenarioSpecificToleration:
    """Test toleration classification."""

    def test_default_kubernetes_not_ready_toleration(self) -> None:
        """Default Kubernetes toleration should not be scenario-specific."""
        toleration = {
            "key": "node.kubernetes.io/not-ready",
            "operator": "Exists",
            "effect": "NoExecute",
            "tolerationSeconds": 300,
        }
        assert not is_scenario_specific_toleration(toleration)

    def test_default_kubernetes_unreachable_toleration(self) -> None:
        """Default Kubernetes unreachable toleration should not be scenario-specific."""
        toleration = {"key": "node.kubernetes.io/unreachable"}
        assert not is_scenario_specific_toleration(toleration)

    def test_default_kubernetes_disk_pressure_toleration(self) -> None:
        """Default Kubernetes disk pressure toleration should not be scenario-specific."""
        toleration = {"key": "node.kubernetes.io/disk-pressure"}
        assert not is_scenario_specific_toleration(toleration)

    def test_default_kubernetes_memory_pressure_toleration(self) -> None:
        """Default Kubernetes memory pressure toleration should not be scenario-specific."""
        toleration = {"key": "node.kubernetes.io/memory-pressure"}
        assert not is_scenario_specific_toleration(toleration)

    def test_default_kubernetes_with_prefix_match(self) -> None:
        """Default Kubernetes tolerations with value prefixes should not be scenario-specific."""
        toleration = {"key": "node.kubernetes.io/not-ready:duration", "operator": "Exists"}
        assert not is_scenario_specific_toleration(toleration)

    def test_k9b_dev_scenario_toleration(self) -> None:
        """k9b.dev toleration should be flagged as scenario-specific."""
        toleration = {"key": "k9b.dev/otel-lab-node"}
        assert is_scenario_specific_toleration(toleration)

    def test_otel_lab_toleration(self) -> None:
        """otel-lab toleration should be flagged as scenario-specific."""
        toleration = {"key": "scenario.k9b/unschedulable"}
        assert is_scenario_specific_toleration(toleration)

    def test_special_node_toleration(self) -> None:
        """special-node toleration should be flagged as scenario-specific."""
        toleration = {"key": "special-node"}
        assert is_scenario_specific_toleration(toleration)

    def test_custom_toleration_is_scenario_specific(self) -> None:
        """Any custom toleration without known pattern should be flagged."""
        toleration = {"key": "my-custom-effect"}
        assert is_scenario_specific_toleration(toleration)

    def test_empty_key_not_scenario_specific(self) -> None:
        """Empty key should not be considered scenario-specific."""
        toleration = {"key": ""}
        assert not is_scenario_specific_toleration(toleration)

    def test_no_key_not_scenario_specific(self) -> None:
        """Missing key should not be considered scenario-specific."""
        toleration = {"operator": "Exists"}
        assert not is_scenario_specific_toleration(toleration)


class TestHasSchedulingConstraints:
    """Test scheduling constraint detection."""

    def test_empty_pod_has_no_constraints(self) -> None:
        """Empty spec should have no scheduling constraints."""
        pod = {"metadata": {"name": "test"}, "spec": {}}
        has_constraints, constraints = has_scheduling_constraints(pod, is_live_pod=True)
        assert not has_constraints
        assert constraints == {}

    def test_node_selector_is_constraint(self) -> None:
        """nodeSelector should be detected as scheduling constraint."""
        pod = {
            "metadata": {"name": "test"},
            "spec": {"nodeSelector": {"k9b.dev/otel-lab-node": "true"}},
        }
        has_constraints, constraints = has_scheduling_constraints(pod, is_live_pod=True)
        assert has_constraints
        assert "nodeSelector" in constraints

    def test_affinity_is_constraint(self) -> None:
        """Affinity should be detected as scheduling constraint."""
        pod = {
            "metadata": {"name": "test"},
            "spec": {
                "affinity": {
                    "nodeAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": []
                        }
                    }
                }
            },
        }
        has_constraints, constraints = has_scheduling_constraints(pod, is_live_pod=True)
        assert has_constraints
        assert "affinity" in constraints

    def test_live_pod_ignores_default_kubernetes_tolerations(self) -> None:
        """Live pods should ignore default Kubernetes tolerations."""
        pod = {
            "metadata": {"name": "shipping"},
            "spec": {
                "tolerations": [
                    {"key": "node.kubernetes.io/not-ready"},
                    {"key": "node.kubernetes.io/unreachable"},
                ]
            },
        }
        has_constraints, constraints = has_scheduling_constraints(pod, is_live_pod=True)
        assert not has_constraints
        assert constraints == {}

    def test_live_pod_flags_scenario_specific_tolerations(self) -> None:
        """Live pods should flag scenario-specific tolerations."""
        pod = {
            "metadata": {"name": "shipping"},
            "spec": {
                "tolerations": [
                    {"key": "k9b.dev/otel-lab-node"},
                ]
            },
        }
        has_constraints, constraints = has_scheduling_constraints(pod, is_live_pod=True)
        assert has_constraints
        assert "tolerations" in constraints

    def test_template_flags_any_toleration_as_constraint(self) -> None:
        """Deployment templates should flag any tolerations as suspicious."""
        template_spec = {
            "tolerations": [
                {"key": "node.kubernetes.io/not-ready"},
            ]
        }
        has_constraints, constraints = has_scheduling_constraints(
            template_spec, is_live_pod=False
        )
        assert has_constraints
        assert "tolerations" in constraints

    def test_multiple_constraints_detected(self) -> None:
        """Multiple constraint types should all be detected."""
        pod = {
            "metadata": {"name": "test"},
            "spec": {
                "nodeSelector": {"foo": "bar"},
                "affinity": {"nodeAffinity": {}},
            },
        }
        has_constraints, constraints = has_scheduling_constraints(pod, is_live_pod=True)
        assert has_constraints
        assert "nodeSelector" in constraints
        assert "affinity" in constraints

    def test_live_pod_with_mixed_tolerations(self) -> None:
        """Live pods should only flag scenario-specific tolerations when mixed with defaults."""
        pod = {
            "metadata": {"name": "shipping"},
            "spec": {
                "tolerations": [
                    {"key": "node.kubernetes.io/not-ready"},  # default, should be ignored
                    {"key": "k9b.dev/otel-lab-node"},  # scenario-specific, should be flagged
                ]
            },
        }
        has_constraints, constraints = has_scheduling_constraints(pod, is_live_pod=True)
        assert has_constraints
        # Should only include the scenario-specific toleration
        assert len(constraints["tolerations"]) == 1
        assert constraints["tolerations"][0]["key"] == "k9b.dev/otel-lab-node"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
