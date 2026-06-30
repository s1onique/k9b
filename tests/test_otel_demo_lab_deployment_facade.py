"""Regression tests for OTel Demo Lab deployment facade.

Ensures the facade module stays LLM-friendly and extracted helpers are importable.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEPLOYMENT_FACADE = REPO_ROOT / "scripts/k9b_otel_demo_lab_deployment.py"
HELM_HELPERS = REPO_ROOT / "scripts/k9b_otel_demo_lab_deployment_helm.py"
MAX_LINES = 500


class TestOtelDemoLabDeploymentFacade:
    """Regression tests for OTel Demo Lab deployment module structure."""

    def test_facade_is_within_llm_friendly_limit(self) -> None:
        """Facade should be under 500 lines to pass LLM-friendly gate."""
        assert DEPLOYMENT_FACADE.exists(), f"Facade not found: {DEPLOYMENT_FACADE}"
        line_count = len(DEPLOYMENT_FACADE.read_text().splitlines())
        assert line_count <= MAX_LINES, f"Facade has {line_count} lines, limit is {MAX_LINES}"

    def test_helm_helpers_module_is_importable(self) -> None:
        """Extracted Helm helpers module should be importable."""
        from scripts import k9b_otel_demo_lab_deployment_helm

        assert k9b_otel_demo_lab_deployment_helm is not None

    def test_helm_helpers_expose_required_functions(self) -> None:
        """Helm helpers module should expose the expected functions."""
        from scripts.k9b_otel_demo_lab_deployment_helm import (
            _classify_connectivity_error,
            _classify_helm_chart_version_error,
            _validate_chart_version,
        )

        assert callable(_classify_connectivity_error)
        assert callable(_classify_helm_chart_version_error)
        assert callable(_validate_chart_version)

    def test_facade_imports_from_helm_helpers(self) -> None:
        """Facade should import helpers from the extracted module."""
        content = DEPLOYMENT_FACADE.read_text()
        assert "from .k9b_otel_demo_lab_deployment_helm import" in content
