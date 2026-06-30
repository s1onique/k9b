"""Lab result verification for OTel demo lab contract verification."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.otel_lab_contracts.models import ContractCheck, VerificationReport


def verify_lab_result(artifact_dir: Path, require_passed: bool, report: VerificationReport) -> bool:
    """Verify lab-result.json exists and indicates success."""
    lab_result_path = artifact_dir / "lab-result.json"

    if not lab_result_path.exists():
        report.add_error(f"lab-result.json not found at {lab_result_path}")
        return False

    try:
        lab_result = json.loads(lab_result_path.read_text())
    except json.JSONDecodeError as e:
        report.add_error(f"lab-result.json is malformed JSON: {e}")
        return False

    # Check for success field using key-presence order (not `or`, which skips False)
    # This ensures `{"success": false}` is detected as a failure, not as missing
    if "success" in lab_result:
        success_field = lab_result["success"]
    elif "status" in lab_result:
        success_field = lab_result["status"]
    elif "outcome" in lab_result:
        success_field = lab_result["outcome"]
    else:
        report.add_error("lab-result.json missing success/status/outcome field")
        return False

    # Normalize success value
    success_values = {"true", "passed", "success", "ok"}
    is_success = str(success_field).lower() in success_values

    if require_passed and not is_success:
        report.add_error(f"lab-result.json indicates failure: success={lab_result.get('success')}, status={lab_result.get('status')}, outcome={lab_result.get('outcome')}")
        return False

    report.add_check(
        ContractCheck(
            name="lab_result",
            passed=True,
            phase="lab",
            reason="lab_passed" if is_success else "lab_skipped",
            details={"success_field": success_field},
        )
    )
    return True
