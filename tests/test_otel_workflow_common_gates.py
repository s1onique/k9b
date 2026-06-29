"""Tests for OTel workflow common gates (CNPG-compatible diagnosis provider wiring).

This test module verifies that the OTel demo live-lab workflow correctly
configures the diagnosis provider to mirror the CNPG live lab setup.

Contract:
- GitHub secrets: K9B_DIAGNOSIS_API_KEY, K9B_DIAGNOSIS_BASE_URL, K9B_DIAGNOSIS_MODEL
- Cluster secret:  k9b-diagnosis-credentials (with K9B_DIAGNOSIS_API_KEY, K9B_EXTERNAL_ANALYSIS_API_KEY)
- Provider:      openai_compatible
- Helm values:   diagnosisProvider.*, scheduler.env.*, scheduler.smallProvider.*
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

# The live-lab workflow owns the deployment contract
LIVE_LAB_WORKFLOW = Path(".github/workflows/k9b-otel-demo-live-lab.yml")


def _load_workflow(path: Path) -> dict[str, Any]:
    """Load a workflow YAML file.

    Args:
        path: Path to the workflow YAML file.

    Returns:
        Parsed workflow dict.

    Raises:
        FileNotFoundError: If workflow file does not exist.
    """
    return cast(dict[str, Any], yaml.safe_load(path.read_text()))


def _workflow_run_text(workflow: dict[str, Any]) -> str:
    """Extract all run text from workflow steps.

    Args:
        workflow: Parsed workflow dict.

    Returns:
        Concatenated run text from all steps.
    """
    parts: list[str] = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            if "run" in step:
                parts.append(step["run"])
    return "\n".join(parts)


def _has_helm_override(workflow: dict[str, Any], pattern: str) -> bool:
    """Check if workflow has a Helm --set or --set-string override matching pattern.

    Args:
        workflow: Parsed workflow dict.
        pattern: Substring to search for in Helm override flags.

    Returns:
        True if pattern found in any Helm override.
    """
    run_text = _workflow_run_text(workflow)
    # Check for --set or --set-string followed by the pattern
    for line in run_text.split("\n"):
        if ("--set" in line or "--set-string" in line) and pattern in line:
            return True
    return False


def _has_secret_reference(workflow: dict[str, Any], secret_name: str) -> bool:
    """Check if workflow references a Kubernetes secret name.

    Args:
        workflow: Parsed workflow dict.
        secret_name: Secret name to look for.

    Returns:
        True if secret name is referenced.
    """
    run_text = _workflow_run_text(workflow)
    return secret_name in run_text


def _has_env_var_reference(workflow: dict[str, Any], var_name: str) -> bool:
    """Check if workflow references an environment variable name.

    Args:
        workflow: Parsed workflow dict.
        var_name: Environment variable name to look for.

    Returns:
        True if env var is referenced (e.g., ${{ secrets.VAR_NAME }}).
    """
    run_text = _workflow_run_text(workflow)
    # Match GitHub Actions secret syntax or shell variable references
    return f"${{ secrets.{var_name} }}" in run_text or f"${{{var_name}}}" in run_text


def _has_literal_in_secret_create(workflow: dict[str, Any], literal: str) -> bool:
    """Check if workflow creates a secret with a specific literal.

    Args:
        workflow: Parsed workflow dict.
        literal: Literal string to find in secret creation commands.

    Returns:
        True if literal is found in --from-literal flags.
    """
    run_text = _workflow_run_text(workflow)
    return "--from-literal=" in run_text and literal in run_text


def _has_validation_check(workflow: dict[str, Any], pattern: str) -> bool:
    """Check if workflow has a validation check for a required variable.

    Args:
        workflow: Parsed workflow dict.
        pattern: Pattern to search for (e.g., "is required").

    Returns:
        True if validation pattern is found.
    """
    run_text = _workflow_run_text(workflow)
    return pattern in run_text


class TestOtelWorkflowCommonGates:
    """Test CNPG-compatible diagnosis provider wiring in OTel live-lab workflow."""

    def test_workflow_references_diagnosis_api_key_secret(self) -> None:
        """Workflow should reference K9B_DIAGNOSIS_API_KEY from GitHub secrets."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_env_var_reference(workflow, "K9B_DIAGNOSIS_API_KEY"), (
            "Live-lab workflow should reference K9B_DIAGNOSIS_API_KEY from GitHub secrets"
        )

    def test_workflow_references_diagnosis_base_url_secret(self) -> None:
        """Workflow should reference K9B_DIAGNOSIS_BASE_URL from GitHub secrets."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_env_var_reference(workflow, "K9B_DIAGNOSIS_BASE_URL"), (
            "Live-lab workflow should reference K9B_DIAGNOSIS_BASE_URL from GitHub secrets"
        )

    def test_workflow_references_diagnosis_model_secret(self) -> None:
        """Workflow should reference K9B_DIAGNOSIS_MODEL from GitHub secrets."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_env_var_reference(workflow, "K9B_DIAGNOSIS_MODEL"), (
            "Live-lab workflow should reference K9B_DIAGNOSIS_MODEL from GitHub secrets"
        )

    def test_workflow_creates_k9b_diagnosis_credentials_secret(self) -> None:
        """Workflow should create k9b-diagnosis-credentials cluster secret."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_secret_reference(workflow, "k9b-diagnosis-credentials"), (
            "Live-lab workflow should create k9b-diagnosis-credentials cluster secret"
        )

    def test_workflow_includes_external_analysis_api_key_literal(self) -> None:
        """Workflow secret should include K9B_EXTERNAL_ANALYSIS_API_KEY literal."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_literal_in_secret_create(workflow, "K9B_EXTERNAL_ANALYSIS_API_KEY"), (
            "Live-lab workflow secret should include K9B_EXTERNAL_ANALYSIS_API_KEY literal"
        )

    def test_workflow_enables_diagnosis_provider(self) -> None:
        """Workflow should enable diagnosisProvider.enabled=true via Helm values."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "diagnosisProvider.enabled=true"), (
            "Live-lab workflow should enable diagnosisProvider.enabled=true"
        )

    def test_workflow_sets_openai_compatible_provider(self) -> None:
        """Workflow should set diagnosisProvider.provider=openai_compatible."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "diagnosisProvider.provider=openai_compatible"), (
            "Live-lab workflow should set diagnosisProvider.provider=openai_compatible"
        )

    def test_workflow_uses_existing_secret(self) -> None:
        """Workflow should use existingSecret=k9b-diagnosis-credentials for diagnosisProvider."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "diagnosisProvider.existingSecret=k9b-diagnosis-credentials"), (
            "Live-lab workflow should use existingSecret=k9b-diagnosis-credentials for diagnosisProvider"
        )

    def test_workflow_uses_correct_api_key_key(self) -> None:
        """Workflow should use apiKeyKey=K9B_DIAGNOSIS_API_KEY for diagnosisProvider."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "diagnosisProvider.apiKeyKey=K9B_DIAGNOSIS_API_KEY"), (
            "Live-lab workflow should use apiKeyKey=K9B_DIAGNOSIS_API_KEY for diagnosisProvider"
        )

    def test_workflow_passes_diagnosis_provider_base_url(self) -> None:
        """Workflow should pass diagnosisProvider.baseUrl via Helm values."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "diagnosisProvider.baseUrl="), (
            "Live-lab workflow should pass diagnosisProvider.baseUrl"
        )

    def test_workflow_passes_diagnosis_provider_model(self) -> None:
        """Workflow should pass diagnosisProvider.model via Helm values."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "diagnosisProvider.model="), (
            "Live-lab workflow should pass diagnosisProvider.model"
        )

    def test_workflow_sets_small_provider_existing_secret(self) -> None:
        """Workflow should use existingSecret=k9b-diagnosis-credentials for scheduler.smallProvider."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials"), (
            "Live-lab workflow should use existingSecret=k9b-diagnosis-credentials for scheduler.smallProvider"
        )

    def test_workflow_enables_review_enrichment(self) -> None:
        """Workflow should enable K9B_REVIEW_ENRICHMENT_ENABLED=true for scheduler."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.env.K9B_REVIEW_ENRICHMENT_ENABLED=true"), (
            "Live-lab workflow should enable K9B_REVIEW_ENRICHMENT_ENABLED=true"
        )

    def test_workflow_sets_scheduler_diagnosis_provider_name(self) -> None:
        """Workflow should set scheduler.env.K9B_DIAGNOSIS_PROVIDER_NAME=openai_compatible."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.env.K9B_DIAGNOSIS_PROVIDER_NAME=openai_compatible"), (
            "Live-lab workflow should set scheduler.env.K9B_DIAGNOSIS_PROVIDER_NAME=openai_compatible"
        )

    def test_workflow_sets_scheduler_diagnosis_base_url(self) -> None:
        """Workflow should pass scheduler.env.K9B_DIAGNOSIS_BASE_URL from secret."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.env.K9B_DIAGNOSIS_BASE_URL="), (
            "Live-lab workflow should pass scheduler.env.K9B_DIAGNOSIS_BASE_URL"
        )

    def test_workflow_sets_scheduler_diagnosis_model(self) -> None:
        """Workflow should pass scheduler.env.K9B_DIAGNOSIS_MODEL from secret."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.env.K9B_DIAGNOSIS_MODEL="), (
            "Live-lab workflow should pass scheduler.env.K9B_DIAGNOSIS_MODEL"
        )

    def test_workflow_sets_scheduler_diagnosis_timeout(self) -> None:
        """Workflow should set scheduler.env.K9B_DIAGNOSIS_TIMEOUT_SECONDS=120."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.env.K9B_DIAGNOSIS_TIMEOUT_SECONDS=120"), (
            "Live-lab workflow should set scheduler.env.K9B_DIAGNOSIS_TIMEOUT_SECONDS=120"
        )

    def test_workflow_sets_scheduler_diagnosis_max_output_chars(self) -> None:
        """Workflow should set scheduler.env.K9B_DIAGNOSIS_MAX_OUTPUT_CHARS=8000."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.env.K9B_DIAGNOSIS_MAX_OUTPUT_CHARS=8000"), (
            "Live-lab workflow should set scheduler.env.K9B_DIAGNOSIS_MAX_OUTPUT_CHARS=8000"
        )

    def test_workflow_validates_diagnosis_api_key_not_empty(self) -> None:
        """Workflow should validate K9B_DIAGNOSIS_API_KEY is not empty before creating secret."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        run_text = _workflow_run_text(workflow)
        assert ("K9B_DIAGNOSIS_API_KEY" in run_text and "is required" in run_text), (
            "Live-lab workflow should validate K9B_DIAGNOSIS_API_KEY is not empty before creating secret"
        )

    def test_workflow_validates_all_required_provider_secrets(self) -> None:
        """Workflow should validate all three required provider secrets via for loop."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        run_text = _workflow_run_text(workflow)
        assert "K9B_DIAGNOSIS_API_KEY" in run_text
        assert "K9B_DIAGNOSIS_BASE_URL" in run_text
        assert "K9B_DIAGNOSIS_MODEL" in run_text
        assert "${required} is required" in run_text, (
            "Live-lab workflow should validate required secrets via for loop"
        )

    def test_workflow_validates_diagnosis_base_url_not_empty(self) -> None:
        """Workflow should validate K9B_DIAGNOSIS_BASE_URL is not empty before baseline install."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        run_text = _workflow_run_text(workflow)
        assert "K9B_DIAGNOSIS_BASE_URL" in run_text and "is required" in run_text, (
            "Live-lab workflow should validate K9B_DIAGNOSIS_BASE_URL is not empty"
        )

    def test_workflow_validates_diagnosis_model_not_empty(self) -> None:
        """Workflow should validate K9B_DIAGNOSIS_MODEL is not empty before baseline install."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        run_text = _workflow_run_text(workflow)
        assert "K9B_DIAGNOSIS_MODEL" in run_text and "is required" in run_text, (
            "Live-lab workflow should validate K9B_DIAGNOSIS_MODEL is not empty"
        )

    def test_workflow_sets_backend_diagnosis_timeout(self) -> None:
        """Workflow should set diagnosisProvider.timeoutSeconds=120."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "diagnosisProvider.timeoutSeconds=120"), (
            "Live-lab workflow should set diagnosisProvider.timeoutSeconds=120"
        )

    def test_workflow_sets_backend_diagnosis_max_output_chars(self) -> None:
        """Workflow should set diagnosisProvider.maxOutputChars=8000."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "diagnosisProvider.maxOutputChars=8000"), (
            "Live-lab workflow should set diagnosisProvider.maxOutputChars=8000"
        )

    def test_workflow_sets_small_provider_api_key_key(self) -> None:
        """Workflow should use apiKeyKey=K9B_EXTERNAL_ANALYSIS_API_KEY for scheduler.smallProvider."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.smallProvider.apiKeyKey=K9B_EXTERNAL_ANALYSIS_API_KEY"), (
            "Live-lab workflow should use apiKeyKey=K9B_EXTERNAL_ANALYSIS_API_KEY for scheduler.smallProvider"
        )

    def test_workflow_sets_external_analysis_base_url(self) -> None:
        """Workflow should set scheduler.env.K9B_EXTERNAL_ANALYSIS_BASE_URL from secret."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.env.K9B_EXTERNAL_ANALYSIS_BASE_URL="), (
            "Live-lab workflow should set scheduler.env.K9B_EXTERNAL_ANALYSIS_BASE_URL"
        )

    def test_workflow_sets_external_analysis_model(self) -> None:
        """Workflow should set scheduler.env.K9B_EXTERNAL_ANALYSIS_MODEL from secret."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.env.K9B_EXTERNAL_ANALYSIS_MODEL="), (
            "Live-lab workflow should set scheduler.env.K9B_EXTERNAL_ANALYSIS_MODEL"
        )

    def test_workflow_no_stale_openrouter_names(self) -> None:
        """Workflow should not use stale OpenRouter-specific names.

        Note: "otel" contains "openrouter" as substring, so we check for
        actual OpenRouter identifiers, not case-insensitive substring match.
        """
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        run_text = _workflow_run_text(workflow)
        assert "OPENROUTER_API_KEY" not in run_text
        assert "openrouter_api_key" not in run_text
        assert "openrouter_model" not in run_text

    def test_workflow_enables_automatic_diagnosis_loop(self) -> None:
        """Workflow should enable K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true for scheduler."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.env.K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true"), (
            "Live-lab workflow should enable K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true"
        )

    def test_workflow_enables_auto_drilldown(self) -> None:
        """Workflow should enable K9B_AUTO_DRILLDOWN_ENABLED=true for scheduler."""
        workflow = _load_workflow(LIVE_LAB_WORKFLOW)
        assert _has_helm_override(workflow, "scheduler.env.K9B_AUTO_DRILLDOWN_ENABLED=true"), (
            "Live-lab workflow should enable K9B_AUTO_DRILLDOWN_ENABLED=true"
        )
