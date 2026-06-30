"""Runtime loop-pass verification for OTel demo lab contract verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.otel_lab_contracts.constants import (
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_PASSES,
    DEFAULT_MAX_TOTAL_CHECKS,
    REQUIRED_PASS_ARTIFACT_FIELDS,
)
from scripts.otel_lab_contracts.models import ContractCheck, VerificationReport


def find_loop_pass_artifacts(artifact_dir: Path) -> list[Path]:
    """Find loop pass artifacts."""
    loop_passes_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
    if loop_passes_dir.exists():
        return list(loop_passes_dir.glob("*.json"))

    # Fall back to embedded in diagnosis-evidence
    diagnosis_evidence_path = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "diagnosis-evidence.json"
    if diagnosis_evidence_path.exists():
        try:
            evidence = json.loads(diagnosis_evidence_path.read_text())
            if "pass_artifacts" in evidence:
                return [diagnosis_evidence_path]  # Marker to use embedded
        except json.JSONDecodeError:
            pass

    return []


def verify_runtime_loop_passes(artifact_dir: Path, report: VerificationReport) -> bool:
    """Verify runtime loop-pass artifacts.

    For every pass artifact, require:
    - All REQUIRED_PASS_ARTIFACT_FIELDS
    - safety_metadata.policy_enforced == true
    - safety_metadata.mutating_checks_executed_count == 0
    - safety_metadata.sensitive_reads_executed_count == 0
    - len(accepted_checks) == len(check_fingerprints)
    - No rejected check id in accepted_checks
    - gate_summary.rejected_checks exists
    - stop_reason present on final pass
    """
    loop_pass_artifacts = find_loop_pass_artifacts(artifact_dir)

    if not loop_pass_artifacts:
        report.add_error("No loop-pass artifacts found")
        return False

    pass_artifacts: list[dict[str, Any]] = []

    for artifact_path in loop_pass_artifacts:
        try:
            if artifact_path.name.endswith(".json"):
                # Standalone pass artifact
                artifact = json.loads(artifact_path.read_text())
                pass_artifacts.append(artifact)
            else:
                continue
        except (json.JSONDecodeError, OSError) as e:
            report.add_warning(f"Failed to parse {artifact_path}: {e}")
            continue

    # Try embedded pass artifacts
    if not pass_artifacts:
        diagnosis_evidence_path = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "diagnosis-evidence.json"
        if diagnosis_evidence_path.exists():
            try:
                evidence = json.loads(diagnosis_evidence_path.read_text())
                pass_artifacts = evidence.get("pass_artifacts", [])
            except json.JSONDecodeError:
                pass

    if not pass_artifacts:
        report.add_error("No parseable pass artifacts found")
        return False

    # Verify each pass artifact and track failures
    schema_valid = True
    for i, artifact in enumerate(pass_artifacts):
        if not _verify_pass_artifact_schema(artifact, i, report):
            schema_valid = False

    # Check aggregate safety
    total_unsafe = sum(a.get("unsafe_check_count", 0) for a in pass_artifacts)
    total_mutating = sum(a.get("safety_metadata", {}).get("mutating_checks_executed_count", 0) for a in pass_artifacts)
    total_sensitive = sum(a.get("safety_metadata", {}).get("sensitive_reads_executed_count", 0) for a in pass_artifacts)

    if total_mutating > 0:
        report.add_error(f"Runtime: mutating_checks_executed_count > 0: {total_mutating}")
        return False

    if total_sensitive > 0:
        report.add_error(f"Runtime: sensitive_reads_executed_count > 0: {total_sensitive}")
        return False

    if not schema_valid:
        report.add_error("Runtime: One or more pass artifacts failed schema validation")
        return False

    # Verify bounded-loop policy
    bounded_loop_valid = _verify_bounded_loop_policy(pass_artifacts, report)
    if not bounded_loop_valid:
        report.add_error("Runtime: Bounded-loop policy violated")
        return False

    report.add_check(
        ContractCheck(
            name="runtime_loop_passes",
            passed=True,
            phase="runtime",
            reason="passes_valid",
            details={
                "pass_count": len(pass_artifacts),
                "total_unsafe": total_unsafe,
                "total_mutating": total_mutating,
                "total_sensitive": total_sensitive,
            },
        )
    )
    return True


def _normalize_check_identity(check: Any) -> str:
    """Normalize check identity for comparison.

    When checks are dicts, stringification is brittle. Extract canonical
    identity fields and normalize for reliable comparison.

    Returns a normalized string suitable for set operations.
    """
    if isinstance(check, dict):
        # Extract canonical identity fields
        identity_parts = []

        # Primary identifiers (in priority order)
        for key in ["check_id", "id", "name"]:
            val = check.get(key)
            if val is not None:
                identity_parts.append(str(val))

        # Target/kind normalization for structured checks
        target = check.get("target") or check.get("resource") or check.get("object")
        if target:
            identity_parts.append(f"target:{target}")

        kind = check.get("kind") or check.get("type")
        if kind:
            identity_parts.append(f"kind:{kind}")

        # If we have identity parts, join them
        if identity_parts:
            return "|".join(identity_parts)

        # Fall back to sorted string representation
        return json.dumps(check, sort_keys=True)

    return str(check)


def _find_overlap(rejected: list[Any], accepted: list[Any]) -> set[str]:
    """Find rejected check IDs that appear in accepted checks.

    Uses normalized check identity for reliable dict comparison.
    """
    rejected_ids = {_normalize_check_identity(c) for c in rejected}
    accepted_ids = {_normalize_check_identity(c) for c in accepted}
    return rejected_ids & accepted_ids


def _verify_pass_artifact_schema(artifact: dict[str, Any], index: int, report: VerificationReport) -> bool:
    """Verify a single pass artifact has required schema fields."""
    missing_fields = [f for f in REQUIRED_PASS_ARTIFACT_FIELDS if f not in artifact]

    if missing_fields:
        report.add_error(f"Pass artifact {index}: missing required fields: {missing_fields}")
        return False

    # Verify safety_metadata
    safety_metadata = artifact.get("safety_metadata", {})
    if safety_metadata.get("policy_enforced") is not True:
        report.add_error(f"Pass artifact {index}: safety_metadata.policy_enforced != True")
        return False

    if safety_metadata.get("mutating_checks_executed_count", 0) > 0:
        report.add_error(f"Pass artifact {index}: mutating_checks_executed_count > 0")
        return False

    if safety_metadata.get("sensitive_reads_executed_count", 0) > 0:
        report.add_error(f"Pass artifact {index}: sensitive_reads_executed_count > 0")
        return False

    # Verify accepted_checks alignment with check_fingerprints
    accepted_checks = artifact.get("accepted_checks", [])
    check_fingerprints = artifact.get("check_fingerprints", [])

    if len(accepted_checks) != len(check_fingerprints):
        report.add_error(f"Pass artifact {index}: len(accepted_checks)={len(accepted_checks)} != len(check_fingerprints)={len(check_fingerprints)}")
        return False

    # Verify no rejected check in accepted (using normalized identity)
    rejected_checks = artifact.get("rejected_checks", [])
    accepted_ids = accepted_checks
    overlap = _find_overlap(rejected_checks, accepted_ids)

    if overlap:
        report.add_error(f"Pass artifact {index}: rejected check ids in accepted_checks: {overlap}")
        return False

    # Verify gate_summary.rejected_checks exists
    gate_summary = artifact.get("gate_summary", {})
    if "rejected_checks" not in gate_summary:
        report.add_error(f"Pass artifact {index}: gate_summary.rejected_checks missing")
        return False

    # Verify gate_summary.rejected_checks overlap with accepted_checks (normalized)
    gate_rejected = gate_summary.get("rejected_checks", [])
    gate_overlap = _find_overlap(gate_rejected, accepted_ids)
    if gate_overlap:
        report.add_error(f"Pass artifact {index}: gate_summary.rejected_checks in accepted_checks: {gate_overlap}")
        return False

    # Verify stop_reason on final pass
    if artifact.get("should_continue") is False and not artifact.get("stop_reason"):
        report.add_error(f"Pass artifact {index}: should_continue=False but stop_reason missing")
        return False

    # Verify unsafe_check_count is zero (safety contract)
    if artifact.get("unsafe_check_count", 0) > 0:
        report.add_error(f"Pass artifact {index}: unsafe_check_count > 0: {artifact.get('unsafe_check_count')}")
        return False

    return True


def _verify_bounded_loop_policy(pass_artifacts: list[dict[str, Any]], report: VerificationReport) -> bool:
    """Verify bounded-loop policy constraints.

    If policy metadata is absent, use live-lab defaults:
    - max_passes = 2
    - max_checks_per_pass = 2
    - max_total_checks = 4

    Returns True if policy is satisfied, False if violated.
    """
    # Try to extract policy from first pass
    first_pass = pass_artifacts[0] if pass_artifacts else {}
    policy = first_pass.get("policy_metadata", first_pass.get("loop_policy", {}))

    max_passes = policy.get("max_passes") or DEFAULT_MAX_PASSES
    max_checks_per_pass = policy.get("max_checks_per_pass") or DEFAULT_MAX_CHECKS_PER_PASS
    max_total_checks = policy.get("max_total_checks") or DEFAULT_MAX_TOTAL_CHECKS

    violations: list[str] = []

    # Verify pass count
    if len(pass_artifacts) > max_passes:
        violations.append(f"Bounded-loop: pass count {len(pass_artifacts)} > max_passes {max_passes}")

    # Verify total checks
    total_accepted = sum(len(p.get("accepted_checks", [])) for p in pass_artifacts)
    if total_accepted > max_total_checks:
        violations.append(f"Bounded-loop: total accepted checks {total_accepted} > max_total_checks {max_total_checks}")

    # Verify per-pass checks
    for i, pass_art in enumerate(pass_artifacts):
        accepted = len(pass_art.get("accepted_checks", []))
        if accepted > max_checks_per_pass:
            violations.append(f"Bounded-loop: pass {i} accepted {accepted} > max_checks_per_pass {max_checks_per_pass}")

    for violation in violations:
        report.add_error(violation)

    return len(violations) == 0
