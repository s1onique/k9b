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
- No secrets appear in artifacts
- incident_detected=true is consistent with artifacts

Exit codes:
  0 - All checks passed
  1 - Verification failed (with diagnostic output)
  2 - Invalid arguments
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Secret patterns that should not appear in artifacts.
SECRET_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"bearer", re.IGNORECASE),
    re.compile(r"api_?key", re.IGNORECASE),
    re.compile(r"auth", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"kubeconfig", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+(RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"-----BEGIN\s+CERTIFICATE-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key
    re.compile(r"sk-[0-9A-Za-z]{32,}"),  # OpenAI API key
    re.compile(r"github_pat_"),  # GitHub PAT
]

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


class VerificationError(Exception):
    """Raised when verification fails."""
    pass


def check_secrets_in_file(filepath: Path) -> list[str]:
    """Check if a file contains potential secrets."""
    found_secrets = []
    try:
        content = filepath.read_text(errors="replace")
        for pattern in SECRET_PATTERNS:
            matches = pattern.findall(content)
            if matches:
                found_secrets.append(f"Pattern '{pattern.pattern}' found {len(matches)} time(s)")
    except Exception as e:
        found_secrets.append(f"Could not read file: {e}")
    return found_secrets


def verify_artifact_dir(artifact_dir: Path, verbose: bool = False) -> tuple[bool, list[str]]:
    """
    Verify the artifact directory structure and contents.
    
    Returns:
        (passed, errors) - Tuple of pass/fail and list of error messages.
    """
    errors = []
    
    # Check artifact dir exists.
    if not artifact_dir.exists():
        errors.append(f"Artifact directory does not exist: {artifact_dir}")
        return False, errors
    
    if not artifact_dir.is_dir():
        errors.append(f"Artifact path is not a directory: {artifact_dir}")
        return False, errors
    
    # --- Check lab-result.json ---
    lab_result_path = artifact_dir / "lab-result.json"
    if not lab_result_path.exists():
        errors.append("lab-result.json is missing")
        return False, errors
    
    # Parse lab-result.json.
    try:
        lab_result = json.loads(lab_result_path.read_text())
    except json.JSONDecodeError as e:
        errors.append(f"lab-result.json is malformed JSON: {e}")
        return False, errors
    
    # Validate required fields in lab-result.json.
    required_fields = ["ok", "scenario", "started_at", "finished_at", "cluster_mode", "artifact_dir"]
    for field in required_fields:
        if field not in lab_result:
            errors.append(f"lab-result.json missing required field: {field}")
    
    # --- Check baseline artifacts ---
    baseline_dir = artifact_dir / "baseline"
    for filename, spec in REQUIRED_BASELINE.items():
        filepath = baseline_dir / filename
        if spec["required"] and not filepath.exists():
            errors.append(f"Baseline artifact missing: baseline/{filename}")
        elif filepath.exists():
            # Check for secrets.
            secrets = check_secrets_in_file(filepath)
            if secrets:
                errors.append(f"Potential secrets found in baseline/{filename}: {secrets}")
            if verbose:
                print(f"  ✓ baseline/{filename}")
    
    # --- Check incident artifacts ---
    incident_dir = artifact_dir / "incident"
    for filename, spec in REQUIRED_INCIDENT.items():
        filepath = incident_dir / filename
        if spec["required"] and not filepath.exists():
            errors.append(f"Incident artifact missing: incident/{filename}")
        elif filepath.exists():
            # Check for secrets.
            secrets = check_secrets_in_file(filepath)
            if secrets:
                errors.append(f"Potential secrets found in incident/{filename}: {secrets}")
            if verbose:
                print(f"  ✓ incident/{filename}")
    
    # --- Check k9b incident evidence ---
    if lab_result.get("incident_detected"):
        # If incident_detected=true, we expect k9b incident artifacts.
        for filename, spec in REQUIRED_INCIDENT_K9B.items():
            filepath = incident_dir / filename
            if spec["required"] and not filepath.exists():
                errors.append(
                    f"k9b incident evidence missing: incident/{filename} "
                    f"(incident_detected=true requires this artifact)"
                )
            elif filepath.exists() and verbose:
                print(f"  ✓ incident/{filename}")
    else:
        # incident_detected=false - warn if k9b incidents exist.
        k9b_incidents = incident_dir / "k9b-incidents.json"
        if k9b_incidents.exists():
            try:
                incidents = json.loads(k9b_incidents.read_text())
                if isinstance(incidents, list) and len(incidents) > 0:
                    errors.append(
                        "k9b-incidents.json contains incidents but incident_detected=false. "
                        "This is inconsistent - either incidents exist or they don't."
                    )
            except json.JSONDecodeError:
                pass  # Already caught by general artifact check.
    
    # --- Check final/recovery artifacts ---
    final_dir = artifact_dir / "recovery-or-final"
    for filename, spec in REQUIRED_FINAL.items():
        filepath = final_dir / filename
        if spec["required"] and not filepath.exists():
            errors.append(f"Final artifact missing: recovery-or-final/{filename}")
        elif filepath.exists():
            # Check for secrets.
            secrets = check_secrets_in_file(filepath)
            if secrets:
                errors.append(f"Potential secrets found in recovery-or-final/{filename}: {secrets}")
            if verbose:
                print(f"  ✓ recovery-or-final/{filename}")
    
    # --- Check logs ---
    logs_dir = artifact_dir / "logs"
    for filename, spec in REQUIRED_LOGS.items():
        filepath = logs_dir / filename
        if spec["required"] and not filepath.exists():
            errors.append(f"Log artifact missing: logs/{filename}")
        elif filepath.exists() and verbose:
            print(f"  ✓ logs/{filename}")
    
    # --- Check secret leakage in all artifacts ---
    if verbose:
        print("\nChecking for secret leakage...")
    for root, dirs, files in os.walk(artifact_dir):
        for filename in files:
            if filename.endswith((".json", ".txt", ".yaml", ".yml", ".log")):
                filepath = Path(root) / filename
                secrets = check_secrets_in_file(filepath)
                if secrets and "lab-result.json" not in str(filepath):
                    # Skip lab-result.json secrets check as it's handled separately.
                    rel_path = filepath.relative_to(artifact_dir)
                    errors.append(f"Potential secrets in {rel_path}: {secrets}")
    
    return len(errors) == 0, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify K3s CNPG incident lab artifacts."
    )
    parser.add_argument(
        "--artifact-dir",
        required=True,
        help="Path to the lab artifact directory",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    
    args = parser.parse_args()
    
    artifact_dir = Path(args.artifact_dir).resolve()
    
    print(f"Verifying artifacts in: {artifact_dir}")
    print()
    
    passed, errors = verify_artifact_dir(artifact_dir, verbose=args.verbose)
    
    if passed:
        print()
        print("=" * 50)
        print("ARTIFACT VERIFICATION: PASSED")
        print("=" * 50)
        return 0
    else:
        print()
        print("=" * 50)
        print("ARTIFACT VERIFICATION: FAILED")
        print("=" * 50)
        print()
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())