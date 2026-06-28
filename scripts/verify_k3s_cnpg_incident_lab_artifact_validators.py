"""Validators for verify_k3s_cnpg_incident_lab_artifact.

This module contains the verification logic for checking lab artifacts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sanitize_live_lab_artifacts_contract import REDACTION_PLACEHOLDER
from verify_k3s_cnpg_incident_lab_artifact_contract import (
    BENIGN_K8S_PATTERNS,
    REQUIRED_BASELINE,
    REQUIRED_FINAL,
    REQUIRED_INCIDENT,
    REQUIRED_INCIDENT_K9B,
    REQUIRED_LOGS,
    SAFE_K8S_PATTERNS,
    VerificationContext,
)

# Regex patterns for anchored field detection in YAML content
# Using anchored patterns prevents false matches like "metadata:" containing "data:"
_DATA_FIELD_RE = re.compile(r"(?im)^\s*data\s*:")
_STRINGDATA_FIELD_RE = re.compile(r"(?im)^\s*stringData\s*:")
_BINARYDATA_FIELD_RE = re.compile(r"(?im)^\s*binaryData\s*:")

# Pattern for redacted field values (the field followed by <redacted>)
_DATA_REDACTED_RE = re.compile(r"(?im)^\s*data\s*:\s*['\"]?<redacted>['\"]?\s*$")
_STRINGDATA_REDACTED_RE = re.compile(r"(?im)^\s*stringData\s*:\s*['\"]?<redacted>['\"]?\s*$")
_BINARYDATA_REDACTED_RE = re.compile(r"(?im)^\s*binaryData\s*:\s*['\"]?<redacted>['\"]?\s*$")

# Pattern for REDACTION_PLACEHOLDER field values
_DATA_PLACEHOLDER_RE = re.compile(r"(?im)^\s*data\s*:\s*" + REDACTION_PLACEHOLDER.lower() + r"\s*$")
_STRINGDATA_PLACEHOLDER_RE = re.compile(r"(?im)^\s*stringData\s*:\s*" + REDACTION_PLACEHOLDER.lower() + r"\s*$")
_BINARYDATA_PLACEHOLDER_RE = re.compile(r"(?im)^\s*binaryData\s*:\s*" + REDACTION_PLACEHOLDER.lower() + r"\s*$")


def _is_safe_k8s_vocabulary(line: str) -> tuple[bool, str | None]:
    """Check if a line contains safe Kubernetes vocabulary.
    
    Returns (is_safe, matched_pattern_name).
    """
    for pattern in SAFE_K8S_PATTERNS:
        if pattern.search(line):
            return True, pattern.pattern[:30]
    return False, None


def _is_benign_k8s_pattern(content: str) -> bool:
    """Check if content matches known benign Kubernetes patterns."""
    for pattern in BENIGN_K8S_PATTERNS:
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
    from sanitize_live_lab_artifacts_contract import _FATAL_PATTERNS

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
            # This is a Kubernetes Secret manifest - use anchored regex to detect sensitive fields
            # This prevents false matches like "metadata:" containing "data:"
            has_data = _DATA_FIELD_RE.search(content) is not None
            has_stringdata = _STRINGDATA_FIELD_RE.search(content) is not None
            has_binarydata = _BINARYDATA_FIELD_RE.search(content) is not None

            # Secret with data fields - should have been sanitized
            if has_data or has_stringdata or has_binarydata:
                # Check for specific redaction patterns using anchored regex
                # This ensures we match "data: <redacted>" not just "data:" anywhere
                has_data_redacted = (
                    _DATA_REDACTED_RE.search(content) is not None
                    or _DATA_PLACEHOLDER_RE.search(content) is not None
                )
                has_stringdata_redacted = (
                    _STRINGDATA_REDACTED_RE.search(content) is not None
                    or _STRINGDATA_PLACEHOLDER_RE.search(content) is not None
                )
                has_binarydata_redacted = (
                    _BINARYDATA_REDACTED_RE.search(content) is not None
                    or _BINARYDATA_PLACEHOLDER_RE.search(content) is not None
                )

                data_sanitized = (has_data and has_data_redacted) or not has_data
                stringdata_sanitized = (has_stringdata and has_stringdata_redacted) or not has_stringdata
                binarydata_sanitized = (has_binarydata and has_binarydata_redacted) or not has_binarydata

                if data_sanitized and stringdata_sanitized and binarydata_sanitized:
                    if has_data:
                        ctx.add_info("Secret.data sanitized", rel_path)
                    if has_stringdata:
                        ctx.add_info("Secret.stringData sanitized", rel_path)
                    if has_binarydata:
                        ctx.add_info("Secret.binaryData sanitized", rel_path)
                else:
                    ctx.add_fatal("Secret manifest with data field not sanitized", rel_path)
                    found_actual_secret = True
            else:
                ctx.add_info("Secret resource reference (not actual secret value)", rel_path)

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
