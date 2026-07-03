"""Tests for k9b_otel_demo_lab_scenario_truth_manifest module."""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_scenario_truth_manifest import (
    SCENARIO_UNSCHEDULABLE_SHIPPING,
    DiagnosisGrade,
    EvidenceMarkers,
    check_markers_present,
    evaluate_diagnosis_grade,
    get_scenario_manifest,
)


class TestEvaluateDiagnosisGrade:
    """Test evaluate_diagnosis_grade() covering all grade levels."""

    def test_no_incident_is_no_signal(self) -> None:
        """No incident_id means no_signal grade."""
        evidence: dict = {}
        manifest = get_scenario_manifest(SCENARIO_UNSCHEDULABLE_SHIPPING)
        assert manifest is not None
        grade = evaluate_diagnosis_grade(evidence, manifest)
        assert grade == DiagnosisGrade.NO_SIGNAL

    def test_shipping_only_is_symptom_level(self) -> None:
        """Shipping workload without scheduling evidence is symptom_level."""
        evidence = {"incident_id": "inc-001", "summary": "shipping deployment has issues"}
        manifest = get_scenario_manifest(SCENARIO_UNSCHEDULABLE_SHIPPING)
        assert manifest is not None
        grade = evaluate_diagnosis_grade(evidence, manifest)
        assert grade == DiagnosisGrade.SYMPTOM_LEVEL

    def test_failed_scheduling_without_selector_is_scheduling_level(self) -> None:
        """FailedScheduling without nodeSelector specificity is scheduling_level."""
        evidence = {
            "incident_id": "inc-001",
            "summary": "shipping deployment FailedScheduling - pod cannot be scheduled",
        }
        manifest = get_scenario_manifest(SCENARIO_UNSCHEDULABLE_SHIPPING)
        assert manifest is not None
        grade = evaluate_diagnosis_grade(evidence, manifest)
        assert grade == DiagnosisGrade.SCHEDULING_LEVEL

    def test_node_selector_without_key_is_scheduling_level(self) -> None:
        """nodeSelector present but without k9b.dev/otel-lab-node key is scheduling_level."""
        evidence = {
            "incident_id": "inc-001",
            "summary": "shipping deployment FailedScheduling due to nodeSelector mismatch",
        }
        manifest = get_scenario_manifest(SCENARIO_UNSCHEDULABLE_SHIPPING)
        assert manifest is not None
        grade = evaluate_diagnosis_grade(evidence, manifest)
        assert grade == DiagnosisGrade.SCHEDULING_LEVEL

    def test_node_selector_with_key_but_no_value_is_causal_level(self) -> None:
        """nodeSelector with k9b.dev/otel-lab-node key but without 'missing' value is causal_level."""
        evidence = {
            "incident_id": "inc-001",
            "summary": (
                "shipping deployment FailedScheduling: nodeSelector k9b.dev/otel-lab-node "
                "did not match any nodes"
            ),
        }
        manifest = get_scenario_manifest(SCENARIO_UNSCHEDULABLE_SHIPPING)
        assert manifest is not None
        grade = evaluate_diagnosis_grade(evidence, manifest)
        assert grade == DiagnosisGrade.CAUSAL_LEVEL

    def test_exact_root_cause_is_exact(self) -> None:
        """nodeSelector with k9b.dev/otel-lab-node=missing is exact_root_cause."""
        evidence = {
            "incident_id": "inc-001",
            "summary": (
                "shipping deployment FailedScheduling: nodeSelector "
                "k9b.dev/otel-lab-node=missing - no matching node found"
            ),
        }
        manifest = get_scenario_manifest(SCENARIO_UNSCHEDULABLE_SHIPPING)
        assert manifest is not None
        grade = evaluate_diagnosis_grade(evidence, manifest)
        assert grade == DiagnosisGrade.EXACT_ROOT_CAUSE

    def test_missing_evidence_does_not_trigger_exact_grade(self) -> None:
        """'missing evidence' without k9b.dev/otel-lab-node=missing is causal_level, not exact."""
        evidence = {
            "incident_id": "inc-001",
            "summary": (
                "shipping deployment FailedScheduling: nodeSelector k9b.dev/otel-lab-node "
                "missing evidence - no matching nodes available"
            ),
        }
        manifest = get_scenario_manifest(SCENARIO_UNSCHEDULABLE_SHIPPING)
        assert manifest is not None
        grade = evaluate_diagnosis_grade(evidence, manifest)
        # "missing evidence" matches \bmissing\b but is rejected by terminator rule
        assert grade == DiagnosisGrade.CAUSAL_LEVEL

    def test_missing_alone_with_key_is_exact(self) -> None:
        """'missing' as word with k9b.dev/otel-lab-node is exact_root_cause."""
        evidence = {
            "incident_id": "inc-001",
            "summary": (
                "shipping deployment FailedScheduling: nodeSelector "
                "k9b.dev/otel-lab-node is missing - no matching node"
            ),
        }
        manifest = get_scenario_manifest(SCENARIO_UNSCHEDULABLE_SHIPPING)
        assert manifest is not None
        grade = evaluate_diagnosis_grade(evidence, manifest)
        assert grade == DiagnosisGrade.EXACT_ROOT_CAUSE


class TestCheckMarkersPresent:
    """Test check_markers_present() with literals and regexes."""

    def test_literal_markers(self) -> None:
        """All literal markers found returns empty missing list."""
        text = "shipping nodeSelector k9b.dev/otel-lab-node=missing"
        markers = EvidenceMarkers(literals=("shipping", "nodeSelector"))
        found, missing = check_markers_present(text, markers)
        assert found == ["shipping", "nodeSelector"]
        assert missing == []

    def test_literal_marker_missing(self) -> None:
        """Missing literal markers are reported."""
        text = "shipping deployment has issues"
        markers = EvidenceMarkers(literals=("shipping", "nodeSelector"))
        found, missing = check_markers_present(text, markers)
        assert found == ["shipping"]
        assert missing == ["nodeSelector"]

    def test_regex_patterns(self) -> None:
        """Regex patterns are matched with re.search()."""
        text = "no pods matching the required node selector were found"
        markers = EvidenceMarkers(regexes=("no.*matching.*node",))
        found, missing = check_markers_present(text, markers)
        assert found == ["no.*matching.*node"]
        assert missing == []

    def test_regex_not_matched(self) -> None:
        """Regex patterns that don't match are reported as missing."""
        text = "all pods are running normally"
        markers = EvidenceMarkers(regexes=("no.*matching.*node",))
        found, missing = check_markers_present(text, markers)
        assert found == []
        assert missing == ["no.*matching.*node"]


class TestScenarioManifest:
    """Test ScenarioTruthManifest retrieval and structure."""

    def test_unschedulable_shipping_manifest_exists(self) -> None:
        """unschedulable-shipping scenario has a manifest."""
        manifest = get_scenario_manifest(SCENARIO_UNSCHEDULABLE_SHIPPING)
        assert manifest is not None
        assert manifest.scenario == SCENARIO_UNSCHEDULABLE_SHIPPING
        assert manifest.workload == "deployment/shipping"
        assert "nodeSelector" in manifest.expected_markers
        assert "k9b.dev/otel-lab-node=missing" in manifest.expected_markers

    def test_unknown_scenario_returns_none(self) -> None:
        """Unknown scenario returns None."""
        manifest = get_scenario_manifest("unknown-scenario")
        assert manifest is None

    def test_manifest_has_evidence_markers(self) -> None:
        """Manifest has separated p4c_output_markers for literals and regexes."""
        manifest = get_scenario_manifest(SCENARIO_UNSCHEDULABLE_SHIPPING)
        assert manifest is not None
        assert isinstance(manifest.p4c_output_markers, EvidenceMarkers)
        assert len(manifest.p4c_output_markers.literals) > 0
        assert len(manifest.p4c_output_markers.regexes) > 0


class TestManifestWiringInP4cOutcome:
    """Regression tests proving manifest has authority over P4c outcome."""

    def test_manifest_rejects_scheduling_level_terminal_success(self) -> None:
        """Terminal/no-checks must not rescue a scheduling-level diagnosis.
        
        When scenario manifest is provided, a diagnosis that only reaches
        scheduling_level (FailedScheduling without causal root cause) must fail.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        # Scheduling-level evidence: has FailedScheduling but no nodeSelector key
        evidence = {
            "incident_id": "inc-001",
            "summary": "shipping deployment FailedScheduling - pod cannot be scheduled",
            "root_cause_summary": "shipping deployment FailedScheduling - pod cannot be scheduled",
            "pass_count": 2,
            "read_only": True,
            "read_only_violations": [],
            "terminal_no_checks_accepted": True,
            "real_pass_artifacts_found": True,
            "terminal_decision_reached": "stop_no_checks_proposed",
        }

        # With manifest, scheduling-level diagnosis should fail
        outcome = compute_p4c_outcome(
            evidence,
            scenario="unschedulable-shipping",
            accept_terminal_single_pass=False,
            min_required_passes=2,
        )

        assert outcome.success is False
        assert outcome.mode == "multipass"
        # Must fail due to diagnosis grade, not just terminal mode
        assert any(
            "diagnosis_output_ignored_root_cause" in failure
            or "scheduling_level" in failure
            for failure in outcome.failure_reasons
        )

    def test_manifest_passes_causal_level_diagnosis(self) -> None:
        """Causal-level diagnosis (nodeSelector with key but no value) passes."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        # Causal-level evidence: has nodeSelector key
        evidence = {
            "incident_id": "inc-001",
            "summary": (
                "shipping deployment FailedScheduling: nodeSelector k9b.dev/otel-lab-node "
                "did not match any nodes"
            ),
            "root_cause_summary": (
                "shipping deployment FailedScheduling: nodeSelector k9b.dev/otel-lab-node "
                "did not match any nodes"
            ),
            "pass_count": 2,
            "read_only": True,
            "read_only_violations": [],
            "terminal_no_checks_accepted": False,
            "real_pass_artifacts_found": True,
        }

        # With manifest, causal-level diagnosis should pass
        outcome = compute_p4c_outcome(
            evidence,
            scenario="unschedulable-shipping",
            accept_terminal_single_pass=False,
            min_required_passes=2,
        )

        # Causal-level is acceptable (no grade failure)
        assert outcome.success is True
        assert "diagnosis_output_ignored_root_cause" not in str(outcome.failure_reasons)

    def test_exact_root_cause_passes_with_manifest(self) -> None:
        """Exact root cause diagnosis passes with manifest validation."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        # Exact root cause evidence
        evidence = {
            "incident_id": "inc-001",
            "summary": (
                "shipping deployment FailedScheduling: nodeSelector "
                "k9b.dev/otel-lab-node=missing - no matching node found"
            ),
            "root_cause_summary": (
                "shipping deployment FailedScheduling: nodeSelector "
                "k9b.dev/otel-lab-node=missing - no matching node found"
            ),
            "pass_count": 2,
            "read_only": True,
            "read_only_violations": [],
            "terminal_no_checks_accepted": False,
            "real_pass_artifacts_found": True,
        }

        outcome = compute_p4c_outcome(
            evidence,
            scenario="unschedulable-shipping",
            accept_terminal_single_pass=False,
            min_required_passes=2,
        )

        assert outcome.success is True
        assert outcome.root_cause_evidence_satisfied is True
        assert outcome.failure_reasons == ()

    def test_unknown_manifest_scenario_fails_closed(self) -> None:
        """Unknown scenario name fails closed - manifest authority cannot be silently disabled."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        # Complete evidence that would pass without manifest
        evidence = {
            "incident_id": "inc-001",
            "summary": (
                "shipping deployment FailedScheduling: nodeSelector "
                "k9b.dev/otel-lab-node=missing - no matching node found"
            ),
            "root_cause_summary": (
                "shipping deployment FailedScheduling: nodeSelector "
                "k9b.dev/otel-lab-node=missing - no matching node found"
            ),
            "pass_count": 2,
            "read_only": True,
            "read_only_violations": [],
            "terminal_no_checks_accepted": False,
            "real_pass_artifacts_found": True,
        }

        # Misspelled scenario name should fail
        outcome = compute_p4c_outcome(
            evidence,
            scenario="unschedulable-shippng",  # typo
            accept_terminal_single_pass=False,
            min_required_passes=2,
        )

        assert outcome.success is False
        assert any("unknown_scenario_manifest" in reason for reason in outcome.failure_reasons)
