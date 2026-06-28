#!/usr/bin/env python3
"""Compatibility facade for the k9b OpenTelemetry demo lab phases.

This module re-exports phase functions from the implementation modules
for backward compatibility. New code should import directly from the
appropriate module:
- k9b_otel_demo_lab_deployment.py (phases 0, 1, 1b)
- k9b_otel_demo_lab_lifecycle.py (phases 2, 3, 4, 5)
- k9b_otel_demo_lab_provider_health.py (P1, P1b)
- k9b_otel_demo_lab_provider_diagnosis.py (P2, P3, P4)
- k9b_otel_demo_lab_types.py (types and constants)
"""

from __future__ import annotations

from .k9b_otel_demo_lab_deployment import (
    phase0_cluster_baseline,
    phase1_deploy_otel_demo,
    phase1b_baseline_readiness,
)
from .k9b_otel_demo_lab_lifecycle import (
    # Original OTel phases
    phase2_inject_incident,
    phase3_incident_discovery,
    phase4_diagnosis,
    phase5_verification,
)
from .k9b_otel_demo_lab_provider_diagnosis import (
    # Provider smoke phases (P2, P3, P4)
    phase_p2_incident_discovery_provider,
    phase_p3_provider_smoke,
    phase_p4_persisted_diagnosis,
)
from .k9b_otel_demo_lab_provider_health import (
    # Provider smoke phases (P1, P1b)
    phase_p1_backend_health_gate,
    phase_p1b_scheduler_health_gate,
)

__all__ = [
    # Original OTel phases
    "phase0_cluster_baseline",
    "phase1_deploy_otel_demo",
    "phase1b_baseline_readiness",
    "phase2_inject_incident",
    "phase3_incident_discovery",
    "phase4_diagnosis",
    "phase5_verification",
    # Provider smoke phases (parity with CNPG)
    "phase_p1_backend_health_gate",
    "phase_p1b_scheduler_health_gate",
    "phase_p2_incident_discovery_provider",
    "phase_p3_provider_smoke",
    "phase_p4_persisted_diagnosis",
]
