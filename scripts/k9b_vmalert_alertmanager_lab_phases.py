#!/usr/bin/env python3
"""Lab phase implementations for vmalert→Alertmanager→K9B incident lab.

This module contains the phase functions that implement the lab workflow.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

from scripts.k9b_vmalert_alertmanager_lab_constants import (
    ALERTMANAGER_CONFIG_TEMPLATE,
    ALERTMANAGER_SERVICE,
    EXPECTED_ENTITY_KIND,
    EXPECTED_ENTITY_NAME,
    EXPECTED_ENTITY_NAMESPACE,
    EXPECTED_INCIDENT_CLASS,
    EXPECTED_INCIDENT_STATUS,
    FAILURE_ALERTMANAGER_DEPLOY_FAILED,
    FAILURE_CLUSTER_ACCESS_FAILED,
    FAILURE_INCIDENT_DUPLICATE,
    FAILURE_INCIDENT_NOT_OPENED,
    FAILURE_INCIDENT_WRONG_STATUS,
    FAILURE_K9B_NOT_READY,
    K9B_BACKEND_DEPLOYMENT,
    K9B_BACKEND_PORT,
    LAB_INCIDENT_KEY,
    LAB_NAME,
    PHASE_DEPLOY,
    PHASE_INJECT,
    PHASE_PREFILIGHT,
    PHASE_RECOVERY,
    PHASE_VERIFY,
    VMALERT_ALERT_NAME,
    VMALERT_RULE_NAME,
    VMALERT_RULE_YAML,
)
from scripts.k9b_vmalert_alertmanager_lab_helpers import (
    apply_manifest,
    check_service_endpoint,
    create_namespace,
    get_deployment_status,
    log,
    port_forward,
    run_kubectl,
    wait_for_deployment,
    write_json_atomically,
)
from scripts.k9b_vmalert_alertmanager_lab_types import LabConfig, LabPhase


def phase_preflight(config: LabConfig) -> LabPhase:
    """Phase 0: Preflight checks."""
    # Check cluster access
    try:
        run_kubectl(
            config.kubeconfig,
            "",
            ["cluster-info"],
            capture_output=True,
            check=True,
        )
        cluster_accessible = True
        log("Cluster access verified")
    except subprocess.CalledProcessError:
        cluster_accessible = False
        log("Cluster access FAILED")

    # Check k9b namespace exists
    try:
        run_kubectl(
            config.kubeconfig,
            "",
            ["get", "namespace", config.k9b_namespace],
            capture_output=True,
            check=True,
        )
        k9b_namespace_exists = True
        log(f"k9b namespace '{config.k9b_namespace}' exists")
    except subprocess.CalledProcessError:
        k9b_namespace_exists = False
        log(f"k9b namespace '{config.k9b_namespace}' does NOT exist")

    # Check k9b backend is ready
    k9b_ready = False
    if k9b_namespace_exists:
        try:
            status = get_deployment_status(
                config.kubeconfig,
                config.k9b_namespace,
                K9B_BACKEND_DEPLOYMENT,
            )
            available = status.get("availableReplicas", 0)
            if available >= 1:
                k9b_ready = True
                log(f"k9b backend ready (replicas: {available})")
            else:
                log(f"k9b backend NOT ready (replicas: {available})")
        except Exception as e:
            log(f"Failed to check k9b status: {e}")

    # Write preflight artifact
    preflight_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "cluster_accessible": cluster_accessible,
        "k9b_namespace": config.k9b_namespace,
        "k9b_namespace_exists": k9b_namespace_exists,
        "k9b_ready": k9b_ready,
    }
    write_json_atomically(config.artifact_dir / PHASE_PREFILIGHT / "preflight.json", preflight_data)

    # Determine success
    success = cluster_accessible and k9b_ready
    failure_class = None
    if not cluster_accessible:
        failure_class = FAILURE_CLUSTER_ACCESS_FAILED
    elif not k9b_ready:
        failure_class = FAILURE_K9B_NOT_READY

    return LabPhase(
        name=PHASE_PREFILIGHT,
        success=success,
        message="Cluster accessible and k9b ready" if success else "Preflight checks failed",
        artifacts={"preflight": preflight_data},
        failure_class=failure_class,
    )


def phase_deploy_alertmanager(config: LabConfig) -> LabPhase:
    """Phase 1: Deploy Alertmanager."""
    # Create monitoring namespace
    create_namespace(config.kubeconfig, config.monitoring_namespace, {
        "app.kubernetes.io/name": "alertmanager",
        "app.kubernetes.io/managed-by": LAB_NAME,
    })

    # Create Alertmanager config
    am_config = ALERTMANAGER_CONFIG_TEMPLATE.format(k9b_namespace=config.k9b_namespace)

    # Save Alertmanager config artifact (redacted)
    config_path = config.artifact_dir / PHASE_DEPLOY / "alertmanager-config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(am_config)

    # Create ConfigMap for Alertmanager config
    config_manifest = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: alertmanager-config
  namespace: {config.monitoring_namespace}
data:
  alertmanager.yml: |
{chr(10).join(f"    {line}" for line in am_config.split(chr(10)))}
"""
    if not apply_manifest(config.kubeconfig, config.monitoring_namespace, config_manifest):
        return LabPhase(
            name=PHASE_DEPLOY,
            success=False,
            message="Failed to apply Alertmanager ConfigMap",
            failure_class=FAILURE_ALERTMANAGER_DEPLOY_FAILED,
        )

    # Deploy Alertmanager via helm
    try:
        subprocess.run(
            [
                "helm", "upgrade", "--install", config.alertmanager_release,
                "prometheus-community/alertmanager",
                "--kubeconfig", config.kubeconfig,
                "--namespace", config.monitoring_namespace,
                "--create-namespace",
                "--set", "configmapExisting=alertmanager-config",
                "--set", "config.enabled=true",
                "--wait", "--timeout", f"{config.readiness_timeout}s",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        return LabPhase(
            name=PHASE_DEPLOY,
            success=False,
            message=f"Helm deploy failed: {e.stderr}",
            failure_class=FAILURE_ALERTMANAGER_DEPLOY_FAILED,
        )

    # Wait for Alertmanager to be ready
    if not wait_for_deployment(config.kubeconfig, config.monitoring_namespace, f"{config.alertmanager_release}-alertmanager", config.readiness_timeout):
        return LabPhase(
            name=PHASE_DEPLOY,
            success=False,
            message="Alertmanager deployment not ready",
            failure_class=FAILURE_ALERTMANAGER_DEPLOY_FAILED,
        )

    log("Alertmanager deployed and ready")

    # Save k9b webhook config artifact
    webhook_config = {
        "enabled": True,
        "auto_promote": True,
        "bearer_token_set": True,  # Don't expose actual token
        "source_instance": "lab-alertmanager",
        "token_placeholder": "<redacted>",
    }
    write_json_atomically(config.artifact_dir / PHASE_DEPLOY / "k9b-webhook-config-redacted.json", webhook_config)

    return LabPhase(
        name=PHASE_DEPLOY,
        success=True,
        message="Alertmanager deployed successfully",
        artifacts={
            "alertmanager_config": am_config,
            "webhook_config": webhook_config,
        },
    )


def phase_inject_alert(config: LabConfig) -> LabPhase:
    """Phase 2: Inject alert via vmalert rule."""
    # Save vmalert rule artifact
    rule_path = config.artifact_dir / PHASE_INJECT / "vmalert-rule.yaml"
    rule_path.parent.mkdir(parents=True, exist_ok=True)
    rule_path.write_text(VMALERT_RULE_YAML)

    # Create lab namespace with k9b-lab label for Alertmanager routing
    create_namespace(config.kubeconfig, config.lab_namespace, {
        "namespace": "k9b-lab",  # For Alertmanager matchers
        "app.kubernetes.io/managed-by": LAB_NAME,
    })

    # Create a synthetic alert payload that mimics what Alertmanager would send
    synthetic_alert = {
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": VMALERT_ALERT_NAME,
                    "namespace": "k9b-lab",
                    "service": "openwebui",
                    "severity": "critical",
                    "k9b.dev/class": EXPECTED_INCIDENT_CLASS,
                    "k9b.dev/entity.kind": EXPECTED_ENTITY_KIND,
                    "k9b.dev/entity.namespace": EXPECTED_ENTITY_NAMESPACE,
                    "k9b.dev/entity.name": EXPECTED_ENTITY_NAME,
                    "k9b.dev/incident.key": LAB_INCIDENT_KEY,
                },
                "annotations": {
                    "summary": "K9B alert promotion lab synthetic alert",
                    "description": "Synthetic alert used to prove vmalert to Alertmanager to K9B incident opening.",
                },
                "startsAt": datetime.now(UTC).isoformat(),
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "http://vmalert:8880/api/v1/group/0",
                "fingerprint": "lab-fingerprint-123456789",
            }
        ],
        "commonLabels": {
            "alertname": VMALERT_ALERT_NAME,
            "namespace": "k9b-lab",
        },
        "commonAnnotations": {
            "summary": "K9B alert promotion lab synthetic alert",
        },
        "externalURL": f"http://{ALERTMANAGER_SERVICE}:9093",
        "groupKey": f"{{\"namespace\"=\"k9b-lab\"}}/{VMALERT_RULE_NAME}",
        "status": "firing",
        "receiver": "k9b-webhook",
    }

    # Save the synthetic alert notification (clearly marked as synthetic)
    synthetic_alert["_meta"] = {
        "delivery_mode": "synthetic_direct_k9b_webhook",
        "alertmanager_delivery_observed": False,
        "vmalert_delivery_observed": False,
        "note": "Synthetic payload injected via curl; real Alertmanager delivery not proven",
    }
    notif_path = config.artifact_dir / PHASE_INJECT / "synthetic-alertmanager-notification.json"
    notif_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomically(notif_path, synthetic_alert)

    # Start port-forward to k9b backend
    log("Starting port-forward to k9b backend...")
    k9b_service_ip = check_service_endpoint(config.kubeconfig, config.k9b_namespace, K9B_BACKEND_DEPLOYMENT)
    if k9b_service_ip:
        log(f"k9b backend service IP: {k9b_service_ip}")

    port_forward_proc = port_forward(
        config.kubeconfig,
        config.k9b_namespace,
        "svc",
        K9B_BACKEND_DEPLOYMENT,
        18080,
        K9B_BACKEND_PORT,
    )

    try:
        # Wait for port-forward to establish
        time.sleep(3)

        # Send alert to webhook endpoint
        alert_json = json.dumps(synthetic_alert)
        curl_result = subprocess.run(
            [
                "curl",
                "-X", "POST",
                "-H", f"Authorization: Bearer {config.webhook_token}",
                "-H", "Content-Type: application/json",
                "-d", alert_json,
                "http://localhost:18080/api/integrations/alertmanager/webhook",
                "-w", "\n%{http_code}",
                "-s",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        log(f"Webhook response code: {curl_result.stdout.strip()[-3:]}")
        log(f"Webhook response body: {curl_result.stdout.strip()[:-3]}")

        if "200" in curl_result.stdout:
            log("Alert successfully sent to k9b webhook")
        else:
            log(f"Alert webhook returned non-200: {curl_result.stdout}")

        # Wait for alert to be processed
        time.sleep(5)

    except subprocess.TimeoutExpired:
        log("Alert webhook request timed out")
    except Exception as e:
        log(f"Error sending alert: {e}")
    finally:
        port_forward_proc.terminate()
        port_forward_proc.wait(timeout=5)

    return LabPhase(
        name=PHASE_INJECT,
        success=True,
        message="Alert injected via synthetic webhook",
        artifacts={
            "vmalert_rule": VMALERT_RULE_YAML,
            "alert_notification": synthetic_alert,
        },
    )


def phase_verify(config: LabConfig) -> LabPhase:
    """Phase 3: Verify incident was created."""
    port_forward_proc = port_forward(
        config.kubeconfig,
        config.k9b_namespace,
        "svc",
        K9B_BACKEND_DEPLOYMENT,
        18080,
        K9B_BACKEND_PORT,
    )

    try:
        time.sleep(2)

        # Get incidents from k9b API
        curl_result = subprocess.run(
            [
                "curl",
                "-s",
                "http://localhost:18080/api/incidents",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        incidents_data: dict[str, Any] = {}
        try:
            incidents_data = json.loads(curl_result.stdout) if curl_result.stdout else {}
        except json.JSONDecodeError:
            log(f"Failed to parse incidents response: {curl_result.stdout}")

        # Filter for lab incident
        lab_incidents = []
        if "incidents" in incidents_data:
            for inc in incidents_data["incidents"]:
                if inc.get("incident_key") == LAB_INCIDENT_KEY or LAB_INCIDENT_KEY.split("/")[-1] in str(inc):
                    lab_incidents.append(inc)

        log(f"Found {len(lab_incidents)} incident(s) for lab key")

        # Save incident artifact
        incident_path = config.artifact_dir / PHASE_VERIFY / "k9b-incident-after-alert.json"
        incident_path.parent.mkdir(parents=True, exist_ok=True)
        incident_data = {
            "incident_key": LAB_INCIDENT_KEY,
            "incidents": lab_incidents,
            "total_count": len(lab_incidents),
        }
        write_json_atomically(incident_path, incident_data)

        # Verify exactly one incident
        if len(lab_incidents) == 0:
            return LabPhase(
                name=PHASE_VERIFY,
                success=False,
                message="No incident found for lab key",
                failure_class=FAILURE_INCIDENT_NOT_OPENED,
            )

        if len(lab_incidents) > 1:
            return LabPhase(
                name=PHASE_VERIFY,
                success=False,
                message=f"Multiple incidents found: {len(lab_incidents)}",
                failure_class=FAILURE_INCIDENT_DUPLICATE,
            )

        # Verify incident properties
        inc = lab_incidents[0]

        if inc.get("status") != EXPECTED_INCIDENT_STATUS:
            return LabPhase(
                name=PHASE_VERIFY,
                success=False,
                message=f"Expected status {EXPECTED_INCIDENT_STATUS}, got {inc.get('status')}",
                failure_class=FAILURE_INCIDENT_WRONG_STATUS,
            )

        log(f"Incident verified: status={inc.get('status')}, class={inc.get('incident_class')}")

        return LabPhase(
            name=PHASE_VERIFY,
            success=True,
            message="Incident verified successfully",
            artifacts={
                "incident": incident_data,
            },
        )

    except Exception as e:
        return LabPhase(
            name=PHASE_VERIFY,
            success=False,
            message=f"Verification failed: {e}",
            failure_class=FAILURE_INCIDENT_NOT_OPENED,
        )
    finally:
        port_forward_proc.terminate()
        port_forward_proc.wait(timeout=5)


def phase_cleanup(config: LabConfig) -> LabPhase:
    """Phase 4: Cleanup resources."""
    try:
        run_kubectl(
            config.kubeconfig,
            "",
            ["delete", "namespace", config.lab_namespace, "--ignore-not-found"],
            capture_output=True,
            check=False,
        )
        log(f"Deleted namespace: {config.lab_namespace}")
    except Exception as e:
        log(f"Failed to delete namespace: {e}")

    return LabPhase(
        name=PHASE_RECOVERY,
        success=True,
        message="Cleanup completed",
    )
