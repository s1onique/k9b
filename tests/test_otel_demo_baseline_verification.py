"""Tests for OTel Demo baseline verification.

This module tests the baseline readiness verification logic for the OTel Demo lab.
It is extracted from test_otel_demo_lab.py to keep files under the 500-line limit.
"""
from __future__ import annotations

from pathlib import Path


class TestOtelDemoBaselineVerifier:
    """Tests for baseline verification using chart 0.40.9 deployment names."""

    def test_verify_baseline_passes_with_correct_deployment_names(self, tmp_path: Path) -> None:
        """Regression: baseline passes when deployments use chart 0.40.9 names.
        
        The OTel Demo chart 0.40.9 uses short names (e.g., 'recommendation', 'product-catalog')
        instead of old long names (e.g., 'recommendationservice', 'productcatalogservice').
        Baseline verifier must accept fixtures with correct deployment names.
        """
        from scripts.k9b_otel_demo_lab_verify_baseline import verify_baseline
        
        # Arrange - baseline with correct chart 0.40.9 deployment names
        baseline_dir = tmp_path / "phase1-baseline"
        baseline_dir.mkdir(parents=True)
        
        # Write deployments.json with correct names
        (baseline_dir / "deployments.json").write_text('''{
  "apiVersion": "v1",
  "items": [
    {"metadata": {"name": "frontend", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "recommendation", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "product-catalog", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "cart", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "checkout", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "payment", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "shipping", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "currency", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "email", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "flagd", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}}
  ]
}''')
        (baseline_dir / "services.json").write_text('{"items": []}')
        (baseline_dir / "pods.json").write_text('{"items": []}')
        (baseline_dir / "readiness-result.json").write_text('''{
  "phase": "baseline",
  "timestamp": "2026-06-28T10:00:00Z",
  "namespace": "otel-demo",
  "status": "ready",
  "deployments_checked": 10,
  "deployments_ready": 10,
  "services_checked": 10,
  "message": "All required OTel Demo services are ready"
}''')
        
        # Act
        result = verify_baseline(tmp_path)
        
        # Assert
        assert result["passed"] is True
        assert result.get("deployments_checked") == 10
        assert result.get("readiness_result", {}).get("status") == "ready"

    def test_verify_baseline_fails_with_old_deployment_names(self, tmp_path: Path) -> None:
        """Regression: baseline fails when deployments use old long names.
        
        Old fixture format used names like 'recommendationservice', 'productcatalogservice'.
        These must NOT match REQUIRED_DEPLOYMENTS which uses chart 0.40.9 names.
        """
        from scripts.k9b_otel_demo_lab_verify_baseline import verify_baseline
        
        # Arrange - baseline with OLD incorrect deployment names
        baseline_dir = tmp_path / "phase1-baseline"
        baseline_dir.mkdir(parents=True)
        
        # Write deployments.json with OLD names (wrong format)
        (baseline_dir / "deployments.json").write_text('''{
  "apiVersion": "v1",
  "items": [
    {"metadata": {"name": "frontend", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "recommendationservice", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "productcatalogservice", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "cartservice", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "checkoutservice", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "paymentservice", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "shippingservice", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "currencyservice", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "emailservice", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}},
    {"metadata": {"name": "flagd", "namespace": "otel-demo"}, "status": {"replicas": 1, "readyReplicas": 1}}
  ]
}''')
        (baseline_dir / "services.json").write_text('{"items": []}')
        (baseline_dir / "pods.json").write_text('{"items": []}')
        (baseline_dir / "readiness-result.json").write_text('''{
  "phase": "baseline",
  "status": "ready",
  "deployments_checked": 10,
  "deployments_ready": 10,
  "services_checked": 10
}''')
        
        # Act
        result = verify_baseline(tmp_path)
        
        # Assert - should FAIL because OLD names don't match REQUIRED_DEPLOYMENTS
        assert result["passed"] is False
        assert "missing_deployments" in result
        assert len(result["missing_deployments"]) > 0  # Many deployments missing due to name mismatch
