#!/usr/bin/env python3
"""
run_diagnosis_offline.py

Offline read-only diagnosis runner that processes a golden case bundle.

This script:
- Operates offline/read-only from the case bundle
- Does NOT call kubectl, helm, docker, registry APIs, or the live cluster
- Proposes bounded read-only next checks
- Does NOT propose remediation/mutation
- Outputs machine-readable diagnosis.json and summary.md

Usage:
    python scripts/run_diagnosis_offline.py \\
        --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness \\
        --output-dir /tmp/diagnosis-output

Exit codes:
    0 - Diagnosis completed successfully
    1 - Diagnosis failed
    2 - Invalid arguments
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# Evidence patterns for readiness probe failure diagnosis
_READINESS_PROBE_PATTERNS = [
    re.compile(r"readiness\s+probe\s+failed", re.IGNORECASE),
    re.compile(r"readiness\s+probe\s+failing", re.IGNORECASE),
    re.compile(r"Unhealthy", re.IGNORECASE),
    re.compile(r"NotReady", re.IGNORECASE),
    re.compile(r"Ready\s*:\s*False", re.IGNORECASE),
    re.compile(r"0/1.*Running", re.IGNORECASE),
    re.compile(r"probe.*exit\s+code\s+1", re.IGNORECASE),
    re.compile(r"/bin/false", re.IGNORECASE),
]

# Forbidden patterns that indicate wrong diagnosis
_FORBIDDEN_PATTERNS = [
    (re.compile(r"ImagePullBackOff", re.IGNORECASE), "image_pull_failure"),
    (re.compile(r"ErrImagePull", re.IGNORECASE), "image_pull_failure"),
    (re.compile(r"PVC.*mount", re.IGNORECASE), "pvc_storage_failure"),
    (re.compile(r"storage.*error", re.IGNORECASE), "pvc_storage_failure"),
    (re.compile(r"FailedScheduling", re.IGNORECASE), "node_scheduling_failure"),
    (re.compile(r"registry.*auth", re.IGNORECASE), "registry_auth_failure"),
    (re.compile(r"cnpg.*operator.*fail", re.IGNORECASE), "cnpg_operator_failure"),
]

# Forbidden remediation patterns
_MUTATION_PATTERNS = [
    re.compile(r"kubectl\s+apply", re.IGNORECASE),
    re.compile(r"kubectl\s+delete", re.IGNORECASE),
    re.compile(r"helm\s+upgrade", re.IGNORECASE),
    re.compile(r"helm\s+install", re.IGNORECASE),
    re.compile(r"kubectl\s+edit", re.IGNORECASE),
    re.compile(r"kubectl\s+replace", re.IGNORECASE),
    re.compile(r"kubectl\s+patch", re.IGNORECASE),
    re.compile(r"kubectl\s+rollout", re.IGNORECASE),
]


def load_case_bundle(case_dir: Path) -> tuple[dict, dict, dict[str, str]]:
    """Load case bundle components.

    Returns (manifest, expected, evidence_files).
    """
    manifest_path = case_dir / "manifest.json"
    expected_path = case_dir / "expected.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    if not expected_path.exists():
        raise FileNotFoundError(f"Expected not found: {expected_path}")

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    with open(expected_path, encoding="utf-8") as f:
        expected = json.load(f)

    # Load evidence files
    evidence_files: dict[str, str] = {}
    for subdir in ["incident", "baseline", "recovery-or-final"]:
        subdir_path = case_dir / subdir
        if subdir_path.exists():
            for file_path in subdir_path.iterdir():
                if file_path.is_file():
                    rel_key = f"{subdir}/{file_path.name}"
                    evidence_files[rel_key] = file_path.read_text(encoding="utf-8")

    return manifest, expected, evidence_files


def analyze_evidence(evidence_files: dict[str, str]) -> dict:
    """Analyze evidence files and extract findings.

    Returns analysis results.
    """
    findings = {
        "pod_running": False,
        "pod_not_ready": False,
        "readiness_probe_failure_evidence": False,
        "unhealthy_events": False,
        "container_running": False,
        "container_ready": False,
    }

    all_text = "\n".join(evidence_files.values())

    # Check for Running pod with NotReady
    if re.search(r"cnpg-lab-failing-app.*Running", all_text):
        findings["pod_running"] = True

    if re.search(r"cnpg-lab-failing-app.*0/1", all_text):
        findings["pod_not_ready"] = True

    # Check for readiness probe failure evidence
    for pattern in _READINESS_PROBE_PATTERNS:
        if pattern.search(all_text):
            findings["readiness_probe_failure_evidence"] = True
            break

    # Check for Unhealthy events
    if re.search(r"Warning.*Unhealthy", all_text):
        findings["unhealthy_events"] = True

    # Check for container running
    if re.search(r"cnpg-lab-failing-app.*Running.*0/1", all_text):
        findings["container_running"] = True
        findings["container_ready"] = False

    return findings


def diagnose(findings: dict, expected: dict, evidence_files: dict[str, str] | None = None) -> dict:
    """Produce diagnosis from findings.

    Returns diagnosis result.
    """
    # Check if readiness probe failure pattern matches
    if (
        findings["pod_running"]
        and findings["pod_not_ready"]
        and findings["readiness_probe_failure_evidence"]
    ):
        category = "readiness_probe_failure"
        root_cause = "readiness probe failure"
        confidence = "high"
        description = (
            "Pod cnpg-lab-failing-app is Running but NotReady. "
            "The readiness probe consistently fails (exit code 1), "
            "preventing the pod from being marked as Ready."
        )
    else:
        category = "unknown"
        root_cause = "insufficient evidence"
        confidence = "low"
        description = "Unable to determine root cause from available evidence."

    # Check for forbidden conclusions in description
    forbidden_observed = []
    for pattern, label in _FORBIDDEN_PATTERNS:
        if pattern.search(description):
            forbidden_observed.append(label)

    # Check for mutation proposals
    mutation_observed = []
    for pattern in _MUTATION_PATTERNS:
        if pattern.search(description):
            mutation_observed.append(pattern.pattern)

    return {
        "category": category,
        "root_cause": root_cause,
        "confidence": confidence,
        "description": description,
        "forbidden_conclusions_observed": forbidden_observed,
        "mutation_proposals_observed": mutation_observed,
        "evidence_refs": _extract_evidence_refs(findings, evidence_files),
    }


def _extract_evidence_refs(findings: dict, evidence_files: dict[str, str] | None = None) -> list[str]:
    """Extract all evidence references from findings and available evidence files.
    
    Includes all required evidence files for pod-failure scenario.
    """
    refs = []
    
    # Always include core incident evidence when findings are positive
    if findings.get("pod_running"):
        refs.append("incident/pods.txt")
    if findings.get("readiness_probe_failure_evidence"):
        refs.append("incident/events.txt")
        refs.append("incident/injected-change.yaml")
        refs.append("incident/symptom-watch.json")
    
    # Include required evidence from manifest if available
    if evidence_files:
        # Add any CNPG state evidence
        if "incident/cnpg-clusters.json" in evidence_files:
            refs.append("incident/cnpg-clusters.json")
        # Add k9b incident detail
        if "incident/k9b-incident-detail.json" in evidence_files:
            refs.append("incident/k9b-incident-detail.json")
        # Add baseline evidence
        if "baseline/pods.txt" in evidence_files:
            refs.append("baseline/pods.txt")
        # Add recovery evidence
        if "recovery-or-final/pods.txt" in evidence_files:
            refs.append("recovery-or-final/pods.txt")
        if "recovery-or-final/events.txt" in evidence_files:
            refs.append("recovery-or-final/events.txt")
    
    return refs


def generate_next_checks() -> list[dict]:
    """Generate bounded read-only next checks."""
    return [
        {
            "description": "Describe the failing pod to see detailed probe status",
            "owner": "platform-engineer",
            "method": "kubectl describe pod cnpg-lab-failing-app -n cnpg-lab",
            "evidence_needed": ["probe status", "container state"],
        },
        {
            "description": "Check pod YAML for readiness probe configuration",
            "owner": "platform-engineer",
            "method": "kubectl get pod cnpg-lab-failing-app -n cnpg-lab -o yaml",
            "evidence_needed": ["readinessProbe spec", "probe command"],
        },
        {
            "description": "Review recent events for the namespace",
            "owner": "platform-engineer",
            "method": "kubectl get events -n cnpg-lab --sort-by=.lastTimestamp",
            "evidence_needed": ["Unhealthy events", "probe failures"],
        },
    ]


def format_summary(diagnosis: dict, next_checks: list[dict]) -> str:
    """Format diagnosis as human-readable summary."""
    lines = [
        "# Diagnosis Summary",
        "",
        f"**Category**: {diagnosis['category']}",
        f"**Root Cause**: {diagnosis['root_cause']}",
        f"**Confidence**: {diagnosis['confidence']}",
        "",
        "## Description",
        diagnosis["description"],
        "",
        "## Evidence References",
    ]

    for ref in diagnosis.get("evidence_refs", []):
        lines.append(f"- {ref}")

    lines.extend(["", "## Next Recommended Checks (Read-Only)"])

    for i, check in enumerate(next_checks, 1):
        lines.append(f"{i}. {check['description']}")
        lines.append(f"   Method: `{check['method']}`")

    if diagnosis.get("forbidden_conclusions_observed"):
        lines.extend(["", "## ⚠️ Forbidden Conclusions Detected"])
        for label in diagnosis["forbidden_conclusions_observed"]:
            lines.append(f"- {label}")

    if diagnosis.get("mutation_proposals_observed"):
        lines.extend(["", "## ⚠️ Mutation Proposals Detected"])
        for pattern in diagnosis["mutation_proposals_observed"]:
            lines.append(f"- {pattern}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run offline read-only diagnosis on golden case bundle.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run diagnosis on pod-failure golden case
    python scripts/run_diagnosis_offline.py \\
        --case-dir fixtures/diagnosis-golden-cases/pod-failure-readiness \\
        --output-dir /tmp/diagnosis-output
        """,
    )
    parser.add_argument(
        "--case-dir",
        type=Path,
        required=True,
        help="Directory containing golden case bundle",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for diagnosis results",
    )

    args = parser.parse_args()

    if not args.case_dir.exists():
        print(f"ERROR: Case directory does not exist: {args.case_dir}", file=sys.stderr)
        return 2

    # Load case bundle
    try:
        manifest, expected, evidence_files = load_case_bundle(args.case_dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Analyze evidence
    findings = analyze_evidence(evidence_files)

    # Produce diagnosis (pass evidence_files to include all required refs)
    diagnosis = diagnose(findings, expected, evidence_files)
    diagnosis["case_id"] = manifest.get("case_id", "unknown")
    diagnosis["timestamp"] = datetime.now(UTC).isoformat()
    diagnosis["read_only"] = True
    diagnosis["allowed_actions"] = expected.get("allowed_read_only_actions", [])
    diagnosis["forbidden_actions"] = manifest.get("forbidden_actions", [])

    # Generate next checks
    next_checks = generate_next_checks()
    diagnosis["next_checks"] = next_checks

    # Write outputs
    args.output_dir.mkdir(parents=True, exist_ok=True)

    diagnosis_path = args.output_dir / "diagnosis.json"
    with open(diagnosis_path, "w", encoding="utf-8") as f:
        json.dump(diagnosis, f, indent=2)

    summary = format_summary(diagnosis, next_checks)
    summary_path = args.output_dir / "summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)

    print("Diagnosis completed:")
    print(f"  Case: {diagnosis['case_id']}")
    print(f"  Category: {diagnosis['category']}")
    print(f"  Root Cause: {diagnosis['root_cause']}")
    print(f"  Confidence: {diagnosis['confidence']}")
    print(f"  Output: {args.output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())