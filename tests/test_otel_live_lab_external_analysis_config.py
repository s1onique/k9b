"""Tests for OTel live lab external analysis config contract.

These tests verify that the live lab health config correctly wires:
- Adapters: defines enabled providers for external analysis
- auto_drilldown: provider points to an enabled adapter
- review_enrichment: provider points to an enabled adapter

Root cause: Without adapters[], both auto_drilldown and review_enrichment have
no available provider, causing review_enrichment to log:
  provider="unspecified" status="skipped" skip_reason="No review enrichment provider configured"
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml


def render_live_lab_manifest() -> dict[str, Any]:
    """Render the Helm chart with values-live-lab.yaml.

    Returns:
        Dict containing the rendered health config data.

    Raises:
        RuntimeError: If helm template fails.
    """
    chart_path = Path(__file__).resolve().parents[1] / "charts" / "k9b"
    values_path = Path(__file__).resolve().parents[1] / "charts" / "k9b" / "values-live-lab.yaml"

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(values_path.read_text())
        values_file = f.name

    try:
        result = subprocess.run(
            [
                "helm",
                "template",
                "k9b",
                str(chart_path),
                "-f",
                values_file,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"helm template failed: {exc.stderr}") from exc
    finally:
        Path(values_file).unlink(missing_ok=True)

    docs = list(yaml.safe_load_all(result.stdout))

    # Find the ConfigMap with health-config.json
    for doc in docs:
        if doc.get("kind") == "ConfigMap" and "data" in doc:
            health_config_raw = doc["data"].get("health-config.json")
            if health_config_raw:
                return cast(dict[str, Any], json.loads(health_config_raw))

    raise RuntimeError("No health-config.json found in rendered ConfigMap")


class TestLiveLabExternalAnalysisConfig:
    """Test that live lab external_analysis config is correctly wired."""

    @pytest.fixture
    def external_analysis(self) -> dict[str, Any]:
        """Load the external_analysis config from rendered live lab health config."""
        health_config = render_live_lab_manifest()
        return cast(dict[str, Any], health_config.get("external_analysis", {}))

    def test_external_analysis_has_adapters(self, external_analysis: dict[str, Any]) -> None:
        """external_analysis must have an adapters array."""
        assert "adapters" in external_analysis, (
            "external_analysis must define adapters[] to enable external analysis providers"
        )
        assert isinstance(external_analysis["adapters"], list), "adapters must be a list"
        assert len(external_analysis["adapters"]) > 0, "adapters[] must not be empty"

    def test_adapters_contain_openai_compatible_enabled(self, external_analysis: dict[str, Any]) -> None:
        """adapters[] must contain an enabled openai_compatible adapter."""
        adapters = external_analysis.get("adapters", [])
        assert any(
            adapter.get("name") == "openai_compatible"
            and adapter.get("enabled") is True
            for adapter in adapters
        ), "adapters[] must contain an enabled entry for name=openai_compatible"

    def test_auto_drilldown_enabled(self, external_analysis: dict[str, Any]) -> None:
        """auto_drilldown must be enabled."""
        auto_drilldown = external_analysis.get("auto_drilldown", {})
        assert auto_drilldown.get("enabled") is True, (
            "auto_drilldown.enabled must be true"
        )

    def test_auto_drilldown_provider_is_set(self, external_analysis: dict[str, Any]) -> None:
        """auto_drilldown must have a provider set (not None/empty)."""
        auto_drilldown = external_analysis.get("auto_drilldown", {})
        provider = auto_drilldown.get("provider")
        assert provider, (
            "auto_drilldown.provider must be set (not None or empty)"
        )
        assert isinstance(provider, str), "auto_drilldown.provider must be a string"

    def test_auto_drilldown_provider_points_to_enabled_adapter(
        self, external_analysis: dict[str, Any]
    ) -> None:
        """auto_drilldown.provider must reference an enabled adapter.

        This is the key regression test: without adapters[], the provider
        cannot be resolved, causing review_enrichment to fail with:
          provider="unspecified" skip_reason="No review enrichment provider configured"
        """
        adapters_list = external_analysis.get("adapters", [])
        adapters_by_name = {a["name"]: a for a in adapters_list}

        auto_drilldown = external_analysis.get("auto_drilldown", {})
        provider = auto_drilldown.get("provider")

        assert provider, "auto_drilldown.provider must be set"
        assert provider in adapters_by_name, (
            f"auto_drilldown.provider '{provider}' must be in adapters[]"
        )
        assert adapters_by_name[provider].get("enabled") is True, (
            f"adapter '{provider}' referenced by auto_drilldown.provider must be enabled"
        )

    def test_auto_drilldown_max_per_run(self, external_analysis: dict[str, Any]) -> None:
        """auto_drilldown.max_per_run should be 1 (lab-safe limit)."""
        auto_drilldown = external_analysis.get("auto_drilldown", {})
        max_per_run = auto_drilldown.get("max_per_run")
        assert max_per_run == 1, (
            "auto_drilldown.max_per_run should be 1 for lab environments"
        )

    def test_review_enrichment_enabled(self, external_analysis: dict[str, Any]) -> None:
        """review_enrichment must be enabled."""
        review_enrichment = external_analysis.get("review_enrichment", {})
        assert review_enrichment.get("enabled") is True, (
            "review_enrichment.enabled must be true"
        )

    def test_review_enrichment_provider_is_set(self, external_analysis: dict[str, Any]) -> None:
        """review_enrichment must have a provider set (not None/empty)."""
        review_enrichment = external_analysis.get("review_enrichment", {})
        provider = review_enrichment.get("provider")
        assert provider, (
            "review_enrichment.provider must be set (not None or empty)"
        )
        assert isinstance(provider, str), "review_enrichment.provider must be a string"

    def test_review_enrichment_provider_points_to_enabled_adapter(
        self, external_analysis: dict[str, Any]
    ) -> None:
        """review_enrichment.provider must reference an enabled adapter.

        This is the primary regression test for the bug where:
        - review_enrichment.enabled=true but provider was missing
        - causing runtime log: provider="unspecified" status="skipped"
          skip_reason="No review enrichment provider configured"
        """
        adapters_list = external_analysis.get("adapters", [])
        adapters_by_name = {a["name"]: a for a in adapters_list}

        review_enrichment = external_analysis.get("review_enrichment", {})
        provider = review_enrichment.get("provider")

        assert provider, "review_enrichment.provider must be set"
        assert provider in adapters_by_name, (
            f"review_enrichment.provider '{provider}' must be in adapters[]"
        )
        assert adapters_by_name[provider].get("enabled") is True, (
            f"adapter '{provider}' referenced by review_enrichment.provider must be enabled"
        )


class TestLiveLabSchedulerEnvBackendConfig:
    """Test that live-lab scheduler backend configuration is correctly wired.

    The live-lab deployment uses:
    - scheduler.env.K9B_EXTERNAL_ANALYSIS_PROVIDER: Backend provider type (openai_compatible)
    - scheduler.env.K9B_REVIEW_ENRICHMENT_ENABLED: Enable review enrichment
    - scheduler.smallProvider.provider: Small provider type for non-incident checks

    This is separate from the healthConfig which uses adapter aliases (e.g., llamacpp).
    The scheduler env vars wire the actual backend implementation, while healthConfig
    defines which adapters are available.
    """

    def test_live_lab_workflow_sets_external_analysis_provider(self) -> None:
        """Live lab workflow should set K9B_EXTERNAL_ANALYSIS_PROVIDER=openai_compatible.

        This wires the scheduler to use the openai_compatible backend.
        """
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "k9b-otel-demo-live-lab.yml"
        )
        assert workflow_path.exists(), f"Live lab workflow not found: {workflow_path}"

        workflow = cast(dict[str, Any], yaml.safe_load(workflow_path.read_text()))

        # Find the helm --set overrides in the ensure k9b lab baseline step
        found_provider_override = False
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                run_text = ""
                if "run" in step:
                    run_text = step["run"]
                elif isinstance(step, dict):
                    for key in ("run", "env"):
                        if key in step:
                            run_text += " " + str(step[key])

                if "--set-string" in run_text and "scheduler.env.K9B_EXTERNAL_ANALYSIS_PROVIDER" in run_text:
                    assert "openai_compatible" in run_text, (
                        "scheduler.env.K9B_EXTERNAL_ANALYSIS_PROVIDER should be set to openai_compatible"
                    )
                    found_provider_override = True

        assert found_provider_override, (
            "Live lab workflow should set scheduler.env.K9B_EXTERNAL_ANALYSIS_PROVIDER=openai_compatible"
        )

    def test_live_lab_workflow_sets_review_enrichment_enabled(self) -> None:
        """Live lab workflow should enable K9B_REVIEW_ENRICHMENT_ENABLED=true."""
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "k9b-otel-demo-live-lab.yml"
        )
        assert workflow_path.exists(), f"Live lab workflow not found: {workflow_path}"

        workflow = cast(dict[str, Any], yaml.safe_load(workflow_path.read_text()))

        # Find the helm --set overrides for review enrichment
        found_review_enrichment = False
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                run_text = ""
                if "run" in step:
                    run_text = step["run"]
                elif isinstance(step, dict):
                    for key in ("run", "env"):
                        if key in step:
                            run_text += " " + str(step[key])

                if "--set" in run_text and "scheduler.env.K9B_REVIEW_ENRICHMENT_ENABLED" in run_text:
                    assert "true" in run_text.lower(), (
                        "scheduler.env.K9B_REVIEW_ENRICHMENT_ENABLED should be set to true"
                    )
                    found_review_enrichment = True

        assert found_review_enrichment, (
            "Live lab workflow should set scheduler.env.K9B_REVIEW_ENRICHMENT_ENABLED=true"
        )

    def test_live_lab_workflow_wires_small_provider(self) -> None:
        """Live lab workflow should wire scheduler.smallProvider.provider=openai_compatible.

        This wires the small provider (used for review enrichment, next-check planning,
        and auto drilldown) to the openai_compatible backend.
        """
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "k9b-otel-demo-live-lab.yml"
        )
        assert workflow_path.exists(), f"Live lab workflow not found: {workflow_path}"

        workflow = cast(dict[str, Any], yaml.safe_load(workflow_path.read_text()))

        # Find the helm --set overrides for smallProvider
        found_small_provider = False
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                run_text = ""
                if "run" in step:
                    run_text = step["run"]
                elif isinstance(step, dict):
                    for key in ("run", "env"):
                        if key in step:
                            run_text += " " + str(step[key])

                if "--set" in run_text and "scheduler.smallProvider.provider" in run_text:
                    assert "openai_compatible" in run_text, (
                        "scheduler.smallProvider.provider should be set to openai_compatible"
                    )
                    found_small_provider = True

        assert found_small_provider, (
            "Live lab workflow should set scheduler.smallProvider.provider=openai_compatible"
        )

    def test_rendered_manifest_has_review_enrichment_provider_in_adapters(
        self,
    ) -> None:
        """Rendered manifest should have a provider for review_enrichment in adapters.

        This is a regression test: review_enrichment needs a provider that points
        to an enabled adapter. Without this, review_enrichment logs:
          provider="unspecified" status="skipped" skip_reason="No review enrichment provider configured"
        """
        external_analysis = cast(
            dict[str, Any],
            render_live_lab_manifest().get("external_analysis", {}),
        )

        adapters_list = external_analysis.get("adapters", [])
        adapters_by_name = {a["name"]: a for a in adapters_list}

        review_enrichment = external_analysis.get("review_enrichment", {})
        provider = review_enrichment.get("provider")

        assert provider, "review_enrichment.provider must be set"
        assert provider in adapters_by_name, (
            f"review_enrichment.provider '{provider}' must be in adapters[]"
        )
        assert adapters_by_name[provider].get("enabled") is True, (
            f"adapter '{provider}' referenced by review_enrichment.provider must be enabled"
        )
