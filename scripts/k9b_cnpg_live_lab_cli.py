#!/usr/bin/env python3
"""CLI entry points for CNPG Live Lab scripts.

This module contains the main CLI functions for:
- main_bootstrap: Main bootstrap flow
- main_classify_error: Classify Helm error from stdin
- main_classify_schema: Classify manifest schema error
- main_extract_schema_evidence: Extract schema warnings evidence
- main_classify_wait_timeout: Classify Helm wait timeout (delegated)
- main_monitor_rollout: Monitor rollout until success or timeout
"""

from __future__ import annotations

import argparse
import os
import subprocess  # noqa: F401  # Re-export for backward compatibility with tests
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

# NOTE: Helm evidence imports are lazy (inside subcommand handlers) to avoid
# requiring PyYAML at module import time when Helm functionality isn't used.
# See: scripts/k9b_cnpg_live_lab_helm_evidence.py for PyYAML dependency handling.
from scripts.k9b_cnpg_live_lab_helpers import (
    error,
    log,
    read_json,
    write_json_atomically,
)
from scripts.k9b_cnpg_live_lab_monitor import monitor_rollout as _monitor_rollout
from scripts.k9b_cnpg_live_lab_schema import (
    extract_schema_warnings,
    generate_bounded_summary,
    write_schema_warnings_json,
)

# NOTE: _classify_wait_timeout_main is imported lazily in main_classify_wait_timeout()
# to avoid importing the full classifier stack (including PyYAML-dependent modules)
# when running --help or other commands that don't need the wait-timeout classifier.


def main_bootstrap(
    env_secret: str = "K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64",
    out_var: str = "KUBECONFIG",
    namespace: str = "",
) -> int:
    """Main bootstrap flow."""
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
    log_content = input_path.read_text() if input_path.exists() else ""

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
    if not input_path.exists():
        error(f"Input file not found: {input_path}")
        return 1
    log_content = input_path.read_text()

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
    """Classify Helm wait timeout using watchdog artifacts.
    
    Delegates to scripts/k9b_cnpg_live_lab_wait_timeout module.
    Uses lazy import to avoid loading PyYAML-dependent modules when not needed.
    """
    from scripts.k9b_cnpg_live_lab_wait_timeout import main_classify_wait_timeout as _func
    return _func()


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


def main_collect_rendered_manifest_evidence() -> int:
    """CLI entry point for collecting rendered manifest evidence.

    Replaces inline python -c blocks in workflows with proper CLI subcommand.
    """
    # Lazy import to avoid requiring PyYAML at module import time
    from scripts.k9b_cnpg_live_lab_helm_evidence import collect_rendered_manifest_evidence

    parser = argparse.ArgumentParser(description="Collect rendered manifest evidence")
    parser.add_argument("--chart-path", required=True, help="Path to Helm chart directory")
    parser.add_argument("--values-path", default="", help="Path to values file")
    parser.add_argument(
        "--artifact-dir",
        default=os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"),
        help="Artifact directory",
    )
    parser.add_argument("--namespace", default="", help="Kubernetes namespace")
    parser.add_argument("--release-name", default="k9b", help="Release name")
    args = parser.parse_args(sys.argv[2:])

    artifact_dir = Path(args.artifact_dir)

    result = collect_rendered_manifest_evidence(
        chart_path=args.chart_path,
        values_path=args.values_path or None,
        artifact_dir=artifact_dir,
        namespace=args.namespace,
        release_name=args.release_name,
    )

    print(f"Rendered manifest evidence collected: {result.get('rendered_manifest_path', 'N/A')}")
    if result.get("errors"):
        print("Errors:")
        for error_msg in result["errors"]:
            print(f"  - {error_msg}")

    return 0


def main_collect_helm_evidence() -> int:
    """CLI entry point for collecting Helm evidence.

    Replaces inline python -c blocks in workflows with proper CLI subcommand.
    """
    # Lazy import to avoid requiring PyYAML at module import time
    import json

    from scripts.k9b_cnpg_live_lab_helm_evidence import collect_helm_evidence

    parser = argparse.ArgumentParser(description="Collect Helm evidence")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig file")
    parser.add_argument("--namespace", required=True, help="Kubernetes namespace")
    parser.add_argument("--release-name", default="k9b", help="Release name")
    parser.add_argument(
        "--artifact-dir",
        default=os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"),
        help="Artifact directory",
    )
    parser.add_argument(
        "--helm-returncode",
        type=int,
        help="Helm install/upgrade exit code",
    )
    parser.add_argument(
        "--helm-stdout",
        default="",
        help="Helm install/upgrade stdout (or use --helm-stdout-file)",
    )
    parser.add_argument(
        "--helm-stderr",
        default="",
        help="Helm install/upgrade stderr (or use --helm-stderr-file)",
    )
    parser.add_argument(
        "--helm-stdout-file",
        default="",
        help="Path to file containing Helm stdout",
    )
    parser.add_argument(
        "--helm-stderr-file",
        default="",
        help="Path to file containing Helm stderr",
    )
    args = parser.parse_args(sys.argv[2:])

    artifact_dir = Path(args.artifact_dir)

    # Read stdout from file or argument
    helm_stdout = args.helm_stdout
    if args.helm_stdout_file:
        stdout_path = Path(args.helm_stdout_file)
        if stdout_path.exists():
            helm_stdout = stdout_path.read_text()

    # Read stderr from file or argument
    helm_stderr = args.helm_stderr
    if args.helm_stderr_file:
        stderr_path = Path(args.helm_stderr_file)
        if stderr_path.exists():
            helm_stderr = stderr_path.read_text()

    result = collect_helm_evidence(
        kubeconfig=args.kubeconfig,
        namespace=args.namespace,
        release_name=args.release_name,
        artifact_dir=artifact_dir,
        helm_install_returncode=args.helm_returncode,
        helm_install_stdout=helm_stdout,
        helm_install_stderr=helm_stderr,
    )

    print(json.dumps(result, indent=2))

    return 0 if not result.get("errors") else 1
