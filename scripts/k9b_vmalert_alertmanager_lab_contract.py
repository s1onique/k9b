#!/usr/bin/env python3
"""Contract verification for vmalert→Alertmanager→K9B incident lab.

This module verifies the end-to-end flow:
- vmalert fires a deterministic rule
- Alertmanager receives the alert
- Alertmanager POSTs to K9B webhook
- K9B normalizes and stores the alert signal
- K9B auto-promotes signal to incident
- K9B opens exactly one incident for the lab incident key
- Incident is OPEN, not RESOLVED
- Diagnosis loop can run on alert-backed incident
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class ContractViolation:
    """A single contract violation."""
    contract: str
    message: str
    severity: str = "error"  # error, warning


@dataclass
class ContractVerificationReport:
    """Report of contract verification results."""
    passed: bool = True
    violations: list[ContractViolation] = field(default_factory=list)
    checked_artifacts: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def add_violation(
        self,
        contract: str,
        message: str,
        severity: str = "error",
    ) -> None:
        """Add a contract violation."""
        self.violations.append(ContractViolation(contract, message, severity))
        if severity == "error":
            self.passed = False

    def add_pass(self, contract: str, message: str) -> None:
        """Add a passing check."""
        if contract not in self.details:
            self.details[contract] = []
        self.details[contract].append({"status": "pass", "message": message})

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "violations": [
                {"contract": v.contract, "message": v.message, "severity": v.severity}
                for v in self.violations
            ],
            "checked_artifacts": self.checked_artifacts,
            "details": self.details,
            "timestamp": datetime.now(UTC).isoformat(),
        }


def verify_contract(artifact_dir: Path) -> ContractVerificationReport:
    """Run full contract verification.

    Args:
        artifact_dir: Directory containing lab artifacts

    Returns:
        Verification report
    """
    from k9b_vmalert_alertmanager_lab_contract_checks import (
        verify_alert_signal_artifacts,
        verify_alertmanager_config,
        verify_alertmanager_notification,
        verify_diagnosis_loop,
        verify_incident,
        verify_k9b_webhook_config,
        verify_preflight,
        verify_vmalert_rule,
    )

    report = ContractVerificationReport()

    # Run all verifications
    verifiers = [
        ("preflight", verify_preflight),
        ("vmalert_rule", verify_vmalert_rule),
        ("alertmanager_config", verify_alertmanager_config),
        ("k9b_webhook", verify_k9b_webhook_config),
        ("alertmanager_notification", verify_alertmanager_notification),
        ("alert_signal", verify_alert_signal_artifacts),
        ("incident", verify_incident),
        ("diagnosis_loop", verify_diagnosis_loop),
    ]

    for name, verifier in verifiers:
        try:
            verifier(artifact_dir, report)
            if report.violations:
                for v in report.violations[-10:]:  # Last 10 violations
                    if name in v.contract or any(
                        name in str(v.contract) for _ in [1]
                    ):
                        pass
        except Exception as e:
            report.add_violation(name, f"Verification error: {e}")

    return report


def main() -> int:
    """CLI entry point for contract verification."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify vmalert→Alertmanager→K9B lab contract")
    parser.add_argument(
        "--artifact-dir",
        required=True,
        help="Directory containing lab artifacts",
    )
    parser.add_argument(
        "--output",
        help="Output file for JSON report",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose output",
    )

    args = parser.parse_args()
    artifact_dir = Path(args.artifact_dir)

    if not artifact_dir.exists():
        print(f"ERROR: Artifact directory not found: {artifact_dir}")
        return 1

    report = verify_contract(artifact_dir)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"Report written to: {output_path}")

    if report.passed:
        print("CONTRACT VERIFICATION: PASSED")
        print(f"Checked {len(report.checked_artifacts)} artifact(s)")
        return 0
    else:
        print("CONTRACT VERIFICATION: FAILED")
        print(f"Checked {len(report.checked_artifacts)} artifact(s)")
        print(f"Found {len(report.violations)} violation(s):")
        for v in report.violations:
            prefix = "ERROR" if v.severity == "error" else "WARNING"
            print(f"  [{prefix}] {v.contract}: {v.message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
