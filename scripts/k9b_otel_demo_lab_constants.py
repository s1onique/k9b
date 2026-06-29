#!/usr/bin/env python3
"""Constants for the OpenTelemetry Demo Lab.

This module defines:
- Lab namespace
- Required deployments for OTel Demo
- Incident scenarios
- Failure class constants
- Provider smoke phase constants
"""

from __future__ import annotations

import os

# =============================================================================
# Lab configuration
# =============================================================================

# Lab namespace for OTel Demo
OTEL_DEMO_NAMESPACE = "otel-demo"

# Lab name for labeling
LAB_NAME = "k9b-otel-demo-incident"

# Helm release name for OTel Demo
OTEL_DEMO_RELEASE = "opentelemetry-demo"

# Helm chart repository configuration
# Split into repo name and chart reference for proper Helm CLI usage
OTEL_DEMO_HELM_REPO_NAME = "open-telemetry"
OTEL_DEMO_HELM_REPO_URL = "https://open-telemetry.github.io/opentelemetry-helm-charts"
OTEL_DEMO_CHART = "open-telemetry/opentelemetry-demo"

# Helm chart version
# Current upstream chart version is 0.40.9 (appVersion 2.2.0)
# See: https://github.com/open-telemetry/opentelemetry-helm-charts/blob/main/charts/opentelemetry-demo/Chart.yaml
OTEL_DEMO_CHART_VERSION = "0.40.9"

# Environment variable name for chart version override
CONFIGURED_OTEL_DEMO_CHART_VERSION_ENV = "K9B_OTEL_DEMO_CHART_VERSION"


def get_configured_otel_demo_chart_version() -> str:
    """Get the configured OTel Demo chart version.

    Supports runtime override via K9B_OTEL_DEMO_CHART_VERSION environment variable.
    Falls back to OTEL_DEMO_CHART_VERSION if not set.

    Note: The OTel Demo chart does NOT support in-place upgrades between versions.
    When changing chart versions on an existing deployment, the release must be
    deleted first (helm uninstall) before installing the new version.
    """
    return os.environ.get(CONFIGURED_OTEL_DEMO_CHART_VERSION_ENV, OTEL_DEMO_CHART_VERSION)


# Failure class for missing chart version (Phase 1, before provider smoke)
FAILURE_HELM_CHART_VERSION_NOT_FOUND = "helm_chart_version_not_found"

# k9b backend configuration (when k9b is deployed alongside OTel Demo)
# These are the single source of truth for k9b backend provider-smoke target
K9B_BACKEND_DEPLOYMENT = "k9b-backend"
K9B_BACKEND_CONTAINER = "backend"
K9B_BACKEND_PORT = 8080
K9B_NAMESPACE = "k9b"
K9B_BACKEND_SERVICE = "k9b-backend"  # Service name (may differ from deployment)


# =============================================================================
# Required deployments for OTel Demo baseline readiness
# =============================================================================

# Core services that must be ready for baseline
# These names match chart 0.40.9 deployment names (NOT the old *service naming)
# See: https://github.com/open-telemetry/opentelemetry-helm-charts/blob/main/charts/opentelemetry-demo/examples/default/rendered/component.yaml
REQUIRED_DEPLOYMENTS = [
    "frontend",
    "recommendation",  # chart 0.40.9 uses "recommendation" (not "recommendationservice")
    "product-catalog",  # chart 0.40.9 uses "product-catalog" (not "productcatalogservice")
    "cart",  # chart 0.40.9 uses "cart" (not "cartservice")
    "checkout",  # chart 0.40.9 uses "checkout" (not "checkoutservice")
    "payment",  # chart 0.40.9 uses "payment" (not "paymentservice")
    "shipping",  # chart 0.40.9 uses "shipping" (not "shippingservice")
    "currency",  # chart 0.40.9 uses "currency" (not "currencyservice")
    "email",  # chart 0.40.9 uses "email" (not "emailservice")
    "flagd",  # Feature flag service
]

# Optional deployments (may not exist in all configurations)
OPTIONAL_DEPLOYMENTS = [
    "loadgenerator",
    "grafana",
    "jaeger",
    "prometheus",
]


# =============================================================================
# Incident scenarios
# =============================================================================

class IncidentScenario:
    """Available incident scenarios for OTel Demo."""
    
    # Primary scenario: recommendation cache failure via feature flag
    RECOMMENDATION_CACHE_FAILURE = "recommendation-cache-failure"
    
    # Fallback scenario: direct pod stress
    RECOMMENDATION_POD_STRESS = "recommendation-pod-stress"


# =============================================================================
# Feature flag names (for recommendationServiceCacheFailure)
# =============================================================================

FEATURE_FLAG_CACHE_FAILURE = "recommendationServiceCacheFailure"


# =============================================================================
# Failure class constants
# =============================================================================

FAILURE_BASELINE_NOT_READY = "baseline_not_ready"
FAILURE_INJECTION_FAILED = "injection_failed"
FAILURE_INCIDENT_NOT_DETECTED = "incident_not_detected"
FAILURE_DIAGNOSIS_WRONG_COMPONENT = "diagnosis_wrong_component"
FAILURE_DIAGNOSIS_MISSING_FLAG_EVIDENCE = "diagnosis_missing_flag_evidence"
FAILURE_DIAGNOSIS_MISSING_RECOMMENDATIONSERVICE_EVIDENCE = "diagnosis_missing_recommendationservice_evidence"
FAILURE_DIAGNOSIS_GENERIC_POD_CRASH = "diagnosis_generic_pod_crash"
FAILURE_MUTATION_DETECTED = "mutation_detected"
FAILURE_REMEDIATION_ATTEMPTED = "remediation_attempted"

# Live mode failure classes
FAILURE_LIVE_TRAFFIC_NOT_ATTEMPTED = "live_traffic_not_attempted"
FAILURE_LIVE_TRAFFIC_FAILED = "live_traffic_failed"
FAILURE_LIVE_OBSERVATION_MISSING = "live_observation_missing"
FAILURE_LIVE_RECOMMENDATIONSERVICE_EVIDENCE_MISSING = "live_recommendationservice_evidence_missing"
FAILURE_LIVE_FEATURE_FLAG_NOT_ENABLED = "live_feature_flag_not_enabled"
FAILURE_LIVE_SYMPTOM_EVIDENCE_MISSING = "live_symptom_evidence_missing"
FAILURE_LIVE_TELEMETRY_UNAVAILABLE = "live_telemetry_unavailable"
FAILURE_LIVE_TELEMETRY_SIGNAL_MISSING = "live_telemetry_signal_missing"

# Provider smoke failure classes
FAILURE_BACKEND_HEALTH_FAILED = "backend_health_failed"
FAILURE_BACKEND_HEALTH_TIMEOUT = "backend_health_timeout"
FAILURE_SCHEDULER_HEALTH_FAILED = "scheduler_health_failed"
FAILURE_INCIDENT_DISCOVERY_FAILED = "incident_discovery_failed"
FAILURE_INCIDENT_DISCOVERY_TIMEOUT = "incident_discovery_timeout"
FAILURE_PROVIDER_SMOKE_HTTP_ERROR = "provider_smoke_http_error"
FAILURE_PROVIDER_SMOKE_NOT_CONFIGURED = "provider_smoke_not_configured"
FAILURE_PROVIDER_SMOKE_NOT_INVOKED = "provider_smoke_not_invoked"
FAILURE_PERSISTED_DIAGNOSIS_FAILED = "persisted_diagnosis_failed"
FAILURE_ARTIFACT_VERIFICATION_FAILED = "artifact_verification_failed"

# Connectivity failure classes (for cluster_api_timeout classification)
FAILURE_CLUSTER_API_TIMEOUT = "cluster_api_timeout"
FAILURE_KUBECONFIG_MISSING = "kubeconfig_missing"
FAILURE_KUBECONFIG_INVALID = "kubeconfig_invalid"
FAILURE_KUBECONFIG_DECODE_FAILED = "kubeconfig_decode_failed"
FAILURE_CLUSTER_AUTH_FAILED = "cluster_auth_failed"
FAILURE_API_DISCOVERY_FAILED = "api_discovery_failed"
FAILURE_NAMESPACE_RBAC_DENIED = "namespace_rbac_denied"
FAILURE_UNKNOWN_CLUSTER_CONNECTIVITY = "unknown_cluster_connectivity_failure"

# k9b backend prerequisite failure classes (Phase 0 / early detection)
# These indicate the k9b backend namespace/service/deployment is missing
# before any HTTP health check is attempted.
FAILURE_BACKEND_NAMESPACE_MISSING = "backend_namespace_missing"
FAILURE_BACKEND_SERVICE_MISSING = "backend_service_missing"
FAILURE_BACKEND_DEPLOYMENT_MISSING = "backend_deployment_missing"
FAILURE_BACKEND_ROLLOUT_NOT_READY = "backend_rollout_not_ready"

# Traffic target failure classes
FAILURE_TRAFFIC_TARGET_SERVICE_MISSING = "traffic_target_service_missing"

# =============================================================================
# K8s-native incident injection constants (P2b)
# =============================================================================

# Shipping deployment for unschedulable rollout
SHIPPING_DEPLOYMENT = "shipping"

# nodeSelector key for unschedulable incident
K8S_INJECTION_NODE_SELECTOR_KEY = "k9b.dev/otel-lab-node"
K8S_INJECTION_NODE_SELECTOR_VALUE = "missing"

# Failure class for K8s injection failure
FAILURE_K8S_INJECTION_FAILED = "k8s_injection_failed"
FAILURE_K8S_INJECTION_NO_SYMPTOM = "k8s_injection_no_symptom"


# =============================================================================
# Expected components for diagnosis oracle
# =============================================================================

# The incident fixture name for provider-smoke P2 (chart 0.40.9 uses "recommendation")
OTEL_INCIDENT_FIXTURE = "recommendation"

# Expected component in diagnosis oracle (chart 0.40.9 uses "recommendation")
EXPECTED_COMPONENT = OTEL_INCIDENT_FIXTURE
EXPECTED_NAMESPACE = "otel-demo"

# Keywords that indicate correct diagnosis
ACCEPTED_DIAGNOSIS_KEYWORDS = [
    "recommendationservice",
    "recommendation",
    "recommendationServiceCacheFailure",
    "feature_flag",
    "feature flag",
    "flagd",
    "cache",
    "cache failure",
    "memory leak",
]

# Keywords that indicate wrong diagnosis
REJECTED_DIAGNOSIS_PATTERNS = [
    "frontend only",
    "frontend-only",
    "only frontend",
    "generic pod crash",
    "random pod",
    "unrelated component",
]


# =============================================================================
# Artifact phase directories
# =============================================================================

PHASE_CLUSTER_BASELINE = "phase0-cluster"
PHASE_OTEL_BASELINE = "phase1-baseline"
PHASE_INJECTED = "phase2-injected"
PHASE_DISCOVERY = "phase3-discovery"
PHASE_DIAGNOSIS = "phase4-diagnosis"
PHASE_VERIFICATION = "phase5-verification"

# Provider smoke phase directories (under lab-artifacts/otel/provider-smoke/)
PHASE_BACKEND_HEALTH = "backend-health"
PHASE_SCHEDULER_HEALTH = "scheduler-health"
PHASE_INCIDENT_DISCOVERY = "incident-discovery"
PHASE_PROVIDER_SMOKE = "incident-provider"
PHASE_PERSISTED_DIAGNOSIS = "persisted-diagnosis"
PHASE_PROVIDER_PREFLIGHT = "provider-preflight"
