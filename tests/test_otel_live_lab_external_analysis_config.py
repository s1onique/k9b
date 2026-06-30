"""Tests for OTel live-lab external analysis Helm configuration.

These tests verify that the live-lab values file renders correct scheduler
environment variables for external analysis (review enrichment, auto drilldown).

Regression tests for:
- Review enrichment was skipped with provider="unspecified" due to missing env vars
- K9B_EXTERNAL_ANALYSIS_MAX_TOKENS_AUTO_DRILLDOWN not rendered
"""

import subprocess
from pathlib import Path
from typing import Any, cast

import yaml


def _load_yaml_mapping(content: str) -> dict[str, Any]:
    """Parse YAML content and assert it is a mapping dict."""
    loaded: object = yaml.safe_load(content)
    if not isinstance(loaded, dict):
        raise AssertionError("YAML content must parse to a mapping")
    return cast(dict[str, Any], loaded)


def _rendered_scheduler_deployment() -> dict[str, Any]:
    """Render the live-lab manifest and return the scheduler Deployment dict."""
    result = subprocess.run(
        [
            "helm", "template", "k9b", "charts/k9b",
            "-f", "charts/k9b/values-live-lab.yaml",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).parent.parent,
    )
    for doc in yaml.safe_load_all(result.stdout):
        if doc and doc.get("kind") == "Deployment" and doc["metadata"]["name"].endswith("scheduler"):
            return cast(dict[str, Any], doc)
    raise AssertionError("scheduler Deployment not found in rendered manifest")


def _scheduler_env() -> dict[str, str]:
    """Return scheduler container env as {name: value} dict."""
    deployment = _rendered_scheduler_deployment()
    containers = deployment["spec"]["template"]["spec"]["containers"]
    scheduler_container = next(
        (c for c in containers if c["name"] == "scheduler"),
        containers[0],
    )
    return {e["name"]: e.get("value") for e in scheduler_container.get("env", [])}


def _health_config_data() -> dict[str, Any]:
    """Return the parsed health-config.json data from the rendered ConfigMap."""
    result = subprocess.run(
        [
            "helm", "template", "k9b", "charts/k9b",
            "-f", "charts/k9b/values-live-lab.yaml",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).parent.parent,
    )
    for doc in yaml.safe_load_all(result.stdout):
        if doc and doc.get("kind") == "ConfigMap" and doc["metadata"]["name"].endswith("health-config"):
            health_config_raw = doc["data"]["health-config.json"]
            return _load_yaml_mapping(health_config_raw)
    raise AssertionError("health-config ConfigMap not found in rendered manifest")


class TestOtelLiveLabExternalAnalysisHelmRender:
    """Test that values-live-lab.yaml renders correct scheduler env vars."""

    def test_scheduler_env_has_review_enrichment_enabled(self) -> None:
        """Scheduler env should have K9B_REVIEW_ENRICHMENT_ENABLED=true."""
        env = _scheduler_env()
        assert env.get("K9B_REVIEW_ENRICHMENT_ENABLED") == "true"

    def test_scheduler_env_has_auto_drilldown_enabled(self) -> None:
        """Scheduler env should have K9B_AUTO_DRILLDOWN_ENABLED=true."""
        env = _scheduler_env()
        assert env.get("K9B_AUTO_DRILLDOWN_ENABLED") == "true"

    def test_scheduler_env_has_openai_compatible_provider(self) -> None:
        """Scheduler env should have K9B_EXTERNAL_ANALYSIS_PROVIDER=openai_compatible."""
        env = _scheduler_env()
        assert env.get("K9B_EXTERNAL_ANALYSIS_PROVIDER") == "openai_compatible"

    def test_scheduler_env_has_max_tokens_auto_drilldown(self) -> None:
        """Scheduler env should have K9B_EXTERNAL_ANALYSIS_MAX_TOKENS_AUTO_DRILLDOWN=3072."""
        env = _scheduler_env()
        assert env.get("K9B_EXTERNAL_ANALYSIS_MAX_TOKENS_AUTO_DRILLDOWN") == "3072"

    def test_scheduler_env_has_max_tokens_review_enrichment(self) -> None:
        """Scheduler env should have K9B_EXTERNAL_ANALYSIS_MAX_TOKENS_REVIEW_ENRICHMENT=4096."""
        env = _scheduler_env()
        assert env.get("K9B_EXTERNAL_ANALYSIS_MAX_TOKENS_REVIEW_ENRICHMENT") == "4096"


class TestOtelLiveLabHealthConfigExternalAnalysis:
    """Test that health-config ConfigMap contains correct external analysis settings."""

    def test_health_config_adapter_enabled(self) -> None:
        """Health config should have openai_compatible adapter enabled."""
        config = _health_config_data()
        adapters_by_name = {a["name"]: a for a in config["external_analysis"]["adapters"]}
        assert "openai_compatible" in adapters_by_name
        assert adapters_by_name["openai_compatible"]["enabled"] is True

    def test_health_config_auto_drilldown_provider(self) -> None:
        """Health config should have auto_drilldown.provider=openai_compatible."""
        config = _health_config_data()
        external_analysis = config["external_analysis"]
        assert external_analysis["auto_drilldown"]["provider"] == "openai_compatible"
        assert external_analysis["auto_drilldown"]["enabled"] is True

    def test_health_config_review_enrichment_provider(self) -> None:
        """Health config should have review_enrichment.provider=openai_compatible."""
        config = _health_config_data()
        external_analysis = config["external_analysis"]
        assert external_analysis["review_enrichment"]["provider"] == "openai_compatible"
        assert external_analysis["review_enrichment"]["enabled"] is True
