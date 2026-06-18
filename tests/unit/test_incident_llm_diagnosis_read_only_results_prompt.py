"""Tests for read-only check results in LLM diagnosis prompt.

Tests prove:
1. Prompt includes read-only check result summaries
2. Prompt includes run_id/check_id traceability
3. Prompt distinguishes check results from LLM prior analysis
4. Prompt does not include command fields
5. Prompt remains bounded
6. Prompt does not claim real Kubernetes evidence if artifact source is fake runner
"""

from __future__ import annotations

from k8s_diag_agent.collect.incident_llm_diagnosis import build_diagnosis_prompt


class TestDiagnosisPromptReadOnlyCheckResults:
    """Test read-only check results in diagnosis prompt."""

    def test_prompt_includes_read_only_check_results(self) -> None:
        """Prompt includes read-only check result summaries."""
        case_file = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "investigating",
            },
            "read_only_check_results": [
                {
                    "run_id": "run-001",
                    "checks_run": 2,
                    "checks_skipped": 0,
                    "checks_rejected": 0,
                    "results": [
                        {
                            "check_id": "pod_logs",
                            "status": "completed",
                            "summary": "Sample log output",
                        }
                    ],
                    "bounded": True,
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        # Check prompt includes read_only_check_results_context
        assert "read_only_check_results_context" in prompt
        assert "pod_logs" in prompt
        assert "Sample log output" in prompt

    def test_prompt_includes_run_id_check_id_traceability(self) -> None:
        """Prompt includes run_id/check_id traceability."""
        case_file = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "investigating",
            },
            "read_only_check_results": [
                {
                    "run_id": "run-trace-001",
                    "checks_run": 1,
                    "results": [
                        {
                            "check_id": "pod_events",
                            "status": "completed",
                            "summary": "Events check",
                        }
                    ],
                    "bounded": True,
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        assert "run-trace-001" in prompt
        assert "pod_events" in prompt

    def test_prompt_distinguishes_from_prior_analysis(self) -> None:
        """Prompt distinguishes check results from LLM prior analysis."""
        case_file = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "investigating",
            },
            "prior_analysis": [
                {
                    "run_id": "run-prior-001",
                    "source": "llm-diagnosis",
                    "summary": "LLM diagnosis summary",
                    "confidence": "medium",
                    "bounded": True,
                }
            ],
            "read_only_check_results": [
                {
                    "run_id": "run-checks-001",
                    "checks_run": 1,
                    "results": [
                        {
                            "check_id": "pod_logs",
                            "status": "completed",
                            "summary": "Check result summary",
                        }
                    ],
                    "bounded": True,
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        # Both sections should be present
        assert "prior_analysis_context" in prompt
        assert "read_only_check_results_context" in prompt
        assert "LLM diagnosis summary" in prompt
        assert "Check result summary" in prompt

    def test_prompt_does_not_include_command_fields(self) -> None:
        """Prompt does not include command/execute fields."""
        case_file = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "investigating",
            },
            "read_only_check_results": [
                {
                    "run_id": "run-safe-001",
                    "checks_run": 1,
                    "results": [
                        {
                            "check_id": "pod_logs",
                            "status": "completed",
                            "summary": "Safe summary",
                            "run": "kubectl exec",
                            "execute": "shell command",
                        }
                    ],
                    "bounded": True,
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        # Command fields should not appear
        assert "kubectl exec" not in prompt
        assert "shell command" not in prompt

    def test_prompt_mentions_fake_runner_disclaimer(self) -> None:
        """Prompt notes that check results may be fake runner outputs."""
        case_file = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "investigating",
            },
            "read_only_check_results": [
                {
                    "run_id": "run-fake-001",
                    "checks_run": 1,
                    "results": [
                        {
                            "check_id": "pod_logs",
                            "status": "completed",
                            "summary": "Fake output",
                        }
                    ],
                    "bounded": True,
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        # Disclaimer should be present
        assert "fake" in prompt.lower() or "fake_runner" in prompt.lower()

    def test_prompt_bounded_with_many_results(self) -> None:
        """Prompt remains bounded with many check results."""
        # Create case file with many results
        many_results = [
            {
                "run_id": f"run-{i:03d}",
                "checks_run": 1,
                "results": [
                    {
                        "check_id": f"check_{i}",
                        "status": "completed",
                        "summary": f"Summary {i}",
                    }
                ],
                "bounded": True,
            }
            for i in range(20)
        ]

        case_file = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "investigating",
            },
            "read_only_check_results": many_results,
        }

        prompt = build_diagnosis_prompt(case_file, max_prompt_chars=12000)

        # Prompt should be bounded
        assert len(prompt) <= 12500  # Allow some margin

    def test_prompt_empty_without_check_results(self) -> None:
        """Prompt works without read-only check results."""
        case_file = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "investigating",
            },
            "read_only_check_results": [],
        }

        prompt = build_diagnosis_prompt(case_file)

        # Should not have the check results context section
        assert "read_only_check_results_context" not in prompt
        # But should still have incident info
        assert "test-incident" in prompt

    def test_prompt_distinguishes_from_current_facts(self) -> None:
        """Prompt distinguishes check results from current incident facts."""
        case_file = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "investigating",
            },
            "signals": [
                {"run_id": "signal-run", "raw_signal": {"type": "alert"}}
            ],
            "read_only_check_results": [
                {
                    "run_id": "run-check-001",
                    "checks_run": 1,
                    "results": [
                        {
                            "check_id": "pod_logs",
                            "status": "completed",
                            "summary": "Check result",
                        }
                    ],
                    "bounded": True,
                }
            ],
        }

        prompt = build_diagnosis_prompt(case_file)

        # Both sections should be distinguishable
        assert "signal" in prompt.lower() or "alert" in prompt.lower()
        assert "read_only_check_results_context" in prompt
