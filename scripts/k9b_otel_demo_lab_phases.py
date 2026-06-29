#!/usr/bin/env python3
"""Compatibility facade for the k9b OpenTelemetry demo lab phases.

This module re-exports phase functions from the implementation modules
for backward compatibility. New code should import directly from the
appropriate module:
- k9b_otel_demo_lab_deployment.py (phases 0, 1, 1b)
- k9b_otel_demo_lab_lifecycle.py (phases 2, 3, 4, 5)
- k9b_otel_demo_lab_provider_health.py (P0, P1, P1b)
- k9b_otel_demo_lab_provider_diagnosis.py (P2, P3, P4)
- k9b_otel_demo_lab_k8s_injection.py (P2b - K8s-native incident)
- k9b_otel_demo_lab_k8s_detection.py (P3c - K8s incident discovery)
- k9b_otel_demo_lab_types.py (types and constants)
"""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_deployment import (
    phase0_cluster_baseline,
    phase1_deploy_otel_demo,
    phase1b_baseline_readiness,
)
from scripts.k9b_otel_demo_lab_k8s_detection import (
    # K8s incident discovery verification (P3c)
    phase_p3c_verify_k8s_incident_discovery,
    verify_unschedulable_shipping_incident_discovered,
)
from scripts.k9b_otel_demo_lab_k8s_injection import (
    cleanup_unschedulable_shipping_rollout,
    # K8s-native incident injection (P2b)
    phase_p2b_inject_unschedulable_shipping_rollout,
)
from scripts.k9b_otel_demo_lab_lifecycle import (
    # Original OTel phases
    phase2_inject_incident,
    phase3_incident_discovery,
    phase4_diagnosis,
    phase5_verification,
)
from scripts.k9b_otel_demo_lab_provider_diagnosis import (
    # Provider smoke phases (P2, P3, P4)
    phase_p2_incident_discovery_provider,
    phase_p3_provider_smoke,
    phase_p4_persisted_diagnosis,
)
from scripts.k9b_otel_demo_lab_provider_health import (
    # Provider smoke phases (P0, P0b, P1, P1b)
    phase_p0_k9b_backend_prerequisite,
    phase_p0b_provider_preflight,
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
    # Provider smoke phases (P0 - k9b backend prerequisite check)
    "phase_p0_k9b_backend_prerequisite",
    # Provider smoke phases (P0b - provider preflight before OTel install)
    "phase_p0b_provider_preflight",
    # Provider smoke phases (P1, P1b - health gates)
    "phase_p1_backend_health_gate",
    "phase_p1b_scheduler_health_gate",
    # Provider smoke phases (P2, P3, P4 - diagnosis)
    "phase_p2_incident_discovery_provider",
    "phase_p3_provider_smoke",
    "phase_p4_persisted_diagnosis",
    # K8s-native incident injection (P2b)
    "phase_p2b_inject_unschedulable_shipping_rollout",
    "cleanup_unschedulable_shipping_rollout",
    # K8s incident discovery verification (P3c)
    "phase_p3c_verify_k8s_incident_discovery",
    "verify_unschedulable_shipping_incident_discovered",
]
