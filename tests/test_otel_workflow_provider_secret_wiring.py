"""Tests for OTel workflow provider secret wiring (mirrors CNPG contract).

These tests verify that the OTel demo incident lab workflow correctly wires
LLM diagnosis credentials using the same contract as CNPG live lab.

Contract with CNPG live lab:
- GitHub secrets: K9B_DIAGNOSIS_API_KEY, K9B_DIAGNOSIS_BASE_URL, K9B_DIAGNOSIS_MODEL
- Cluster secret:  k9b-diagnosis-credentials
- Secret keys:     K9B_DIAGNOSIS_API_KEY, K9B_EXTERNAL_ANALYSIS_API_KEY
- Provider:        openai_compatible
"""

from pathlib import Path

WORKFLOW = Path(".github/workflows/k9b-otel-demo-incident-lab.yml")


class TestOtelWorkflowProviderSecretWiring:
    """Test that OTel workflow wires provider secrets like CNPG."""

    def test_workflow_references_diagnosis_api_key_secret(self) -> None:
        """Workflow should reference K9B_DIAGNOSIS_API_KEY from GitHub secrets."""
        text = WORKFLOW.read_text()
        assert "secrets.K9B_DIAGNOSIS_API_KEY" in text

    def test_workflow_creates_k9b_diagnosis_credentials_secret(self) -> None:
        """Workflow should create k9b-diagnosis-credentials cluster secret."""
        text = WORKFLOW.read_text()
        assert "k9b-diagnosis-credentials" in text

    def test_workflow_includes_diagnosis_api_key_literal(self) -> None:
        """Workflow secret should include K9B_DIAGNOSIS_API_KEY literal."""
        text = WORKFLOW.read_text()
        assert "K9B_DIAGNOSIS_API_KEY" in text

    def test_workflow_includes_external_analysis_api_key_literal(self) -> None:
        """Workflow secret should include K9B_EXTERNAL_ANALYSIS_API_KEY literal."""
        text = WORKFLOW.read_text()
        assert "K9B_EXTERNAL_ANALYSIS_API_KEY" in text

    def test_workflow_validates_diagnosis_api_key_not_empty(self) -> None:
        """Workflow should validate K9B_DIAGNOSIS_API_KEY is not empty before creating secret."""
        text = WORKFLOW.read_text()
        assert 'if [ -z "${K9B_DIAGNOSIS_API_KEY:-}" ]' in text
        assert "K9B_DIAGNOSIS_API_KEY is required" in text

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


class TestOtelWorkflowProviderConfig:
    """Test that OTel workflow configures diagnosisProvider correctly."""

    def test_workflow_enables_diagnosis_provider(self) -> None:
        """Workflow should enable diagnosisProvider via Helm values."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.enabled=true" in text

    def test_workflow_sets_openai_compatible_provider(self) -> None:
        """Workflow should set provider to openai_compatible."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.provider=openai_compatible" in text

    def test_workflow_uses_existing_secret(self) -> None:
        """Workflow should use existingSecret for diagnosisProvider."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.existingSecret=k9b-diagnosis-credentials" in text

    def test_workflow_uses_correct_api_key_key(self) -> None:
        """Workflow should use K9B_DIAGNOSIS_API_KEY as apiKeyKey."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.apiKeyKey=K9B_DIAGNOSIS_API_KEY" in text


class TestOtelWorkflowSchedulerProvider:
    """Test that OTel workflow configures scheduler smallProvider correctly."""

    def test_workflow_enables_review_enrichment(self) -> None:
        """Workflow should enable K9B_REVIEW_ENRICHMENT_ENABLED."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_REVIEW_ENRICHMENT_ENABLED=true" in text

    def test_workflow_sets_external_analysis_base_url(self) -> None:
        """Workflow should set K9B_EXTERNAL_ANALYSIS_BASE_URL from secret."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_EXTERNAL_ANALYSIS_BASE_URL=${K9B_DIAGNOSIS_BASE_URL}" in text

    def test_workflow_sets_external_analysis_model(self) -> None:
        """Workflow should set K9B_EXTERNAL_ANALYSIS_MODEL from secret."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_EXTERNAL_ANALYSIS_MODEL=${K9B_DIAGNOSIS_MODEL}" in text

    def test_workflow_uses_small_provider_existing_secret(self) -> None:
        """Workflow should use existingSecret for scheduler.smallProvider."""
        text = WORKFLOW.read_text()
        assert "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials" in text

    def test_workflow_uses_small_provider_api_key_key(self) -> None:
        """Workflow should use K9B_EXTERNAL_ANALYSIS_API_KEY for smallProvider."""
        text = WORKFLOW.read_text()
        assert "scheduler.smallProvider.apiKeyKey=K9B_EXTERNAL_ANALYSIS_API_KEY" in text


class TestOtelWorkflowSecretsFromEnvironment:
    """Test that OTel workflow passes secrets from environment."""

    def test_workflow_passes_diagnosis_base_url_to_baseline(self) -> None:
        """Workflow should pass K9B_DIAGNOSIS_BASE_URL from secret to baseline."""
        text = WORKFLOW.read_text()
        assert "K9B_DIAGNOSIS_BASE_URL: ${{ secrets.K9B_DIAGNOSIS_BASE_URL }}" in text

    def test_workflow_passes_diagnosis_model_to_baseline(self) -> None:
        """Workflow should pass K9B_DIAGNOSIS_MODEL from secret to baseline."""
        text = WORKFLOW.read_text()
        assert "K9B_DIAGNOSIS_MODEL: ${{ secrets.K9B_DIAGNOSIS_MODEL }}" in text


class TestOtelWorkflowNoStaleInputs:
    """Regression tests to prevent drift back to stale OpenRouter-specific names."""

    def test_workflow_does_not_use_stale_openrouter_specific_inputs(self) -> None:
        """Workflow should use CNPG-compatible K9B_DIAGNOSIS_* secrets, not stale OpenRouter names."""
        text = WORKFLOW.read_text()

        assert "OPENROUTER_API_KEY" not in text
        assert "openrouter_model" not in text
