"""Main verification orchestration for OTel demo lab contract verification."""

from __future__ import annotations

from pathlib import Path

from scripts.otel_lab_contracts.lab_result import verify_lab_result
from scripts.otel_lab_contracts.models import OtelTracesMode, VerificationReport
from scripts.otel_lab_contracts.otel_traces import verify_otel_traces
from scripts.otel_lab_contracts.p3c_discovery import verify_p3c_discovery
from scripts.otel_lab_contracts.p4c_diagnosis import verify_p4c_diagnosis
from scripts.otel_lab_contracts.runtime_passes import verify_runtime_loop_passes
from scripts.otel_lab_contracts.sensitive_scan import scan_for_sensitive_payloads


def verify_live_lab_contracts(
    artifact_dir: Path,
    scenario: str,
    require_lab_passed: bool,
    otel_traces_mode: OtelTracesMode,
) -> VerificationReport:
    """Run all contract verifications for a live-lab run."""
    report = VerificationReport(passed=True)

    # Phase 0: Lab result
    verify_lab_result(artifact_dir, require_lab_passed, report)

    # Phase 1: Sensitive payload scan (runs on all artifacts)
    scan_for_sensitive_payloads(artifact_dir, report)

    if scenario == "unschedulable-shipping":
        # Phase 2: P3c discovery
        verify_p3c_discovery(artifact_dir, report)

        # Phase 3: P4c diagnosis
        verify_p4c_diagnosis(artifact_dir, report)

        # Phase 4: Runtime loop passes
        verify_runtime_loop_passes(artifact_dir, report)

    # Phase 5: OTel traces
    verify_otel_traces(artifact_dir, otel_traces_mode, report)

    return report
