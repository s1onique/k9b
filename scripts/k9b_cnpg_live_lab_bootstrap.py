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
    python k9b_cnpg_live_lab_bootstrap.py classify-schema --input <path>
    python k9b_cnpg_live_lab_bootstrap.py classify-wait-timeout --helm-log <path> --namespace <name> [--kubeconfig <path>]

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
FAILURE_HELM_MANIFEST_SCHEMA_WARNING = "helm_manifest_schema_warning"
FAILURE_HELM_MANIFEST_SERVER_DRY_RUN_FAILED = "helm_manifest_server_dry_run_failed"
FAILURE_IMAGE_PULL_FAILED = "image_pull_failed"
FAILURE_CNPG_CRD_MISSING = "cnpg_crd_missing"
FAILURE_STORAGE_OR_CAPACITY = "storageclass_or_capacity_issue"
FAILURE_WORKLOAD_NOT_READY = "workload_not_ready"
FAILURE_DEPLOYMENT_NOT_AVAILABLE = "deployment_not_available"
FAILURE_POD_CRASH_LOOP = "pod_crash_loop"
FAILURE_PROBE_FAILED = "probe_failed"
FAILURE_PVC_PENDING = "pvc_pending"
FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN = "helm_wait_timeout_unknown"
FAILURE_HELM_UNKNOWN = "helm_unknown_error"

# Rollout failure classes (proactive monitor)
FAILURE_IMAGE_PULL_BACKOFF = "image_pull_backoff"
FAILURE_CRASH_LOOP = "crash_loop"
FAILURE_FAILED_SCHEDULING = "failed_scheduling"
FAILURE_PVC_PENDING = "pvc_pending"
FAILURE_READINESS_PROBE_FAILED = "readiness_probe_failed"
FAILURE_DEPLOYMENT_REPLICA_FAILURE = "deployment_replica_failure"
FAILURE_DEPLOYMENT_PROGRESS_DEADLINE = "deployment_progress_deadline"
FAILURE_ROLLOUT_TIMEOUT = "rollout_timeout"
FAILURE_SNAPSHOT_COLLECTION_FAILED = "rollout_snapshot_collection_failed"


# =============================================================================
# Helpers
# =============================================================================

def _is_transient_volume_binding_conflict(reason: str, message: str) -> bool:
    """Detect transient VolumeBinding PreBind conflict that should be retried.

    This catches the scheduler PreBind race condition where the PVC object changes
    while the scheduler tries to bind or reserve volume state. Kubernetes should
    retry this automatically, so we treat it as nonfatal.

    Args:
        reason: Event reason (e.g., "FailedScheduling")
        message: Event message containing the error details

    Returns:
        True if this is a transient VolumeBinding PreBind conflict, False otherwise
    """
    msg = message.lower()
    return (
        reason == "FailedScheduling"
        and "prebind plugin" in msg
        and "volumebinding" in msg
        and "object has been modified" in msg
        and "please apply your changes" in msg
    )


def _detect_transient_volume_binding_conflict_from_events(events_json: str) -> tuple[bool, str, str]:
    """Scan events JSON for transient VolumeBinding PreBind conflict.

    Returns: (has_transient, message, pod_name)
    """
    if not events_json:
        return False, "", ""
    try:
        data = json.loads(events_json)
        for event in data.get("items", []):
            if event.get("reason") == "FailedScheduling":
                msg = event.get("message", "") or ""
                if _is_transient_volume_binding_conflict("FailedScheduling", msg):
                    involved = event.get("involvedObject", {})
                    obj_name = involved.get("name", "unknown")
                    return True, msg, obj_name
    except (json.JSONDecodeError, TypeError):
        pass
    return False, "", ""

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
# Schema Evidence Extraction
# =============================================================================

# Schema validation patterns for precise detection (not generic "error")
SCHEMA_VALIDATION_PATTERNS = [
    r"unknown field",
    r"strict decoding error",
    r"ValidationError\b",
    r"error validating data",
    r"field not declared in schema",
]

# Valid resource name pattern (must start with alphanumeric, can contain dash/underscore)
VALID_RESOURCE_NAME_PATTERN = r'[a-zA-Z0-9][-a-zA-Z0-9_]*'


def _parse_rendered_yaml_for_resource(
    rendered_content: str,
    field_path: str,
) -> tuple[str, str, str]:
    """Parse rendered YAML to find the resource containing a field path.

    Args:
        rendered_content: The rendered YAML content
        field_path: The field path to search for (e.g., "spec.template.spec.containers[0].allowPrivilegeEscalation")

    Returns:
        Tuple of (kind, name, namespace) for the resource containing the field
    """
    # Split into YAML documents
    documents = rendered_content.split("---")

    for doc in documents:
        lines = doc.strip().split("\n")
        if not lines:
            continue

        # Find kind and name in this document
        kind = ""
        name = ""
        namespace = ""

        for line in lines:
            kind_match = re.match(r'\s*kind:\s*(\w+)', line)
            if kind_match:
                kind = kind_match.group(1)
            name_match = re.match(r'\s*name:\s*([a-zA-Z0-9][-a-zA-Z0-9_]*)', line)
            if name_match:
                name = name_match.group(1)
            namespace_match = re.match(r'\s*namespace:\s*([a-zA-Z0-9][-a-zA-Z0-9_]*)', line)
            if namespace_match:
                namespace = namespace_match.group(1)

        # Check if this document contains the field path
        # For container fields, check if the container name matches
        if kind and name:
            doc_content = doc.lower()
            # Check for indicators that this document has the problematic field
            if "containers" in field_path.lower():
                # For container-level fields, check if document has containers section
                if "containers" in doc_content:
                    return kind, name, namespace
            else:
                # For non-container fields, any matching document works
                return kind, name, namespace

    return "", "", ""


def extract_schema_warnings(
    log_content: str,
    rendered_content: str = "",
) -> list[dict]:
    """Extract bounded schema warnings from log content.

    Parses log output for schema validation errors and extracts:
    - line number
    - message text
    - unknown field path if present
    - resource kind/name if inferable from rendered YAML
    - source file/log name

    Args:
        log_content: Content of the helm dry-run or template log
        rendered_content: Optional rendered YAML content for accurate resource mapping

    Returns:
        List of warning dictionaries with bounded evidence
    """
    warnings: list[dict] = []
    lines = log_content.split("\n")

    for i, line in enumerate(lines, start=1):
        line_lower = line.lower()

        # Check if line matches any schema validation pattern
        matched_pattern = None
        for pattern in SCHEMA_VALIDATION_PATTERNS:
            # Use IGNORECASE to handle case-insensitive matching
            if re.search(pattern, line_lower, re.IGNORECASE):
                matched_pattern = pattern
                break

        if matched_pattern is None:
            continue

        # Extract field path from "unknown field" messages
        field_path = ""
        field_match = re.search(r'unknown field "([^"]+)"', line)
        if field_match:
            field_path = field_match.group(1)

        # Extract resource kind and name
        kind = ""
        name = ""

        # Priority 1: Use rendered YAML to find the actual resource
        if rendered_content and field_path:
            kind, name, _ = _parse_rendered_yaml_for_resource(rendered_content, field_path)

        # Priority 2: Try to extract from error message format: "error from <kind>/<name>"
        # Only accept if the name matches valid resource name pattern (not "in", "version", etc.)
        if not kind or not name:
            resource_match = re.search(
                rf'(Deployment|StatefulSet|DaemonSet|Job|CronJob|Service|ConfigMap|Secret)/({VALID_RESOURCE_NAME_PATTERN})',
                line
            )
            if resource_match:
                kind = resource_match.group(1)
                name = resource_match.group(2)
                # Additional validation: name must not be a common word
                if name.lower() in ("in", "version", "the", "a", "an", "for", "with"):
                    name = ""  # Reject bogus names

        warning: dict[str, str | int] = {
            "line": i,
            "message": line.strip(),
            "pattern_matched": matched_pattern,
        }

        if field_path:
            warning["field"] = field_path
        if kind:
            warning["kind"] = kind
        if name:
            warning["name"] = name

        warnings.append(warning)

    return warnings


def write_schema_warnings_json(
    artifact_dir: Path,
    warnings: list[dict],
    source_log: str,
    failure_class: str,
) -> Path:
    """Write schema warnings to JSON file atomically.

    Args:
        artifact_dir: Directory to write the JSON file
        warnings: List of warning dictionaries
        source_log: Name of the source log file
        failure_class: The failure class being reported

    Returns:
        Path to the written JSON file
    """
    data = {
        "failure_class": failure_class,
        "source_log": source_log,
        "match_count": len(warnings),
        "matches": warnings,
    }

    output_path = artifact_dir / "logs" / "schema-warnings.json"
    write_json_atomically(output_path, data)
    return output_path


def generate_bounded_summary(warnings: list[dict], max_lines: int = 20) -> str:
    """Generate bounded sanitized summary of schema warnings.

    Args:
        warnings: List of warning dictionaries
        max_lines: Maximum number of warnings to include

    Returns:
        Sanitized summary string suitable for GitHub Actions output
    """
    if not warnings:
        return "No schema warnings detected."

    lines = ["Schema validation failed before Helm install.", ""]
    lines.append(f"Failure class: {FAILURE_HELM_MANIFEST_SCHEMA_WARNING}")
    lines.append("")
    lines.append("Matched warnings:")

    # Bounded output - limit to max_lines
    for warning in warnings[:max_lines]:
        parts = []
        if "field" in warning:
            parts.append(f'unknown field "{warning["field"]}"')
        elif "message" in warning:
            # Truncate long messages
            msg = warning["message"]
            if len(msg) > 120:
                msg = msg[:117] + "..."
            parts.append(msg)

        if "kind" in warning and "name" in warning:
            parts.append(f"({warning['kind']}/{warning['name']})")

        if parts:
            lines.append(f"- {' '.join(parts)}")

    # Indicate truncation if needed
    if len(warnings) > max_lines:
        lines.append(f"... and {len(warnings) - max_lines} more warnings")

    lines.append("")
    lines.append("Evidence:")
    lines.append("- logs/helm-server-dry-run.log")
    lines.append("- logs/helm-rendered.yaml")
    lines.append("- logs/schema-warnings.json")

    return "\n".join(lines)


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


def classify_schema_error(
    output: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> str:
    """Classify Kubernetes schema/dry-run error and return failure class.

    Used for both helm template and kubectl apply --dry-run=server failures.
    """
    diagnosis.heading(2, "Helm Manifest Schema Classification")

    failure_class = FAILURE_HELM_UNKNOWN
    output_lower = output.lower()

    # Schema warning - "unknown field" pattern
    unknown_field_patterns = [
        r"unknown field",
        r"spec\.template\.spec\.containers\[0\]\.(allowPrivilegeEscalation|capabilities|limits|requests|readOnlyRootFilesystem)",
    ]
    has_unknown_field = any(re.search(p, output_lower) for p in unknown_field_patterns)
    if has_unknown_field:
        failure_class = FAILURE_HELM_MANIFEST_SCHEMA_WARNING
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm chart renders container security/resource fields")
        diagnosis.text("at the wrong level (directly under containers[0]) instead of nested under")
        diagnosis.text("securityContext or resources.")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Common mistakes')}:")
        diagnosis.text("- `allowPrivilegeEscalation: false` should be `securityContext.allowPrivilegeEscalation: false`")
        diagnosis.text("- `capabilities:` should be `securityContext.capabilities:`")
        diagnosis.text("- `limits:`/`requests:` should be `resources.limits:`/`resources.requests:`")
        diagnosis.text("- `readOnlyRootFilesystem: true` should be `securityContext.readOnlyRootFilesystem: true`")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Evidence file')}: helm-rendered.yaml")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Fix chart templates to nest securityContext/resources fields.")

    # Server dry-run validation failed
    elif any(pattern in output_lower for pattern in [
        "error: error validating",
        "error validating data",
        "dry-run failed",
        "validation failed",
    ]):
        failure_class = FAILURE_HELM_MANIFEST_SERVER_DRY_RUN_FAILED
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Server-side dry-run validation failed for rendered manifests.")
        diagnosis.text(f"{diagnosis.bold('Evidence file')}: helm-server-dry-run.log")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Review rendered manifests and fix schema issues.")

    else:
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Unknown manifest validation error.")

    # Set failure class
    if preflight.failure_class is None:
        preflight.failure_class = failure_class
        preflight.failure_stage = "helm_deploy"

    preflight.save()
    diagnosis.save()
    return failure_class


def classify_wait_timeout(
    helm_output: str,
    kubeconfig: str | None,
    namespace: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> str:
    """Classify Helm wait timeout using JSON-based parser helpers.

    Delegates to the parser helpers from main_classify_wait_timeout() for
    accurate crash loop, probe failure, and deployment-not-ready detection.
    """
    diagnosis.heading(2, "Helm Wait Timeout Classification")

    failure_class = FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN

    if kubeconfig and namespace:
        # Collect kubectl artifacts
        kubectl_artifacts = [
            ("watchdog/pods.txt", ["get", "pods", "-n", namespace, "-o", "wide"]),
            ("watchdog/deployments.txt", ["get", "deployments", "-n", namespace, "-o", "wide"]),
            ("watchdog/events.txt", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]),
        ]

        for filename, cmd in kubectl_artifacts:
            result = subprocess.run(
                ["kubectl", "--kubeconfig", kubeconfig] + cmd,
                capture_output=True,
                text=True,
            )
            (artifact_dir / filename).write_text(result.stdout or "(empty)")

        # Get JSON for proper parsing
        pods_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "pods", "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
        )
        deployments_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "deployments", "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
        )
        events_result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "events", "-n", namespace, "--sort-by=.lastTimestamp"],
            capture_output=True,
            text=True,
        )

        pods_json = pods_result.stdout
        deployments_json = deployments_result.stdout
        events_text = events_result.stdout
        helm_lower = helm_output.lower()

        # Use JSON-based parsers for accurate detection (no false positives)
        if _parse_crash_loop_from_pods(pods_json):
            failure_class = FAILURE_POD_CRASH_LOOP
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Pod is in CrashLoopBackOff state.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/pods.txt")

        elif _parse_image_pull_failure_from_pods(pods_json):
            failure_class = FAILURE_IMAGE_PULL_FAILED
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Container image could not be pulled.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/pods.txt")

        elif _parse_probe_failure_from_pods(pods_json):
            failure_class = FAILURE_PROBE_FAILED
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Container probe failed (exit code != 0).")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/pods.txt")

        elif _parse_deployment_not_ready_from_deployments(deployments_json):
            failure_class = FAILURE_DEPLOYMENT_NOT_AVAILABLE
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Deployment has no available replicas.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/deployments.txt")

        elif _parse_pvc_pending_from_pods(pods_json, events_text):
            failure_class = FAILURE_PVC_PENDING
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: PVC is stuck in Pending state.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/pods.txt, watchdog/events.txt")

        elif "unknown field" in helm_lower:
            failure_class = FAILURE_HELM_MANIFEST_SCHEMA_WARNING
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Helm chart has schema drift (unknown field warnings).")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: logs/helm-install.log")

        else:
            diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
            diagnosis.text(f"{diagnosis.bold('Cause')}: Helm wait timed out but specific cause unknown.")
            diagnosis.text(f"{diagnosis.bold('Evidence')}: watchdog/ directory")

    else:
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm wait timed out without cluster state data.")
        diagnosis.text(f"{diagnosis.bold('Evidence')}: logs/helm-install.log")

    diagnosis.text("")
    diagnosis.text(f"{diagnosis.bold('Suggested action')}: Review watchdog/ artifacts and helm-install.log")
    diagnosis.text("to determine the root cause of the timeout.")

    # Set failure class
    if preflight.failure_class is None:
        preflight.failure_class = failure_class
        preflight.failure_stage = "helm_deploy"

    preflight.save()
    diagnosis.save()
    return failure_class


def classify_helm_error(
    helm_output: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
    kubeconfig: str | None = None,
    namespace: str = "",
) -> str:
    """Classify Helm error and return failure class.

    The failure_class is preserved even if this is called after bootstrap failures.
    """
    diagnosis.heading(2, "Helm Error Classification")

    failure_class = FAILURE_HELM_UNKNOWN
    helm_lower = helm_output.lower()

    # Schema warning - "unknown field" pattern (highest priority for manifest issues)
    unknown_field_patterns = [
        r"unknown field",
        r"spec\.template\.spec\.containers\[0\]\.(allowPrivilegeEscalation|capabilities|limits|requests|readOnlyRootFilesystem)",
    ]
    has_unknown_field = any(re.search(p, helm_lower) for p in unknown_field_patterns)
    if has_unknown_field:
        failure_class = FAILURE_HELM_MANIFEST_SCHEMA_WARNING
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm chart renders container security/resource fields")
        diagnosis.text("at the wrong level (directly under containers[0]) instead of nested under")
        diagnosis.text("securityContext or resources.")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Common mistakes')}:")
        diagnosis.text("- `allowPrivilegeEscalation: false` should be `securityContext.allowPrivilegeEscalation: false`")
        diagnosis.text("- `capabilities:` should be `securityContext.capabilities:`")
        diagnosis.text("- `limits:`/`requests:` should be `resources.limits:`/`resources.requests:`")
        diagnosis.text("- `readOnlyRootFilesystem: true` should be `securityContext.readOnlyRootFilesystem: true`")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Evidence file')}: helm-rendered.yaml")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Fix chart templates to nest securityContext/resources fields.")

    # RBAC denied - highest priority (use regex for proper pattern matching)
    # Must have both forbidden/cannot AND rbac-related keywords
    elif any(re.search(p, helm_lower) for p in [r"forbidden", r"is forbidden", r"cannot get resource"]) and \
         any(re.search(p, helm_lower) for p in [r"roles?", r"rolebindings?", r"rbac"]):
        failure_class = FAILURE_HELM_RBAC_DENIED
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Helm command failed due to missing RBAC permissions for")
        diagnosis.text("Role/RoleBinding resources.")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Ensure the kubeconfig has permissions for")
        diagnosis.text("roles.rbac.authorization.k8s.io and rolebindings.rbac.authorization.k8s.io.")

    # Server dry-run validation failed
    elif any(pattern in helm_lower for pattern in [
        "error: error validating",
        "error validating data",
        "dry-run failed",
        "validation failed",
    ]):
        failure_class = FAILURE_HELM_MANIFEST_SERVER_DRY_RUN_FAILED
        diagnosis.text(f"{diagnosis.bold('Classification')}: {diagnosis.inline_code(failure_class)}")
        diagnosis.text(f"{diagnosis.bold('Cause')}: Server-side dry-run validation failed for rendered manifests.")
        diagnosis.text(f"{diagnosis.bold('Evidence file')}: helm-server-dry-run.log")
        diagnosis.text(f"{diagnosis.bold('Suggested action')}: Review rendered manifests and fix schema issues.")

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


def main_classify_schema() -> int:
    """Classify manifest schema error from file.

    Usage: classify-schema --input <path> [--rendered <path>]
    """
    import argparse

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
    """Extract schema warnings evidence from log file.

    Usage: extract-schema-evidence --input <path> [--rendered <path>] --output <path>
    """
    import argparse

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


def _parse_crash_loop_from_pods(pods_json_str: str) -> bool:
    """Parse pod JSON and detect actual CrashLoopBackOff state.

    Returns True only if we find containerStatuses with waiting.reason == CrashLoopBackOff.
    """
    try:
        pods_data = json.loads(pods_json_str)
        if not isinstance(pods_data, dict):
            return False

        items = pods_data.get("items", [])
        for pod in items:
            # Check containerStatuses for CrashLoopBackOff
            container_statuses = pod.get("status", {}).get("containerStatuses", [])
            for cs in container_statuses:
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                reason = waiting.get("reason", "")
                if reason == "CrashLoopBackOff":
                    return True

            # Also check initContainerStatuses
            init_container_statuses = pod.get("status", {}).get("initContainerStatuses", [])
            for cs in init_container_statuses:
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                reason = waiting.get("reason", "")
                if reason == "CrashLoopBackOff":
                    return True

        return False
    except (json.JSONDecodeError, TypeError):
        return False


def _parse_image_pull_failure_from_pods(pods_json_str: str) -> bool:
    """Parse pod JSON and detect image pull failures.

    Returns True if we find containerStatuses with waiting.reason in
    (ImagePullBackOff, ErrImagePull).
    """
    try:
        pods_data = json.loads(pods_json_str)
        if not isinstance(pods_data, dict):
            return False

        items = pods_data.get("items", [])
        for pod in items:
            container_statuses = pod.get("status", {}).get("containerStatuses", [])
            for cs in container_statuses:
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                reason = waiting.get("reason", "")
                if reason in ("ImagePullBackOff", "ErrImagePull"):
                    return True

            init_container_statuses = pod.get("status", {}).get("initContainerStatuses", [])
            for cs in init_container_statuses:
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                reason = waiting.get("reason", "")
                if reason in ("ImagePullBackOff", "ErrImagePull"):
                    return True

        return False
    except (json.JSONDecodeError, TypeError):
        return False


def _parse_probe_failure_from_pods(pods_json_str: str) -> bool:
    """Parse pod JSON and detect readiness/liveness probe failures.

    Returns True if containers have lastState.terminated with exit code != 0
    due to health check failures.
    """
    try:
        pods_data = json.loads(pods_json_str)
        if not isinstance(pods_data, dict):
            return False

        items = pods_data.get("items", [])
        for pod in items:
            container_statuses = pod.get("status", {}).get("containerStatuses", [])
            for cs in container_statuses:
                last_state = cs.get("lastState", {})
                terminated = last_state.get("terminated", {})
                exit_code = terminated.get("exitCode", 0)
                reason = terminated.get("reason", "")
                # Health check failures often show as exit code 1 or specific reasons
                if exit_code != 0 and reason in ("Error", "Completed", ""):
                    return True

        return False
    except (json.JSONDecodeError, TypeError):
        return False


def _parse_deployment_not_ready_from_deployments(deployments_json_str: str) -> bool:
    """Parse deployment JSON and detect unavailable replicas.

    Returns True if any deployment has availableReplicas < replicas.
    """
    try:
        data = json.loads(deployments_json_str)
        if not isinstance(data, dict):
            return False

        items = data.get("items", [])
        for deploy in items:
            status = deploy.get("status", {})
            replicas = status.get("replicas", 0)
            available = status.get("availableReplicas", 0)
            if replicas > 0 and available == 0:
                return True

        return False
    except (json.JSONDecodeError, TypeError):
        return False


def _parse_pvc_pending_from_pods(pods_json_str: str, events_str: str) -> bool:
    """Parse pod and event JSON to detect PVC pending state.

    Returns True if pods have PVC volumes stuck in pending state.
    """
    try:
        pods_data = json.loads(pods_json_str)
        if not isinstance(pods_data, dict):
            return False

        items = pods_data.get("items", [])
        for pod in items:
            # Check if pod is in Pending state
            phase = pod.get("status", {}).get("phase", "")
            if phase == "Pending":
                # Check conditions for pending reason
                conditions = pod.get("status", {}).get("conditions", [])
                for cond in conditions:
                    reason = cond.get("reason", "")
                    if "pvc" in reason.lower() or "volume" in reason.lower():
                        return True

        # Also check events for PVC-related pending messages
        events_lower = events_str.lower()
        if ("pending" in events_lower and "pvc" in events_lower) or \
           ("waiting" in events_lower and "volume" in events_lower):
            return True

        return False
    except (json.JSONDecodeError, TypeError):
        return False


def main_classify_wait_timeout() -> int:
    """Classify Helm wait timeout using watchdog artifacts.

    Usage: classify-wait-timeout --helm-log <path> --namespace <name> [--kubeconfig <path>]
    """
    import argparse

    parser = argparse.ArgumentParser(description="Classify Helm wait timeout")
    parser.add_argument("--helm-log", required=True, help="Path to Helm install log")
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
            (artifact_dir / filename).write_text(result.stdout or "(empty)")

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
        if _parse_crash_loop_from_pods(pods_json):
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

    preflight.save()
    diagnosis.save()
    print(failure_class)
    return 0


# =============================================================================
# Proactive Rollout Monitor
# =============================================================================

from dataclasses import dataclass, field


@dataclass
class RolloutDiagnosis:
    """Structured diagnosis result from rollout monitor."""
    
    # Classification
    failure_class: str = ""
    fatal: bool = False
    
    # Affected resources
    affected_pods: list[str] = field(default_factory=list)
    affected_deployments: list[str] = field(default_factory=list)
    affected_pvcs: list[str] = field(default_factory=list)
    
    # Pod details
    pod_phase: str = ""
    container_waiting_reason: str = ""
    container_name: str = ""
    
    # Event details
    latest_event_reason: str = ""
    latest_event_message: str = ""
    
    # Snapshot path
    snapshot_path: str = ""
    
    # All diagnostics for JSON artifact
    diagnostics: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "failure_class": self.failure_class,
            "fatal": self.fatal,
            "affected_pods": self.affected_pods,
            "affected_deployments": self.affected_deployments,
            "affected_pvcs": self.affected_pvcs,
            "pod_phase": self.pod_phase,
            "container_waiting_reason": self.container_waiting_reason,
            "container_name": self.container_name,
            "latest_event_reason": self.latest_event_reason,
            "latest_event_message": self.latest_event_message,
            "snapshot_path": self.snapshot_path,
            "diagnostics": self.diagnostics,
        }


@dataclass
class KubectlResult:
    """Result from kubectl collection with success tracking."""
    
    json_data: str
    text_data: str = ""
    success: bool = False
    error_message: str = ""


def _get_kubectl_json(kubeconfig: str, namespace: str, resource: str) -> KubectlResult:
    """Execute kubectl get command and return structured result with success tracking."""
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", resource, "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return KubectlResult(json_data=result.stdout, text_data=result.stdout, success=True)
    else:
        return KubectlResult(
            json_data="{}",
            text_data=result.stderr or f"kubectl failed with exit code {result.returncode}",
            success=False,
            error_message=result.stderr.strip() or f"Exit code: {result.returncode}"
        )


def _get_kubectl_events(kubeconfig: str, namespace: str) -> KubectlResult:
    """Execute kubectl get events command and return structured result."""
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "events", "-n", namespace, "-o", "json", "--sort-by=.lastTimestamp"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return KubectlResult(json_data=result.stdout, text_data=result.stdout, success=True)
    else:
        return KubectlResult(
            json_data='{"items": []}',
            text_data=result.stderr or f"kubectl failed with exit code {result.returncode}",
            success=False,
            error_message=result.stderr.strip() or f"Exit code: {result.returncode}"
        )


def _get_kubectl_text(kubeconfig: str, namespace: str, resource: str) -> KubectlResult:
    """Execute kubectl get command and return text output with success tracking."""
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", resource, "-n", namespace, "--sort-by=.lastTimestamp"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return KubectlResult(json_data="{}", text_data=result.stdout, success=True)
    else:
        return KubectlResult(
            json_data="{}",
            text_data=result.stderr or f"kubectl failed with exit code {result.returncode}",
            success=False,
            error_message=result.stderr.strip() or f"Exit code: {result.returncode}"
        )


def _get_deployment_conditions(deployments_json: str) -> list[dict]:
    """Parse deployment conditions from JSON."""
    try:
        data = json.loads(deployments_json)
        conditions = []
        for deploy in data.get("items", []):
            for cond in deploy.get("status", {}).get("conditions", []):
                cond["deployment"] = deploy.get("metadata", {}).get("name", "unknown")
                conditions.append(cond)
        return conditions
    except (json.JSONDecodeError, TypeError):
        return []


def _get_pvc_status(pvc_json: str) -> list[dict]:
    """Parse PVC status from JSON."""
    try:
        data = json.loads(pvc_json)
        pvcs = []
        for pvc in data.get("items", []):
            status = pvc.get("status", {}).get("phase", "Unknown")
            if status != "Bound":
                pvcs.append({
                    "name": pvc.get("metadata", {}).get("name", "unknown"),
                    "namespace": pvc.get("metadata", {}).get("namespace", "unknown"),
                    "status": status,
                    "reason": pvc.get("status", {}).get("reason", ""),
                    "storage_class_name": pvc.get("spec", {}).get("storageClassName", ""),
                    "access_modes": pvc.get("spec", {}).get("accessModes", []),
                    "resources": pvc.get("spec", {}).get("resources", {}),
                })
        return pvcs
    except (json.JSONDecodeError, TypeError):
        return []


def _get_pod_waiting_info(pods_json: str) -> list[dict]:
    """Parse pod container waiting info from JSON."""
    try:
        data = json.loads(pods_json)
        waiting_info = []
        for pod in data.get("items", []):
            pod_name = pod.get("metadata", {}).get("name", "unknown")
            phase = pod.get("status", {}).get("phase", "Unknown")
            
            for cs in pod.get("status", {}).get("containerStatuses", []):
                container_name = cs.get("name", "unknown")
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                if waiting:
                    waiting_info.append({
                        "pod": pod_name,
                        "container": container_name,
                        "phase": phase,
                        "reason": waiting.get("reason", ""),
                        "message": waiting.get("message", ""),
                    })
            
            for cs in pod.get("status", {}).get("initContainerStatuses", []):
                container_name = cs.get("name", "unknown")
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                if waiting:
                    waiting_info.append({
                        "pod": pod_name,
                        "container": container_name,
                        "phase": phase,
                        "reason": waiting.get("reason", ""),
                        "message": waiting.get("message", ""),
                        "init": True,
                    })
        return waiting_info
    except (json.JSONDecodeError, TypeError):
        return []


def _check_image_pull_backoff(waiting_info: list[dict]) -> tuple[bool, str, str]:
    """Check for image pull backoff conditions.
    
    Returns: (is_fatal, reason, message)
    """
    for w in waiting_info:
        reason = w.get("reason", "")
        if reason in ("ImagePullBackOff", "ErrImagePull"):
            return True, reason, w.get("message", "")
    return False, "", ""


def _check_crash_loop(waiting_info: list[dict]) -> tuple[bool, str, str]:
    """Check for crash loop conditions.
    
    Returns: (is_fatal, reason, message)
    """
    for w in waiting_info:
        reason = w.get("reason", "")
        if reason == "CrashLoopBackOff":
            return True, reason, w.get("message", "")
    return False, "", ""


def _check_failed_scheduling_from_events(events_json: str) -> tuple[bool, str, str]:
    """Check for failed scheduling conditions using structural event JSON.
    
    Returns: (is_fatal, reason, message)
    Nonfatal transient conflicts (e.g., VolumeBinding PreBind race) return False.
    """
    try:
        data = json.loads(events_json)
        for event in data.get("items", []):
            reason = event.get("reason", "")
            
            # Primary: event.reason == "FailedScheduling"
            if reason == "FailedScheduling":
                message = event.get("message", "")
                
                # Check for transient VolumeBinding PreBind conflict
                # This is a race condition that Kubernetes should retry automatically
                if _is_transient_volume_binding_conflict(reason, message):
                    # Return nonfatal - the scheduler will retry
                    involved = event.get("involvedObject", {})
                    obj_name = involved.get("name", "unknown")
                    obj_kind = involved.get("kind", "Pod")
                    return False, "", f"{obj_kind}/{obj_name}: {message}"  # is_fatal=False
                
                involved = event.get("involvedObject", {})
                obj_name = involved.get("name", "unknown")
                obj_kind = involved.get("kind", "Pod")
                return True, reason, f"{obj_kind}/{obj_name}: {message}"
            
            # Secondary: Warning type events for scheduling
            event_type = event.get("type", "")
            if event_type == "Warning":
                # Check for scheduling-related reasons
                scheduling_reasons = [
                    "Unschedulable",
                    "SchedulingDisabled", 
                    "InsufficientCPU",
                    "InsufficientMemory",
                    "NoNodeSelector",
                    "NoVolumeZoneConflict",
                    "NodeSelectorMismatching",
                    "TaintTolerationMismatch",
                    "AffinityConflict",
                    "PVCBindingFailed",
                ]
                if reason in scheduling_reasons:
                    message = event.get("message", "")
                    involved = event.get("involvedObject", {})
                    obj_name = involved.get("name", "unknown")
                    return True, reason, f"{reason}: {message}"
    except (json.JSONDecodeError, TypeError):
        pass
    
    return False, "", ""


def _check_readiness_probe_failed_from_events(events_json: str) -> tuple[bool, str, str]:
    """Check for readiness probe failure events using structural event JSON.
    
    Returns: (is_fatal, reason, message)
    """
    try:
        data = json.loads(events_json)
        for event in data.get("items", []):
            reason = event.get("reason", "")
            event_type = event.get("type", "")
            message = event.get("message", "")
            involved = event.get("involvedObject", {})
            obj_name = involved.get("name", "unknown")
            obj_kind = involved.get("kind", "")
            
            # Primary: event.reason == "Unhealthy" with readiness message
            if reason == "Unhealthy" and event_type == "Warning":
                if "readiness" in message.lower():
                    return True, reason, f"{obj_kind}/{obj_name}: {message}"
            
            # Secondary: probe-related reasons
            probe_reasons = [
                "ProbeFailed",
                "ReadinessProbeFailed",
                "LivenessProbeFailed",
                "StartupProbeFailed",
                "ContainerProbeFailed",
            ]
            if reason in probe_reasons:
                return True, reason, f"{obj_kind}/{obj_name}: {message}"
            
            # Tertiary: BackOff events for probes
            if "BackOff" in reason and "probe" in message.lower():
                return True, reason, f"{obj_kind}/{obj_name}: {message}"
    except (json.JSONDecodeError, TypeError):
        pass
    
    return False, "", ""


def _check_failed_scheduling(pods_json: str, events_text: str, events_json: str = "") -> tuple[bool, str, str]:
    """Check for failed scheduling conditions using structural JSON with text fallback.
    
    Returns: (is_fatal, reason, message)
    """
    # Primary: Use structural JSON events when available
    if events_json:
        is_fatal, reason, message = _check_failed_scheduling_from_events(events_json)
        if is_fatal:
            return True, reason, message
    
    # Fallback: Check pods for scheduling failure conditions
    try:
        data = json.loads(pods_json)
        for pod in data.get("items", []):
            for cond in pod.get("status", {}).get("conditions", []):
                cond_type = cond.get("type", "")
                reason = cond.get("reason", "")
                message = cond.get("message", "")
                
                # PodScheduled False with scheduling failure reasons
                if cond_type == "PodScheduled" and cond.get("status") == "False":
                    failure_reasons = [
                        "Unschedulable",
                        "SchedulingDisabled",
                        "InsufficientCPU",
                        "InsufficientMemory",
                        "NoNodeSelector",
                        "NoVolumeZoneConflict",
                        "NodeSelectorMismatching",
                        "TaintTolerationMismatch",
                        "AffinityConflict",
                    ]
                    if reason in failure_reasons or "unschedulable" in reason.lower():
                        return True, reason, message
                    
                    # Generic unschedulable
                    if "cannot schedule pod" in message.lower() or "no nodes available" in message.lower():
                        return True, reason, message
    except (json.JSONDecodeError, TypeError):
        pass
    
    # Last resort: Check events text for scheduling failure (substring fallback)
    if events_text:
        events_lower = events_text.lower()
        scheduling_keywords = [
            "failed to schedule",
            "no nodes available",
            "insufficient cpu",
            "insufficient memory",
            "node(s) had taints",
            "node affinity",
            "pod affinity",
            "cannot schedule",
        ]
        for keyword in scheduling_keywords:
            if keyword in events_lower:
                return True, "FailedScheduling", keyword
    
    return False, "", ""


def _check_pvc_pending(
    pvcs: list[dict],
) -> tuple[bool, str, str, str]:
    """Check for ordinary non-bound PVCs with no hard evidence.

    This helper is called AFTER classify_rollout_state() has already ruled out:
    - Explicit provisioning failure (5a)
    - Missing StorageClass (5b)
    - WaitForFirstConsumer (5c)

    So this only answers: "is there still a pending PVC with no hard evidence?"

    Args:
        pvcs: List of PVC info dicts

    Returns:
        Tuple of (is_pending, status, reason, failure_class)
        - is_pending: True if a non-bound PVC exists
        - status: PVC status string
        - reason: Failure reason
        - failure_class: "pvc_pending" for ordinary pending
    """
    # Ordinary pending - non-fatal until deadline
    for pvc in pvcs:
        if pvc.get("status") != "Bound":
            return True, pvc.get("status", "Pending"), pvc.get("reason", "PVC not Bound"), "pvc_pending"

    return False, "", "", ""


def _get_pvc_binding_mode(storage_class_json: str, storage_class_name: str) -> str:
    """Get volumeBindingMode for a StorageClass.
    
    Note: volumeBindingMode is a top-level StorageClass field, not a parameter.
    See https://kubernetes.io/docs/concepts/storage/storage-classes/
    
    Args:
        storage_class_json: JSON output from kubectl get storageclass -o json
        storage_class_name: Name of the StorageClass to look up
    
    Returns:
        "WaitForFirstConsumer", "Immediate", or "" if not found/unknown
    """
    try:
        data = json.loads(storage_class_json)
        for sc in data.get("items", []):
            if sc.get("metadata", {}).get("name") == storage_class_name:
                # volumeBindingMode is a top-level field on StorageClass, not in parameters
                mode: str = sc.get("volumeBindingMode", "Immediate")
                return mode
        return ""
    except (json.JSONDecodeError, TypeError):
        return ""


def _get_default_storage_class(storage_class_json: str) -> str:
    """Get the name of the default StorageClass.
    
    Args:
        storage_class_json: JSON output from kubectl get storageclass -o json
    
    Returns:
        Name of default StorageClass or "" if none
    """
    try:
        data = json.loads(storage_class_json)
        for sc in data.get("items", []):
            metadata = sc.get("metadata", {})
            if not isinstance(metadata, dict):
                continue
            annotations = metadata.get("annotations", {})
            if not isinstance(annotations, dict):
                continue
            ann1: str = annotations.get("storageclass.kubernetes.io/is-default-class", "")
            ann2: str = annotations.get("storageclass.beta.kubernetes.io/is-default-class", "")
            if ann1.lower() == "true" or ann2.lower() == "true":
                sc_name: str = metadata.get("name", "")
                return sc_name
        return ""
    except (json.JSONDecodeError, TypeError):
        return ""


def _check_pvc_provisioning_failure(events_json: str) -> tuple[bool, str, str]:
    """Check for explicit provisioning failures in events.
    
    Args:
        events_json: JSON output from kubectl get events -o json
    
    Returns: (is_fatal, reason, message)
    """
    try:
        data = json.loads(events_json)
        for event in data.get("items", []):
            reason = event.get("reason", "")
            # Explicit provisioning failures
            if reason in ("ProvisioningFailed", "VolumeBindingFailed", "CreateContainerConfigError"):
                message = event.get("message", "")
                involved = event.get("involvedObject", {})
                obj_name = involved.get("name", "unknown")
                obj_kind = involved.get("kind", "PVC")
                return True, reason, f"{obj_kind}/{obj_name}: {message}"
    except (json.JSONDecodeError, TypeError):
        pass
    return False, "", ""


def _check_pvc_missing_storage_class(
    pvcs: list[dict],
    storage_class_json: str,
) -> tuple[bool, str, str]:
    """Check for PVCs referencing non-existent StorageClasses.
    
    Args:
        pvcs: List of PVC info dicts
        storage_class_json: JSON output from kubectl get storageclass -o json
    
    Returns: (is_fatal, reason, message)
    """
    try:
        data = json.loads(storage_class_json)
        existing_classes: set[str] = set()
        for sc in data.get("items", []):
            existing_classes.add(sc.get("metadata", {}).get("name", ""))
        
        default_class = _get_default_storage_class(storage_class_json)
        
        for pvc in pvcs:
            if pvc.get("status") != "Bound":
                # Note: _get_pvc_status normalizes the key to storage_class_name
                storage_class_name = str(pvc.get("storage_class_name", ""))
                if storage_class_name:
                    # Check if requested storageClass exists
                    if storage_class_name not in existing_classes:
                        return True, "StorageClassNotFound", (
                            f"PVC {pvc.get('name')} requests storageClass '{storage_class_name}' "
                            f"which does not exist"
                        )
                else:
                    # PVC has no storageClassName and no default exists
                    if not default_class:
                        return True, "NoStorageClassAvailable", (
                            f"PVC {pvc.get('name')} has no storageClassName and no default "
                            f"StorageClass is configured"
                        )
    except (json.JSONDecodeError, TypeError):
        pass
    return False, "", ""


def _check_pvc_wait_for_first_consumer(
    pvcs: list[dict],
    storage_class_json: str,
    pods_json: str,
) -> tuple[bool, str, str]:
    """Check for PVCs pending due to WaitForFirstConsumer binding mode.
    
    This is a non-fatal condition - the PVC will bind once a Pod using it
    is scheduled and its constraints are known.
    
    Args:
        pvcs: List of PVC info dicts
        storage_class_json: JSON output from kubectl get storageclass -o json
        pods_json: JSON output from kubectl get pods -o json
    
    Returns: (is_wait_for_first_consumer, reason, message)
    """
    try:
        data = json.loads(storage_class_json)
        binding_modes: dict[str, str] = {}
        for sc in data.get("items", []):
            sc_name = sc.get("metadata", {}).get("name", "")
            # volumeBindingMode is a top-level field on StorageClass, not in parameters
            mode = sc.get("volumeBindingMode", "Immediate")
            binding_modes[sc_name] = mode
        
        pods_data = json.loads(pods_json)
        pods_using_pvcs: set[str] = set()
        for pod in pods_data.get("items", []):
            for vol in pod.get("spec", {}).get("volumes", []):
                if "persistentVolumeClaim" in vol:
                    pvc_name = vol.get("persistentVolumeClaim", {}).get("claimName", "")
                    if pvc_name:
                        pods_using_pvcs.add(pvc_name)
        
        for pvc in pvcs:
            if pvc.get("status") != "Bound":
                # Note: _get_pvc_status normalizes the key to storage_class_name
                storage_class_name = str(pvc.get("storage_class_name", ""))
                pvc_name = pvc.get("name", "")
                
                if storage_class_name:
                    binding_mode = binding_modes.get(storage_class_name, "Immediate")
                    if binding_mode == "WaitForFirstConsumer":
                        # Check if there's a pod using this PVC
                        if pvc_name not in pods_using_pvcs:
                            return True, "WaitForFirstConsumer", (
                                f"PVC {pvc_name} uses StorageClass '{storage_class_name}' "
                                f"with volumeBindingMode=WaitForFirstConsumer and no Pod "
                                f"is currently using it - binding will occur when Pod is scheduled"
                            )
                        else:
                            return True, "WaitForFirstConsumerPodScheduled", (
                                f"PVC {pvc_name} uses StorageClass '{storage_class_name}' "
                                f"with volumeBindingMode=WaitForFirstConsumer - waiting for "
                                f"Pod scheduling constraints to be resolved"
                            )
    except (json.JSONDecodeError, TypeError):
        pass
    return False, "", ""


def _collect_pvc_diagnostic_info(
    pvc_name: str,
    pvc_json: str,
    storage_class_json: str,
    events_json: str,
) -> dict:
    """Collect comprehensive PVC diagnostic information.
    
    Args:
        pvc_name: Name of the PVC to diagnose
        pvc_json: JSON output from kubectl get pvc -o json
        storage_class_json: JSON output from kubectl get storageclass -o json
        events_json: JSON output from kubectl get events -o json
    
    Returns:
        Dict with PVC diagnostic info
    """
    diagnostics: dict[str, object] = {
        "pvc_name": pvc_name,
        "spec": {},
        "status": {},
        "events": [],
        "storage_class": {},
        "binding_mode": "",
    }
    
    # Extract PVC spec and status
    try:
        data = json.loads(pvc_json)
        for pvc in data.get("items", []):
            if pvc.get("metadata", {}).get("name") == pvc_name:
                diagnostics["spec"] = {
                    "access_modes": pvc.get("spec", {}).get("accessModes", []),
                    "resources": pvc.get("spec", {}).get("resources", {}),
                    "storage_class_name": pvc.get("spec", {}).get("storageClassName", ""),
                    "volume_name": pvc.get("spec", {}).get("volumeName", ""),
                    "selector": pvc.get("spec", {}).get("selector", {}),
                }
                diagnostics["status"] = {
                    "phase": pvc.get("status", {}).get("phase", ""),
                    "reason": pvc.get("status", {}).get("reason", ""),
                    "message": pvc.get("status", {}).get("message", ""),
                    "capacity": pvc.get("status", {}).get("capacity", {}),
                }
                break
    except (json.JSONDecodeError, TypeError):
        pass
    
    # Extract relevant events
    try:
        data = json.loads(events_json)
        for event in data.get("items", []):
            involved = event.get("involvedObject", {})
            if involved.get("kind") == "PersistentVolumeClaim" and involved.get("name") == pvc_name:
                diagnostics["events"].append({
                    "reason": event.get("reason", ""),
                    "message": event.get("message", ""),
                    "type": event.get("type", ""),
                    "last_timestamp": event.get("lastTimestamp", ""),
                })
    except (json.JSONDecodeError, TypeError):
        pass
    
    # Extract StorageClass info
    pvc_sc_name = str(diagnostics.get("spec", {}).get("storage_class_name", ""))
    if pvc_sc_name:
        try:
            data = json.loads(storage_class_json)
            for sc in data.get("items", []):
                if sc.get("metadata", {}).get("name") == pvc_sc_name:
                    # volumeBindingMode is a top-level field on StorageClass, not in parameters
                    binding_mode = sc.get("volumeBindingMode", "Immediate")
                    diagnostics["storage_class"] = {
                        "name": pvc_sc_name,
                        "provisioner": sc.get("provisioner", ""),
                        "parameters": sc.get("parameters", {}),
                        "volume_binding_mode": binding_mode,
                    }
                    diagnostics["binding_mode"] = binding_mode
                    break
        except (json.JSONDecodeError, TypeError):
            pass
    
    return diagnostics


def _check_readiness_probe_failed(
    waiting_info: list[dict],
    events_text: str = "",
    events_json: str = "",
) -> tuple[bool, str, str]:
    """Check for readiness probe failure events.
    
    Uses events_json for structural classification, events_text as fallback.
    
    Returns: (is_fatal, reason, message)
    """
    for w in waiting_info:
        reason = w.get("reason", "")
        # Readiness probe failures often show as container not ready
        if reason == "ContainersNotReady":
            return True, reason, w.get("message", "")
    
    # Primary: Use structural JSON events for probe failure detection
    if events_json:
        is_fatal, reason, message = _check_readiness_probe_failed_from_events(events_json)
        if is_fatal:
            return True, reason, message
    
    # Fallback: Check events text for readiness probe failure patterns
    if events_text:
        events_lower = events_text.lower()
        readiness_patterns = [
            "readiness probe failed",
            "readiness check failed",
            "unhealthy",
            "liveness probe failed",
        ]
        for pattern in readiness_patterns:
            if pattern in events_lower:
                # Extract message near the pattern
                lines = events_text.split("\n")
                for line in lines:
                    if pattern in line.lower():
                        return True, "ProbeFailed", line.strip()
    
    return False, "", ""


def _check_deployment_replica_failure(conditions: list[dict]) -> tuple[bool, str, str]:
    """Check for deployment ReplicaFailure condition.
    
    Returns: (is_fatal, reason, message)
    """
    for cond in conditions:
        cond_type = cond.get("type", "")
        if cond_type == "ReplicaFailure" and cond.get("status") == "True":
            return True, "ReplicaFailure", cond.get("message", "")
    return False, "", ""


def _check_deployment_progress_deadline(conditions: list[dict]) -> tuple[bool, str, str]:
    """Check for deployment ProgressDeadlineExceeded condition.
    
    Returns: (is_fatal, reason, message)
    """
    for cond in conditions:
        cond_type = cond.get("type", "")
        if cond_type == "Progressing" and cond.get("status") == "False":
            reason = cond.get("reason", "")
            if reason == "ProgressDeadlineExceeded":
                return True, reason, cond.get("message", "")
    return False, "", ""


# Expected workloads for k9b CNPG lab
EXPECTED_WORKLOADS = frozenset([
    "k9b-backend",
    "k9b-frontend", 
    "k9b-scheduler",
])


def _check_rollout_success(
    pods_json: str,
    deployments_json: str,
    pvc_json: str,
) -> bool:
    """Check if rollout is complete and successful.
    
    Returns True only if ALL conditions for successful rollout are met:
    - Expected deployments exist and have availableReplicas == desired replicas
    - All pods are Running with Ready condition True
    - All PVCs are Bound
    - observedGeneration matches generation (rollout complete)
    
    IMPORTANT: Empty or failed kubectl collection does NOT count as success.
    This prevents false-green when kubectl commands fail silently.
    
    Args:
        pods_json: JSON output from kubectl get pods -o json
        deployments_json: JSON output from kubectl get deployments -o json
        pvc_json: JSON output from kubectl get pvc -o json
    
    Returns:
        True if rollout is successful, False otherwise
    """
    try:
        # Check deployments: must have expected workloads with available replicas
        deploy_data = json.loads(deployments_json)
        
        # Track which expected workloads we found
        found_workloads: set[str] = set()
        deploy_items = deploy_data.get("items", [])
        
        # If no deployments found at all, rollout is NOT successful
        if not deploy_items:
            return False
        
        for deploy in deploy_items:
            name = deploy.get("metadata", {}).get("name", "")
            found_workloads.add(name)
            
            spec_replicas = deploy.get("spec", {}).get("replicas", 0)
            status = deploy.get("status", {})
            available = status.get("availableReplicas", 0)
            updated = status.get("updatedReplicas", 0)
            
            # Check if deployment is fully rolled out
            if available < spec_replicas or updated < spec_replicas:
                return False
            
            # Check observedGeneration matches generation (rollout complete)
            generation = deploy.get("metadata", {}).get("generation", 0)
            observed = status.get("observedGeneration", 0)
            if observed < generation:
                return False
            
            # Check Available condition is True
            has_available_true = False
            for cond in status.get("conditions", []):
                if cond.get("type") == "Available" and cond.get("status") == "True":
                    has_available_true = True
                    break
            if not has_available_true:
                return False
        
        # Verify expected workloads were found
        # This prevents false-green when kubectl fails and returns empty list
        missing_workloads = EXPECTED_WORKLOADS - found_workloads
        if missing_workloads:
            # Some expected workloads are missing - rollout not complete
            return False
        
        # Check pods: all should be Running with Ready condition True
        pods_data = json.loads(pods_json)
        pod_items = pods_data.get("items", [])
        
        # If no pods found at all, rollout is NOT successful
        if not pod_items:
            return False
        
        # Track pods per expected workload
        pods_per_workload: dict[str, int] = {w: 0 for w in EXPECTED_WORKLOADS}
        
        for pod in pod_items:
            # Skip pods that are being deleted
            if pod.get("metadata", {}).get("deletionTimestamp"):
                continue
            
            # Check owner reference to associate with workload
            owner_refs = pod.get("metadata", {}).get("ownerReferences", [])
            for ref in owner_refs:
                if ref.get("kind") == "ReplicaSet":
                    # Get the parent Deployment name from the ReplicaSet
                    # ReplicaSet names are typically: <deployment-name>-<hash>
                    rs_name = ref.get("name", "")
                    for workload in EXPECTED_WORKLOADS:
                        if rs_name.startswith(workload + "-"):
                            pods_per_workload[workload] += 1
                            break
            
            phase = pod.get("status", {}).get("phase", "")
            if phase != "Running":
                return False
            
            # Check Ready condition - must be present AND True
            has_ready_true = False
            for cond in pod.get("status", {}).get("conditions", []):
                if cond.get("type") == "Ready":
                    if cond.get("status") == "True":
                        has_ready_true = True
                        break
                    # Ready condition exists but is not True
                    return False
            # If Ready condition doesn't exist at all, pod is not ready
            if not has_ready_true:
                return False
        
        # Verify at least one pod per expected workload
        # This prevents false-green when pods fail to schedule
        for workload, count in pods_per_workload.items():
            if count == 0:
                return False
        
        # Check PVCs: all should be Bound
        pvc_data = json.loads(pvc_json)
        for pvc in pvc_data.get("items", []):
            phase = pvc.get("status", {}).get("phase", "")
            if phase != "Bound":
                return False
        
        return True
        
    except (json.JSONDecodeError, TypeError, KeyError):
        # If we can't parse, assume not successful
        return False


def classify_rollout_state(
    pods_json: str,
    deployments_json: str,
    pvc_json: str,
    events_text: str,
    events_json: str = "",
    storage_class_json: str = "",
    storage_class_available: bool = True,
) -> RolloutDiagnosis:
    """Classify rollout state from Kubernetes JSON data.
    
    Performs structural JSON parsing to detect failure conditions.
    Uses events_json for primary event classification, events_text as fallback.
    
    Evidence-backed PVC classification:
    - WaitForFirstConsumer: non-fatal until consuming Pod scheduling evidence
    - Missing StorageClass: fatal (hard evidence) - ONLY when StorageClass data was collected
    - Provisioning failure: fatal (hard evidence)
    - Ordinary Pending: non-fatal until deadline expires
    
    IMPORTANT: If storage_class_available is False (e.g., RBAC denied), we cannot emit
    StorageClassNotFound or NoStorageClassAvailable because that would be a false
    positive. StorageClass is cluster-scoped and may need separate permissions.
    
    Args:
        pods_json: JSON output from kubectl get pods -o json
        deployments_json: JSON output from kubectl get deployments -o json
        pvc_json: JSON output from kubectl get pvc -o json
        events_text: Text output from kubectl get events (fallback)
        events_json: JSON output from kubectl get events -o json (primary)
        storage_class_json: JSON output from kubectl get storageclass -o json
        storage_class_available: True if kubectl get storageclass succeeded
    
    Returns:
        RolloutDiagnosis with classification and details
    """
    diagnosis = RolloutDiagnosis()
    
    # Parse diagnostic data
    waiting_info = _get_pod_waiting_info(pods_json)
    conditions = _get_deployment_conditions(deployments_json)
    pvcs = _get_pvc_status(pvc_json)
    
    # Store diagnostics for artifact
    diagnosis.diagnostics = {
        "waiting_containers": waiting_info,
        "deployment_conditions": conditions,
        "pending_pvcs": pvcs,
        "events_sample": events_text[:2000] if events_text else "",  # Limit events
    }
    
    # Priority order: most specific failure classes first
    
    # 1. Image pull backoff
    is_fatal, reason, message = _check_image_pull_backoff(waiting_info)
    if is_fatal:
        affected = [w["pod"] for w in waiting_info if w.get("reason") in ("ImagePullBackOff", "ErrImagePull")]
        diagnosis.failure_class = FAILURE_IMAGE_PULL_BACKOFF
        diagnosis.fatal = True
        diagnosis.affected_pods = affected
        diagnosis.container_waiting_reason = reason
        diagnosis.container_name = next((w["container"] for w in waiting_info if w.get("reason") == reason), "")
        diagnosis.latest_event_reason = reason
        diagnosis.latest_event_message = message
        return diagnosis
    
    # 2. Crash loop
    is_fatal, reason, message = _check_crash_loop(waiting_info)
    if is_fatal:
        affected = [w["pod"] for w in waiting_info if w.get("reason") == "CrashLoopBackOff"]
        diagnosis.failure_class = FAILURE_CRASH_LOOP
        diagnosis.fatal = True
        diagnosis.affected_pods = affected
        diagnosis.pod_phase = next((w["phase"] for w in waiting_info if w.get("reason") == "CrashLoopBackOff"), "")
        diagnosis.container_waiting_reason = reason
        diagnosis.container_name = next((w["container"] for w in waiting_info if w.get("reason") == "CrashLoopBackOff"), "")
        diagnosis.latest_event_reason = reason
        diagnosis.latest_event_message = message
        return diagnosis
    
    # 3. Transient VolumeBinding PreBind conflict - check BEFORE failed_scheduling
    # This is nonfatal - the scheduler will retry automatically
    # If present, we skip failed_scheduling and PVC classification to avoid false positives
    has_transient, transient_msg, transient_pod = _detect_transient_volume_binding_conflict_from_events(events_json)
    if has_transient:
        diagnosis.diagnostics["transient_volume_binding_conflict"] = True
        diagnosis.diagnostics["transient_volume_binding_message"] = transient_msg
        diagnosis.diagnostics["transient_volume_binding_pod"] = transient_pod
        # Return nonfatal - the scheduler will retry and PVC may become Bound
        diagnosis.failure_class = ""
        diagnosis.fatal = False
        return diagnosis
    
    # 4. Failed scheduling (use events_json for structural classification)
    # Note: Transient VolumeBinding conflicts are handled above, so this only catches
    # genuine scheduling failures (insufficient CPU, memory, taints, etc.)
    is_fatal, reason, message = _check_failed_scheduling(pods_json, events_text, events_json)
    if is_fatal:
        affected = []
        # Add pods from waiting_info
        for w in waiting_info:
            if "unschedulable" in w.get("message", "").lower():
                affected.append(w["pod"])
        # Also add pods from the pods_json that have scheduling conditions
        try:
            pods_data = json.loads(pods_json)
            for pod in pods_data.get("items", []):
                pod_name = pod.get("metadata", {}).get("name", "unknown")
                for cond in pod.get("status", {}).get("conditions", []):
                    if cond.get("type") == "PodScheduled" and cond.get("status") == "False":
                        if pod_name not in affected:
                            affected.append(pod_name)
        except (json.JSONDecodeError, TypeError):
            pass
        diagnosis.failure_class = FAILURE_FAILED_SCHEDULING
        diagnosis.fatal = True
        diagnosis.affected_pods = affected
        diagnosis.pod_phase = "Pending"
        diagnosis.latest_event_reason = reason
        diagnosis.latest_event_message = message
        return diagnosis
    
    # 5. Evidence-backed PVC classification
    # Check for non-Bound PVCs and classify based on evidence
    # IMPORTANT: Only check StorageClass if collection succeeded (storage_class_available=True)
    # If RBAC denied, we cannot emit StorageClassNotFound/NoStorageClassAvailable
    if pvcs and storage_class_available and storage_class_json:
        # 5a. Explicit provisioning failure (fatal)
        is_fatal, reason, message = _check_pvc_provisioning_failure(events_json)
        if is_fatal:
            affected = [p["name"] for p in pvcs]
            diagnosis.failure_class = FAILURE_PVC_PENDING
            diagnosis.fatal = True
            diagnosis.affected_pvcs = affected
            diagnosis.latest_event_reason = reason
            diagnosis.latest_event_message = message
            # Collect comprehensive PVC diagnostic info
            for pvc_name in affected[:3]:  # Limit to first 3
                pvc_diag = _collect_pvc_diagnostic_info(pvc_name, pvc_json, storage_class_json, events_json)
                diagnosis.diagnostics[f"pvc_diagnostic_{pvc_name}"] = pvc_diag
            return diagnosis
        
        # 5b. Missing StorageClass (fatal)
        is_fatal, reason, message = _check_pvc_missing_storage_class(pvcs, storage_class_json)
        if is_fatal:
            affected = [p["name"] for p in pvcs]
            diagnosis.failure_class = FAILURE_PVC_PENDING
            diagnosis.fatal = True
            diagnosis.affected_pvcs = affected
            diagnosis.latest_event_reason = reason
            diagnosis.latest_event_message = message
            # Collect comprehensive PVC diagnostic info
            for pvc_name in affected[:3]:
                pvc_diag = _collect_pvc_diagnostic_info(pvc_name, pvc_json, storage_class_json, events_json)
                diagnosis.diagnostics[f"pvc_diagnostic_{pvc_name}"] = pvc_diag
            return diagnosis
        
        # 5c. WaitForFirstConsumer (non-fatal - keep polling)
        is_wfcf, reason, message = _check_pvc_wait_for_first_consumer(pvcs, storage_class_json, pods_json)
        if is_wfcf:
            affected = [p["name"] for p in pvcs]
            diagnosis.failure_class = "waiting_for_first_consumer"
            diagnosis.fatal = False  # Non-fatal - will bind when Pod is scheduled
            diagnosis.affected_pvcs = affected
            diagnosis.latest_event_reason = reason
            diagnosis.latest_event_message = message
            # Collect comprehensive PVC diagnostic info
            for pvc_name in affected[:3]:
                pvc_diag = _collect_pvc_diagnostic_info(pvc_name, pvc_json, storage_class_json, events_json)
                diagnosis.diagnostics[f"pvc_diagnostic_{pvc_name}"] = pvc_diag
            return diagnosis
        
        # 5d. PVC pending without hard evidence (non-fatal - keep polling until deadline)
        # Note: Called AFTER 5a-5c have ruled out hard failures
        is_pending, status, reason, _failure_class = _check_pvc_pending(pvcs)
        if is_pending:
            affected = [p["name"] for p in pvcs]
            diagnosis.failure_class = "pvc_pending"
            diagnosis.fatal = False  # Non-fatal - waiting for provisioning
            diagnosis.affected_pvcs = affected
            diagnosis.latest_event_reason = "PVCNotBound"
            diagnosis.latest_event_message = f"PVC pending: {status}, reason: {reason} - waiting for provisioning"
            # Collect comprehensive PVC diagnostic info
            for pvc_name in affected[:3]:
                pvc_diag = _collect_pvc_diagnostic_info(pvc_name, pvc_json, storage_class_json, events_json)
                diagnosis.diagnostics[f"pvc_diagnostic_{pvc_name}"] = pvc_diag
            return diagnosis
    
    # 6. Readiness probe failed (use events_json for structural classification)
    is_fatal, reason, message = _check_readiness_probe_failed(waiting_info, events_text, events_json)
    if is_fatal:
        affected = [w["pod"] for w in waiting_info if w.get("reason") == "ContainersNotReady"]
        diagnosis.failure_class = FAILURE_READINESS_PROBE_FAILED
        diagnosis.fatal = True
        diagnosis.affected_pods = affected
        diagnosis.container_waiting_reason = reason
        diagnosis.latest_event_reason = reason
        diagnosis.latest_event_message = message
        return diagnosis
    
    # 7. Deployment replica failure
    is_fatal, reason, message = _check_deployment_replica_failure(conditions)
    if is_fatal:
        affected = [c["deployment"] for c in conditions if c.get("type") == "ReplicaFailure"]
        diagnosis.failure_class = FAILURE_DEPLOYMENT_REPLICA_FAILURE
        diagnosis.fatal = True
        diagnosis.affected_deployments = affected
        diagnosis.latest_event_reason = reason
        diagnosis.latest_event_message = message
        return diagnosis
    
    # 8. Deployment progress deadline
    is_fatal, reason, message = _check_deployment_progress_deadline(conditions)
    if is_fatal:
        affected = [c["deployment"] for c in conditions if c.get("type") == "Progressing"]
        diagnosis.failure_class = FAILURE_DEPLOYMENT_PROGRESS_DEADLINE
        diagnosis.fatal = True
        diagnosis.affected_deployments = affected
        diagnosis.latest_event_reason = reason
        diagnosis.latest_event_message = message
        return diagnosis
    
    # No fatal condition found - workload may be progressing
    diagnosis.failure_class = ""
    diagnosis.fatal = False
    return diagnosis


def _get_kubectl_storageclass(kubeconfig: str) -> KubectlResult:
    """Execute kubectl get storageclass command and return structured result."""
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "storageclass", "-o", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return KubectlResult(json_data=result.stdout, text_data=result.stdout, success=True)
    else:
        return KubectlResult(
            json_data="{}",
            text_data=result.stderr or f"kubectl failed with exit code {result.returncode}",
            success=False,
            error_message=result.stderr.strip() or f"Exit code: {result.returncode}"
        )


def _collect_rollout_snapshot(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
    snapshot_id: int,
) -> tuple[KubectlResult, KubectlResult, KubectlResult, KubectlResult, KubectlResult, KubectlResult]:
    """Collect rollout snapshot and return structured results.
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace name
        artifact_dir: Base artifact directory
        snapshot_id: Snapshot sequence number
    
    Returns:
        Tuple of KubectlResult objects for (pods, deployments, pvc, events_text, events_json, storageclass)
    """
    rollout_dir = artifact_dir / "rollout-watch"
    rollout_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    
    # Collect pods JSON
    pods_result = _get_kubectl_json(kubeconfig, namespace, "pods")
    pods_path = rollout_dir / f"pods-{snapshot_id:03d}-{timestamp}.json"
    pods_path.write_text(pods_result.json_data)
    
    # Collect deployments JSON
    deployments_result = _get_kubectl_json(kubeconfig, namespace, "deployments")
    deployments_path = rollout_dir / f"deployments-{snapshot_id:03d}-{timestamp}.json"
    deployments_path.write_text(deployments_result.json_data)
    
    # Collect PVCs JSON
    pvc_result = _get_kubectl_json(kubeconfig, namespace, "pvc")
    pvc_path = rollout_dir / f"pvc-{snapshot_id:03d}-{timestamp}.json"
    pvc_path.write_text(pvc_result.json_data)
    
    # Collect events text
    events_text_result = _get_kubectl_text(kubeconfig, namespace, "events")
    events_path = rollout_dir / f"events-{snapshot_id:03d}-{timestamp}.txt"
    events_path.write_text(events_text_result.text_data)
    
    # Collect events JSON for structural parsing
    events_json_result = _get_kubectl_events(kubeconfig, namespace)
    events_json_path = rollout_dir / f"events-{snapshot_id:03d}-{timestamp}.json"
    events_json_path.write_text(events_json_result.json_data)
    
    # Collect StorageClass for PVC diagnosis
    storageclass_result = _get_kubectl_storageclass(kubeconfig)
    storageclass_path = rollout_dir / f"storageclass-{snapshot_id:03d}-{timestamp}.json"
    storageclass_path.write_text(storageclass_result.json_data)
    
    return pods_result, deployments_result, pvc_result, events_text_result, events_json_result, storageclass_result


def _format_bounded_summary(diagnosis: RolloutDiagnosis, snapshot_path: str) -> str:
    """Format bounded diagnosis summary for GitHub Actions output.
    
    Args:
        diagnosis: RolloutDiagnosis result
        snapshot_path: Path to snapshot artifact
    
    Returns:
        Bounded summary string suitable for CI logs
    """
    lines = []
    
    if diagnosis.fatal and diagnosis.failure_class:
        lines.append(f"FAILURE_CLASS={diagnosis.failure_class}")
        lines.append("")
        
        if diagnosis.affected_pods:
            lines.append(f"Affected pods: {', '.join(diagnosis.affected_pods[:5])}")
            if len(diagnosis.affected_pods) > 5:
                lines.append(f"  ... and {len(diagnosis.affected_pods) - 5} more")
        
        if diagnosis.affected_deployments:
            lines.append(f"Affected deployments: {', '.join(diagnosis.affected_deployments[:5])}")
        
        if diagnosis.affected_pvcs:
            lines.append(f"Affected PVCs: {', '.join(diagnosis.affected_pvcs[:5])}")
        
        if diagnosis.pod_phase:
            lines.append(f"Pod phase: {diagnosis.pod_phase}")
        
        if diagnosis.container_waiting_reason:
            lines.append(f"Container waiting reason: {diagnosis.container_waiting_reason}")
        
        if diagnosis.container_name:
            lines.append(f"Container name: {diagnosis.container_name}")
        
        if diagnosis.latest_event_reason:
            lines.append(f"Latest event reason: {diagnosis.latest_event_reason}")
        
        if diagnosis.latest_event_message:
            # Truncate long messages
            msg = diagnosis.latest_event_message
            if len(msg) > 200:
                msg = msg[:197] + "..."
            lines.append(f"Latest event message: {msg}")
        
        lines.append("")
        lines.append(f"Artifact: {snapshot_path}")
    else:
        lines.append("Rollout progressing - no fatal condition detected")
        lines.append(f"Artifact: {snapshot_path}")
    
    return "\n".join(lines)


def monitor_rollout(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
    deadline_seconds: int = 90,
    poll_interval: int = 8,
) -> RolloutDiagnosis:
    """Monitor rollout with proactive short-interval polling.
    
    Polls Kubernetes every poll_interval seconds until either:
    - A fatal failure condition is detected
    - The deadline is reached
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace name
        artifact_dir: Base artifact directory
        deadline_seconds: Maximum time to monitor (default 90s)
        poll_interval: Seconds between polls (default 8s)
    
    Returns:
        RolloutDiagnosis with classification
    """
    import time
    
    rollout_dir = artifact_dir / "rollout-watch"
    rollout_dir.mkdir(parents=True, exist_ok=True)
    
    # Index file for snapshots
    index_file = rollout_dir / "index.json"
    snapshots: list[dict] = []
    
    snapshot_id = 0
    start_time = time.time()
    last_diagnosis: RolloutDiagnosis | None = None
    
    while True:
        elapsed = time.time() - start_time
        remaining = deadline_seconds - elapsed
        
        if remaining <= 0:
            log(f"Rollout monitor: deadline reached ({deadline_seconds}s)")
            if last_diagnosis and not last_diagnosis.fatal:
                # Timeout without fatal condition
                last_diagnosis.failure_class = FAILURE_ROLLOUT_TIMEOUT
                last_diagnosis.fatal = True
                last_diagnosis.diagnostics["timeout_seconds"] = deadline_seconds
            break
        
        # Collect snapshot (including events JSON for structural classification)
        timestamp = datetime.now(UTC).isoformat()
        pods_result, deployments_result, pvc_result, events_text_result, events_json_result, storageclass_result = _collect_rollout_snapshot(
            kubeconfig, namespace, artifact_dir, snapshot_id
        )
        
        # Check for collection failures - fail immediately with explicit failure class
        # All collections must succeed to have meaningful diagnostics
        if not pods_result.success or not deployments_result.success or not pvc_result.success:
            elapsed = time.time() - start_time
            log(f"Rollout monitor: kubectl collection failed at {elapsed:.1f}s")
            
            diagnosis = RolloutDiagnosis()
            diagnosis.failure_class = FAILURE_SNAPSHOT_COLLECTION_FAILED
            diagnosis.fatal = True
            diagnosis.diagnostics = {
                "elapsed_seconds": round(elapsed, 1),
                "total_snapshots": snapshot_id + 1,
                "pods_success": pods_result.success,
                "pods_error": pods_result.error_message,
                "deployments_success": deployments_result.success,
                "deployments_error": deployments_result.error_message,
                "pvc_success": pvc_result.success,
                "pvc_error": pvc_result.error_message,
                "events_success": events_json_result.success,
            }
            diagnosis.snapshot_path = str(rollout_dir)
            diagnosis.latest_event_reason = "SnapshotCollectionFailed"
            diagnosis.latest_event_message = (
                f"pods={pods_result.error_message}, "
                f"deployments={deployments_result.error_message}, "
                f"pvc={pvc_result.error_message}"
            )
            
            # Save final diagnosis
            final_diag = diagnosis.to_dict()
            final_diag["final"] = True
            write_json_atomically(rollout_dir / "final-diagnosis.json", final_diag)
            
            # Save bounded summary
            summary = _format_bounded_summary(diagnosis, str(rollout_dir))
            (rollout_dir / "bounded-summary.txt").write_text(summary)
            
            # Update index
            snapshots.append({
                "id": snapshot_id,
                "timestamp": timestamp,
                "elapsed_seconds": round(elapsed, 1),
                "failure_class": diagnosis.failure_class,
                "fatal": True,
            })
            snapshots[-1]["final"] = True
            write_json_atomically(index_file, {"snapshots": snapshots})
            
            return diagnosis
        
        # Extract raw JSON/text from results
        pods_json = pods_result.json_data
        deployments_json = deployments_result.json_data
        pvc_json = pvc_result.json_data
        events_text = events_text_result.text_data
        events_json = events_json_result.json_data
        storage_class_json = storageclass_result.json_data
        
        # Classify state using structural JSON events
        # Pass storageclass_result.success to prevent false-positive StorageClassNotFound
        # when RBAC denies get on cluster-scoped storageclass resource
        diagnosis = classify_rollout_state(pods_json, deployments_json, pvc_json, events_text, events_json, storage_class_json, storageclass_result.success)
        
        # Check for successful rollout - if all deployments are healthy and pods are ready
        if _check_rollout_success(pods_json, deployments_json, pvc_json):
            elapsed = time.time() - start_time
            log(f"Rollout monitor: success detected at {elapsed:.1f}s")
            
            # Create success diagnosis
            diagnosis = RolloutDiagnosis()
            diagnosis.fatal = False
            diagnosis.failure_class = ""
            diagnosis.diagnostics = {
                "elapsed_seconds": round(elapsed, 1),
                "total_snapshots": snapshot_id + 1,
            }
            diagnosis.snapshot_path = str(rollout_dir)
            
            # Save final diagnosis
            final_diag = diagnosis.to_dict()
            final_diag["final"] = True
            final_diag["success"] = True
            write_json_atomically(rollout_dir / "final-diagnosis.json", final_diag)
            
            # Save bounded summary
            (rollout_dir / "bounded-summary.txt").write_text(
                f"SUCCESS: Rollout complete at {elapsed:.1f}s\n"
                f"Snapshots: {snapshot_id + 1}\n"
                f"Artifact: {rollout_dir}"
            )
            
            # Update index
            snapshot_info = {
                "id": snapshot_id,
                "timestamp": timestamp,
                "elapsed_seconds": round(elapsed, 1),
                "failure_class": "",
                "fatal": False,
                "success": True,
            }
            snapshots.append(snapshot_info)
            snapshots[-1]["final"] = True
            write_json_atomically(index_file, {"snapshots": snapshots})
            
            return diagnosis
        
        # Record snapshot info
        snapshot_info = {
            "id": snapshot_id,
            "timestamp": timestamp,
            "elapsed_seconds": round(elapsed, 1),
            "failure_class": diagnosis.failure_class,
            "fatal": diagnosis.fatal,
            "affected_pods": diagnosis.affected_pods,
        }
        snapshots.append(snapshot_info)
        
        # Update diagnosis snapshot path
        diagnosis.snapshot_path = str(rollout_dir / f"*-{snapshot_id:03d}-*.json")
        
        # Save diagnosis for this snapshot
        diag_path = rollout_dir / f"diagnosis-{snapshot_id:03d}.json"
        write_json_atomically(diag_path, diagnosis.to_dict())
        
        log(f"Rollout snapshot #{snapshot_id}: elapsed={elapsed:.1f}s, fatal={diagnosis.fatal}, class={diagnosis.failure_class}")
        
        if diagnosis.fatal:
            # Save final diagnosis
            final_diag = diagnosis.to_dict()
            final_diag["final"] = True
            final_diag["total_snapshots"] = snapshot_id + 1
            final_diag["total_elapsed_seconds"] = round(elapsed, 1)
            write_json_atomically(rollout_dir / "final-diagnosis.json", final_diag)
            
            # Save bounded summary
            summary = _format_bounded_summary(diagnosis, str(diag_path))
            (rollout_dir / "bounded-summary.txt").write_text(summary)
            
            # Update index
            snapshots[-1]["final"] = True
            write_json_atomically(index_file, {"snapshots": snapshots})
            
            return diagnosis
        
        last_diagnosis = diagnosis
        snapshot_id += 1
        
        # Wait before next poll
        time.sleep(poll_interval)
    
    # Timeout reached - handle zero-snapshot edge case
    if not last_diagnosis:
        # Initialize a diagnosis even if no snapshots were collected
        # (e.g., if deadline is 0 or negative)
        last_diagnosis = RolloutDiagnosis()
        last_diagnosis.failure_class = FAILURE_ROLLOUT_TIMEOUT
        last_diagnosis.fatal = True
        last_diagnosis.diagnostics = {
            "timeout_seconds": deadline_seconds,
            "total_snapshots": 0,
            "total_elapsed_seconds": round(time.time() - start_time, 1),
        }
    
    last_diagnosis.failure_class = FAILURE_ROLLOUT_TIMEOUT
    last_diagnosis.fatal = True
    last_diagnosis.diagnostics["timeout_seconds"] = deadline_seconds
    last_diagnosis.diagnostics["total_snapshots"] = len(snapshots)
    last_diagnosis.diagnostics["total_elapsed_seconds"] = round(time.time() - start_time, 1)
    
    # Save final diagnosis
    final_diag = last_diagnosis.to_dict()
    final_diag["final"] = True
    write_json_atomically(rollout_dir / "final-diagnosis.json", final_diag)
    
    # Save bounded summary
    summary = _format_bounded_summary(last_diagnosis, str(rollout_dir))
    (rollout_dir / "bounded-summary.txt").write_text(summary)
    
    # Update index - mark last snapshot as final
    if snapshots:
        snapshots[-1]["final"] = True
    write_json_atomically(index_file, {"snapshots": snapshots})
    
    return last_diagnosis


def main_monitor_rollout() -> int:
    """CLI entry point for rollout monitor.
    
    Usage:
        monitor-rollout --kubeconfig <path> --namespace <name>
                       [--artifact-dir <path>] [--deadline <seconds>] [--poll-interval <seconds>]
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor rollout with proactive polling")
    parser.add_argument("--kubeconfig", required=True, help="Path to kubeconfig")
    parser.add_argument("--namespace", required=True, help="Namespace name")
    parser.add_argument(
        "--artifact-dir",
        default=os.environ.get("ARTIFACT_DIR", "./lab-artifacts/live"),
        help="Artifact directory",
    )
    parser.add_argument(
        "--deadline",
        type=int,
        default=90,
        help="Maximum monitoring time in seconds (default: 90)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=8,
        help="Poll interval in seconds (default: 8)",
    )
    args = parser.parse_args(sys.argv[2:])
    
    kubeconfig = args.kubeconfig
    namespace = args.namespace
    artifact_dir = Path(args.artifact_dir)
    deadline = args.deadline
    poll_interval = args.poll_interval
    
    if not Path(kubeconfig).exists():
        error(f"Kubeconfig not found: {kubeconfig}")
        return 1
    
    log(f"Starting rollout monitor for namespace: {namespace}")
    log(f"Deadline: {deadline}s, poll interval: {poll_interval}s")
    
    diagnosis = monitor_rollout(
        kubeconfig=kubeconfig,
        namespace=namespace,
        artifact_dir=artifact_dir,
        deadline_seconds=deadline,
        poll_interval=poll_interval,
    )
    
    # Output for CI
    print(f"FAILURE_CLASS={diagnosis.failure_class}")
    print(f"FATAL={str(diagnosis.fatal).lower()}")
    
    if diagnosis.affected_pods:
        print(f"AFFECTED_PODS={','.join(diagnosis.affected_pods[:10])}")
    if diagnosis.affected_deployments:
        print(f"AFFECTED_DEPLOYMENTS={','.join(diagnosis.affected_deployments[:10])}")
    if diagnosis.affected_pvcs:
        print(f"AFFECTED_PVCS={','.join(diagnosis.affected_pvcs[:10])}")
    
    if diagnosis.container_waiting_reason:
        print(f"CONTAINER_WAITING_REASON={diagnosis.container_waiting_reason}")
    
    if diagnosis.latest_event_reason:
        print(f"LATEST_EVENT_REASON={diagnosis.latest_event_reason}")
    
    # Return 0 if not fatal (workload progressing), 1 if fatal
    return 0 if not diagnosis.fatal else 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        subcommand = sys.argv[1]
        if subcommand == "classify-error":
            sys.exit(main_classify_error())
        elif subcommand == "classify-schema":
            sys.exit(main_classify_schema())
        elif subcommand == "classify-wait-timeout":
            sys.exit(main_classify_wait_timeout())
        elif subcommand == "extract-schema-evidence":
            sys.exit(main_extract_schema_evidence())
        elif subcommand == "monitor-rollout":
            sys.exit(main_monitor_rollout())

    env_secret = sys.argv[1] if len(sys.argv) > 1 else "K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64"
    out_var = sys.argv[2] if len(sys.argv) > 2 else "KUBECONFIG"
    namespace = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("LAB_NAMESPACE", "")
    sys.exit(main_bootstrap(env_secret, out_var, namespace))
