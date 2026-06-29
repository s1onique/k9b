"""Regression tests for OTel Demo Helm values schema compliance.

These tests verify the fix for the Phase 1 failure where featureFlags
was incorrectly placed under components.recommendation, violating the
chart's additionalProperties:false schema constraint.

The OTel Demo chart 0.40.9 Component schema does NOT support featureFlags
as a child key. Feature flags must be managed by flagd post-install via
UI/ConfigMap/API, not by Helm component values.

See: https://github.com/open-telemetry/opentelemetry-helm-charts/blob/main/charts/opentelemetry-demo/values.yaml
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_types import LabConfig


class TestHelmValuesSchemaCompliance:
    """Regression tests for OTel Demo Helm values schema compliance."""

    @patch("subprocess.run")
    def test_phase1_values_do_not_contain_featureFlags_under_components_recommendation(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Phase 1 Helm values must NOT contain featureFlags under components.recommendation.

        The chart schema has additionalProperties:false on Component - putting
        featureFlags there will cause Helm to reject the values with a validation error.
        """
        from scripts.k9b_otel_demo_lab_deployment import phase1_deploy_otel_demo

        # Mock successful Helm operations
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # helm repo add
            MagicMock(returncode=0, stdout="", stderr=""),  # helm repo update
            MagicMock(returncode=0, stdout='[{"version": "0.40.9"}]', stderr=""),  # helm search
            MagicMock(returncode=0, stdout="Release installed", stderr=""),  # helm install
        ]

        config = LabConfig()
        result = phase1_deploy_otel_demo(config, tmp_path)

        # Verify install succeeded
        assert result.success is True

        # Extract the values YAML that was passed to helm
        helm_call = [c for c in mock_run.call_args_list if "upgrade" in str(c)][0]
        values_yaml = helm_call.kwargs.get("input", "")

        # Parse YAML to check for invalid structure
        import yaml
        values = yaml.safe_load(values_yaml) or {}

        # Phase 1 must use explicit empty values for clean baseline install
        assert values == {}, f"Phase 1 values must be empty, got: {values}"

        # The critical assertion: featureFlags must NOT be under components.recommendation
        components = values.get("components", {})
        recommendation = components.get("recommendation", {})
        assert "featureFlags" not in recommendation, (
            "featureFlags under components.recommendation is invalid for chart 0.40.9. "
            "Feature flags belong to flagd, not Helm component values."
        )

    def test_helm_values_comment_documents_why_featureFlags_not_in_values(self) -> None:
        """Comments in deployment script must explain why featureFlags is excluded.

        This is a documentation regression test - if someone removes the comment
        thinking it's unnecessary, this test documents WHY it exists.
        """
        from scripts import k9b_otel_demo_lab_deployment

        # Read the source file
        source_path = Path(k9b_otel_demo_lab_deployment.__file__)
        source_content = source_path.read_text()

        # Must contain the schema warning
        assert "additionalProperties:false" in source_content, (
            "Deployment script must document the schema constraint"
        )
        assert "featureFlags" in source_content, (
            "Deployment script must reference featureFlags in its warning comment"
        )
        assert "flagd" in source_content, (
            "Deployment script must explain that feature flags belong to flagd"
        )
