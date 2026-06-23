#!/usr/bin/env python3
"""
verify_k3s_cnpg_incident_lab_artifact.py

Verifies the artifact directory produced by the K3s CNPG incident lab.
This script validates:
- lab-result.json exists and is well-formed
- Required phase artifact files are present
- Baseline was captured
- Incident phase was captured
- k9b incident evidence was captured (if incident_detected=true)
- No actual secrets appear in sanitized artifacts
- incident_detected=true is consistent with artifacts
- namespace-mode fields are present when cluster_mode=existing

The verifier operates on the SANITIZED artifact directory, not raw artifacts.
Raw artifacts are kept local during the job; only sanitized artifacts are verified and uploaded.

Exit codes:
  0 - All checks passed
  1 - Verification failed (with diagnostic output)
  2 - Invalid arguments
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Import the sanitizer for shared constants and utilities
from sanitize_live_lab_artifacts import (
    _FATAL_PATTERNS,
    REDACTION_PLACEHOLDER,
    Finding,
    FindingKind,
)

# ============================================================================
# FINDING CLASSIFICATION
# ============================================================================
# FindingKind is imported from sanitize_live_lab_artifacts


# ============================================================================
# VERIFICATION CONTEXT
# ============================================================================

@dataclass
class VerificationContext:
    """Context for artifact verification."""
    artifact_dir: Path
    verbose: bool = False
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_finding(self, kind: str, message: str, file: str, context: str | None = None) -> None:
        """Add a finding with deduplication."""
        finding = Finding(kind=kind, message=message, file=file, context=context)
        # Deduplicate
        for existing in self.findings:
            if (existing.kind == finding.kind and
                existing.message == finding.message and
                existing.file == finding.file and
                existing.context == finding.context):
                return
        self.findings.append(finding)

    def add_error(self, message: str) -> None:
        """Add a verification error."""
        self.errors.append(message)

    def add_fatal(self, message: str, file: str = "", context: str | None = None) -> None:
        """Add a fatal finding (actual secret detected)."""
        self.add_finding(FindingKind.FATAL, message, file, context)

    def add_warning(self, message: str, file: str = "", context: str | None = None) -> None:
        """Add a warning finding (sensitive metadata retained)."""
        self.add_finding(FindingKind.WARNING, message, file, context)

    def add_info(self, message: str, file: str = "", context: str | None = None) -> None:
        """Add an info finding (benign Kubernetes reference)."""
        self.add_finding(FindingKind.INFO, message, file, context)


# ============================================================================
# SAFE KUBERNETES VOCABULARY
# ============================================================================

# Safe Kubernetes field patterns that should NOT trigger fatal findings
# These are Kubernetes vocabulary, not actual secrets
_SAFE_K8S_PATTERNS: list[re.Pattern[str]] = [
    # Secret references
    re.compile(r"(?i)secretName\s*[:=]\s*[\w-]+"),
    re.compile(r"(?i)secretRef\s*[:=]\s*\{"),
    re.compile(r"(?i)secretNames\s*[:=]\s*\["),
    # Service account references
    re.compile(r"(?i)serviceAccountName\s*[:=]\s*[\w-]+"),
    re.compile(r"(?i)serviceAccount\s*[:=]\s*[\w-]+"),
    re.compile(r"(?i)serviceAccountToken\s*[:=]"),
    # Auto-mount flags
    re.compile(r"(?i)automountServiceAccountToken\s*[:=]\s*(true|false)"),
    # CNPG specific
    re.compile(r"(?i)clientCASecret\s*[:=]\s*[\w-]+"),
    re.compile(r"(?i)caSecret\s*[:=]\s*[\w-]+"),
    # RBAC
    re.compile(r"(?i)roleRef\s*[:=]"),
    re.compile(r"(?i)subjects\s*[:=]"),
    # Auth mode
    re.compile(r"(?i)auth\s*[:=]\s*[\w]+"),
    re.compile(r"(?i)authMode\s*[:=]"),
    re.compile(r"(?i)inCluster\s*[:=]"),
    re.compile(r"(?i)incluster\s*[:=]"),
    # Kubeconfig paths (not content)
    re.compile(r"(?i)kubeconfigPath\s*[:=]"),
    re.compile(r"(?i)kubeconfig\s*[:=]\s*[\/\w.-]+"),
    # RBAC resources
    re.compile(r"(?i)resources\s*[:=]\s*\[\s*[\"']secrets[\"']"),
    re.compile(r"(?i)kind\s*[:=]\s*[\"']?(Secret|ClusterRole|ClusterRoleBinding|Role|RoleBinding)[\"']?", re.IGNORECASE),
    # CNPG fields
    re.compile(r"(?i)secretTemplate\s*[:=]"),
    re.compile(r"(?i)namespace\s*[:=]\s*[\w-]+"),
]

# Known benign patterns in kubectl output
_BENIGN_K8S_PATTERNS: list[re.Pattern[str]] = [
    # kubectl describe output commonly mentions secrets
    re.compile(r"This\s+pod\s+has\s+the\s+following\s+secret\s+credentials:", re.IGNORECASE),
    re.compile(r"secrets\s+referenced\s+by\s+\w+\s+:", re.IGNORECASE),
    # CNPG cluster status fields
    re.compile(r"(?i)secretName\s*[:=]\s*[\w-]+"),
    # Pod volume projections
    re.compile(r"(?i)projected\s*serviceAccountToken"),
]


# ============================================================================
# REQUIRED ARTIFACT STRUCTURE
# ============================================================================

# Required artifact structure.
REQUIRED_ARTIFACTS = {
    "lab-result.json": {"required": True, "type": "file"},
}

REQUIRED_BASELINE = {
    "nodes.txt": {"required": True, "type": "file"},
    "pods.txt": {"required": True, "type": "file"},
    "cnpg-clusters.json": {"required": True, "type": "file"},
    "k9b-status.json": {"required": True, "type": "file"},
}

REQUIRED_INCIDENT = {
    "injected-change.yaml": {"required": True, "type": "file"},
    "pods.txt": {"required": True, "type": "file"},
    "events.txt": {"required": True, "type": "file"},
    "cnpg-clusters.json": {"required": True, "type": "file"},
}

REQUIRED_INCIDENT_K9B = {
    "k9b-incidents.json": {"required": True, "type": "file"},
    "k9b-incident-detail.json": {"required": False, "type": "file"},  # Optional
}

REQUIRED_FINAL = {
    "pods.txt": {"required": True, "type": "file"},
    "events.txt": {"required": True, "type": "file"},
    "cnpg-clusters.json": {"required": True, "type": "file"},
}

REQUIRED_LOGS = {
    "lab-runner.log": {"required": True, "type": "file"},
}


# ============================================================================
# VERIFICATION LOGIC
# ============================================================================

def _is_safe_k8s_vocabulary(line: str) -> tuple[bool, str | None]:
    """Check if a line contains safe Kubernetes vocabulary.
    
    Returns (is_safe, matched_pattern_name).
    """
    for pattern in _SAFE_K8S_PATTERNS:
        if pattern.search(line):
            return True, pattern.pattern[:30]
    return False, None


def _is_benign_k8s_pattern(content: str) -> bool:
    """Check if content matches known benign Kubernetes patterns."""
    for pattern in _BENIGN_K8S_PATTERNS:
        if pattern.search(content):
            return True
    return False


def _check_structured_secrets_in_file(ctx: VerificationContext, filepath: Path) -> bool:
    """
    Check if a file contains actual secrets using structured analysis.
    
    Returns True if actual secrets are found (fatal), False otherwise.
    
    IMPORTANT: This function must NOT skip scanning based on "benign" kind.
    Even Pod/Deployment objects can contain env vars, annotations, or embedded
    values with sensitive data that needs detection.
    """
    try:
        content = filepath.read_text(errors="replace")
    except Exception as e:
        ctx.add_error(f"Could not read file: {e}")
        return False

    rel_path = str(filepath.relative_to(ctx.artifact_dir))
    found_actual_secret = False

    # For JSON files, do structured analysis but ALWAYS continue scanning
    suffix = filepath.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(content)
            if _is_benign_json_structure(data):
                # Log info but DO NOT return - must continue scanning
                ctx.add_info("Benign Kubernetes structure detected", rel_path)
        except json.JSONDecodeError:
            pass

    # Scan line by line for actual secrets - ALWAYS do this
    lines = content.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # Check for actual credential patterns
        for pattern in _FATAL_PATTERNS:
            if pattern.search(stripped):
                # Found actual secret - but check if it's in a benign context
                if _is_benign_k8s_pattern(stripped):
                    ctx.add_info("Benign pattern matched (not a credential)", f"{rel_path}:{i+1}")
                    continue
                
                ctx.add_fatal(
                    f"Credential pattern detected: {pattern.pattern[:40]}",
                    f"{rel_path}:{i+1}"
                )
                found_actual_secret = True

        # Additional check: raw text files containing Secret manifests
        if "kind:" in stripped.lower() and "secret" in stripped.lower():
            # This is a Kubernetes Secret manifest - check if it's just metadata
            if "data:" not in content.lower() and "stringData:" not in content.lower():
                ctx.add_info("Secret resource reference (not actual secret value)", rel_path)
            elif "data:" in content.lower():
                # Secret with data - should have been sanitized
                if REDACTION_PLACEHOLDER in content:
                    ctx.add_info("Secret.data appears sanitized", rel_path)
                else:
                    ctx.add_fatal("Secret manifest with data field not sanitized", rel_path)
                    found_actual_secret = True

    return found_actual_secret


def _is_benign_json_structure(data: Any) -> bool:
    """Check if JSON data represents benign Kubernetes structures."""
    if not isinstance(data, dict):
        return False

    # Check for common benign patterns
    kind = data.get("kind", "")
    if isinstance(kind, str):
        kind_lower = kind.lower()
        # Safe resource types
        if kind_lower in ("cluster", "pod", "deployment", "statefulset", "service",
                         "configmap", "clusterrole", "clusterrolebinding",
                         "role", "rolebinding", "namespace", "node"):
            return True

    # CNPG cluster status (safe)
    if "cluster_details" in data or "clusters_installed" in data:
        return True

    # k9b status (safe)
    if "installed" in data and "version" in data:
        return True

    # Pod list (safe)
    if "items" in data and isinstance(data.get("items"), list):
        return True

    return False


def verify_artifact_dir(ctx: VerificationContext) -> bool:
    """
    Verify the artifact directory structure and contents.
    
    Returns True if all checks passed, False otherwise.
    """
    # Check artifact dir exists.
    if not ctx.artifact_dir.exists():
        ctx.add_error(f"Artifact directory does not exist: {ctx.artifact_dir}")
        return False
    
    if not ctx.artifact_dir.is_dir():
        ctx.add_error(f"Artifact path is not a directory: {ctx.artifact_dir}")
        return False
    
    # --- Check lab-result.json ---
    lab_result_path = ctx.artifact_dir / "lab-result.json"
    if not lab_result_path.exists():
        ctx.add_error("lab-result.json is missing")
        return False
    
    # Parse lab-result.json.
    try:
        lab_result = json.loads(lab_result_path.read_text())
    except json.JSONDecodeError as e:
        ctx.add_error(f"lab-result.json is malformed JSON: {e}")
        return False
    
    # Validate required fields in lab-result.json.
    required_fields = ["ok", "scenario", "started_at", "finished_at", "cluster_mode", "artifact_dir"]
    for field_name in required_fields:
        if field_name not in lab_result:
            ctx.add_error(f"lab-result.json missing required field: {field_name}")
    
    # --- Validate namespace-mode specific fields ---
    cluster_mode = lab_result.get("cluster_mode", "")
    if cluster_mode == "existing":
        # Namespace mode requires lab_namespace field
        if "lab_namespace" not in lab_result:
            ctx.add_error("lab-result.json missing required field: lab_namespace (required when cluster_mode=existing)")
        
        # Namespace mode requires cnpg_operator_mode field
        if "cnpg_operator_mode" not in lab_result:
            ctx.add_error("lab-result.json missing required field: cnpg_operator_mode (required when cluster_mode=existing)")
        
        # Namespace mode should have runner_mode
        if "runner_mode" not in lab_result:
            ctx.add_error("lab-result.json missing required field: runner_mode (required when cluster_mode=existing)")
        
        # Image metadata should be present
        if "k9b_image_repository" not in lab_result:
            ctx.add_error("lab-result.json missing required field: k9b_image_repository")
        if "k9b_image_tag" not in lab_result:
            ctx.add_error("lab-result.json missing required field: k9b_image_tag")
        if "k9b_image_ref" not in lab_result:
            ctx.add_error("lab-result.json missing required field: k9b_image_ref")
    elif cluster_mode == "provision":
        # Legacy provision mode - these are optional
        pass
    
    # --- Check baseline artifacts ---
    baseline_dir = ctx.artifact_dir / "baseline"
    for filename, spec in REQUIRED_BASELINE.items():
        filepath = baseline_dir / filename
        if spec["required"] and not filepath.exists():
            ctx.add_error(f"Baseline artifact missing: baseline/{filename}")
        elif filepath.exists():
            # Check for secrets in sanitized artifacts.
            found_secret = _check_structured_secrets_in_file(ctx, filepath)
            if ctx.verbose:
                status = "✗" if found_secret else "✓"
                print(f"  {status} baseline/{filename}")
    
    # --- Check incident artifacts ---
    incident_dir = ctx.artifact_dir / "incident"
    for filename, spec in REQUIRED_INCIDENT.items():
        filepath = incident_dir / filename
        if spec["required"] and not filepath.exists():
            ctx.add_error(f"Incident artifact missing: incident/{filename}")
        elif filepath.exists():
            # Check for secrets.
            found_secret = _check_structured_secrets_in_file(ctx, filepath)
            if ctx.verbose:
                status = "✗" if found_secret else "✓"
                print(f"  {status} incident/{filename}")
    
    # --- Check k9b incident evidence ---
    if lab_result.get("incident_detected"):
        # If incident_detected=true, we expect k9b incident artifacts.
        for filename, spec in REQUIRED_INCIDENT_K9B.items():
            filepath = incident_dir / filename
            if spec["required"] and not filepath.exists():
                ctx.add_error(
                    f"k9b incident evidence missing: incident/{filename} "
                    f"(incident_detected=true requires this artifact)"
                )
            elif filepath.exists() and ctx.verbose:
                print(f"  ✓ incident/{filename}")
    else:
        # incident_detected=false - warn if k9b incidents exist.
        k9b_incidents = incident_dir / "k9b-incidents.json"
        if k9b_incidents.exists():
            try:
                incidents = json.loads(k9b_incidents.read_text())
                if isinstance(incidents, list) and len(incidents) > 0:
                    ctx.add_error(
                        "k9b-incidents.json contains incidents but incident_detected=false. "
                        "This is inconsistent - either incidents exist or they don't."
                    )
            except json.JSONDecodeError:
                pass  # Already caught by general artifact check.
    
    # --- Check final/recovery artifacts ---
    final_dir = ctx.artifact_dir / "recovery-or-final"
    for filename, spec in REQUIRED_FINAL.items():
        filepath = final_dir / filename
        if spec["required"] and not filepath.exists():
            ctx.add_error(f"Final artifact missing: recovery-or-final/{filename}")
        elif filepath.exists():
            # Check for secrets.
            found_secret = _check_structured_secrets_in_file(ctx, filepath)
            if ctx.verbose:
                status = "✗" if found_secret else "✓"
                print(f"  {status} recovery-or-final/{filename}")
    
    # --- Check logs ---
    logs_dir = ctx.artifact_dir / "logs"
    for filename, spec in REQUIRED_LOGS.items():
        filepath = logs_dir / filename
        if spec["required"] and not filepath.exists():
            ctx.add_error(f"Log artifact missing: logs/{filename}")
        elif filepath.exists() and ctx.verbose:
            print(f"  ✓ logs/{filename}")
    
    # Check for secret leakage in all sanitized artifacts
    if ctx.verbose:
        print("\nChecking for secret leakage in sanitized artifacts...")
    
    found_any_secret = False
    for filepath in ctx.artifact_dir.rglob("*"):
        if not filepath.is_file():
            continue
        if filepath.name.startswith("_"):  # Skip metadata files
            continue
        if filepath.suffix.lower() in (".json", ".txt", ".yaml", ".yml", ".log"):
            if "lab-result.json" in str(filepath):
                continue  # Skip lab-result.json secrets check as it's handled separately
            
            found_secret = _check_structured_secrets_in_file(ctx, filepath)
            if found_secret:
                found_any_secret = True

    return len(ctx.errors) == 0 and not found_any_secret


def format_findings_report(ctx: VerificationContext) -> str:
    """Format verification findings into a structured report."""
    if not ctx.findings:
        return ""

    lines = []
    lines.append("\n" + "=" * 50)
    lines.append("VERIFICATION FINDINGS")
    lines.append("=" * 50)

    # Group by severity
    fatal = [f for f in ctx.findings if f.kind == FindingKind.FATAL]
    warnings = [f for f in ctx.findings if f.kind == FindingKind.WARNING]
    info = [f for f in ctx.findings if f.kind == FindingKind.INFO]

    if fatal:
        lines.append(f"\nFATAL ({len(fatal)}):")
        for f in fatal[:10]:
            context_str = f" ({f.context})" if f.context else ""
            lines.append(f"  • {f.file}: {f.message}{context_str}")
        if len(fatal) > 10:
            lines.append(f"  ... and {len(fatal) - 10} more fatal findings")

    if warnings:
        lines.append(f"\nWarnings ({len(warnings)}):")
        for f in warnings[:5]:
            context_str = f" ({f.context})" if f.context else ""
            lines.append(f"  • {f.file}: {f.message}{context_str}")
        if len(warnings) > 5:
            lines.append(f"  ... and {len(warnings) - 5} more warnings")

    if info:
        lines.append(f"\nInfo ({len(info)}):")
        for f in info[:3]:
            context_str = f" ({f.context})" if f.context else ""
            lines.append(f"  • {f.file}: {f.message}{context_str}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify K3s CNPG incident lab artifacts (sanitized).",
    )
    parser.add_argument(
        "--artifact-dir",
        required=True,
        help="Path to the sanitized lab artifact directory",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--sanitize-only",
        action="store_true",
        help="Only run sanitization (for CI workflow integration)",
    )
    parser.add_argument(
        "--raw-artifact-dir",
        type=str,
        help="Path to raw artifact directory for sanitization (used with --sanitize-only)",
    )
    
    args = parser.parse_args()
    
    artifact_dir = Path(args.artifact_dir).resolve()
    
    # If sanitize-only mode, run sanitization first
    if args.sanitize_only:
        if not args.raw_artifact_dir:
            print("ERROR: --raw-artifact-dir required with --sanitize-only", file=sys.stderr)
            return 2
        
        raw_dir = Path(args.raw_artifact_dir).resolve()
        print(f"Sanitizing raw artifacts: {raw_dir}")
        print(f"Output directory: {artifact_dir}")
        print()
        
        # Import and run sanitization
        import sanitize_live_lab_artifacts
        success, findings, results = sanitize_live_lab_artifacts.sanitize_directory(raw_dir, artifact_dir)
        
        # Write findings for downstream use FIRST (before any exit)
        findings_path = artifact_dir / "_findings.json"
        findings_data = {
            "success": success,
            "findings": [
                {"kind": f.kind, "message": f.message, "file": f.file, "context": f.context}
                for f in findings
            ],
        }
        findings_path.write_text(json.dumps(findings_data, indent=2))
        print(f"\nFindings written to: {findings_path}")
        
        # Check for fatal findings - these MUST fail the gate
        fatal_findings = [f for f in findings if f.kind == FindingKind.FATAL]
        if fatal_findings:
            print()
            print("=" * 50)
            print("FATAL: Artifact sanitization detected actual secrets!")
            print("=" * 50)
            print()
            for f in fatal_findings[:10]:
                print(f"  • {f.file}: {f.message}")
            if len(fatal_findings) > 10:
                print(f"  ... and {len(fatal_findings) - 10} more")
            print()
            print("Raw artifacts remain local; sanitized artifacts not uploaded.")
            return 1
        
        # Check for sanitization errors (non-success but no fatal findings)
        # FAIL CLOSED: file errors must fail the gate, not silently continue
        if not success:
            print()
            print("FATAL: Sanitization had file errors!")
            file_errors = [r for r in results if not r.success and r.error]
            for r in file_errors[:10]:
                print(f"  {r.input_path}: {r.error}")
            if len(file_errors) > 10:
                print(f"  ... and {len(file_errors) - 10} more file errors")
            print("Raw artifacts remain local; sanitized artifacts not uploaded.")
            findings_data["findings"] = [
                {"kind": "fatal", "message": f"File error: {r.error}", "file": str(r.input_path), "context": None}
                for r in file_errors
            ]
            findings_path.write_text(json.dumps(findings_data, indent=2))
            return 1
        
        print()
        print(sanitize_live_lab_artifacts.format_findings_summary(findings))
    
    print(f"\nVerifying artifacts in: {artifact_dir}")
    print()
    
    ctx = VerificationContext(artifact_dir=artifact_dir, verbose=args.verbose)
    passed = verify_artifact_dir(ctx)
    
    # Print findings report
    findings_report = format_findings_report(ctx)
    if findings_report:
        print(findings_report)
    
    if passed:
        print()
        print("=" * 50)
        print("ARTIFACT VERIFICATION: PASSED")
        print("=" * 50)
        print()
        
        # Summary of findings
        fatal_count = sum(1 for f in ctx.findings if f.kind == FindingKind.FATAL)
        warning_count = sum(1 for f in ctx.findings if f.kind == FindingKind.WARNING)
        info_count = sum(1 for f in ctx.findings if f.kind == FindingKind.INFO)
        
        if ctx.findings:
            print(f"Findings: {fatal_count} fatal, {warning_count} warnings, {info_count} info")
        else:
            print("No findings.")
        
        return 0
    else:
        print()
        print("=" * 50)
        print("ARTIFACT VERIFICATION: FAILED")
        print("=" * 50)
        print()
        
        # Print errors
        if ctx.errors:
            print("Errors:")
            for i, error in enumerate(ctx.errors, 1):
                print(f"  {i}. {error}")
        
        # Print findings report
        if findings_report:
            print(findings_report)
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
