#!/usr/bin/env python3
"""Compatibility facade for the k9b OpenTelemetry demo lab phases.

This module re-exports phase functions from the implementation modules
for backward compatibility. New code should import directly from the
appropriate module:
- k9b_otel_demo_lab_deployment.py (phases 0, 1, 1b)
- k9b_otel_demo_lab_lifecycle.py (phases 2, 3, 4, 5)
- k9b_otel_demo_lab_types.py (types and constants)
"""

from __future__ import annotations

from .k9b_otel_demo_lab_deployment import (
    phase0_cluster_baseline,
    phase1_deploy_otel_demo,
    phase1b_baseline_readiness,
)
from .k9b_otel_demo_lab_lifecycle import (
    phase2_inject_incident,
    phase3_incident_discovery,
    phase4_diagnosis,
    phase5_verification,
)

__all__ = [
    "phase0_cluster_baseline",
    "phase1_deploy_otel_demo",
    "phase1b_baseline_readiness",
    "phase2_inject_incident",
    "phase3_incident_discovery",
    "phase4_diagnosis",
    "phase5_verification",
]
