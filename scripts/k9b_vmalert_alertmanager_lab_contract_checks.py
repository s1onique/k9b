#!/usr/bin/env python3
"""Contract checks for vmalert→Alertmanager→K9B incident lab.

This module contains individual verification functions for each artifact type.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from k9b_vmalert_alertmanager_lab_contract import ContractVerificationReport

# Patterns that indicate forbidden secrets in artifacts
_FORBIDDEN_PATTERNS = [
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-]+"), "Bearer token found"),
    (re.compile(r"Authorization:\s*\S+"), "Authorization header found"),
    (re.compile(r"api[_-]?key[\s]*[=:][\s]*\S+", re.IGNORECASE), "API key found"),
    (re.compile(r"secret[\s]*[=:][\s]*\S+", re.IGNORECASE), "Secret found"),
    (re.compile(r"password[\s]*[=:][\s]*\S+", re.IGNORECASE), "Password found"),
    (re.compile(r"token[\s]*[=:][\s]*\S+", re.IGNORECASE), "Token found"),
    (re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"), "Private key found"),
    (re.compile(r"-----BEGIN\s+CERTIFICATE-----"), "Certificate found"),
    (re.compile(r"client[_-]?cert", re.IGNORECASE), "Client cert found"),
    (re.compile(r"kubeconfig", re.IGNORECASE), "Kubeconfig reference found"),
]


def check_forbidden_secrets(content: str, artifact_path: str) -> list[str]:
    """Check content for forbidden secret patterns.

    Args:
        content: File content to check
        artifact_path: Path to the artifact (for context)

    Returns:
        List of violation messages
    """
    violations = []
    for pattern, message in _FORBIDDEN_PATTERNS:
        match = pattern.search(content)
        if match:
            # Provide context around the match
            start = max(0, match.start() - 20)
            end = min(len(content), match.end() + 20)
            context = content[start:end].replace("\n", "\\n")
            violations.append(f"{message} in {artifact_path}: ...{context}...")
    return violations


def verify_preflight(artifact_dir: Path, report: ContractVerificationReport) -> None:
    """Verify preflight artifacts."""

    # Look for preflight artifact in phase0-preflight directory
    preflight_path = artifact_dir / "phase0-preflight" / "preflight.json"
    if not preflight_path.exists():
        # Fallback to root level
        preflight_path = artifact_dir / "preflight.json"
        if not preflight_path.exists():
            report.add_violation("preflight", "preflight.json not found")
            return

    report.checked_artifacts.append(str(preflight_path))
    with open(preflight_path) as f:
        content = f.read()
        violations = check_forbidden_secrets(content, str(preflight_path))
        for v in violations:
            report.add_violation("forbidden_secrets", v)

    try:
        preflight = json.loads(content)
    except json.JSONDecodeError as e:
        report.add_violation("preflight", f"Invalid JSON: {e}")
        return

    # Check required fields
    required_fields = ["cluster_accessible", "k9b_namespace"]
    for required_field in required_fields:
        if required_field not in preflight:
            report.add_violation("preflight", f"Missing required field: {required_field}")

    if preflight.get("cluster_accessible"):
        report.add_pass("preflight", "Cluster access verified")
    else:
        report.add_violation("preflight", "Cluster access failed")


def verify_vmalert_rule(artifact_dir: Path, report: ContractVerificationReport) -> None:
    """Verify vmalert rule artifact."""
    from k9b_vmalert_alertmanager_lab_constants import LAB_INCIDENT_KEY

    # Look for vmalert rule artifact in phase2-inject directory
    rule_path = artifact_dir / "phase2-inject" / "vmalert-rule.yaml"
    if not rule_path.exists():
        # Fallback to root level
        rule_path = artifact_dir / "vmalert-rule.yaml"
        if not rule_path.exists():
            report.add_violation("vmalert_rule", "vmalert-rule.yaml not found")
            return

    report.checked_artifacts.append(str(rule_path))
    with open(rule_path) as f:
        content = f.read()
        violations = check_forbidden_secrets(content, str(rule_path))
        for v in violations:
            report.add_violation("forbidden_secrets", v)

    # Check rule structure
    if "K9BAlertPromotionLabAlwaysFiring" in content:
        report.add_pass("vmalert_rule", "Rule name matches expected")
    else:
        report.add_violation("vmalert_rule", "Expected rule name not found")

    if 'expr: vector(1)' in content:
        report.add_pass("vmalert_rule", "Deterministic expression found")
    else:
        report.add_violation("vmalert_rule", "Expected deterministic expression not found")

    if LAB_INCIDENT_KEY in content:
        report.add_pass("vmalert_rule", "Lab incident key found")
    else:
        report.add_violation("vmalert_rule", "Lab incident key not found in rule")


def verify_alertmanager_config(artifact_dir: Path, report: ContractVerificationReport) -> None:
    """Verify Alertmanager config artifact."""
    # Look for Alertmanager config in phase1-deploy directory
    config_path = artifact_dir / "phase1-deploy" / "alertmanager-config.yaml"
    if not config_path.exists():
        # Fallback to root level
        config_path = artifact_dir / "alertmanager-config.yaml"
        if not config_path.exists():
            report.add_violation("alertmanager_config", "Alertmanager config not found")
            return

    report.checked_artifacts.append(str(config_path))
    with open(config_path) as f:
        content = f.read()
        violations = check_forbidden_secrets(content, str(config_path))
        for v in violations:
            report.add_violation("forbidden_secrets", v)

    # Check webhook receiver
    if "k9b-webhook" in content:
        report.add_pass("alertmanager_config", "k9b-webhook receiver defined")
    else:
        report.add_violation("alertmanager_config", "k9b-webhook receiver not found")

    if "/api/integrations/alertmanager/webhook" in content:
        report.add_pass("alertmanager_config", "Webhook path found")
    else:
        report.add_violation("alertmanager_config", "Webhook path not found")

    if "send_resolved" in content:
        report.add_pass("alertmanager_config", "send_resolved configured")
    else:
        report.add_violation("alertmanager_config", "send_resolved not configured")


def verify_k9b_webhook_config(artifact_dir: Path, report: ContractVerificationReport) -> None:
    """Verify K9B webhook config artifact."""
    # Look for webhook config in phase1-deploy directory
    config_path = artifact_dir / "phase1-deploy" / "k9b-webhook-config-redacted.json"
    if not config_path.exists():
        # Fallback to root level
        config_path = artifact_dir / "k9b-webhook-config-redacted.json"
        if not config_path.exists():
            report.add_violation("k9b_webhook", "k9b-webhook-config-redacted.json not found")
            return

    report.checked_artifacts.append(str(config_path))
    with open(config_path) as f:
        content = f.read()
        violations = check_forbidden_secrets(content, str(config_path))
        for v in violations:
            report.add_violation("forbidden_secrets", v)

    try:
        config = json.loads(content)
    except json.JSONDecodeError as e:
        report.add_violation("k9b_webhook", f"Invalid JSON: {e}")
        return

    # Check required fields
    if config.get("enabled"):
        report.add_pass("k9b_webhook", "Webhook enabled")
    else:
        report.add_violation("k9b_webhook", "Webhook not enabled")

    if config.get("auto_promote"):
        report.add_pass("k9b_webhook", "Auto-promote enabled")
    else:
        report.add_violation("k9b_webhook", "Auto-promote not enabled")

    if config.get("source_instance") == "lab-alertmanager":
        report.add_pass("k9b_webhook", "Source instance matches lab")
    else:
        report.add_violation(
            "k9b_webhook",
            f"Expected source_instance=lab-alertmanager, got {config.get('source_instance')}",
        )


def verify_alertmanager_notification(artifact_dir: Path, report: ContractVerificationReport) -> None:
    """Verify Alertmanager notification artifact."""
    # Look for synthetic notification artifact in phase2-inject directory
    notif_path = artifact_dir / "phase2-inject" / "synthetic-alertmanager-notification.json"
    if not notif_path.exists():
        # Fallback to root level
        notif_path = artifact_dir / "synthetic-alertmanager-notification.json"
        if not notif_path.exists():
            report.add_violation(
                "alertmanager_notification",
                "synthetic-alertmanager-notification.json not found",
            )
            return

    report.checked_artifacts.append(str(notif_path))
    with open(notif_path) as f:
        content = f.read()
        violations = check_forbidden_secrets(content, str(notif_path))
        for v in violations:
            report.add_violation("forbidden_secrets", v)

    try:
        notif = json.loads(content)
    except json.JSONDecodeError as e:
        report.add_violation("alertmanager_notification", f"Invalid JSON: {e}")
        return

    alerts = notif.get("alerts", [])
    if len(alerts) >= 1:
        report.add_pass("alertmanager_notification", f"Found {len(alerts)} alert(s)")
    else:
        report.add_violation("alertmanager_notification", "No alerts found in notification")

    # Check for firing alert
    firing_alerts = [a for a in alerts if a.get("status") == "firing"]
    if firing_alerts:
        report.add_pass("alertmanager_notification", "At least one firing alert")
    else:
        report.add_violation("alertmanager_notification", "No firing alerts found")


def verify_alert_signal_artifacts(artifact_dir: Path, report: ContractVerificationReport) -> None:
    """Verify K9B alert signal artifacts."""
    from k9b_vmalert_alertmanager_lab_constants import VMALERT_ALERT_NAME

    # Look for alert signal artifacts
    signals_dir = artifact_dir / "external-analysis" / "alert-signals"
    if not signals_dir.exists():
        report.add_violation("alert_signal", "Alert signals directory not found")
        return

    signal_files = list(signals_dir.glob("alert-signal-*.json"))
    if not signal_files:
        report.add_violation("alert_signal", "No alert signal artifacts found")
        return

    report.checked_artifacts.extend([str(f) for f in signal_files])

    # Check each signal artifact
    for signal_file in signal_files:
        with open(signal_file) as f:
            content = f.read()
            violations = check_forbidden_secrets(content, str(signal_file))
            for v in violations:
                report.add_violation("forbidden_secrets", v)

        try:
            signal = json.loads(content)
        except json.JSONDecodeError:
            report.add_violation("alert_signal", f"Invalid JSON in {signal_file.name}")
            continue

        # Verify schema version
        if signal.get("schema_version", "").startswith("k9b.alert_signal"):
            report.add_pass("alert_signal", f"{signal_file.name} has valid schema version")
        else:
            report.add_violation(
                "alert_signal",
                f"{signal_file.name} missing valid schema version",
            )

        # Verify signal data
        sig_data = signal.get("signal", {})
        if sig_data.get("alertname") == VMALERT_ALERT_NAME:
            report.add_pass("alert_signal", "Alert name matches lab rule")
        else:
            report.add_violation(
                "alert_signal",
                f"Expected alertname {VMALERT_ALERT_NAME}, got {sig_data.get('alertname')}",
            )

    report.add_pass("alert_signal", f"Found {len(signal_files)} alert signal artifact(s)")


def verify_incident(artifact_dir: Path, report: ContractVerificationReport) -> None:
    """Verify K9B incident artifact."""
    from k9b_vmalert_alertmanager_lab_constants import (
        EXPECTED_ENTITY_KIND,
        EXPECTED_ENTITY_NAME,
        EXPECTED_ENTITY_NAMESPACE,
        EXPECTED_INCIDENT_CLASS,
        EXPECTED_INCIDENT_STATUS,
        EXPECTED_SOURCE_TYPE,
        LAB_INCIDENT_KEY,
    )

    # Look for incident artifact in phase3-verify directory
    incident_path = artifact_dir / "phase3-verify" / "k9b-incident-after-alert.json"
    if not incident_path.exists():
        # Try alternative names/locations
        incident_path = artifact_dir / "phase3-verify" / "k9b-incident.json"
        if not incident_path.exists():
            incident_path = artifact_dir / "k9b-incident-after-alert.json"
            if not incident_path.exists():
                incident_path = artifact_dir / "k9b-incident.json"
                if not incident_path.exists():
                    report.add_violation("incident", "Incident artifact not found")
                    return

    report.checked_artifacts.append(str(incident_path))
    with open(incident_path) as f:
        content = f.read()
        violations = check_forbidden_secrets(content, str(incident_path))
        for v in violations:
            report.add_violation("forbidden_secrets", v)

    try:
        incident = json.loads(content)
    except json.JSONDecodeError as e:
        report.add_violation("incident", f"Invalid JSON: {e}")
        return

    # Check incident key
    if incident.get("incident_key") == LAB_INCIDENT_KEY:
        report.add_pass("incident", "Incident key matches lab key")
    else:
        report.add_violation(
            "incident",
            f"Expected incident_key={LAB_INCIDENT_KEY}, got {incident.get('incident_key')}",
        )

    # Check exactly one incident
    incidents = incident.get("incidents", [])
    if len(incidents) == 1:
        report.add_pass("incident", "Exactly one incident created")
    elif len(incidents) == 0:
        report.add_violation("incident", "No incidents found")
        return
    else:
        report.add_violation("incident", f"Expected 1 incident, found {len(incidents)}")

    # Check incident properties
    inc = incidents[0]

    if inc.get("status") == EXPECTED_INCIDENT_STATUS:
        report.add_pass("incident", f"Incident status is {EXPECTED_INCIDENT_STATUS}")
    else:
        report.add_violation(
            "incident",
            f"Expected status={EXPECTED_INCIDENT_STATUS}, got {inc.get('status')}",
        )

    if inc.get("incident_class") == EXPECTED_INCIDENT_CLASS:
        report.add_pass("incident", f"Incident class is {EXPECTED_INCIDENT_CLASS}")
    else:
        report.add_violation(
            "incident",
            f"Expected incident_class={EXPECTED_INCIDENT_CLASS}, got {inc.get('incident_class')}",
        )

    # Check primary entity
    primary_entity = inc.get("primary_entity", {})
    if primary_entity.get("kind") == EXPECTED_ENTITY_KIND:
        report.add_pass("incident", f"Primary entity kind is {EXPECTED_ENTITY_KIND}")
    else:
        report.add_violation(
            "incident",
            f"Expected entity kind={EXPECTED_ENTITY_KIND}, got {primary_entity.get('kind')}",
        )

    if primary_entity.get("name") == EXPECTED_ENTITY_NAME:
        report.add_pass("incident", f"Primary entity name is {EXPECTED_ENTITY_NAME}")
    else:
        report.add_violation(
            "incident",
            f"Expected entity name={EXPECTED_ENTITY_NAME}, got {primary_entity.get('name')}",
        )

    if primary_entity.get("namespace") == EXPECTED_ENTITY_NAMESPACE:
        report.add_pass("incident", f"Primary entity namespace is {EXPECTED_ENTITY_NAMESPACE}")
    else:
        report.add_violation(
            "incident",
            f"Expected entity namespace={EXPECTED_ENTITY_NAMESPACE}, got {primary_entity.get('namespace')}",
        )

    # Check alert source
    if inc.get("source_type") == EXPECTED_SOURCE_TYPE:
        report.add_pass("incident", f"Source type is {EXPECTED_SOURCE_TYPE}")
    else:
        report.add_violation(
            "incident",
            f"Expected source_type={EXPECTED_SOURCE_TYPE}, got {inc.get('source_type')}",
        )


def verify_diagnosis_loop(artifact_dir: Path, report: ContractVerificationReport) -> None:
    """Verify diagnosis loop artifacts."""
    diag_path = artifact_dir / "k9b-diagnosis-loop-result.json"
    if not diag_path.exists():
        # This is optional - diagnosis loop may not have run
        report.add_pass("diagnosis_loop", "Diagnosis loop artifact not found (optional)")
        return

    report.checked_artifacts.append(str(diag_path))
    with open(diag_path) as f:
        content = f.read()
        violations = check_forbidden_secrets(content, str(diag_path))
        for v in violations:
            report.add_violation("forbidden_secrets", v)

    try:
        diag = json.loads(content)
    except json.JSONDecodeError as e:
        report.add_violation("diagnosis_loop", f"Invalid JSON: {e}")
        return

    # Check diagnosis ran
    if diag.get("run_id"):
        report.add_pass("diagnosis_loop", f"Diagnosis loop ran with run_id={diag.get('run_id')}")
    else:
        report.add_violation("diagnosis_loop", "No run_id in diagnosis result")

    # Check alert context was included
    if "alert_context" in diag or "alert_signal" in diag:
        report.add_pass("diagnosis_loop", "Alert context included in diagnosis")
    else:
        report.add_violation(
            "diagnosis_loop",
            "Alert context not found in diagnosis result",
            severity="warning",
        )
