"""P4c diagnosis outcome computation for OTel demo backend contract checks."""

from __future__ import annotations

from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contract_types import P4cDiagnosisOutcome


def _check_terminal_mode_scheduling_markers(evidence: dict[str, Any]) -> list[str]:
    """Check for scheduling markers in terminal mode evidence.

    For terminal no-checks single-pass, scheduling evidence comes from
    deterministic K8s evidence (P2b injection, P3c discovery) rather than
    diagnosis prose.

    Args:
        evidence: Diagnosis evidence dict

    Returns:
        List of scheduling markers found
    """
    found: list[str] = []
    SCHEDULING_MARKERS = ["FailedScheduling", "Unschedulable", "nodeSelector", "no matching node"]

    # Check p4c_verdict for matched evidence
    p4c_verdict = evidence.get("p4c_verdict", {})
    if isinstance(p4c_verdict, dict):
        matched = p4c_verdict.get("matched_evidence", [])
        if isinstance(matched, list):
            found.extend(matched)

    # Check root_cause_summary
    root_cause_summary = str(evidence.get("root_cause_summary", "")).lower()
    for marker in SCHEDULING_MARKERS:
        if marker.lower() in root_cause_summary:
            found.append(marker)

    # Check detection evidence
    detection_evidence = evidence.get("detection_evidence", {})
    if isinstance(detection_evidence, dict):
        summary = str(detection_evidence.get("summary", "")).lower()
        for marker in SCHEDULING_MARKERS:
            if marker.lower() in summary:
                found.append(marker)

    # Deduplicate
    return list(dict.fromkeys(found))


def _diagnosis_used_simulation(pass_run_ids: tuple[str, ...]) -> bool:
    """Check if any pass run ID indicates simulation was used.

    Simulation pass IDs follow the pattern 'sim-{incident_id[:8]}-pass{N}'.
    Even if simulation_used flag is not set, checking pass_run_ids provides
    an additional guard against simulated diagnosis being treated as success.

    Args:
        pass_run_ids: Tuple of pass run IDs

    Returns:
        True if any pass_run_id starts with 'sim-'
    """
    return any(str(rid).startswith("sim-") for rid in pass_run_ids)


def compute_p4c_outcome(
    evidence: dict[str, Any],
    *,
    scenario: str | None = None,
    accept_terminal_single_pass: bool = False,
    min_required_passes: int = 2,
    require_root_cause_terms: bool = True,
) -> P4cDiagnosisOutcome:
    """Compute the normalized P4c outcome from diagnosis evidence.

    This function is the SINGLE AUTHORITATIVE SOURCE for P4c outcome classification.
    All downstream validation and lab-result rendering must use the returned
    P4cDiagnosisOutcome instead of re-checking evidence fields.

    LAB-STRICT MODE (default, accept_terminal_single_pass=False):
        - Terminal single-pass before required passes is a FAILURE
        - P4c must demonstrate >= min_required_passes observable passes
        - Root-cause evidence for scheduling root cause is required
        - Scenario manifest grades determine pass/fail for causal-level diagnosis

    PRODUCT MODE (accept_terminal_single_pass=True):
        - Terminal single-pass with all requirements met is SUCCESS
        - Useful for contexts where single-pass diagnosis is acceptable

    Args:
        evidence: Diagnosis evidence dict from phase_p4c_verify_k8s_mult_pass_diagnosis
        scenario: Scenario name for manifest-based diagnosis grade validation.
            When provided, the manifest's evaluate_diagnosis_grade() is used to
            determine if the diagnosis reached causal-level or exact-root-cause.
        accept_terminal_single_pass: If True, allow terminal single-pass as success
            (for product-mode compatibility). If False (default, lab-strict mode),
            terminal single-pass before required passes is treated as failure.
        min_required_passes: Minimum passes required for multipass mode (default: 2).
        require_root_cause_terms: If True (default), require specific root cause
            prose terms in addition to manifest grade validation.

    Returns:
        P4cDiagnosisOutcome with the definitive success/failure determination
    """
    # Import here to avoid circular imports at module level
    from scripts.k9b_otel_demo_lab_scenario_truth_manifest import (
        DiagnosisGrade,
        EvidencePipelineFailure,
        evaluate_diagnosis_grade,
        get_scenario_manifest,
    )

    # Get scenario manifest for diagnosis grade evaluation
    # FAIL CLOSED: Unknown scenario names must not silently disable manifest authority
    manifest = None
    unknown_scenario: str | None = None
    if scenario:
        manifest = get_scenario_manifest(scenario)
        if manifest is None:
            unknown_scenario = scenario
    incident_id = evidence.get("incident_id", "")
    pass_count = evidence.get("pass_count", 0)
    pass_run_ids_raw = evidence.get("pass_run_ids", [])
    pass_run_ids = tuple(str(r) for r in pass_run_ids_raw if r)

    # STRICT: Simulation diagnosis must NOT satisfy the live-lab phase contract.
    # Check both the simulation_used flag and pass_run_ids for simulation markers.
    simulation_used_flag = evidence.get("simulation_used", False)
    simulation_via_pass_ids = _diagnosis_used_simulation(pass_run_ids)

    if simulation_used_flag or simulation_via_pass_ids:
        return P4cDiagnosisOutcome(
            success=False,
            mode="multipass",
            incident_id=incident_id,
            pass_count=pass_count,
            pass_run_ids=pass_run_ids,
            review_artifact_paths=(),
            terminal_decision=None,
            read_only_constraints_satisfied=False,
            root_cause_evidence_satisfied=False,
            root_cause_evidence_reason="simulation_used_but_not_allowed",
            failure_reasons=("simulation_used_but_not_allowed",),
        )

    terminal_no_checks_accepted = evidence.get("terminal_no_checks_accepted", False)
    terminal_decision = evidence.get("terminal_decision_reached")

    # Review artifact paths
    # EVIDENCE PRESERVATION: Include accumulated review_artifact_paths from all passes.
    # This is the fallback observable pass evidence when pass_run_ids are not available.
    # The runner accumulates review artifacts from each targeted-diagnosis pass.
    review_paths_raw: list[str] = []
    # Include single review_packet_path if present
    if evidence.get("review_packet_path"):
        review_paths_raw.append(str(evidence["review_packet_path"]))
    # Include accumulated review_artifact_paths from all passes (deduplicated)
    accumulated_paths = evidence.get("review_artifact_paths", [])
    for path in accumulated_paths:
        if path and path not in review_paths_raw:
            review_paths_raw.append(path)
    review_artifact_paths = tuple(review_paths_raw)

    # Read-only constraints
    read_only = evidence.get("read_only", True)
    read_only_violations = evidence.get("read_only_violations", [])
    read_only_constraints_satisfied = read_only and len(read_only_violations) == 0

    # Root cause evidence
    root_cause_summary = str(evidence.get("root_cause_summary", ""))

    # Collect failure reasons
    failure_reasons: list[str] = []

    # FAIL CLOSED: Unknown scenario names fail the outcome
    if unknown_scenario:
        failure_reasons.append(f"unknown_scenario_manifest:{unknown_scenario}")

    # Determine mode and validate
    # CONTRACT: terminal_single_pass mode requires accept_terminal_single_pass=True
    # - accept_terminal_single_pass=True → terminal_single_pass may succeed
    # - accept_terminal_single_pass=False and pass_count < required → premature_terminal_no_checks
    # - accept_terminal_single_pass=False and pass_count >= required → multipass
    if terminal_no_checks_accepted and pass_count >= 1 and evidence.get("real_pass_artifacts_found"):
        if accept_terminal_single_pass:
            # PRODUCT MODE: Terminal single-pass is acceptable
            # STRICT: terminal_decision must be stop_no_checks_proposed
            if terminal_decision is None:
                failure_reasons.append("terminal_decision_missing")
            elif terminal_decision != "stop_no_checks_proposed":
                failure_reasons.append(f"terminal_decision_unexpected:{terminal_decision}")

            # For terminal mode, pass_run_ids should come from review artifact if not set
            if not pass_run_ids:
                review = evidence.get("backend_incident_detail", {})
                if not isinstance(review, dict):
                    review = {}
                auto_review = review.get("automatic_diagnosis_review", {}) or {}
                run_id = auto_review.get("run_id")
                if run_id:
                    pass_run_ids = (str(run_id),)
                # Also check for run_id in evidence directly (from phase2)
                if not pass_run_ids and evidence.get("review_available"):
                    # Use a generated run_id based on incident_id if we have a review
                    pass_run_ids = (f"auto-{incident_id}",)

            if not review_artifact_paths and evidence.get("review_packet_path"):
                review_artifact_paths = (str(evidence["review_packet_path"]),)

            # STRICT: terminal mode requires a durable run/artifact reference
            if not pass_run_ids and not review_artifact_paths:
                failure_reasons.append("missing_review_artifact_reference")

            # Read-only is required for terminal mode
            if not read_only_constraints_satisfied:
                failure_reasons.append(f"read_only_contract_violated: {read_only_violations}")

            # Terminal mode doesn't require root_cause_evidence in prose
            # (evidence comes from deterministic K8s markers in p4c_verdict)
            p4c_verdict = evidence.get("p4c_verdict", {})
            if isinstance(p4c_verdict, dict):
                root_cause_evidence_satisfied = p4c_verdict.get("success", False)
            else:
                # Fallback: check scheduling markers in evidence
                scheduling_markers_found = _check_terminal_mode_scheduling_markers(evidence)
                root_cause_evidence_satisfied = len(scheduling_markers_found) > 0

            if not root_cause_evidence_satisfied:
                root_cause_evidence_reason = "missing_scheduling_root_cause_evidence"
                failure_reasons.append(root_cause_evidence_reason)
            else:
                root_cause_evidence_reason = None

            # Terminal single-pass success requires ALL of:
            # - terminal_decision == "stop_no_checks_proposed" (checked above)
            # - durable run/artifact reference (checked above)
            # - read_only_constraints_satisfied (checked above)
            # - root_cause_evidence_satisfied (checked above)
            success = len(failure_reasons) == 0

            return P4cDiagnosisOutcome(
                success=success,
                mode="terminal_single_pass",
                incident_id=incident_id,
                pass_count=pass_count,
                pass_run_ids=pass_run_ids,
                review_artifact_paths=review_artifact_paths,
                terminal_decision=terminal_decision,
                read_only_constraints_satisfied=read_only_constraints_satisfied,
                root_cause_evidence_satisfied=root_cause_evidence_satisfied,
                root_cause_evidence_reason=root_cause_evidence_reason,
                failure_reasons=tuple(failure_reasons),
            )

        # LAB-STRICT: Terminal with accept_terminal_single_pass=False
        # Reject premature termination, but let pass_count >= required fall through to multipass
        if pass_count < min_required_passes:
            # Extract pass_run_ids for the failure response
            if not pass_run_ids:
                review = evidence.get("backend_incident_detail", {})
                if isinstance(review, dict):
                    auto_review = review.get("automatic_diagnosis_review", {}) or {}
                    run_id = auto_review.get("run_id")
                    if run_id:
                        pass_run_ids = (str(run_id),)

            return P4cDiagnosisOutcome(
                success=False,
                mode="premature_terminal_no_checks",
                incident_id=incident_id,
                pass_count=pass_count,
                pass_run_ids=pass_run_ids,
                review_artifact_paths=review_artifact_paths,
                terminal_decision=terminal_decision,
                read_only_constraints_satisfied=read_only_constraints_satisfied,
                root_cause_evidence_satisfied=False,
                root_cause_evidence_reason="premature_terminal_no_checks_before_required_passes",
                failure_reasons=(
                    f"premature_terminal_no_checks: {pass_count} < {min_required_passes}",
                    "missing_multipass_root_cause_confirmation",
                ),
            )

        # pass_count >= min_required_passes: fall through to multipass validation
        # (lab-strict mode treats this as multipass, not terminal_single_pass)

    # Multi-pass mode (only reached when NOT terminal single-pass)
    MIN_REQUIRED = min_required_passes

    if pass_count < MIN_REQUIRED:
        failure_reasons.append(f"insufficient_passes: {pass_count} < {MIN_REQUIRED}")

    if not read_only_constraints_satisfied:
        failure_reasons.append(f"read_only_contract_violated: {read_only_violations}")

    # Ensure review_artifact_paths is populated from backend_incident_detail if not set
    if not review_artifact_paths:
        review = evidence.get("backend_incident_detail", {})
        if isinstance(review, dict):
            auto_review = review.get("automatic_diagnosis_review", {}) or {}
            artifact_name = auto_review.get("artifact_name")
            if artifact_name:
                review_artifact_paths = (f"backend:{artifact_name}",)

    # Root cause evidence from prose terms (only if require_root_cause_terms is True)
    if require_root_cause_terms:
        required_terms = ["shipping", "nodeSelector", "k9b.dev/otel-lab-node"]
        missing_terms = [t for t in required_terms if t.lower() not in root_cause_summary.lower()]

        # Check for scheduling evidence
        scheduling_markers = ["FailedScheduling", "Unschedulable", "nodeSelector", "no matching node"]
        scheduling_found = any(m.lower() in root_cause_summary.lower() for m in scheduling_markers)

        if missing_terms:
            root_cause_evidence_reason = f"missing_root_cause_term: {', '.join(missing_terms)}"
            failure_reasons.append(root_cause_evidence_reason)
            root_cause_evidence_satisfied = False
        elif not scheduling_found:
            root_cause_evidence_reason = "missing_scheduling_root_cause_evidence"
            failure_reasons.append(root_cause_evidence_reason)
            root_cause_evidence_satisfied = False
        else:
            root_cause_evidence_reason = None
            root_cause_evidence_satisfied = True
    else:
        # When root cause terms are not required, check p4c_verdict
        # Only use p4c_verdict if it has a meaningful "success" key
        p4c_verdict = evidence.get("p4c_verdict", {})
        if isinstance(p4c_verdict, dict) and "success" in p4c_verdict:
            root_cause_evidence_satisfied = bool(p4c_verdict.get("success"))
            root_cause_evidence_reason = None if root_cause_evidence_satisfied else "missing_scheduling_root_cause_evidence"
        else:
            root_cause_evidence_satisfied = True
            root_cause_evidence_reason = None

    # MANIFEST AUTHORITY: When scenario manifest is provided, validate diagnosis grade.
    # A scheduling-level diagnosis (without causal root cause) is insufficient.
    if manifest is not None:
        diagnosis_grade = evaluate_diagnosis_grade(evidence, manifest)
        if diagnosis_grade in (DiagnosisGrade.NO_SIGNAL, DiagnosisGrade.SYMPTOM_LEVEL, DiagnosisGrade.SCHEDULING_LEVEL):
            grade_failure = (
                f"{EvidencePipelineFailure.DIAGNOSIS_OUTPUT_IGNORED_ROOT_CAUSE}: "
                f"diagnosis reached {diagnosis_grade}, expected causal_level or exact_root_cause"
            )
            failure_reasons.append(grade_failure)
            if root_cause_evidence_satisfied:
                root_cause_evidence_satisfied = False
                root_cause_evidence_reason = f"insufficient_diagnosis_grade:{diagnosis_grade}"

    success = len(failure_reasons) == 0

    return P4cDiagnosisOutcome(
        success=success,
        mode="multipass",
        incident_id=incident_id,
        pass_count=pass_count,
        pass_run_ids=pass_run_ids,
        review_artifact_paths=review_artifact_paths,
        terminal_decision=terminal_decision,
        read_only_constraints_satisfied=read_only_constraints_satisfied,
        root_cause_evidence_satisfied=root_cause_evidence_satisfied,
        root_cause_evidence_reason=root_cause_evidence_reason,
        failure_reasons=tuple(failure_reasons),
    )


__all__ = [
    "compute_p4c_outcome",
]
