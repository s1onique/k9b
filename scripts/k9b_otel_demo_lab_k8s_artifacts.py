#!/usr/bin/env python3
"""Artifact bundle contract verification for K8s-native scenario.

This module provides verification that the K8s-native artifact bundle contains all required artifacts:
- phase2-injected/p2b-k8s-injection/injection-evidence.json
- phase3-discovery/p3c-k8s-discovery/detection-evidence.json
- phase4-diagnosis/p4c-k8s-multipass-diagnosis/diagnosis-evidence.json
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .k9b_otel_demo_lab_constants import (
    K8S_DIAGNOSIS_ARTIFACT_FILENAME,
    K8S_DISCOVERY_ARTIFACT_FILENAME,
    K8S_INJECTION_ARTIFACT_FILENAME,
    PHASE_K8S_DIAGNOSIS_SUBDIR,
    PHASE_K8S_DISCOVERY_SUBDIR,
    PHASE_K8S_INJECTION_SUBDIR,
)


@dataclass
class BundleVerificationResult:
    """Result of K8s-native artifact bundle verification."""

    verified: bool
    p2b_found: bool
    p3c_found: bool
    p4c_found: bool
    p2b_path: str
    p3c_path: str
    p4c_path: str
    reason: str


def verify_k8s_native_bundle(artifact_dir: Path | str) -> BundleVerificationResult:
    """Verify K8s-native artifact bundle contains all required artifacts.

    Args:
        artifact_dir: Root artifact directory containing phase directories.

    Returns:
        BundleVerificationResult with verification status.
    """
    artifact_dir = Path(artifact_dir)

    # Build expected artifact paths
    p2b_path = (
        artifact_dir
        / "phase2-injected"
        / PHASE_K8S_INJECTION_SUBDIR
        / K8S_INJECTION_ARTIFACT_FILENAME
    )
    p3c_path = (
        artifact_dir
        / "phase3-discovery"
        / PHASE_K8S_DISCOVERY_SUBDIR
        / K8S_DISCOVERY_ARTIFACT_FILENAME
    )
    p4c_path = (
        artifact_dir
        / "phase4-diagnosis"
        / PHASE_K8S_DIAGNOSIS_SUBDIR
        / K8S_DIAGNOSIS_ARTIFACT_FILENAME
    )

    # Check each artifact
    p2b_found = p2b_path.exists()
    p3c_found = p3c_path.exists()
    p4c_found = p4c_path.exists()

    all_found = p2b_found and p3c_found and p4c_found

    if all_found:
        return BundleVerificationResult(
            verified=True,
            p2b_found=True,
            p3c_found=True,
            p4c_found=True,
            p2b_path=str(p2b_path),
            p3c_path=str(p3c_path),
            p4c_path=str(p4c_path),
            reason="All K8s-native artifacts present",
        )
    else:
        missing = []
        if not p2b_found:
            missing.append("P2b (injection-evidence.json)")
        if not p3c_found:
            missing.append("P3c (detection-evidence.json)")
        if not p4c_found:
            missing.append("P4c (diagnosis-evidence.json)")

        return BundleVerificationResult(
            verified=False,
            p2b_found=p2b_found,
            p3c_found=p3c_found,
            p4c_found=p4c_found,
            p2b_path=str(p2b_path),
            p3c_path=str(p3c_path),
            p4c_path=str(p4c_path),
            reason=f"Missing artifacts: {', '.join(missing)}",
        )


def main() -> int:
    """CLI entry point for K8s-native artifact bundle verification."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify K8s-native artifact bundle"
    )
    parser.add_argument(
        "--artifact-dir",
        required=True,
        help="Artifact directory containing phase directories",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON format",
    )

    args = parser.parse_args()

    result = verify_k8s_native_bundle(args.artifact_dir)

    if args.json:
        print(
            json.dumps(
                {
                    "verified": result.verified,
                    "p2b_found": result.p2b_found,
                    "p3c_found": result.p3c_found,
                    "p4c_found": result.p4c_found,
                    "p2b_path": result.p2b_path,
                    "p3c_path": result.p3c_path,
                    "p4c_path": result.p4c_path,
                    "reason": result.reason,
                },
                indent=2,
            )
        )
    else:
        print(f"Bundle verification: {'PASS' if result.verified else 'FAIL'}")
        print(f"Reason: {result.reason}")
        print(f"P2b artifact: {result.p2b_path} ({'found' if result.p2b_found else 'missing'})")
        print(f"P3c artifact: {result.p3c_path} ({'found' if result.p3c_found else 'missing'})")
        print(f"P4c artifact: {result.p4c_path} ({'found' if result.p4c_found else 'missing'})")

    return 0 if result.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
