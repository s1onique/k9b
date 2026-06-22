#!/usr/bin/env python3
"""Bootstrap script for CNPG Live Lab credential validation and diagnosis.

Reusable bootstrap for the live lab workflow:
- Decodes protected kubeconfig to RUNNER_TEMP
- Validates credential source and fails closed if wrong identity detected
- Runs preflight checks
- Classifies Helm errors
- Emits machine-readable diagnostics as valid JSON

Usage:
    python k9b_cnpg_live_lab_bootstrap.py <env_secret_name> <kubeconfig_out_var> [namespace]
    python k9b_cnpg_live_lab_bootstrap.py classify-error <helm_output>

Exit codes:
    0 - Bootstrap succeeded, KUBECONFIG exported
    1 - Secret missing, decode failed, or wrong credential source
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

# Failure class constants
FAILURE_KUBECONFIG_MISSING = "kubeconfig_missing"
FAILURE_KUBECONFIG_DECODE_FAILED = "kubeconfig_decode_failed"
FAILURE_KUBECONFIG_AUTH_FAILED = "kubeconfig_auth_failed"
FAILURE_CREDENTIAL_SOURCE_WRONG = "credential_source_wrong"
FAILURE_HELM_RBAC_DENIED = "helm_rbac_denied"
FAILURE_IMAGE_PULL_FAILED = "image_pull_failed"
FAILURE_CNPG_CRD_MISSING = "cnpg_crd_missing"
FAILURE_STORAGE_OR_CAPACITY = "storageclass_or_capacity_issue"
FAILURE_WORKLOAD_NOT_READY = "workload_not_ready"
FAILURE_HELM_UNKNOWN = "helm_unknown_error"


# =============================================================================
# Helpers
# =============================================================================

def log(msg: str) -> None:
    """Log info message."""
    print(f"[bootstrap] {msg}", flush=True)


def warn(msg: str) -> None:
    """Log warning message."""
    print(f"[bootstrap] WARNING: {msg}", file=sys.stderr, flush=True)


def error(msg: str) -> None:
    """Log error message."""
    print(f"[bootstrap] ERROR: {msg}", file=sys.stderr, flush=True)


def write_json_atomically(path: Path, data: dict) -> None:
    """Write JSON file atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.rename(path)


def read_json(path: Path) -> dict:
    """Read JSON file, returning empty dict if not found."""
    if path.exists():
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    return {}


def get_env_secret(secret_name: str) -> str | None:
    """Get environment secret value, returning None if not set."""
    # Handle GitHub Actions secrets format
    value = os.environ.get(secret_name)
    if value is None:
        # Try lowercase
        value = os.environ.get(secret_name.lower())
    return value


# =============================================================================
# Preflight data structure
# =============================================================================

class PreflightData:
    """Container for preflight diagnostic data."""

    def __init__(self, artifact_dir: Path, namespace: str = ""):
        self.artifact_dir = artifact_dir
        self.namespace = namespace
        self.timestamp = datetime.now(UTC).isoformat()
        self.failure_class: str | None = None
        self.failure_reason: str | None = None
        self.failure_stage: str | None = None  # "bootstrap" or "helm_deploy"
        self.active_identity: str | None = None
        self.credential_source: str | None = None
        self.current_context: str | None = None
        self.api_reachable: bool | None = None
        self.namespace_exists: bool | None = None
        self.namespace_status: str | None = None
        self.rbac_checks_complete: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "bootstrap_timestamp": self.timestamp,
            "namespace": self.namespace,
            "failure_class": self.failure_class,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "active_identity": self.active_identity,
            "credential_source": self.credential_source,
            "current_context": self.current_context,
            "api_reachable": self.api_reachable,
            "namespace_exists": self.namespace_exists,
            "namespace_status": self.namespace_status,
            "rbac_checks_complete": self.rbac_checks_complete,
        }

    def save(self) -> None:
        """Save preflight data to JSON file."""
        path = self.artifact_dir / "lab-preflight.json"
        write_json_atomically(path, self.to_dict())


# =============================================================================
# Diagnosis markdown generator
# =============================================================================

class DiagnosisGenerator:
    """Generates lab-diagnosis.md markdown file."""

    def __init__(self, artifact_dir: Path, namespace: str = ""):
        self.artifact_dir = artifact_dir
        self.namespace = namespace
        self.lines: list[str] = []

    def heading(self, level: int, text: str) -> None:
        """Add a heading."""
        self.lines.append(f"{'#' * level} {text}\n")

    def text(self, text: str) -> None:
        """Add plain text."""
        self.lines.append(f"{text}\n")

    def code(self, code: str, lang: str = "") -> None:
        """Add code block."""
        self.lines.append(f"```{lang}\n{code}\n```\n")

    def bold(self, text: str) -> str:
        """Wrap text in bold markdown."""
        return f"**{text}**"

    def inline_code(self, text: str) -> str:
        """Wrap text in inline code markdown."""
        return f"`{text}`"

    def bullet(self, text: str) -> None:
        """Add bullet point."""
        self.lines.append(f"- {text}\n")

    def save(self) -> None:
        """Save diagnosis to markdown file."""
        path = self.artifact_dir / "lab-diagnosis.md"
        path.write_text("".join(self.lines))


# =============================================================================
# Bootstrap functions
# =============================================================================

def bootstrap_decode_kubeconfig(
    secret_name: str,
    out_var: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> tuple[str | None, int]:
    """Decode kubeconfig from base64 secret.

    Returns:
        Tuple of (kubeconfig_path, exit_code)
    """
    secret_value = get_env_secret(secret_name)
    if not secret_value:
        error(f"Secret '{secret_name}' is not set or empty")
        preflight.failure_class = FAILURE_KUBECONFIG_MISSING
        preflight.failure_reason = "KUBECONFIG secret not found in environment"
        preflight.save()
        diagnosis.text("**FAIL**: KUBECONFIG secret not found in environment")
        diagnosis.save()
        return None, 1

    out_path = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "k9b-lab-kubeconfig"

    # Decode base64 to file
    import base64 as b64_module
    try:
        # Try standard base64 decode with padding
        kubeconfig_bytes = b64_module.b64decode(secret_value + "=" * (4 - len(secret_value) % 4))
    except Exception:
        try:
            kubeconfig_bytes = b64_module.b64decode(secret_value)
        except Exception:
            error("Failed to decode base64 kubeconfig")
            preflight.failure_class = FAILURE_KUBECONFIG_DECODE_FAILED
            preflight.failure_reason = "KUBECONFIG base64 decode failed"
            preflight.save()
            diagnosis.text("**FAIL**: KUBECONFIG base64 decode failed")
            diagnosis.save()
            return None, 1

    # Write kubeconfig file
    out_path.write_bytes(kubeconfig_bytes)
    out_path.chmod(0o600)

    # Verify it's a valid kubeconfig
    content = out_path.read_text()
    if "apiVersion:" not in content:
        error("Decoded file does not appear to be a valid kubeconfig")
        out_path.unlink(missing_ok=True)
        preflight.failure_class = FAILURE_KUBECONFIG_DECODE_FAILED
        preflight.failure_reason = "KUBECONFIG does not appear valid after decode"
        preflight.save()
        diagnosis.text("**FAIL**: KUBECONFIG does not appear valid after decode")
        diagnosis.save()
        return None, 1

    log(f"KUBECONFIG={out_path}")
    log("KUBECONFIG decoded successfully")

    # Export to GITHUB_ENV
    github_env = Path(os.environ.get("GITHUB_ENV", ".github_env"))
    with open(github_env, "a") as f:
        f.write(f"{out_var}={out_path}\n")
        f.write(f"KUBECONFIG_PATH={out_path}\n")

    return str(out_path), 0


def validate_credential_source(
    kubeconfig: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> int:
    """Validate credential source using kubectl auth whoami.

    Returns:
        Exit code (0 = valid, 1 = invalid)
    """
    log("Validating credential source...")

    # Get active identity
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "auth", "whoami"],
        capture_output=True,
        text=True,
    )
    whoami_output = result.stdout.strip()
    preflight.active_identity = whoami_output

    diagnosis.heading(2, "Credential Validation Result")

    if result.returncode != 0 or not whoami_output:
        error("kubectl auth whoami failed or returned empty")
        preflight.failure_class = FAILURE_KUBECONFIG_AUTH_FAILED
        preflight.failure_reason = f"kubectl auth whoami failed (exit={result.returncode})"
        preflight.save()
        diagnosis.text("**FAIL**: kubectl auth whoami failed")
        diagnosis.text(f"Exit code: {result.returncode}")
        diagnosis.text(f"Output: {whoami_output or result.stderr}")
        diagnosis.save()
        return 1

    diagnosis.text("**PASS**: Credential source is valid")
    diagnosis.text(f"Active identity: {diagnosis.inline_code(whoami_output)}")
    preflight.credential_source = "valid"

    # Check for wrong credential source (ARC runner SA)
    if whoami_output.startswith("system:serviceaccount:github-actions-runner:"):
        error("Credential source is ARC runner ServiceAccount - this is WRONG")
        error(f"Active identity: {whoami_output}")
        error("Expected: protected environment kubeconfig identity")
        preflight.failure_class = FAILURE_CREDENTIAL_SOURCE_WRONG
        preflight.failure_reason = "Wrong credential source: ARC runner ServiceAccount used instead of protected kubeconfig"
        preflight.save()
        diagnosis.text("**FAIL**: Wrong credential source detected")
        diagnosis.text(f"Active identity: {diagnosis.inline_code(whoami_output)}")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Problem')}: The workflow is using the ARC runner's ServiceAccount credentials")
        diagnosis.text("instead of the protected environment kubeconfig.")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Root cause')}: The protected kubeconfig secret was not properly loaded,")
        diagnosis.text("or the workflow fell back to ambient in-cluster credentials.")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Required action')}: Verify the workflow is running in the protected")
        diagnosis.text("environment 'k9b-live-lab-admin' and that the KUBECONFIG_B64 secret")
        diagnosis.text("is correctly set in that environment.")
        diagnosis.save()
        return 1

    log(f"Active identity: {whoami_output}")
    return 0


def run_preflight_checks(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> None:
    """Run preflight checks for cluster reachability and permissions."""
    if not namespace:
        return

    log(f"Running preflight checks for namespace: {namespace}")
    diagnosis.heading(2, "Kubernetes Preflight Checks")

    # Current context
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "config", "current-context"],
        capture_output=True,
        text=True,
    )
    ctx = result.stdout.strip() or "unknown"
    preflight.current_context = ctx
    diagnosis.text(f"**Current context**: {diagnosis.inline_code(ctx)}")

    # API reachability
    diagnosis.text("**API reachability**: checking...")
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "cluster-info"],
        capture_output=True,
        text=True,
    )
    preflight.api_reachable = result.returncode == 0
    if result.returncode == 0:
        diagnosis.code(result.stdout, "")
    else:
        diagnosis.code(result.stderr or "cluster-info failed", "")

    # Namespace check
    diagnosis.text(f"**Namespace {diagnosis.inline_code(namespace)}**: checking...")
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "namespace", namespace, "-o", "jsonpath={.status.phase}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        preflight.namespace_exists = True
        preflight.namespace_status = result.stdout.strip()
        diagnosis.text(f"Status: {diagnosis.inline_code(preflight.namespace_status)}")
    else:
        preflight.namespace_exists = False
        preflight.namespace_status = "not_found"
        diagnosis.text(f"Not found or not accessible: {result.stderr}")

    # RBAC can-i checks
    diagnosis.text("**RBAC permissions for Helm deployment**: running can-i checks...")
    rbac_lines = []
    rbac_lines.append("=== RBAC can-i checks ===")
    rbac_lines.append(f"Timestamp: {datetime.now(UTC).isoformat()}")
    rbac_lines.append("")

    can_i_checks = [
        ("get", "pods", namespace),
        ("create", "pods", namespace),
        ("delete", "pods", namespace),
        ("get", "services", namespace),
        ("create", "services", namespace),
        ("get", "configmaps", namespace),
        ("create", "configmaps", namespace),
        ("get", "secrets", namespace),
        ("create", "secrets", namespace),
        ("get", "deployments.apps", namespace),
        ("create", "deployments.apps", namespace),
        ("get", "statefulsets.apps", namespace),
        ("create", "statefulsets.apps", namespace),
        ("get", "jobs.batch", namespace),
        ("create", "jobs.batch", namespace),
        ("get", "persistentvolumeclaims", namespace),
        ("create", "persistentvolumeclaims", namespace),
        ("get", "rolebindings.rbac.authorization.k8s.io", namespace),
        ("create", "rolebindings.rbac.authorization.k8s.io", namespace),
        ("get", "roles.rbac.authorization.k8s.io", namespace),
        ("create", "roles.rbac.authorization.k8s.io", namespace),
        ("get", "clusters.postgresql.cnpg.io", namespace),
        ("create", "clusters.postgresql.cnpg.io", namespace),
        ("get", "events", namespace),
        ("get", "pods/log", namespace),
    ]

    failed_count = 0
    for verb, resource, ns in can_i_checks:
        resource_ref = f"{resource} -n {ns}" if ns else resource
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "auth", "can-i", verb, resource, "-n", ns, "--quiet"],
            capture_output=True,
            text=True,
        )
        # With --quiet, kubectl communicates success/failure via exit code only
        # stdout is empty on success, so we use returncode only
        if result.returncode == 0:
            rbac_lines.append(f"[YES] {verb} {resource_ref}")
        else:
            rbac_lines.append(f"[NO]  {verb} {resource_ref}")
            failed_count += 1

    rbac_lines.append("")
    if failed_count > 0:
        rbac_lines.append(f"FAILED: {failed_count} permission(s) missing")
    else:
        rbac_lines.append("PASSED: All can-i checks succeeded")

    # Write RBAC results
    (artifact_dir / "rbac-can-i.txt").write_text("\n".join(rbac_lines) + "\n")
    diagnosis.text("RBAC checks written to rbac-can-i.txt")
    preflight.rbac_checks_complete = True


def classify_helm_error(
    helm_output: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> str:
    """Classify Helm error and return failure class.

    The failure_class is preserved even if this is called after bootstrap failures.
    """
    diagnosis.heading(2, "Helm Error Classification")

    failure_class = FAILURE_HELM_UNKNOWN
    helm_lower = helm_output.lower()

    # RBAC denied - highest priority (use regex for proper pattern matching)
    # Must have both forbidden/cannot AND rbac-related keywords
    has_rbac_error = any(re.search(p, helm_lower) for p in [r"forbidden", r"is forbidden", r"cannot get resource"])
    has_rbac_keyword = any(re.search(p, helm_lower) for p in [r"roles?", r"rolebindings?", r"rbac"])
    if has_rbac_error and has_rbac_keyword:
        failure_class = FAILURE_HELM_RBAC_DENIED
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm command failed due to missing RBAC permissions for")
        diagnosis.text("Role/RoleBinding resources.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Ensure the kubeconfig has permissions for")
        diagnosis.text("roles.rbac.authorization.k8s.io and rolebindings.rbac.authorization.k8s.io.")

    # Image pull errors
    elif any(pattern in helm_lower for pattern in [
        "imagepullbackoff",
        "errimagepull",
        "failed to pull image",
        "image.*not found",
    ]):
        failure_class = FAILURE_IMAGE_PULL_FAILED
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Container image could not be pulled.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Verify the image repository is accessible and image exists.")

    # CNPG CRD missing
    elif any(pattern in helm_lower for pattern in [
        "no matches for kind.*cluster",
        "customresourcedefinition.*not found",
        "clusters.postgresql.cnpg.io",
    ]):
        failure_class = FAILURE_CNPG_CRD_MISSING
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: CNPG CRD (clusters.postgresql.cnpg.io) is not installed.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Install CloudNativePG operator before running the lab.")

    # Storage/capacity issues
    elif any(pattern in helm_lower for pattern in [
        "persistentvolumeclaim.*pending",
        "waiting for a volume",
        "no storage class",
        "cannot find storageclass",
    ]):
        failure_class = FAILURE_STORAGE_OR_CAPACITY
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: PVC is stuck in Pending state.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Verify StorageClass is available and has sufficient capacity.")

    # Timeout/workload not ready
    elif any(pattern in helm_lower for pattern in [
        "timeout",
        "timed out",
        "deadline exceeded",
        "has no deployed releases",
    ]):
        failure_class = FAILURE_WORKLOAD_NOT_READY
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm deployment timed out waiting for resources to become ready.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Check pod status and resource constraints.")

    else:
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Unknown Helm error.")

    # Preserve the specific failure_class - don't overwrite bootstrap failures
    if preflight.failure_class is None:
        preflight.failure_class = failure_class
        preflight.failure_stage = "helm_deploy"
    # If we already have a failure_class from bootstrap, don't overwrite it
    # The specific class takes precedence

    preflight.save()
    diagnosis.save()
    return failure_class


def collect_failure_artifacts(
    kubeconfig: str | None,
    namespace: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
    image_tag: str = "unknown",
) -> None:
    """Collect failure artifacts."""
    log("Collecting failure artifacts...")
    diagnosis.heading(2, "Failure Artifacts")

    if not namespace or not kubeconfig:
        diagnosis.text("No namespace or kubeconfig provided for artifact collection")
        diagnosis.save()
        return

    # Collect kubectl artifacts
    kubectl_artifacts = [
        ("namespace-events.txt", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]),
        ("pods.txt", ["get", "pods", "-n", namespace, "-o", "wide"]),
        ("services.txt", ["get", "svc", "-n", namespace]),
        ("pvc.txt", ["get", "pvc", "-n", namespace]),
    ]

    for filename, cmd in kubectl_artifacts:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig] + cmd,
            capture_output=True,
            text=True,
        )
        (artifact_dir / filename).write_text(result.stdout or result.stderr or "(empty)")
        diagnosis.bullet(f"{diagnosis.inline_code(filename)}")

    # CNPG CRDs
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "crd", "clusters.postgresql.cnpg.io"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "clusters", "-n", namespace, "-o", "yaml"],
            capture_output=True,
            text=True,
        )
        (artifact_dir / "cnpg.txt").write_text(result.stdout or result.stderr or "(empty)")
        diagnosis.bullet(f"{diagnosis.inline_code('cnpg.txt')}")

    # Generate summary.json with proper JSON
    summary = {
        "failure_class": preflight.failure_class or "unknown",
        "failure_stage": preflight.failure_stage or "unknown",
        "active_identity": preflight.active_identity or "unknown",
        "namespace": namespace,
        "release": "k9b",
        "image_tag": image_tag,
        "next_suggested_action": "Review lab-diagnosis.md for root cause and required fix",
    }
    write_json_atomically(artifact_dir / "summary.json", summary)
    diagnosis.bullet(f"{diagnosis.inline_code('summary.json')}")

    # Next steps
    diagnosis.heading(2, "Next Steps")
    diagnosis.text("1. Review the diagnosis file for root cause analysis")
    diagnosis.text("2. Check the summary file for failure classification")
    diagnosis.text("3. Address the identified issue and re-run the workflow")
    diagnosis.save()


# =============================================================================
# Main entry points
# =============================================================================

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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "classify-error":
        sys.exit(main_classify_error())
    else:
        env_secret = sys.argv[1] if len(sys.argv) > 1 else "K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64"
        out_var = sys.argv[2] if len(sys.argv) > 2 else "KUBECONFIG"
        namespace = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("LAB_NAMESPACE", "")
        sys.exit(main_bootstrap(env_secret, out_var, namespace))
