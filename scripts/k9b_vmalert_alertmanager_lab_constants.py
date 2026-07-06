#!/usr/bin/env python3
"""Constants for the vmalert→Alertmanager→K9B incident lab.

This module defines:
- Lab namespace
- vmalert rule configuration
- Alertmanager receiver configuration
- Artifact directory structure
- Failure class constants
"""

from __future__ import annotations

# =============================================================================
# Lab configuration
# =============================================================================

# Lab namespace
LAB_NAMESPACE = "k9b-alertmanager-lab"

# Lab name for labeling
LAB_NAME = "k9b-vmalert-alertmanager-incident"

# Helm release name for k9b
K9B_RELEASE = "k9b"

# Lab namespace for Alertmanager/vmalert stack
MONITORING_NAMESPACE = "monitoring"

# =============================================================================
# Phase names (must match artifact directory names)
# =============================================================================

PHASE_PREFILIGHT = "phase0-preflight"
PHASE_DEPLOY = "phase1-deploy"
PHASE_INJECT = "phase2-inject"
PHASE_VERIFY = "phase3-verify"
PHASE_RECOVERY = "phase4-recovery"

# =============================================================================
# vmalert configuration
# =============================================================================

# vmalert alert rule (deterministic, always-firing)
VMALERT_RULE_NAME = "k9b-alert-promotion-lab"
VMALERT_ALERT_NAME = "K9BAlertPromotionLabAlwaysFiring"

# The incident key used for deduplication
LAB_INCIDENT_KEY = "k9b-lab/service/openwebui/alert-promotion"

# =============================================================================
# Alertmanager configuration
# =============================================================================

# Alertmanager release name
ALERTMANAGER_RELEASE = "alertmanager"

# Alertmanager service name in monitoring namespace
ALERTMANAGER_SERVICE = "alertmanager.monitoring.svc.cluster.local"
ALERTMANAGER_PORT = 9093

# Alertmanager webhook receiver endpoint
ALERTMANAGER_WEBHOOK_PATH = "/api/integrations/alertmanager/webhook"

# =============================================================================
# k9b backend configuration
# =============================================================================

K9B_BACKEND_DEPLOYMENT = "k9b-backend"
K9B_BACKEND_CONTAINER = "backend"
K9B_BACKEND_PORT = 8080
K9B_NAMESPACE = "k9b"
K9B_BACKEND_SERVICE = "k9b-backend"  # Service name (may differ from deployment)

# Artifact subdirectories
ARTIFACT_SUBDIR = "external-analysis/alertmanager-lab"

# =============================================================================
# vmalert rule YAML
# =============================================================================

VMALERT_RULE_YAML = """groups:
  - name: k9b-alert-promotion-lab
    rules:
      - alert: K9BAlertPromotionLabAlwaysFiring
        expr: vector(1)
        for: 0s
        labels:
          severity: critical
          namespace: k9b-lab
          service: openwebui
          k9b.dev/class: target_unreachable
          k9b.dev/entity.kind: service
          k9b.dev/entity.namespace: k9b-lab
          k9b.dev/entity.name: openwebui
          k9b.dev/incident.key: k9b-lab/service/openwebui/alert-promotion
        annotations:
          summary: K9B alert promotion lab synthetic alert
          description: Synthetic alert used to prove vmalert to Alertmanager to K9B incident opening.
"""

# =============================================================================
# Alertmanager config (webhook receiver)
# =============================================================================

ALERTMANAGER_CONFIG_TEMPLATE = """global:
  resolve_timeout: 1m

route:
  receiver: k9b-webhook
  group_by: ['alertname', 'namespace', 'service']
  group_wait: 1s
  group_interval: 1s
  repeat_interval: 1m
  matchers:
    - namespace="k9b-lab"

receivers:
  - name: k9b-webhook
    webhook_configs:
      - url: 'http://k9b-backend.{k9b_namespace}:8080/api/integrations/alertmanager/webhook'
        send_resolved: true
        http_config:
          tls_config:
            insecure_skip_verify: true

inhibit_rules:
  - source_match:
      severity: critical
    target_match:
      severity: warning
    equal: ['alertname', 'namespace', 'service']
"""

# =============================================================================
# Failure class constants
# =============================================================================

# Preflight failures
FAILURE_KUBECONFIG_MISSING = "kubeconfig_missing"
FAILURE_CLUSTER_ACCESS_FAILED = "cluster_access_failed"
FAILURE_K9B_NOT_READY = "k9b_not_ready"

# Deployment failures
FAILURE_ALERTMANAGER_DEPLOY_FAILED = "alertmanager_deploy_failed"
FAILURE_VMALERT_DEPLOY_FAILED = "vmalert_deploy_failed"
FAILURE_K9B_WEBHOOK_NOT_ENABLED = "k9b_webhook_not_enabled"
FAILURE_WEBHOOK_AUTH_FAILED = "webhook_auth_failed"

# Alert injection failures
FAILURE_VMALERT_RULE_NOT_LOADED = "vmalert_rule_not_loaded"
FAILURE_ALERT_NOT_RECEIVED = "alert_not_received_by_alertmanager"
FAILURE_WEBHOOK_NOT_RECEIVED = "webhook_not_received_by_k9b"

# Verification failures
FAILURE_SIGNAL_ARTIFACT_MISSING = "signal_artifact_missing"
FAILURE_INCIDENT_NOT_OPENED = "incident_not_opened"
FAILURE_INCIDENT_WRONG_STATUS = "incident_wrong_status"
FAILURE_INCIDENT_DUPLICATE = "incident_duplicate_created"
FAILURE_DIAGNOSIS_LOOP_FAILED = "diagnosis_loop_failed"
FAILURE_DIAGNOSIS_LOOP_NO_ALERT_CONTEXT = "diagnosis_loop_no_alert_context"

# Success
FAILURE_LAB_PASSED = "lab_passed"


# =============================================================================
# Expected values for verification
# =============================================================================

EXPECTED_INCIDENT_STATUS = "OPEN"
EXPECTED_INCIDENT_CLASS = "target_unreachable"
EXPECTED_ENTITY_KIND = "service"
EXPECTED_ENTITY_NAME = "openwebui"
EXPECTED_ENTITY_NAMESPACE = "k9b-lab"
EXPECTED_SOURCE_TYPE = "alertmanager"
