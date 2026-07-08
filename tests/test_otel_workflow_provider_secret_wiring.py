"""Tests for OTel workflow provider secret wiring (mirrors CNPG contract).

These tests verify that the OTel live lab workflow correctly wires
LLM diagnosis credentials using the same contract as CNPG live lab.

Contract with CNPG live lab:
- GitHub secrets: K9B_DIAGNOSIS_API_KEY, K9B_DIAGNOSIS_BASE_URL, K9B_DIAGNOSIS_MODEL
- Cluster secret:  k9b-diagnosis-credentials
- Secret keys:     K9B_DIAGNOSIS_API_KEY, K9B_EXTERNAL_ANALYSIS_API_KEY
- Provider:        openai_compatible

NOTE: This file tests the OTel LIVE LAB workflow (k9b-otel-demo-live-lab.yml).
CI-only workflow (k9b-otel-demo-incident-lab.yml) is scaffold-only.
"""

from pathlib import Path

from tests.helm_test_helpers import COMMON_INTERNAL_API_SET

WORKFLOW = Path(".github/workflows/k9b-otel-demo-live-lab.yml")
CI_ONLY_WORKFLOW = Path(".github/workflows/k9b-otel-demo-incident-lab.yml")


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

    def test_workflow_sets_small_provider_provider_type(self) -> None:
        """Workflow should set scheduler.smallProvider.provider to openai_compatible (CNPG parity)."""
        text = WORKFLOW.read_text()
        assert "scheduler.smallProvider.provider=openai_compatible" in text

    def test_workflow_sets_external_analysis_provider(self) -> None:
        """Workflow should set K9B_EXTERNAL_ANALYSIS_PROVIDER=openai_compatible."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_EXTERNAL_ANALYSIS_PROVIDER=openai_compatible" in text

    def test_workflow_enables_automatic_diagnosis_loop(self) -> None:
        """Workflow should enable K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true" in text

    def test_workflow_enables_auto_drilldown(self) -> None:
        """Workflow should enable K9B_AUTO_DRILLDOWN_ENABLED=true."""
        text = WORKFLOW.read_text()
        assert "scheduler.env.K9B_AUTO_DRILLDOWN_ENABLED=true" in text


class TestOtelWorkflowSchedulerProviderSecretParity:
    """Test scheduler provider wiring matches CNPG live lab contract.

    Regression tests for the scheduler provider parity issue:
    - review_enrichment was skipped with provider="unspecified"
    - automatic diagnosis loop was disabled

    These tests verify the OTel workflow now mirrors CNPG's scheduler small-provider wiring.
    """

    def test_workflow_wires_scheduler_automatic_diagnosis_loop(self) -> None:
        """Workflow should wire scheduler automatic diagnosis loop (CNPG parity)."""
        text = WORKFLOW.read_text()
        assert "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true" in text

    def test_workflow_wires_scheduler_review_enrichment_provider(self) -> None:
        """Workflow should wire scheduler review enrichment provider (CNPG parity)."""
        text = WORKFLOW.read_text()
        assert "scheduler.smallProvider" in text
        assert "K9B_REVIEW_ENRICHMENT_ENABLED=true" in text
        assert "K9B_EXTERNAL_ANALYSIS_BASE_URL" in text
        assert "K9B_EXTERNAL_ANALYSIS_MODEL" in text
        assert "K9B_EXTERNAL_ANALYSIS_API_KEY" in text
        assert "scheduler.smallProvider.provider=openai_compatible" in text

    def test_workflow_uses_same_secret_for_backend_and_scheduler_providers(self) -> None:
        """Workflow should use same k9b-diagnosis-credentials secret for both providers."""
        text = WORKFLOW.read_text()
        assert "k9b-diagnosis-credentials" in text
        assert "K9B_DIAGNOSIS_API_KEY" in text
        assert "K9B_EXTERNAL_ANALYSIS_API_KEY" in text

    def test_workflow_has_all_required_scheduler_provider_env_vars(self) -> None:
        """Workflow should pass all required scheduler provider env vars."""
        text = WORKFLOW.read_text()
        required_vars = [
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true",
            "K9B_AUTO_DRILLDOWN_ENABLED=true",
            "K9B_REVIEW_ENRICHMENT_ENABLED=true",
            "K9B_EXTERNAL_ANALYSIS_PROVIDER=openai_compatible",
            "K9B_EXTERNAL_ANALYSIS_BASE_URL",
            "K9B_EXTERNAL_ANALYSIS_MODEL",
        ]
        for var in required_vars:
            assert var in text, f"Missing scheduler provider config: {var}"

    def test_workflow_has_small_provider_complete_config(self) -> None:
        """Workflow should have complete smallProvider config (CNPG parity)."""
        text = WORKFLOW.read_text()
        assert "scheduler.smallProvider.provider=openai_compatible" in text
        assert "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials" in text
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


class TestOtelWorkflowBackendProviderConfigParity:
    """Test backend diagnosisProvider Helm values match CNPG live lab.

    These tests prevent regression of the root cause of 503 errors in OTel live lab:
    CNPG passes diagnosisProvider.baseUrl, diagnosisProvider.model, timeoutSeconds,
    and maxOutputChars, but OTel was missing baseUrl and model, causing the backend
    to receive empty env vars from chart defaults.
    """

    def test_workflow_passes_backend_diagnosis_provider_base_url(self) -> None:
        """Workflow should pass diagnosisProvider.baseUrl to Helm (CNPG parity)."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.baseUrl=${K9B_DIAGNOSIS_BASE_URL}" in text

    def test_workflow_passes_backend_diagnosis_provider_model(self) -> None:
        """Workflow should pass diagnosisProvider.model to Helm (CNPG parity)."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.model=${K9B_DIAGNOSIS_MODEL}" in text

    def test_workflow_sets_backend_diagnosis_provider_timeout_seconds(self) -> None:
        """Workflow should set diagnosisProvider.timeoutSeconds=120 (CNPG parity)."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.timeoutSeconds=120" in text

    def test_workflow_sets_backend_diagnosis_provider_max_output_chars(self) -> None:
        """Workflow should set diagnosisProvider.maxOutputChars=8000 (CNPG parity)."""
        text = WORKFLOW.read_text()
        assert "diagnosisProvider.maxOutputChars=8000" in text


class TestOtelWorkflowSchedulerRenderedManifest:
    """Test that scheduler rendered manifest has correct env vars.

    These tests render the Helm chart and verify the scheduler container
    receives the correct env vars. This is stronger than workflow substring
    checks because it proves the chart actually produces the desired output.

    Regression tests for the scheduler provider parity issue:
    - review_enrichment was skipped with provider="unspecified"
    - automatic diagnosis loop was disabled
    """

    def test_rendered_scheduler_has_required_external_analysis_env_vars(self) -> None:
        """Rendered scheduler manifest should have required external analysis env vars."""
        import subprocess
        result = subprocess.run(
            [
                "helm", "template", "k9b", "charts/k9b",
                "--namespace", "k9b",
                "--set", "scheduler.env.K9B_REVIEW_ENRICHMENT_ENABLED=true",
                "--set", "scheduler.env.K9B_EXTERNAL_ANALYSIS_BASE_URL=https://example.com",
                "--set", "scheduler.env.K9B_EXTERNAL_ANALYSIS_MODEL=gpt-4",
                "--set", "scheduler.env.K9B_AUTO_DRILLDOWN_ENABLED=true",
                "--set", "scheduler.env.K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true",
                "--set", "scheduler.env.K9B_EXTERNAL_ANALYSIS_PROVIDER=openai_compatible",
                "--set", "scheduler.smallProvider.provider=openai_compatible",
                "--set", "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials",
                "--set", "scheduler.smallProvider.apiKeyKey=K9B_EXTERNAL_ANALYSIS_API_KEY",
                *COMMON_INTERNAL_API_SET,
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0, f"helm template failed: {result.stderr}"

        manifest = result.stdout

        # Verify scheduler container exists
        assert "name: k9b-scheduler" in manifest

        # Verify key env vars are rendered
        required_env_vars = [
            'name: K9B_REVIEW_ENRICHMENT_ENABLED',
            'value: "true"',
            'name: K9B_EXTERNAL_ANALYSIS_PROVIDER',
            'value: "openai_compatible"',
            'name: K9B_EXTERNAL_ANALYSIS_BASE_URL',
            'value: "https://example.com"',
            'name: K9B_EXTERNAL_ANALYSIS_MODEL',
            'value: "gpt-4"',
        ]
        for env_var in required_env_vars:
            assert env_var in manifest, f"Missing in rendered manifest: {env_var}"

    def test_rendered_scheduler_has_secret_key_ref_for_api_key(self) -> None:
        """Rendered scheduler manifest should have secretKeyRef for K9B_EXTERNAL_ANALYSIS_API_KEY."""
        import subprocess
        result = subprocess.run(
            [
                "helm", "template", "k9b", "charts/k9b",
                "--namespace", "k9b",
                "--set", "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials",
                "--set", "scheduler.smallProvider.apiKeyKey=K9B_EXTERNAL_ANALYSIS_API_KEY",
                *COMMON_INTERNAL_API_SET,
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0, f"helm template failed: {result.stderr}"

        manifest = result.stdout

        # Verify secretKeyRef is rendered
        assert "name: K9B_EXTERNAL_ANALYSIS_API_KEY" in manifest
        assert "secretKeyRef:" in manifest
        assert "name: k9b-diagnosis-credentials" in manifest
        assert "key: K9B_EXTERNAL_ANALYSIS_API_KEY" in manifest

    def test_rendered_scheduler_has_explicit_provider_not_empty(self) -> None:
        """Rendered scheduler should have K9B_EXTERNAL_ANALYSIS_PROVIDER set to openai_compatible."""
        import subprocess
        result = subprocess.run(
            [
                "helm", "template", "k9b", "charts/k9b",
                "--namespace", "k9b",
                "--set", "scheduler.env.K9B_EXTERNAL_ANALYSIS_PROVIDER=openai_compatible",
                *COMMON_INTERNAL_API_SET,
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0, f"helm template failed: {result.stderr}"

        manifest = result.stdout

        # Provider should be explicitly set to openai_compatible
        # Check for the specific env var being set to openai_compatible
        assert 'name: K9B_EXTERNAL_ANALYSIS_PROVIDER' in manifest
        assert 'value: "openai_compatible"' in manifest


class TestOtelCiWorkflowIsCiOnly:
    """Test that CI-only workflow stays small and does NOT contain live-lab markers."""

    def test_ci_workflow_is_ci_only(self) -> None:
        """CI-only workflow should NOT contain live-lab markers."""
        text = CI_ONLY_WORKFLOW.read_text()
        # CI-only workflow should have CI markers
        assert "K3s OTel Demo Incident Lab CI" in text
        assert "build-and-verify" in text
        # CI-only workflow should NOT have live-lab markers
        assert "live-k3s-lab" not in text
        assert "harbor-pve1.spbnix.local" not in text
        assert "diagnosisProvider.existingSecret=k9b-diagnosis-credentials" not in text
        assert "Ensure k9b lab baseline" not in text
        assert "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true" not in text
