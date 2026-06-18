"""Tests for incident_llm_diagnosis loop-passes prompt integration.

Tests prove:
1. Prompt includes diagnosis_loop_passes_context when case file has loop-pass artifacts
2. Prompt includes run_id and decision
3. Prompt includes stop reason for stop artifacts
4. Prompt includes linked artifact names for run artifacts
5. Prompt does not include raw full runner output
6. Prompt remains bounded
7. Prompt works when diagnosis_loop_passes is empty
"""

from __future__ import annotations

from k8s_diag_agent.collect.incident_llm_diagnosis import build_diagnosis_prompt


class TestDiagnosisLoopPassesPromptIntegration:
    """Test diagnosis_loop_passes_context in build_diagnosis_prompt."""

    def test_prompt_includes_loop_passes_context(self) -> None:
        """Prompt includes diagnosis_loop_passes_context when case file has loop-pass artifacts."""
        case_file = {
            "incident": {
                "incident_id": "test-001",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "warning",
                "status": "active",
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "prior_analysis": [],
            "read_only_check_results": [],
            "diagnosis_loop_passes": [
                {
                    "run_id": "loop-pass-001",
                    "generated_at": "2024-01-01T00:00:00Z",
                    "decision": "run_allowed_read_only_checks",
                    "stop_reason": None,
                    "checks_requested": 2,
                    "checks_run": 2,
                    "checks_skipped": 0,
                    "checks_rejected": 0,
                    "case_file_linked_artifact": True,
                    "linked_artifacts": [
                        {
                            "kind": "external-analysis",
                            "type": "read-only-check-results",
                            "name": "loop-pass-001-read-only-check-results.json",
                            "run_id": "loop-pass-001",
                            "safe": True,
                        }
                    ],
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        assert "diagnosis_loop_passes_context" in prompt
        assert "loop-pass-001" in prompt
        assert "run_allowed_read_only_checks" in prompt

    def test_prompt_includes_run_id_and_decision(self) -> None:
        """Prompt includes run_id and decision."""
        case_file = {
            "incident": {
                "incident_id": "test-002",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "warning",
                "status": "active",
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "prior_analysis": [],
            "read_only_check_results": [],
            "diagnosis_loop_passes": [
                {
                    "run_id": "loop-pass-002",
                    "generated_at": "2024-01-01T00:00:00Z",
                    "decision": "run_allowed_read_only_checks",
                    "stop_reason": None,
                    "checks_requested": 1,
                    "checks_run": 1,
                    "checks_skipped": 0,
                    "checks_rejected": 0,
                    "case_file_linked_artifact": True,
                    "linked_artifacts": [],
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        assert "loop-pass-002" in prompt
        assert "run_allowed_read_only_checks" in prompt

    def test_prompt_includes_stop_reason(self) -> None:
        """Prompt includes stop reason for stop artifacts."""
        case_file = {
            "incident": {
                "incident_id": "test-003",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "warning",
                "status": "active",
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "prior_analysis": [],
            "read_only_check_results": [],
            "diagnosis_loop_passes": [
                {
                    "run_id": "loop-pass-003",
                    "generated_at": "2024-01-01T00:00:00Z",
                    "decision": "stop_root_cause_found",
                    "stop_reason": "root_cause_found",
                    "checks_requested": 0,
                    "checks_run": 0,
                    "checks_skipped": 0,
                    "checks_rejected": 0,
                    "case_file_linked_artifact": False,
                    "linked_artifacts": [],
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        assert "stop_root_cause_found" in prompt
        assert "loop-pass-003" in prompt

    def test_prompt_includes_linked_artifact_names(self) -> None:
        """Prompt includes linked artifact names for run artifacts."""
        case_file = {
            "incident": {
                "incident_id": "test-004",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "warning",
                "status": "active",
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "prior_analysis": [],
            "read_only_check_results": [],
            "diagnosis_loop_passes": [
                {
                    "run_id": "loop-pass-004",
                    "generated_at": "2024-01-01T00:00:00Z",
                    "decision": "run_allowed_read_only_checks",
                    "stop_reason": None,
                    "checks_requested": 2,
                    "checks_run": 2,
                    "checks_skipped": 0,
                    "checks_rejected": 0,
                    "case_file_linked_artifact": True,
                    "linked_artifacts": [
                        {
                            "name": "loop-pass-004-read-only-check-results.json",
                        }
                    ],
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        assert "loop-pass-004-read-only-check-results.json" in prompt

    def test_prompt_does_not_include_raw_runner_output(self) -> None:
        """Prompt does not include raw full runner output."""
        case_file = {
            "incident": {
                "incident_id": "test-005",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "warning",
                "status": "active",
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "prior_analysis": [],
            "read_only_check_results": [],
            "diagnosis_loop_passes": [
                {
                    "run_id": "loop-pass-005",
                    "generated_at": "2024-01-01T00:00:00Z",
                    "decision": "run_allowed_read_only_checks",
                    "stop_reason": None,
                    "checks_requested": 1,
                    "checks_run": 1,
                    "checks_skipped": 0,
                    "checks_rejected": 0,
                    "case_file_linked_artifact": True,
                    "linked_artifacts": [],
                    # This would be raw runner output - should NOT appear in prompt
                    "runner_result": {
                        "raw_output": "kubectl get pods -n default" * 1000,
                        "full_dump": "x" * 10000,
                    },
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        # Should contain the run_id but NOT the raw output
        assert "loop-pass-005" in prompt
        # Raw output should not appear
        assert "kubectl get pods" not in prompt

    def test_prompt_remains_bounded(self) -> None:
        """Prompt remains bounded with many loop passes."""
        case_file = {
            "incident": {
                "incident_id": "test-006",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "warning",
                "status": "active",
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "prior_analysis": [],
            "read_only_check_results": [],
            "diagnosis_loop_passes": [
                {
                    "run_id": f"loop-pass-{i:03d}",
                    "generated_at": "2024-01-01T00:00:00Z",
                    "decision": "run_allowed_read_only_checks",
                    "stop_reason": None,
                    "checks_requested": 2,
                    "checks_run": 2,
                    "checks_skipped": 0,
                    "checks_rejected": 0,
                    "case_file_linked_artifact": True,
                    "linked_artifacts": [],
                }
                for i in range(20)  # Many loop passes
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        # Should be bounded (not excessively long)
        assert len(prompt) < 50000  # Much smaller than untruncated would be

    def test_prompt_works_when_loop_passes_empty(self) -> None:
        """Prompt works when diagnosis_loop_passes is empty."""
        case_file = {
            "incident": {
                "incident_id": "test-007",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "warning",
                "status": "active",
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "prior_analysis": [],
            "read_only_check_results": [],
            "diagnosis_loop_passes": [],  # Empty
        }

        prompt = build_diagnosis_prompt(case_file)

        # Should not crash
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should still have basic context
        assert "test-007" in prompt

    def test_prompt_works_without_diagnosis_loop_passes_key(self) -> None:
        """Prompt works when diagnosis_loop_passes key is missing."""
        case_file = {
            "incident": {
                "incident_id": "test-008",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "warning",
                "status": "active",
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "prior_analysis": [],
            "read_only_check_results": [],
            # diagnosis_loop_passes key is missing entirely
        }

        prompt = build_diagnosis_prompt(case_file)

        # Should not crash
        assert isinstance(prompt, str)
        assert len(prompt) > 0
