#!/usr/bin/env python3
"""CLI entry points for CNPG Live Lab scripts.

This module contains the main CLI functions for:
- main_bootstrap: Main bootstrap flow
- main_classify_error: Classify Helm error from stdin
- main_classify_schema: Classify manifest schema error
- main_extract_schema_evidence: Extract schema warnings evidence
- main_classify_wait_timeout: Classify Helm wait timeout
- main_monitor_rollout: Monitor rollout until success/timeout
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.k9b_cnpg_live_lab_bootstrap_funcs import (
    bootstrap_decode_kubeconfig,
    classify_helm_error,
    classify_schema_error,
    collect_failure_artifacts,
    run_preflight_checks,
    validate_credential_source,
)
from scripts.k9b_cnpg_live_lab_config import DiagnosisGenerator, PreflightData
from scripts.k9b_cnpg_live_lab_constants import FAILURE_HELM_MANIFEST_SCHEMA_WARNING
from scripts.k9b_cnpg_live_lab_helpers import (
    error,
    read_json,
    write_json_atomically,
)
from scripts.k9b_cnpg_live_lab_monitor import monitor_rollout as _monitor_rollout
from scripts.k9b_cnpg_live_lab_schema import (
    extract_schema_warnings,
    generate_bounded_summary,
    write_schema_warnings_json,
)


def main_bootstrap(
    env_secret: str = "K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64",
    out_var: str = "KUBECONFIG",
    namespace: str = "",
) -> int:
    """Main bootstrap flow."""
    from scripts.k9b_cnpg_live_lab_helpers import log

    artifact_dir = Path(os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"))
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Initialize data structures
    preflight = PreflightData(artifact_dir, namespace)
    diagnosis = DiagnosisGenerator(artifact_dir, namespace)
    diagnosis.heading(1, "k9b CNPG Live Lab Diagnosis")
    diagnosis.text(f"Generated: {datetime.now(UTC).isoformat()}")
    diagnosis.text(f"Namespace: {namespace}")
    diagnosis.text("Bootstrap: k9b_cnpg_live_lab_bootstrap.py")
    diagnosis.heading(2, "Workflow Bootstrap Diagnosis")
    diagnosis.text("This file is generated automatically by the live lab workflow to diagnose")
    diagnosis.text("bootstrap and deployment failures without requiring manual kubectl commands.")

    log(f"Starting bootstrap for namespace: {namespace}")
    log(f"Using secret: {env_secret}")

    # Step 1: Decode kubeconfig
    kubeconfig_path, rc = bootstrap_decode_kubeconfig(
        env_secret, out_var, artifact_dir, preflight, diagnosis
    )
    if rc != 0:
        error("Kubeconfig bootstrap failed")
        collect_failure_artifacts(None, namespace, artifact_dir, preflight, diagnosis)
        return 1

    assert kubeconfig_path is not None, "kubeconfig_path must not be None after successful bootstrap"
    log(f"Kubeconfig bootstrapped to: {kubeconfig_path}")

    # Step 2: Validate credential source
    preflight.failure_stage = "bootstrap"
    rc = validate_credential_source(kubeconfig_path, artifact_dir, preflight, diagnosis)
    if rc != 0:
        error("Credential source validation failed")
        collect_failure_artifacts(kubeconfig_path, namespace, artifact_dir, preflight, diagnosis)
        return 1

    log("Credential validation passed")

    # Step 3: Run preflight checks
    if namespace:
        run_preflight_checks(kubeconfig_path, namespace, artifact_dir, preflight, diagnosis)

    # Save success state
    preflight.save()
    diagnosis.heading(2, "Bootstrap Result")
    diagnosis.text(f"{diagnosis.bold('PASS')}: Bootstrap completed successfully")
    diagnosis.text(f"KUBECONFIG: {diagnosis.inline_code(kubeconfig_path)}")
    diagnosis.text("Credential source: valid")
    diagnosis.save()

    log("Bootstrap completed successfully")
    return 0


def main_classify_error() -> int:
    """Classify Helm error from stdin."""
    helm_output = sys.stdin.read()
    artifact_dir = Path(os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"))

    preflight = PreflightData(artifact_dir)
    diagnosis = DiagnosisGenerator(artifact_dir)

    # Read existing preflight if present
    existing = read_json(artifact_dir / "lab-preflight.json")
    if existing:
        preflight.active_identity = existing.get("active_identity")
        preflight.failure_class = existing.get("failure_class")
        preflight.namespace = existing.get("namespace", "")
        preflight.timestamp = existing.get("bootstrap_timestamp", preflight.timestamp)

    failure_class = classify_helm_error(helm_output, artifact_dir, preflight, diagnosis)
    print(failure_class)
    return 0


def main_classify_schema() -> int:
    """Classify manifest schema error from file."""
    parser = argparse.ArgumentParser(description="Classify manifest schema error")
    parser.add_argument("--input", required=True, help="Path to schema validation log file")
    parser.add_argument(
        "--rendered",
        default="",
        help="Path to rendered Helm YAML (optional, for context)",
    )
    parser.add_argument(
        "--artifact-dir",
        default=os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"),
        help="Artifact directory",
    )
    args = parser.parse_args(sys.argv[2:])

    artifact_dir = Path(args.artifact_dir)
    input_path = Path(args.input)
    rendered_path = Path(args.rendered) if args.rendered else None

    # Read log file
    if input_path.exists():
        log_content = input_path.read_text()
    else:
        log_content = ""

    # Read rendered YAML for context if provided
    rendered_content = ""
    if rendered_path and rendered_path.exists():
        rendered_content = rendered_path.read_text()

    # Extract schema warnings for bounded evidence
    warnings = extract_schema_warnings(log_content, rendered_content)

    preflight = PreflightData(artifact_dir)
    diagnosis = DiagnosisGenerator(artifact_dir)

    # Read existing preflight to preserve context
    existing = read_json(artifact_dir / "lab-preflight.json")
    if existing:
        preflight.active_identity = existing.get("active_identity")
        preflight.failure_class = existing.get("failure_class")
        preflight.namespace = existing.get("namespace", "")
        preflight.timestamp = existing.get("bootstrap_timestamp", preflight.timestamp)

    # Classify the error
    failure_class = classify_schema_error(log_content, artifact_dir, preflight, diagnosis)

    # Write schema-warnings.json with bounded evidence
    if warnings:
        schema_warnings_path = write_schema_warnings_json(
            artifact_dir, warnings, input_path.name, failure_class
        )
        # Add bounded summary to diagnosis
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Extracted Evidence')}: {diagnosis.inline_code(schema_warnings_path.name)}")
        bounded_summary = generate_bounded_summary(warnings)
        diagnosis.text("")
        diagnosis.text(bounded_summary)
        diagnosis.save()

    print(failure_class)
    return 0


def main_extract_schema_evidence() -> int:
    """Extract schema warnings evidence from log file."""
    parser = argparse.ArgumentParser(description="Extract schema warnings from log")
    parser.add_argument("--input", required=True, help="Path to schema validation log file")
    parser.add_argument(
        "--rendered",
        default="",
        help="Path to rendered Helm YAML (optional, for context)",
    )
    parser.add_argument("--output", required=True, help="Output path for schema-warnings.json")
    args = parser.parse_args(sys.argv[2:])

    input_path = Path(args.input)
    rendered_path = Path(args.rendered) if args.rendered else None
    output_path = Path(args.output)

    # Read log file
    if input_path.exists():
        log_content = input_path.read_text()
    else:
        error(f"Input file not found: {input_path}")
        return 1

    # Read rendered YAML for context if provided
    rendered_content = ""
    if rendered_path and rendered_path.exists():
        rendered_content = rendered_path.read_text()

    # Extract schema warnings
    warnings = extract_schema_warnings(log_content, rendered_content)

    # Write output JSON
    data = {
        "failure_class": FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
        "source_log": input_path.name,
        "match_count": len(warnings),
        "matches": warnings,
    }
    write_json_atomically(output_path, data)

    # Print bounded summary to stdout
    summary = generate_bounded_summary(warnings)
    print(summary)
    return 0


def main_classify_wait_timeout() -> int:
    """Classify Helm wait timeout using watchdog artifacts."""
    from scripts.k9b_cnpg_live_lab_bootstrap_funcs import (
        _parse_crash_loop_from_pods,
        _parse_deployment_not_found,
        _parse_deployment_not_ready_from_deployments,
        _parse_image_pull_failure_from_pods,
        _parse_probe_failure_from_pods,
        _parse_pvc_pending_from_pods,
    )
    from scripts.k9b_cnpg_live_lab_constants import (
        FAILURE_DEPLOYMENT_NOT_AVAILABLE,
        FAILURE_EXPECTED_WORKLOAD_MISSING,
        FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
        FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN,
        FAILURE_IMAGE_PULL_FAILED,
        FAILURE_POD_CRASH_LOOP,
        FAILURE_PROBE_FAILED,
        FAILURE_PVC_PENDING,
    )
    parser = argparse.ArgumentParser(description="Classify Helm wait timeout")
    parser.add_argument(
        "--helm-log",
        default=os.environ.get("HELM_LOG", "./lab-artifacts/live/logs/helm-install.log"),
        help="Path to Helm install log (default: $HELM_LOG or ./lab-artifacts/live/logs/helm-install.log)",
    )
    parser.add_argument("--namespace", required=True, help="Namespace name")
    parser.add_argument(
        "--kubeconfig",
        default=os.environ.get("KUBECONFIG", ""),
        help="Path to kubeconfig",
    )
    parser.add_argument(
        "--artifact-dir",
        default=os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"),
        help="Artifact directory",
    )
    parser.add_argument(
        "--release-name",
        default="k9b",
        help="Helm release name (default: k9b)",
    )
    args = parser.parse_args(sys.argv[2:])

    artifact_dir = Path(args.artifact_dir)
    helm_log_path = Path(args.helm_log)
    namespace = args.namespace
    kubeconfig = args.kubeconfig or None

    # Read Helm log
    if helm_log_path.exists():
        helm_output = helm_log_path.read_text()
    else:
        helm_output = ""

    preflight = PreflightData(artifact_dir, namespace)
    diagnosis = DiagnosisGenerator(artifact_dir, namespace)

    # Read existing preflight to preserve context
    existing = read_json(artifact_dir / "lab-preflight.json")
    if existing:
        preflight.active_identity = existing.get("active_identity")
        preflight.namespace = existing.get("namespace", namespace)
        preflight.timestamp = existing.get("bootstrap_timestamp", preflight.timestamp)

    # If we have kubeconfig, collect and analyze watchdog artifacts
    failure_subclass = ""
    if kubeconfig and Path(kubeconfig).exists():
        # Collect current state
        kubectl_artifacts = [
            ("watchdog/pods-final.json", ["get", "pods", "-n", namespace, "-o", "json"]),
            ("watchdog/deployments-final.json", ["get", "deployments", "-n", namespace, "-o", "json"]),
            ("watchdog/events-final.txt", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]),
        ]

        for filename, cmd in kubectl_artifacts:
            result = subprocess.run(
                ["kubectl", "--kubeconfig", kubeconfig] + cmd,
                capture_output=True,
                text=True,
            )
            artifact_path = artifact_dir / filename
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(result.stdout or "(empty)", encoding="utf-8")

        # Parse and classify based on actual state
        pods_json = ""
        deployments_json = ""
        events_text = ""

        pods_path = artifact_dir / "watchdog/pods-final.json"
        if pods_path.exists():
            pods_json = pods_path.read_text()

        deployments_path = artifact_dir / "watchdog/deployments-final.json"
        if deployments_path.exists():
            deployments_json = deployments_path.read_text()

        events_path = artifact_dir / "watchdog/events-final.txt"
        if events_path.exists():
            events_text = events_path.read_text()

        helm_lower = helm_output.lower()

        # Priority order: most specific first
        # Check for expected workload missing first (primary failure indicator)
        if _parse_deployment_not_found(deployments_json):
            failure_class = FAILURE_EXPECTED_WORKLOAD_MISSING
            diagnosis.text(f"**Classification**: `{failure_class}`")
            diagnosis.text("**Cause**: Expected Deployment was never observed before rollout deadline.")
            diagnosis.text("**Evidence**: watchdog/deployments-final.json (empty items list)")

            # Sub-classify expected_workload_missing
            from scripts.k9b_cnpg_live_lab_workload_missing_classify import (
                classify_expected_workload_missing,
            )

            # Collect render metadata (trust check)
            render_exit_code_path = artifact_dir / "helm" / "rendered-manifest-exit-code.txt"
            render_stderr_path = artifact_dir / "helm" / "rendered-manifest-stderr.log"
            render_exit_code = ""
            render_stderr = ""
            rendered_manifest = ""
            
            if render_exit_code_path.exists():
                render_exit_code = render_exit_code_path.read_text().strip()
            
            if render_stderr_path.exists():
                render_stderr = render_stderr_path.read_text()
            
            # Only trust rendered manifest when exit code is 0
            if render_exit_code == "0":
                rendered_path = artifact_dir / "helm" / "rendered-manifest.yaml"
                if rendered_path.exists():
                    rendered_manifest = rendered_path.read_text()
            else:
                diagnosis.text(f"**Note**: helm template failed (exit code: {render_exit_code}), ignoring rendered manifest")
                if render_stderr:
                    diagnosis.text(f"**Render stderr**: {render_stderr[:500]}...")

            # Collect Helm install logs (trust check)
            install_exit_code_path = artifact_dir / "helm" / "install-exit-code.txt"
            install_stderr_path = artifact_dir / "helm" / "install-stderr.log"
            install_exit_code = ""
            install_stderr = ""
            
            if install_exit_code_path.exists():
                install_exit_code = install_exit_code_path.read_text().strip()
            
            if install_stderr_path.exists():
                install_stderr = install_stderr_path.read_text()

            # Collect Helm evidence
            helm_status_json = ""
            helm_history_json = ""
            helm_values_json = ""

            status_path = artifact_dir / "helm" / "status.json"
            if status_path.exists():
                helm_status_json = status_path.read_text()

            history_path = artifact_dir / "helm" / "history.json"
            if history_path.exists():
                helm_history_json = history_path.read_text()

            values_path = artifact_dir / "helm" / "get-values.json"
            if values_path.exists():
                helm_values_json = values_path.read_text()

            # Run sub-classification
            failure_subclass, subclass_diagnostics = classify_expected_workload_missing(
                artifact_dir=artifact_dir,
                namespace=namespace,
                deployments_json=deployments_json,
                helm_install_stdout=helm_output,
                helm_install_stderr=install_stderr,
                helm_status_json=helm_status_json,
                helm_history_json=helm_history_json,
                helm_values_json=helm_values_json,
                rendered_manifest_yaml=rendered_manifest,
            )

            # Report sub-classification
            diagnosis.text("")
            diagnosis.text(f"**Sub-classification**: `{failure_subclass}`")

            # Add diagnostics about rendered workload inventory
            if subclass_diagnostics.get("rendered_manifest_captured"):
                rendered_deployment_present = subclass_diagnostics.get("rendered_deployment_present", False)
                cluster_deployment_present = subclass_diagnostics.get("cluster_deployment_present", False)
                diagnosis.text(f"**Rendered manifest captured**: {rendered_deployment_present}")
                diagnosis.text(f"**Cluster deployment present**: {cluster_deployment_present}")

                if subclass_diagnostics.get("evidence_artifacts"):
                    artifacts = subclass_diagnostics["evidence_artifacts"]
                    diagnosis.text(f"**Evidence artifacts**: {', '.join(artifacts)}")

            # Add Helm release status if available
            if helm_status_json:
                import json
                try:
                    status_data = json.loads(helm_status_json)
                    release_status = status_data.get("info", {}).get("status", {}).get("status")
                    diagnosis.text(f"**Helm release status**: {release_status}")
                except (json.JSONDecodeError, TypeError):
                    pass

        elif _parse_crash_loop_from_pods(pods_json):
            failure_class = FAILURE_POD_CRASH_LOOP
            diagnosis.text(f"**Classification**: `{failure_class}`")
            diagnosis.text("**Cause**: Pod containers are in CrashLoopBackOff state.")
            diagnosis.text("**Evidence**: watchdog/pods-final.json")

        elif _parse_image_pull_failure_from_pods(pods_json):
            failure_class = FAILURE_IMAGE_PULL_FAILED
            diagnosis.text(f"**Classification**: `{failure_class}`")
            diagnosis.text("**Cause**: Container image could not be pulled.")
            diagnosis.text("**Evidence**: watchdog/pods-final.json")

        elif _parse_probe_failure_from_pods(pods_json):
            failure_class = FAILURE_PROBE_FAILED
            diagnosis.text(f"**Classification**: `{failure_class}`")
            diagnosis.text("**Cause**: Container probe failed (exit code != 0).")
            diagnosis.text("**Evidence**: watchdog/pods-final.json")

        elif _parse_deployment_not_ready_from_deployments(deployments_json):
            failure_class = FAILURE_DEPLOYMENT_NOT_AVAILABLE
            diagnosis.text(f"**Classification**: `{failure_class}`")
            diagnosis.text("**Cause**: Deployment has no available replicas.")
            diagnosis.text("**Evidence**: watchdog/deployments-final.json")

        elif _parse_pvc_pending_from_pods(pods_json, events_text):
            failure_class = FAILURE_PVC_PENDING
            diagnosis.text(f"**Classification**: `{failure_class}`")
            diagnosis.text("**Cause**: PVC is stuck in Pending state.")
            diagnosis.text("**Evidence**: watchdog/pods-final.json, watchdog/events-final.txt")

        elif "unknown field" in helm_lower:
            failure_class = FAILURE_HELM_MANIFEST_SCHEMA_WARNING
            diagnosis.text(f"**Classification**: `{failure_class}`")
            diagnosis.text("**Cause**: Helm chart has schema drift (unknown field warnings).")
            diagnosis.text("**Evidence**: helm install log")

        else:
            failure_class = FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN
            diagnosis.text(f"**Classification**: `{failure_class}`")
            diagnosis.text("**Cause**: Helm wait timed out but specific cause not determined.")
            diagnosis.text("**Evidence**: Review watchdog/ artifacts for details.")

    else:
        failure_class = FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN
        diagnosis.text(f"**Classification**: `{failure_class}`")
        diagnosis.text("**Cause**: Helm wait timed out without cluster state data.")
        diagnosis.text("**Evidence**: helm install log")

    diagnosis.text("")
    diagnosis.text(f"**Suggested action**: Review watchdog/ artifacts and {helm_log_path.name}")
    diagnosis.text("to determine the root cause of the timeout.")

    if preflight.failure_class is None:
        preflight.failure_class = failure_class
        preflight.failure_stage = "helm_deploy"
        # Store subclass in failure_reason if present
        if failure_subclass:
            preflight.failure_reason = failure_subclass

    preflight.save()
    diagnosis.save()

    # Output classification to stdout
    output = failure_class
    if failure_subclass:
        output = f"{failure_class}::{failure_subclass}"
    print(output)
    return 0


def main_monitor_rollout() -> int:
    """CLI entry point for rollout monitor."""
    import json

    parser = argparse.ArgumentParser(
        description="Monitor Kubernetes rollout until success or timeout"
    )
    parser.add_argument(
        "--kubeconfig",
        required=True,
        help="Path to kubeconfig file",
    )
    parser.add_argument(
        "--namespace",
        required=True,
        help="Kubernetes namespace",
    )
    parser.add_argument(
        "--release",
        default="k9b",
        help="Release name (default: k9b)",
    )
    parser.add_argument(
        "--max-wait",
        "--deadline",
        dest="max_wait",
        type=int,
        default=300,
        help="Max wait time in seconds (default: 300). Alias: --deadline",
    )
    parser.add_argument(
        "--interval",
        "--poll-interval",
        dest="interval",
        type=int,
        default=15,
        help="Polling interval in seconds (default: 15). Alias: --poll-interval",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=1,
        help="Expected replica count (default: 1)",
    )
    parser.add_argument(
        "--artifact-dir",
        default=os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"),
        help="Artifact directory (default: $ARTIFACT_DIR or ./lab-artifacts/live)",
    )
    args = parser.parse_args(sys.argv[2:])

    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Monitor rollout
    success, status, snapshot = _monitor_rollout(
        args.kubeconfig,
        args.namespace,
        args.release,
        args.max_wait,
        args.interval,
        args.target_count,
        artifact_dir,
    )

    # Output result
    result = {
        "success": success,
        "status": status,
        "failure_class": snapshot.get("rollout_checks", {}).get("failure_class", "")
            if snapshot else "",
        "rollout_checks": snapshot.get("rollout_checks", {}) if snapshot else {},
    }

    # Write result JSON
    write_json_atomically(artifact_dir / "rollout-result.json", result)

    # Print to stdout
    print(json.dumps(result, indent=2))

    return 0 if success else 1
