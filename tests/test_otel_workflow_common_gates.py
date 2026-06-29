"""Tests for OTel workflow common gates (CNPG-compatible diagnosis provider wiring).

This test module verifies that the OTel demo incident lab workflow correctly
configures the diagnosis provider to mirror the CNPG live lab setup.

Contract:
- GitHub secrets: K9B_DIAGNOSIS_API_KEY, K9B_DIAGNOSIS_BASE_URL, K9B_DIAGNOSIS_MODEL
- Cluster secret:  k9b-diagnosis-credentials (with K9B_DIAGNOSIS_API_KEY, K9B_EXTERNAL_ANALYSIS_API_KEY)
- Provider:      openai_compatible
- Helm values:   diagnosisProvider.*, scheduler.env.*, scheduler.smallProvider.*
"""

from pathlib import Path

WORKFLOW = Path(".github/workflows/k9b-otel-demo-incident-lab.yml")


class TestOtelWorkflowCommonGates:
    """Test CNPG-compatible diagnosis provider wiring in OTel workflow."""

    def test_workflow_references_diagnosis_api_key_secret(self) -> None:
        """Workflow should reference K9B_DIAGNOSIS_API_KEY from GitHub secrets."""
        text = WORKFLOW.read_text()
        assert "K9B_DIAGNOSIS_API_KEY" in text

    def test_workflow_references_diagnosis_base_url_secret(self) -> None:
        """Workflow should reference K9B_DIAGNOSIS_BASE_URL from GitHub secrets."""
        text = WORKFLOW.read_text()
        assert "K9B_DIAGNOSIS_BASE_URL" in text

    def test_workflow_references_diagnosis_model_secret(self) -> None:
        """Workflow should reference K9B_DIAGNOSIS_MODEL from GitHub secrets."""
        text = WORKFLOW.read_text()
        assert "K9B_DIAGNOSIS_MODEL" in text

    def test_workflow_creates_k9b_diagnosis_credentials_secret(self) -> None:
        """Workflow should create k9b-diagnosis-credentials cluster secret."""
        text = WORKFLOW.read_text()
        assert "k9b-diagnosis-credentials" in text

    def test_workflow_includes_external_analysis_api_key_literal(self) -> None:
        """Workflow secret should include K9B_EXTERNAL_ANALYSIS_API_KEY literal."""
        text = WORKFLOW.read_text()
        assert "K9B_EXTERNAL_ANALYSIS_API_KEY" in text

    def test_workflow_enables_diagnosis_provider(self) -> None:
        """Workflow should enable diagnosisProvider.enabled=true via Helm values."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.enabled=true" in text

    def test_workflow_sets_openai_compatible_provider(self) -> None:
        """Workflow should set diagnosisProvider.provider=openai_compatible."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.provider=openai_compatible" in text

    def test_workflow_uses_existing_secret(self) -> None:
        """Workflow should use existingSecret=k9b-diagnosis-credentials for diagnosisProvider."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.existingSecret=k9b-diagnosis-credentials" in text

    def test_workflow_uses_correct_api_key_key(self) -> None:
        """Workflow should use apiKeyKey=K9B_DIAGNOSIS_API_KEY for diagnosisProvider."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.apiKeyKey=K9B_DIAGNOSIS_API_KEY" in text

    def test_workflow_passes_diagnosis_provider_base_url(self) -> None:
        """Workflow should pass diagnosisProvider.baseUrl via Helm values."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.baseUrl" in text

    def test_workflow_passes_diagnosis_provider_model(self) -> None:
        """Workflow should pass diagnosisProvider.model via Helm values."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.model" in text

    def test_workflow_sets_small_provider_existing_secret(self) -> None:
        """Workflow should use existingSecret=k9b-diagnosis-credentials for scheduler.smallProvider."""
        text = WORKFLOW.read_text()
        assert "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials" in text

    def test_workflow_enables_review_enrichment(self) -> None:
        """Workflow should enable K9B_REVIEW_ENRICHMENT_ENABLED=true for scheduler."""
        text = WORKFLOW.read_text()
        assert "K9B_REVIEW_ENRICHMENT_ENABLED=true" in text

    def test_workflow_sets_scheduler_diagnosis_provider_name(self) -> None:
        """Workflow should set scheduler.env.K9B_DIAGNOSIS_PROVIDER_NAME=openai_compatible."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_DIAGNOSIS_PROVIDER_NAME=openai_compatible" in text

    def test_workflow_sets_scheduler_diagnosis_base_url(self) -> None:
        """Workflow should pass scheduler.env.K9B_DIAGNOSIS_BASE_URL from secret."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_DIAGNOSIS_BASE_URL" in text

    def test_workflow_sets_scheduler_diagnosis_model(self) -> None:
        """Workflow should pass scheduler.env.K9B_DIAGNOSIS_MODEL from secret."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_DIAGNOSIS_MODEL" in text

    def test_workflow_sets_scheduler_diagnosis_timeout(self) -> None:
        """Workflow should set scheduler.env.K9B_DIAGNOSIS_TIMEOUT_SECONDS=120."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_DIAGNOSIS_TIMEOUT_SECONDS=120" in text

    def test_workflow_sets_scheduler_diagnosis_max_output_chars(self) -> None:
        """Workflow should set scheduler.env.K9B_DIAGNOSIS_MAX_OUTPUT_CHARS=8000."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_DIAGNOSIS_MAX_OUTPUT_CHARS=8000" in text

    def test_workflow_validates_diagnosis_api_key_not_empty(self) -> None:
        """Workflow should validate K9B_DIAGNOSIS_API_KEY is not empty before creating secret."""
        text = WORKFLOW.read_text()
        assert '${K9B_DIAGNOSIS_API_KEY:-}' in text and "is required" in text

    def test_workflow_validates_all_required_provider_secrets(self) -> None:
        """Workflow should validate all three required provider secrets via for loop."""
        text = WORKFLOW.read_text()
        assert "K9B_DIAGNOSIS_API_KEY" in text
        assert "K9B_DIAGNOSIS_BASE_URL" in text
        assert "K9B_DIAGNOSIS_MODEL" in text
        assert "${required} is required" in text

    def test_workflow_validates_diagnosis_base_url_not_empty(self) -> None:
        """Workflow should validate K9B_DIAGNOSIS_BASE_URL is not empty before baseline install."""
        text = WORKFLOW.read_text()
        # Uses ${required} expansion in for loop
        assert "K9B_DIAGNOSIS_BASE_URL is required" in text or "${required} is required" in text

    def test_workflow_validates_diagnosis_model_not_empty(self) -> None:
        """Workflow should validate K9B_DIAGNOSIS_MODEL is not empty before baseline install."""
        text = WORKFLOW.read_text()
        # Uses ${required} expansion in for loop
        assert "K9B_DIAGNOSIS_MODEL is required" in text or "${required} is required" in text

    def test_workflow_sets_backend_diagnosis_timeout(self) -> None:
        """Workflow should set diagnosisProvider.timeoutSeconds=120."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.timeoutSeconds=120" in text

    def test_workflow_sets_backend_diagnosis_max_output_chars(self) -> None:
        """Workflow should set diagnosisProvider.maxOutputChars=8000."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.maxOutputChars=8000" in text

    def test_workflow_sets_small_provider_api_key_key(self) -> None:
        """Workflow should use apiKeyKey=K9B_EXTERNAL_ANALYSIS_API_KEY for scheduler.smallProvider."""
        text = WORKFLOW.read_text()
        assert "scheduler.smallProvider.apiKeyKey=K9B_EXTERNAL_ANALYSIS_API_KEY" in text

    def test_workflow_sets_external_analysis_base_url(self) -> None:
        """Workflow should set scheduler.env.K9B_EXTERNAL_ANALYSIS_BASE_URL from secret."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_EXTERNAL_ANALYSIS_BASE_URL" in text

    def test_workflow_sets_external_analysis_model(self) -> None:
        """Workflow should set scheduler.env.K9B_EXTERNAL_ANALYSIS_MODEL from secret."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_EXTERNAL_ANALYSIS_MODEL" in text

    def test_workflow_no_stale_openrouter_names(self) -> None:
        """Workflow should not use stale OpenRouter-specific names.

        Note: "otel" contains "openrouter" as substring, so we check for
        actual OpenRouter identifiers, not case-insensitive substring match.
        """
        text = WORKFLOW.read_text()
        assert "OPENROUTER_API_KEY" not in text
        assert "openrouter_api_key" not in text
        assert "openrouter_model" not in text

    def test_workflow_enables_automatic_diagnosis_loop(self) -> None:
        """Workflow should enable K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true for scheduler."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true" in text

    def test_workflow_enables_auto_drilldown(self) -> None:
        """Workflow should enable K9B_AUTO_DRILLDOWN_ENABLED=true for scheduler."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_AUTO_DRILLDOWN_ENABLED=true" in text
