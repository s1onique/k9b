#!/usr/bin/env python3
"""Diagnosis oracle verifier for OpenTelemetry Demo Lab.

This module validates that:
1. Baseline readiness artifacts are present
2. Incident injection evidence is captured
3. Diagnosis correctly identifies recommendationservice and feature flag issue
4. No forbidden mutations or remediations were attempted

For LLM-friendly reading, see companion modules:
- k9b_otel_demo_lab_verify_baseline.py - baseline verification
- k9b_otel_demo_lab_verify_injection.py - injection verification
- k9b_otel_demo_lab_verify_diagnosis.py - diagnosis verification
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .k9b_otel_demo_lab_constants import (
    FAILURE_BASELINE_NOT_READY,
    FAILURE_DIAGNOSIS_GENERIC_POD_CRASH,
    FAILURE_DIAGNOSIS_MISSING_FLAG_EVIDENCE,
    FAILURE_DIAGNOSIS_MISSING_RECOMMENDATIONSERVICE_EVIDENCE,
    FAILURE_DIAGNOSIS_WRONG_COMPONENT,
    FAILURE_INJECTION_FAILED,
    FAILURE_MUTATION_DETECTED,
    FAILURE_REMEDIATION_ATTEMPTED,
)
from .k9b_otel_demo_lab_verify_baseline import verify_baseline as _verify_baseline
from .k9b_otel_demo_lab_verify_diagnosis import verify_diagnosis as _verify_diagnosis
from .k9b_otel_demo_lab_verify_injection import verify_injection as _verify_injection


@dataclass
class VerificationResult:
    """Result of verification."""
    
    passed: bool
    failure_classes: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    recommendationservice_found: bool = False
    feature_flag_evidence_found: bool = False
    mutation_detected: bool = False
    remediation_attempted: bool = False


def verify_otel_demo_lab(
    artifact_dir: Path,
    include_baseline: bool = True,
    include_injection: bool = True,
    include_diagnosis: bool = True,
) -> VerificationResult:
    """Verify the complete OTel Demo lab run."""
    failure_classes: list[str] = []
    details: dict[str, Any] = {}
    recommendationservice_found = False
    feature_flag_evidence_found = False
    mutation_detected = False
    remediation_attempted = False
    
    # Phase 1: Verify baseline readiness
    if include_baseline:
        baseline_result = _verify_baseline(artifact_dir)
        details["baseline"] = baseline_result
        if not baseline_result.get("passed", False):
            failure_classes.append(FAILURE_BASELINE_NOT_READY)
    
    # Phase 2: Verify incident injection
    if include_injection:
        injection_result = _verify_injection(artifact_dir)
        details["injection"] = injection_result
        if not injection_result.get("passed", False):
            failure_classes.append(FAILURE_INJECTION_FAILED)
        if not injection_result.get("recommendationservice_evidence", False):
            failure_classes.append(FAILURE_DIAGNOSIS_MISSING_RECOMMENDATIONSERVICE_EVIDENCE)
        if injection_result.get("recommendationservice_evidence", False):
            recommendationservice_found = True
    
    # Phase 3: Verify diagnosis
    if include_diagnosis:
        diagnosis_result = _verify_diagnosis(artifact_dir)
        details["diagnosis"] = diagnosis_result
        
        if diagnosis_result.get("wrong_component", False):
            failure_classes.append(FAILURE_DIAGNOSIS_WRONG_COMPONENT)
        
        if diagnosis_result.get("missing_flag_evidence", False):
            failure_classes.append(FAILURE_DIAGNOSIS_MISSING_FLAG_EVIDENCE)
        
        if diagnosis_result.get("generic_pod_crash", False):
            failure_classes.append(FAILURE_DIAGNOSIS_GENERIC_POD_CRASH)
        
        recommendationservice_found = recommendationservice_found or diagnosis_result.get("recommendationservice_mentioned", False)
        feature_flag_evidence_found = diagnosis_result.get("feature_flag_evidence_found", False)
        mutation_detected = diagnosis_result.get("mutation_detected", False)
        remediation_attempted = diagnosis_result.get("remediation_attempted", False)
        
        if mutation_detected:
            failure_classes.append(FAILURE_MUTATION_DETECTED)
        
        if remediation_attempted:
            failure_classes.append(FAILURE_REMEDIATION_ATTEMPTED)
    
    passed = len(failure_classes) == 0
    
    return VerificationResult(
        passed=passed,
        failure_classes=failure_classes,
        details=details,
        recommendationservice_found=recommendationservice_found,
        feature_flag_evidence_found=feature_flag_evidence_found,
        mutation_detected=mutation_detected,
        remediation_attempted=remediation_attempted,
    )


def verify_pass_fixture(artifact_dir: Path) -> VerificationResult:
    """Verify a passing fixture for testing."""
    return verify_otel_demo_lab(artifact_dir)


def verify_fail_no_recommendationservice(artifact_dir: Path) -> VerificationResult:
    """Verify that a diagnosis missing recommendationservice fails."""
    result = verify_otel_demo_lab(artifact_dir)
    expected_failures = [FAILURE_DIAGNOSIS_WRONG_COMPONENT, FAILURE_DIAGNOSIS_GENERIC_POD_CRASH]
    if not any(f in expected_failures for f in result.failure_classes):
        result.failure_classes.append(FAILURE_DIAGNOSIS_GENERIC_POD_CRASH)
    result.passed = False
    return result


def verify_fail_missing_flag_evidence(artifact_dir: Path) -> VerificationResult:
    """Verify that a diagnosis missing flag evidence fails."""
    result = verify_otel_demo_lab(artifact_dir)
    if FAILURE_DIAGNOSIS_MISSING_FLAG_EVIDENCE not in result.failure_classes:
        result.failure_classes.append(FAILURE_DIAGNOSIS_MISSING_FLAG_EVIDENCE)
    result.passed = False
    return result


def verify_fail_mutation(artifact_dir: Path) -> VerificationResult:
    """Verify that a diagnosis with mutations fails."""
    result = verify_otel_demo_lab(artifact_dir)
    if not result.mutation_detected:
        result.failure_classes.append(FAILURE_MUTATION_DETECTED)
    result.passed = False
    return result


# CLI entry point
def main() -> int:
    """CLI entry point for verification."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Verify OTel Demo lab artifacts")
    parser.add_argument("--artifact-dir", required=True, help="Root artifact directory")
    parser.add_argument("--mode", choices=["scaffold", "live"], default="scaffold",
                       help="Verification mode: scaffold or live (default: scaffold)")
    parser.add_argument("--fixture", choices=["pass", "fail-no-recommendationservice", "fail-missing-flag", "fail-mutation"],
                       help="Fixture type to verify")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    
    args = parser.parse_args()
    artifact_dir = Path(args.artifact_dir)
    
    if args.mode == "live":
        from .k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        live_result = verify_otel_demo_lab_live(artifact_dir)
        result = VerificationResult(
            passed=live_result["passed"],
            failure_classes=live_result["failure_classes"],
            details=live_result["details"],
            recommendationservice_found=live_result.get("recommendationservice_found", False),
            feature_flag_evidence_found=live_result.get("flag_enabled", False),
        )
    elif args.fixture == "pass":
        result = verify_pass_fixture(artifact_dir)
    elif args.fixture == "fail-no-recommendationservice":
        result = verify_fail_no_recommendationservice(artifact_dir)
    elif args.fixture == "fail-missing-flag":
        result = verify_fail_missing_flag_evidence(artifact_dir)
    elif args.fixture == "fail-mutation":
        result = verify_fail_mutation(artifact_dir)
    else:
        result = verify_otel_demo_lab(artifact_dir)
    
    if args.json:
        print(json.dumps({
            "passed": result.passed,
            "failure_classes": result.failure_classes,
            "details": result.details,
            "mode": args.mode,
        }, indent=2))
    else:
        if result.passed:
            print(f"VERIFICATION PASSED (mode={args.mode})")
        else:
            print(f"VERIFICATION FAILED: {', '.join(result.failure_classes)} (mode={args.mode})")
            print("\nDetails:")
            print(json.dumps(result.details, indent=2))
    
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
