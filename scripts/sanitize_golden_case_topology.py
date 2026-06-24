#!/usr/bin/env python3
"""
sanitize_golden_case_topology.py

Sanitize internal topology information from golden case evidence files.

This script:
- Normalizes RFC1918 private IPs to <PRIVATE_IP>
- Normalizes Kubernetes node names to <K8S_NODE>
- Normalizes internal registry/local domains to <REGISTRY_HOST>
- Normalizes internal namespace names to <LAB_NAMESPACE>
- Cleans up sanitizer-findings.json path metadata

This script is idempotent: running it multiple times produces the same result.

Usage:
    python scripts/sanitize_golden_case_topology.py fixtures/diagnosis-golden-cases/pod-failure-readiness
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def sanitize_file_content(content: str) -> str:
    """Sanitize internal topology from file content."""
    # Normalize RFC1918 private IPs (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    content = re.sub(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "<PRIVATE_IP>", content)
    content = re.sub(r"\b172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}\b", "<PRIVATE_IP>", content)
    content = re.sub(r"\b192\.168\.\d{1,3}\.\d{1,3}\b", "<PRIVATE_IP>", content)
    
    # Normalize Kubernetes node names (k3s-worker-*, k3s-master-*)
    content = re.sub(r"\bk3s-master-\d+\b", "<K8S_NODE>", content)
    content = re.sub(r"\bk3s-worker-\d+\b", "<K8S_NODE>", content)
    
    # Normalize internal registry/local domains
    content = re.sub(r"\bharbor-[a-z0-9-]+\.spbnix\.local\b", "<REGISTRY_HOST>", content, flags=re.IGNORECASE)
    content = re.sub(r"\bregistry\.spbnix\.com\b", "<REGISTRY_HOST>", content, flags=re.IGNORECASE)
    content = re.sub(r"\b[a-z0-9-]+\.spbnix\.local\b", "<INTERNAL_DOMAIN>", content, flags=re.IGNORECASE)
    
    # Normalize internal namespace names (k9b-cnpg-lab-*)
    content = re.sub(r"\bk9b-cnpg-lab-\d+\b", "<LAB_NAMESPACE>", content)
    
    # Normalize namespace in error messages: podname_namespacename(uid) format
    # e.g., k9b-scheduler-xxx_k9b-cnpg-lab-12345678(uid)
    content = re.sub(r"_k9b-cnpg-lab-\d+", "_<LAB_NAMESPACE>", content)
    
    return content


def sanitize_text_file(file_path: Path) -> bool:
    """Sanitize a text file in place. Returns True if modified."""
    content = file_path.read_text(encoding="utf-8")
    original = content
    content = sanitize_file_content(content)
    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def sanitize_json_file(file_path: Path) -> bool:
    """Sanitize a JSON file in place. Returns True if modified."""
    content = file_path.read_text(encoding="utf-8")
    original = content
    
    # Handle the sanitizer-findings.json specially
    if file_path.name == "sanitizer-findings.json":
        try:
            data = json.loads(content)
            # Redact raw artifact path metadata (only if not already redacted)
            if data.get("input_dir") and "REDACTED" not in str(data.get("input_dir", "")):
                data["input_dir"] = "<REDACTED_RAW_ARTIFACT_DIR>"
            if data.get("output_dir") and "SANITIZED" not in str(data.get("output_dir", "")):
                data["output_dir"] = "<SANITIZED_ARTIFACT_DIR>"
            # Add topology sanitized flag only once
            if not data.get("topology_sanitized"):
                data["topology_sanitized"] = True
                # Add note only if not already present
                note = data.get("note", "")
                if "Internal topology sanitized" not in note:
                    data["note"] = note + " Internal topology sanitized for golden case."
            content = json.dumps(data, indent=2)
        except json.JSONDecodeError:
            # Fall back to text sanitization
            content = sanitize_file_content(content)
    else:
        content = sanitize_file_content(content)
    
    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def sanitize_yaml_file(file_path: Path) -> bool:
    """Sanitize a YAML file in place. Returns True if modified."""
    content = file_path.read_text(encoding="utf-8")
    original = content
    content = sanitize_file_content(content)
    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def sanitize_directory(case_dir: Path) -> tuple[int, int]:
    """Sanitize all evidence files in the golden case directory.
    
    Returns (files_modified, files_checked).
    """
    modified = 0
    checked = 0
    
    # Files to sanitize
    patterns = [
        "*.txt",
        "*.json",
        "*.yaml",
        "*.yml",
    ]
    
    for pattern in patterns:
        for file_path in case_dir.rglob(pattern):
            checked += 1
            if file_path.suffix in (".json",):
                if sanitize_json_file(file_path):
                    modified += 1
                    print(f"  Sanitized: {file_path.relative_to(case_dir)}")
            elif file_path.suffix in (".yaml", ".yml", ".txt"):
                if sanitize_text_file(file_path):
                    modified += 1
                    print(f"  Sanitized: {file_path.relative_to(case_dir)}")
    
    return modified, checked


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanitize internal topology from golden case evidence files.",
    )
    parser.add_argument(
        "case_dir",
        type=Path,
        help="Path to golden case directory",
    )
    
    args = parser.parse_args()
    
    if not args.case_dir.exists():
        print(f"ERROR: Directory does not exist: {args.case_dir}", file=sys.stderr)
        return 1
    
    if not args.case_dir.is_dir():
        print(f"ERROR: Path is not a directory: {args.case_dir}", file=sys.stderr)
        return 1
    
    print(f"Sanitizing golden case topology: {args.case_dir}")
    print()
    
    modified, checked = sanitize_directory(args.case_dir)
    
    print()
    print(f"Summary: {modified}/{checked} files sanitized")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
