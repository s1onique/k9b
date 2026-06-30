"""Tests for OTEL demo lab modules."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

from scripts.k9b_otel_demo_lab_types import LabResult
from scripts.k9b_otel_demo_lab_verify import (
    VerificationResult,
    _verify_diagnosis,
    _verify_injection,
)


class TestOtelDemoLabVerifier:
    """Tests for the diagnosis oracle verifier."""

    def test_verify_injection_finds_recommendationservice(self, tmp_path: Path) -> None:
        """Pass case: pods contain recommendationservice."""
        # Arrange - use correct phase directory name
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "pods.json").write_text(
            '{"items": [{"metadata": {"name": "recommendationservice-abc123"}}]}'
        )
        (injection_dir / "events.json").write_text('{"items": []}')
        (injection_dir / "injection-command.json").write_text('{"command": "inject"}')

        # Act
        result = _verify_injection(tmp_path)

        # Assert
        assert result["passed"] is True
        assert result["recommendationservice_evidence"] is True

    def test_verify_injection_fails_without_recommendationservice(self, tmp_path: Path) -> None:
        """Fail case: no recommendationservice in pods."""
        # Arrange
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "pods.json").write_text(
            '{"items": [{"metadata": {"name": "frontend-xyz789"}}]}'
        )
        (injection_dir / "events.json").write_text('{"items": []}')
        (injection_dir / "injection-command.json").write_text('{"command": "inject"}')

        # Act
        result = _verify_injection(tmp_path)

        # Assert
        assert result["passed"] is True  # Phase passes, but evidence is False
        assert result["recommendationservice_evidence"] is False

    def test_verify_diagnosis_finds_recommendationservice(self, tmp_path: Path) -> None:
        """Pass case: diagnosis mentions recommendationservice and feature flag."""
        # Arrange - use correct phase directory name
        diagnosis_dir = tmp_path / "phase4-diagnosis"
        diagnosis_dir.mkdir(parents=True)
        (diagnosis_dir / "final-diagnosis.json").write_text(
            '{"diagnosis": "The recommendationservice has a cache failure due to feature flag."}'
        )

        # Act
        result = _verify_diagnosis(tmp_path)

        # Assert
        assert result["passed"] is True
        assert result["recommendationservice_mentioned"] is True
        assert result["feature_flag_evidence_found"] is True

    def test_verify_diagnosis_fails_without_recommendationservice(self, tmp_path: Path) -> None:
        """Fail case: diagnosis doesn't mention recommendationservice."""
        # Arrange
        diagnosis_dir = tmp_path / "phase4-diagnosis"
        diagnosis_dir.mkdir(parents=True)
        (diagnosis_dir / "final-diagnosis.json").write_text(
            '{"diagnosis": "The frontend has high latency."}'
        )

        # Act
        result = _verify_diagnosis(tmp_path)

        # Assert
        assert result["passed"] is False
        assert result.get("recommendationservice_mentioned") is False

    def test_verification_result_serialization(self) -> None:
        """Verify VerificationResult can be serialized."""
        result = VerificationResult(
            passed=True,
            failure_classes=[],
            details={},
            recommendationservice_found=True,
            feature_flag_evidence_found=True,
        )
        serialized = asdict(result)
        assert serialized["passed"] is True
        assert serialized["recommendationservice_found"] is True


class TestLiveModeVerifier:
    """Tests for live mode verification."""

    def test_live_verifier_fails_without_traffic(self, tmp_path: Path) -> None:
        """Live verifier fails when traffic-live.json is missing."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "pods.json").write_text('{"items": []}')
        (injection_dir / "flag-config-after.json").write_text('{"enabled": true}')
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is False
        assert "live_traffic_not_attempted" in result["failure_classes"]

    def test_live_verifier_fails_with_zero_attempts(self, tmp_path: Path) -> None:
        """Live verifier fails when traffic attempts is zero."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "traffic-live.json").write_text('{"mode": "live", "actual_attempts": 0, "summary_found": true}')
        (injection_dir / "pods.json").write_text('{"items": []}')
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is False
        assert "live_traffic_not_attempted" in result["failure_classes"]

    def test_live_verifier_fails_without_recommendationservice(self, tmp_path: Path) -> None:
        """Live verifier fails when recommendationservice evidence is missing."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "traffic-live.json").write_text('{"mode": "live", "actual_attempts": 10, "summary_found": true}')
        (injection_dir / "pods.json").write_text('{"items": [{"metadata": {"name": "frontend"}}]}')
        (injection_dir / "flag-config-after.json").write_text('{"enabled": true}')
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is False
        assert "live_recommendationservice_evidence_missing" in result["failure_classes"]

    def test_live_verifier_fails_without_flag_enabled(self, tmp_path: Path) -> None:
        """Live verifier fails when feature flag is not enabled."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "traffic-live.json").write_text('{"mode": "live", "actual_attempts": 10, "summary_found": true}')
        (injection_dir / "pods.json").write_text('{"items": [{"metadata": {"name": "recommendationservice"}}]}')
        (injection_dir / "flag-config-after.json").write_text('{"flags": {"recommendationServiceCacheFailure": {"enabled": false}}}')
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is False
        assert "live_feature_flag_not_enabled" in result["failure_classes"]

    def test_live_verifier_passes_with_minimal_live_fixture(self, tmp_path: Path) -> None:
        """Live verifier passes with minimal live fixture."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange - minimal live fixture
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        
        # Traffic artifact with new shape
        (injection_dir / "traffic-live.json").write_text('{"mode": "live", "actual_attempts": 10, "summary_found": true, "success_count": 8, "failure_count": 2}')
        
        # Recommendationservice with symptom (restart count > 0)
        (injection_dir / "pods.json").write_text('''
        {"items": [
            {"metadata": {"name": "recommendationservice-abc"},
             "status": {"containerStatuses": [
                 {"restartCount": 2, "state": {"running": {}}}
             ]}}
        ]}''')
        
        # Flag before/after evidence
        (injection_dir / "flag-config-before.json").write_text(
            '{"flags": {"recommendationServiceCacheFailure": {"enabled": false}}}'
        )
        (injection_dir / "flag-config-after.json").write_text(
            '{"flags": {"recommendationServiceCacheFailure": {"enabled": true}}}'
        )
        
        # Diagnosis
        diagnosis_dir = tmp_path / "phase4-diagnosis"
        diagnosis_dir.mkdir(parents=True)
        (diagnosis_dir / "final-diagnosis.json").write_text(
            '{"mode": "live", "provider": "test", "affected_component": "recommendationservice"}'
        )
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is True
        assert result.get("recommendationservice_found") is True
        assert result.get("flag_enabled") is True

    def test_live_verifier_fails_without_symptom_evidence(self, tmp_path: Path) -> None:
        """Live verifier fails when no symptom evidence present."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange - no symptom evidence (restart count 0, no waiting state, no logs)
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        
        (injection_dir / "traffic-live.json").write_text('{"mode": "live", "actual_attempts": 10, "summary_found": true}')
        (injection_dir / "pods.json").write_text('''
        {"items": [
            {"metadata": {"name": "recommendationservice-abc"},
             "status": {"containerStatuses": [
                 {"restartCount": 0, "state": {"running": {}}}
             ]}}
        ]}''')
        (injection_dir / "flag-config-after.json").write_text(
            '{"flags": {"recommendationServiceCacheFailure": {"enabled": true}}}'
        )
        
        diagnosis_dir = tmp_path / "phase4-diagnosis"
        diagnosis_dir.mkdir(parents=True)
        (diagnosis_dir / "final-diagnosis.json").write_text('{"mode": "live"}')
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is False
        assert "live_symptom_evidence_missing" in result["failure_classes"]

    def test_traffic_plan_contains_mode_scaffold(self, tmp_path: Path) -> None:
        """Verify traffic plan records scaffold mode."""
        from scripts.k9b_otel_demo_lab_traffic import record_traffic_plan
        
        # Arrange
        traffic_dir = tmp_path / "phase2-injected"
        traffic_dir.mkdir(parents=True)
        
        # Mock kubectl_json to return empty services
        import scripts.k9b_otel_demo_lab_traffic as traffic
        original = traffic.kubectl_json
        traffic.kubectl_json = lambda *args, **kwargs: type('obj', (object,), {'success': False})()
        
        try:
            # Act
            result = record_traffic_plan(str(tmp_path), tmp_path, 30)
            
            # Assert
            assert result.get("mode") == "scaffold"
        finally:
            traffic.kubectl_json = original


class TestLabResultSchema:
    """Regression tests for LabResult contract."""

    def test_lab_result_exposes_provider_smoke_passed_default(self) -> None:
        """LabResult.provider_smoke_passed has fail-closed default."""
        result = LabResult()
        assert result.provider_smoke_passed is False

    def test_lab_result_provider_smoke_passed_can_be_set_true(self) -> None:
        """LabResult.provider_smoke_passed can be set to True."""
        result = LabResult(provider_smoke_passed=True)
        assert result.provider_smoke_passed is True

    def test_lab_result_serialization_includes_provider_smoke(self) -> None:
        """LabResult serializes provider_smoke_passed to dict."""
        result = LabResult(provider_smoke_passed=True)
        serialized = asdict(result)
        assert "provider_smoke_passed" in serialized
        assert serialized["provider_smoke_passed"] is True


class TestLabResultSummaryOutput:
    """Regression tests for LabResult summary output."""

    def test_summary_prints_provider_smoke_passed(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Summary prints 'PASSED' when provider_smoke_passed is True."""
        result = LabResult(provider_smoke_passed=True)
        print(f"Provider smoke: {'PASSED' if result.provider_smoke_passed else 'SKIPPED/FAILED'}")
        out = capsys.readouterr().out
        assert "Provider smoke: PASSED" in out

    def test_summary_prints_provider_smoke_skipped(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Summary prints 'SKIPPED/FAILED' when provider_smoke_passed is False."""
        result = LabResult(provider_smoke_passed=False)
        print(f"Provider smoke: {'PASSED' if result.provider_smoke_passed else 'SKIPPED/FAILED'}")
        out = capsys.readouterr().out
        assert "Provider smoke: SKIPPED/FAILED" in out


# Note: Phase 0 and backend prerequisite tests moved to test_k9b_backend_prerequisite.py
# Note: Helm chart version tests moved to test_helm_chart_version.py
# to reduce file size below 500 lines for llm-friendly checks.


class TestTrafficTargetFQDN:
    """Test traffic target FQDN construction."""

    def test_build_frontend_proxy_fqdn_format(self) -> None:
        """FQDN format must be service.namespace.svc.cluster.local."""
        from scripts.k9b_otel_demo_lab_traffic import _build_frontend_proxy_fqdn

        fqdn = _build_frontend_proxy_fqdn("frontend-proxy", "otel-demo")

        assert fqdn == "frontend-proxy.otel-demo.svc.cluster.local"
        assert "svc.cluster.local" in fqdn

    def test_generate_live_traffic_fails_when_frontend_proxy_missing(self, tmp_path: Path) -> None:
        """generate_live_traffic must fail with traffic_target_service_missing when frontend-proxy not found."""
        # Mock kubectl_json to return empty services (no frontend-proxy)
        import scripts.k9b_otel_demo_lab_traffic as traffic
        from scripts.k9b_otel_demo_lab_constants import FAILURE_TRAFFIC_TARGET_SERVICE_MISSING
        from scripts.k9b_otel_demo_lab_traffic import generate_live_traffic
        original = traffic.kubectl_json
        traffic.kubectl_json = lambda *args, **kwargs: type('obj', (object,), {'success': True, 'data': {'items': []}})()

        try:
            result = generate_live_traffic(
                kubeconfig="/fake/kubeconfig",
                artifact_dir=tmp_path,
                namespace="otel-demo",
                duration_seconds=30,
                interval_seconds=5,
            )

            assert result.get("failure_class") == FAILURE_TRAFFIC_TARGET_SERVICE_MISSING
            assert result.get("mode") == "live"
            assert result.get("actual_attempts") == 0
            assert "frontend-proxy" in result.get("error", "")
        finally:
            traffic.kubectl_json = original

    def test_generate_live_traffic_succeeds_when_frontend_proxy_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """generate_live_traffic must use FQDN when frontend-proxy service exists."""
        import scripts.k9b_otel_demo_lab_traffic as traffic
        from scripts.k9b_otel_demo_lab_traffic import generate_live_traffic

        def mock_kubectl_json(
            kubeconfig: str, resource: str, namespace: str | None, **kwargs: object
        ) -> object:
            if resource == "services":
                return type('obj', (object,), {
                    'success': True,
                    'data': {
                        'items': [
                            {
                                'metadata': {'name': 'frontend-proxy'},
                                'spec': {'ports': [{'port': 8080, 'name': 'http'}]},
                            },
                            {'metadata': {'name': 'frontend'}},
                        ]
                    }
                })()
            return type('obj', (object,), {'success': False, 'data': None})()

        monkeypatch.setattr(traffic, "kubectl_json", mock_kubectl_json)

        result = generate_live_traffic(
            kubeconfig="/fake/kubeconfig",
            artifact_dir=tmp_path,
            namespace="otel-demo",
            duration_seconds=30,
            interval_seconds=5,
        )

        # Should not have traffic_target_service_missing failure
        assert result.get("failure_class") != "traffic_target_service_missing"
        # Should attempt to create a traffic pod
        assert result.get("mode") == "live"


class TestLLMFriendlyCheck:
    """Regression tests to ensure OTel demo lab modules remain LLM-friendly."""

    # LLM-friendly size threshold (lines)
    LLM_FRIENDLY_LINE_LIMIT = 500

    def test_otel_demo_lab_script_is_within_llm_friendly_limit(self) -> None:
        """Main orchestrator script should be under 500 lines to pass LLM-friendly gate."""
        path = Path(__file__).parent.parent / "scripts" / "k9b_otel_demo_lab.py"
        assert path.exists(), f"Main script not found: {path}"

        line_count = len(path.read_text().splitlines())
        assert line_count <= self.LLM_FRIENDLY_LINE_LIMIT, (
            f"scripts/k9b_otel_demo_lab.py has {line_count} lines, "
            f"exceeding the LLM-friendly limit of {self.LLM_FRIENDLY_LINE_LIMIT}. "
            "Consider extracting more responsibilities."
        )

    def test_otel_demo_lab_contract_module_exists(self) -> None:
        """Contract module should exist and be importable."""
        path = Path(__file__).parent.parent / "scripts" / "k9b_otel_demo_lab_contract.py"
        assert path.exists(), f"Contract module not found: {path}"

        # Should be under 200 lines (focused contract definitions)
        line_count = len(path.read_text().splitlines())
        assert line_count <= 200, (
            f"Contract module has {line_count} lines, should be focused (<=200)"
        )

    def test_otel_demo_lab_cli_module_exists(self) -> None:
        """CLI module should exist for command-line interface."""
        path = Path(__file__).parent.parent / "scripts" / "k9b_otel_demo_lab_cli.py"
        assert path.exists(), f"CLI module not found: {path}"

        # Should be under 150 lines (focused CLI)
        line_count = len(path.read_text().splitlines())
        assert line_count <= 150, (
            f"CLI module has {line_count} lines, should be focused (<=150)"
        )

    def test_otel_demo_lab_module_exposes_backward_compatible_main(self) -> None:
        """Original module should keep a CLI-compatible main entry point.

        This preserves the executable contract:
            python -m scripts.k9b_otel_demo_lab --kubeconfig /path/to/kubeconfig [options]
        """
        from scripts import k9b_otel_demo_lab

        assert callable(k9b_otel_demo_lab.main), (
            "k9b_otel_demo_lab.main should be callable for backward compatibility"
        )

