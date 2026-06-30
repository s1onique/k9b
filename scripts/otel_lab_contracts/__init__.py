"""OTel demo lab contract verification package.

This package verifies that the live-lab run produced valid artifacts for:
- P3c: K8s incident discovery
- P4c: K8s multi-pass diagnosis with scheduling root-cause evidence
- Runtime: Loop pass artifacts with safety and budget enforcement
- OTel: Optional trace verification

Re-exports all stable verification functions for backward compatibility.
"""

from scripts.otel_lab_contracts.lab_result import verify_lab_result
from scripts.otel_lab_contracts.models import ContractCheck, OtelTracesMode, VerificationReport
from scripts.otel_lab_contracts.otel_traces import verify_otel_traces
from scripts.otel_lab_contracts.p3c_discovery import verify_p3c_discovery
from scripts.otel_lab_contracts.p4c_diagnosis import verify_p4c_diagnosis
from scripts.otel_lab_contracts.reporting import format_report
from scripts.otel_lab_contracts.runtime_passes import verify_runtime_loop_passes
from scripts.otel_lab_contracts.sensitive_scan import scan_for_sensitive_payloads
from scripts.otel_lab_contracts.verify import verify_live_lab_contracts

__all__ = [
    "ContractCheck",
    "OtelTracesMode",
    "VerificationReport",
    "verify_lab_result",
    "verify_p3c_discovery",
    "verify_p4c_diagnosis",
    "verify_runtime_loop_passes",
    "scan_for_sensitive_payloads",
    "verify_otel_traces",
    "verify_live_lab_contracts",
    "format_report",
]
