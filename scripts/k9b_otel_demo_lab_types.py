#!/usr/bin/env python3
"""OTel Demo Lab types - re-exports from contract module.

This module exists for backward compatibility. New code should import from
k9b_otel_demo_lab_contract instead.
"""

from __future__ import annotations

# Re-export all definitions from contract module for backward compatibility
from .k9b_otel_demo_lab_contract import (
    INCIDENT_SCENARIOS,
    LAB_MODE_LIVE,
    LAB_MODE_SCAFFOLD,
    LAB_MODES,
    SCENARIO_K8S_NATIVE_UNSCHEDULABLE,
    SCENARIO_PROVIDER_SMOKE,
    SCENARIO_RECOMMENDATION_CACHE_FAILURE,
    SCENARIO_RECOMMENDATION_POD_STRESS,
    LabConfig,
    LabPhaseResult,
    LabResult,
)

__all__ = [
    "LabConfig",
    "LabPhaseResult",
    "LabResult",
    "LAB_MODE_SCAFFOLD",
    "LAB_MODE_LIVE",
    "LAB_MODES",
    "SCENARIO_RECOMMENDATION_CACHE_FAILURE",
    "SCENARIO_RECOMMENDATION_POD_STRESS",
    "SCENARIO_K8S_NATIVE_UNSCHEDULABLE",
    "SCENARIO_PROVIDER_SMOKE",
    "INCIDENT_SCENARIOS",
]
