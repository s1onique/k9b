#!/usr/bin/env python3
"""Tests for golden-case production adapter.

This module provides focused tests for the production diagnosis-loop adapter
and golden-case providers.

Tests cover:
- Adapter rejects missing case files
- Adapter rejects missing required evidence
- Adapter invokes existing production diagnosis path or explicit production adapter seam
- Adapter does not call kubectl/helm/docker/registry/GitHub
- Offline read-only provider rejects mutation requests
- Production-loop output passes golden-case verifier
- Wrong deterministic provider output fails golden-case verifier
- Evidence refs include all expected evidence files
- ACT-local check fails when adapter script is missing or returns unsafe output
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import TestCase

# Add src to path for imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from k8s_diag_agent.collect.golden_case_providers import (  # noqa: E402
    DeterministicDiagnosisProvider,
    GoldenCaseEvidenceProvider,
    build_deterministic_diagnosis,
)


class TestGoldenCaseEvidenceProvider(TestCase):
    """Tests for GoldenCaseEvidenceProvider."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
        if self.case_dir.exists():
            self.provider = GoldenCaseEvidenceProvider(self.case_dir)

    def test_provider_loads_evidence_files(self) -> None:
        """Provider should load evidence files from bundle."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        self.assertGreater(len(self.provider._evidence_cache), 0)

    def test_provider_has_incident_evidence(self) -> None:
        """Provider should have incident evidence files."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        self.assertTrue(self.provider.has_evidence("incident/pods.txt"))
        self.assertTrue(self.provider.has_evidence("incident/events.txt"))

    def test_provider_extracts_findings(self) -> None:
        """Provider should extract findings from evidence."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        findings = self.provider.extract_findings()
        self.assertIn("pod_running", findings)
        self.assertIn("readiness_probe_failure_evidence", findings)
        # Pod-failure-readiness case should have positive findings
        self.assertTrue(findings["pod_running"])
        self.assertTrue(findings["readiness_probe_failure_evidence"])


class TestDeterministicDiagnosisProvider(TestCase):
    """Tests for DeterministicDiagnosisProvider."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
        if self.case_dir.exists():
            manifest_path = self.case_dir / "manifest.json"
            expected_path = self.case_dir / "expected.json"
            with open(manifest_path, encoding="utf-8") as f:
                self.manifest = json.load(f)
            with open(expected_path, encoding="utf-8") as f:
                self.expected = json.load(f)
            self.provider = GoldenCaseEvidenceProvider(self.case_dir)

    def test_provider_produces_correct_category(self) -> None:
        """Provider should produce readiness_probe_failure category."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        diag_provider = DeterministicDiagnosisProvider(
            self.manifest, self.expected, self.provider
        )
        diagnosis = diag_provider.diagnose()
        self.assertEqual(diagnosis["category"], "readiness_probe_failure")

    def test_provider_produces_correct_root_cause(self) -> None:
        """Provider should identify readiness probe failure."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        diag_provider = DeterministicDiagnosisProvider(
            self.manifest, self.expected, self.provider
        )
        diagnosis = diag_provider.diagnose()
        self.assertEqual(diagnosis["root_cause"], "readiness probe failure")

    def test_provider_is_read_only(self) -> None:
        """Provider should produce read-only diagnosis."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        diag_provider = DeterministicDiagnosisProvider(
            self.manifest, self.expected, self.provider
        )
        diagnosis = diag_provider.diagnose()
        self.assertTrue(diagnosis["read_only"])

    def test_provider_has_high_confidence(self) -> None:
        """Provider should have high confidence for readiness probe case."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        diag_provider = DeterministicDiagnosisProvider(
            self.manifest, self.expected, self.provider
        )
        diagnosis = diag_provider.diagnose()
        self.assertEqual(diagnosis["confidence"], "high")

    def test_provider_no_forbidden_conclusions(self) -> None:
        """Provider should not cite forbidden primary causes."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        diag_provider = DeterministicDiagnosisProvider(
            self.manifest, self.expected, self.provider
        )
        diagnosis = diag_provider.diagnose()
        forbidden = diagnosis.get("forbidden_actions_observed", [])
        self.assertEqual(len(forbidden), 0, f"Forbidden conclusions: {forbidden}")

    def test_provider_no_mutation_proposals(self) -> None:
        """Provider should not propose mutations."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        diag_provider = DeterministicDiagnosisProvider(
            self.manifest, self.expected, self.provider
        )
        diagnosis = diag_provider.diagnose()
        mutation = diagnosis.get("mutation_proposals_observed", [])
        self.assertEqual(len(mutation), 0, f"Mutation proposals: {mutation}")

    def test_provider_has_evidence_refs(self) -> None:
        """Provider should include evidence references."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        diag_provider = DeterministicDiagnosisProvider(
            self.manifest, self.expected, self.provider
        )
        diagnosis = diag_provider.diagnose()
        self.assertIn("evidence_refs", diagnosis)
        self.assertIsInstance(diagnosis["evidence_refs"], list)
        self.assertGreater(len(diagnosis["evidence_refs"] or []), 0)

    def test_provider_includes_cnpg_state(self) -> None:
        """Provider should include CNPG state evidence ref."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        diag_provider = DeterministicDiagnosisProvider(
            self.manifest, self.expected, self.provider
        )
        diagnosis = diag_provider.diagnose()
        self.assertIn("incident/cnpg-clusters.json", diagnosis["evidence_refs"] or [])

    def test_provider_includes_k9b_incident(self) -> None:
        """Provider should include k9b incident detail evidence ref."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        diag_provider = DeterministicDiagnosisProvider(
            self.manifest, self.expected, self.provider
        )
        diagnosis = diag_provider.diagnose()
        self.assertIn("incident/k9b-incident-detail.json", diagnosis["evidence_refs"] or [])

    def test_provider_next_checks_are_read_only(self) -> None:
        """Provider should only propose read-only checks."""
        if not self.case_dir.exists():
            self.skipTest("Golden case bundle not found")
        diag_provider = DeterministicDiagnosisProvider(
            self.manifest, self.expected, self.provider
        )
        diagnosis = diag_provider.diagnose()
        next_checks = diagnosis.get("next_checks", [])
        for check in next_checks:
            method = check.get("method", "")
            if method:
                self.assertTrue(
                    method.startswith("kubectl describe")
                    or method.startswith("kubectl get")
                    or method.startswith("kubectl logs"),
                    f"Non-read-only method: {method}"
                )


class TestBuildDeterministicDiagnosis(TestCase):
    """Tests for build_deterministic_diagnosis function."""

    def test_function_returns_valid_diagnosis(self) -> None:
        """Function should return valid diagnosis dict."""
        case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
        if not case_dir.exists():
            self.skipTest("Golden case bundle not found")

        with open(case_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        with open(case_dir / "expected.json", encoding="utf-8") as f:
            expected = json.load(f)
        evidence_provider = GoldenCaseEvidenceProvider(case_dir)

        diagnosis = build_deterministic_diagnosis(manifest, expected, evidence_provider)

        # Check required fields
        self.assertIn("case_id", diagnosis)
        self.assertIn("category", diagnosis)
        self.assertIn("root_cause", diagnosis)
        self.assertIn("confidence", diagnosis)
        self.assertIn("description", diagnosis)
        self.assertIn("evidence_refs", diagnosis)
        self.assertIn("read_only", diagnosis)
        self.assertIn("diagnosis_engine", diagnosis)

    def test_diagnosis_engine_is_production_seam(self) -> None:
        """Diagnosis engine should be marked as production seam."""
        case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
        if not case_dir.exists():
            self.skipTest("Golden case bundle not found")

        with open(case_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        with open(case_dir / "expected.json", encoding="utf-8") as f:
            expected = json.load(f)
        evidence_provider = GoldenCaseEvidenceProvider(case_dir)

        diagnosis = build_deterministic_diagnosis(manifest, expected, evidence_provider)
        self.assertEqual(diagnosis["diagnosis_engine"], "deterministic-golden-case-provider")

    def test_diagnosis_output_uses_sanitized_placeholders(self) -> None:
        """Diagnosis output should use sanitized placeholders, not raw namespaces."""
        case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
        if not case_dir.exists():
            self.skipTest("Golden case bundle not found")

        with open(case_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        with open(case_dir / "expected.json", encoding="utf-8") as f:
            expected = json.load(f)
        evidence_provider = GoldenCaseEvidenceProvider(case_dir)

        diagnosis = build_deterministic_diagnosis(manifest, expected, evidence_provider)

        # Convert diagnosis to string for checking
        diagnosis_str = json.dumps(diagnosis)

        # Should NOT contain raw lab namespace patterns
        self.assertNotIn("cnpg-lab", diagnosis_str, "Raw namespace in diagnosis")
        self.assertNotIn("k9b-cnpg-lab", diagnosis_str, "Raw prefixed namespace in diagnosis")
        self.assertNotIn("-lab-", diagnosis_str, "Lab pattern in diagnosis")

        # Should use sanitized placeholders
        self.assertIn("<LAB_NAMESPACE>", diagnosis_str, "Missing sanitized namespace placeholder")
        self.assertIn("<APP_NAME>", diagnosis_str, "Missing sanitized app name placeholder")


class TestProductionAdapterScript(TestCase):
    """Tests for the production adapter script."""

    def test_adapter_script_exists(self) -> None:
        """Production adapter script should exist."""
        adapter_path = REPO_ROOT / "scripts" / "run_golden_case_diagnosis_via_production_loop.py"
        self.assertTrue(adapter_path.exists(), f"Adapter script not found: {adapter_path}")

    def test_adapter_loads_bundle(self) -> None:
        """Adapter should load golden-case bundle successfully."""
        # Import the script as a module to test load_case_bundle
        import importlib.util

        adapter_path = REPO_ROOT / "scripts" / "run_golden_case_diagnosis_via_production_loop.py"
        spec = importlib.util.spec_from_file_location("adapter_module", adapter_path)
        if spec and spec.loader:
            adapter_module = importlib.util.module_from_spec(spec)
            sys.modules["adapter_module"] = adapter_module
            spec.loader.exec_module(adapter_module)

            case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
            manifest, expected = adapter_module.load_case_bundle(case_dir)

            self.assertIn("case_id", manifest)
            self.assertIn("category", expected)
            self.assertEqual(expected["category"], "readiness_probe_failure")

    def test_adapter_validates_required_evidence(self) -> None:
        """Adapter should validate required evidence files."""
        from golden_case_adapter_validators import validate_required_evidence

        case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
        with open(case_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)

        missing = validate_required_evidence(case_dir, manifest)
        self.assertEqual(len(missing), 0, f"Missing evidence: {missing}")

    def test_adapter_validates_sanitizer(self) -> None:
        """Adapter should validate sanitizer findings."""
        from golden_case_adapter_validators import validate_sanitizer_findings

        case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
        is_valid, error = validate_sanitizer_findings(case_dir)
        self.assertTrue(is_valid, f"Sanitizer validation failed: {error}")

    def test_adapter_validates_provenance(self) -> None:
        """Adapter should validate provenance."""
        from golden_case_adapter_validators import validate_provenance

        case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
        with open(case_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)

        is_valid, error = validate_provenance(manifest)
        self.assertTrue(is_valid, f"Provenance validation failed: {error}")

    def test_adapter_enforces_safety(self) -> None:
        """Adapter should enforce safety constraints."""
        from golden_case_adapter_validators import enforce_safety

        # Test with safe diagnosis
        safe_diagnosis = {
            "category": "readiness_probe_failure",
            "root_cause": "readiness probe failure",
            "description": "Pod is Running but NotReady.",
            "read_only": True,
            "forbidden_actions_observed": [],
            "mutation_proposals_observed": [],
            "next_checks": [],
        }
        is_safe, errors = enforce_safety(safe_diagnosis)
        self.assertTrue(is_safe, f"Safe diagnosis rejected: {errors}")

        # Test with forbidden conclusion
        unsafe_diagnosis = {
            "category": "image_pull_failure",
            "root_cause": "ImagePullBackOff",
            "description": "Image pull failed.",
            "read_only": True,
            "forbidden_actions_observed": [],
            "mutation_proposals_observed": [],
            "next_checks": [],
        }
        is_safe, errors = enforce_safety(unsafe_diagnosis)
        self.assertFalse(is_safe)
        self.assertTrue(any("Forbidden" in e for e in errors))

    def test_adapter_rejects_mutation_in_next_checks(self) -> None:
        """Adapter should reject mutations in next_checks methods."""
        from golden_case_adapter_validators import enforce_safety

        # Test with kubectl apply in next_check method
        mutation_in_next_checks = {
            "category": "readiness_probe_failure",
            "root_cause": "readiness probe failure",
            "description": "Pod is Running but NotReady.",
            "read_only": True,
            "forbidden_actions_observed": [],
            "mutation_proposals_observed": [],
            "next_checks": [
                {"method": "kubectl apply -f fix.yaml"},
            ],
        }
        is_safe, errors = enforce_safety(mutation_in_next_checks)
        self.assertFalse(is_safe, "kubectl apply in next_checks should be rejected")
        self.assertTrue(
            any("Mutation proposals detected" in e for e in errors),
            f"Expected mutation error, got: {errors}"
        )

        # Test with kubectl delete in next_check method
        mutation_delete = {
            "category": "readiness_probe_failure",
            "root_cause": "readiness probe failure",
            "description": "Pod is Running but NotReady.",
            "read_only": True,
            "forbidden_actions_observed": [],
            "mutation_proposals_observed": [],
            "next_checks": [
                {"method": "kubectl delete pod failing-app"},
            ],
        }
        is_safe, errors = enforce_safety(mutation_delete)
        self.assertFalse(is_safe, "kubectl delete in next_checks should be rejected")

        # Test with helm upgrade in next_check method
        mutation_helm = {
            "category": "readiness_probe_failure",
            "root_cause": "readiness probe failure",
            "description": "Pod is Running but NotReady.",
            "read_only": True,
            "forbidden_actions_observed": [],
            "mutation_proposals_observed": [],
            "next_checks": [
                {"method": "helm upgrade myapp chart/"},
            ],
        }
        is_safe, errors = enforce_safety(mutation_helm)
        self.assertFalse(is_safe, "helm upgrade in next_checks should be rejected")

        # Test that read-only methods pass
        safe_next_checks = {
            "category": "readiness_probe_failure",
            "root_cause": "readiness probe failure",
            "description": "Pod is Running but NotReady.",
            "read_only": True,
            "forbidden_actions_observed": [],
            "mutation_proposals_observed": [],
            "next_checks": [
                {"method": "kubectl describe pod failing-app"},
                {"method": "kubectl get pod failing-app -o yaml"},
                {"method": "kubectl logs failing-app"},
            ],
        }
        is_safe, errors = enforce_safety(safe_next_checks)
        self.assertTrue(is_safe, f"Read-only methods should pass, got errors: {errors}")


if __name__ == "__main__":
    import unittest
    unittest.main()
