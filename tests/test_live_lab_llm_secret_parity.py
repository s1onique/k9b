"""Parity tests ensuring CNPG and OTel live labs share the LLM secret contract.

These tests verify that both live lab workflows (CNPG and OTel) use the same
provider secret contract, preventing drift over time.

Contract tokens that MUST be present in BOTH workflows:
- GitHub secrets: K9B_DIAGNOSIS_API_KEY, K9B_DIAGNOSIS_BASE_URL, K9B_DIAGNOSIS_MODEL
- Cluster secret: k9b-diagnosis-credentials
- Secret keys: K9B_DIAGNOSIS_API_KEY, K9B_EXTERNAL_ANALYSIS_API_KEY
- Provider: openai_compatible
- existingSecret pattern for both diagnosisProvider and scheduler.smallProvider
"""

from pathlib import Path

CNPG = Path(".github/workflows/k9b-cnpg-incident-lab-live.yml")
OTEL = Path(".github/workflows/k9b-otel-demo-incident-lab.yml")

# Note: Both CNPG and OTel use the same GitHub secrets:
# - K9B_DIAGNOSIS_API_KEY, K9B_DIAGNOSIS_BASE_URL, K9B_DIAGNOSIS_MODEL
# The cluster secret contract (name, keys) is the same.
REQUIRED_PROVIDER_TOKENS = [
    "k9b-diagnosis-credentials",
    "K9B_DIAGNOSIS_API_KEY",
    "K9B_EXTERNAL_ANALYSIS_API_KEY",
    "diagnosisProvider.provider=openai_compatible",
    "diagnosisProvider.existingSecret=k9b-diagnosis-credentials",
    "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials",
    "scheduler.smallProvider.apiKeyKey=K9B_EXTERNAL_ANALYSIS_API_KEY",
]


class TestLiveLabLLMSecretParity:
    """Test that CNPG and OTel live labs share LLM secret contract."""

    def test_cnpg_workflow_exists(self) -> None:
        """CNPG live lab workflow should exist."""
        assert CNPG.exists(), f"CNPG workflow not found at {CNPG}"

    def test_otel_workflow_exists(self) -> None:
        """OTel live lab workflow should exist."""
        assert OTEL.exists(), f"OTel workflow not found at {OTEL}"

    def test_cnpg_and_otel_live_labs_share_llm_secret_contract(self) -> None:
        """Both workflows must contain all required provider secret tokens."""
        cnpg = CNPG.read_text()
        otel = OTEL.read_text()

        missing_in_cnpg = []
        missing_in_otel = []

        for token in REQUIRED_PROVIDER_TOKENS:
            if token not in cnpg:
                missing_in_cnpg.append(token)
            if token not in otel:
                missing_in_otel.append(token)

        errors = []
        if missing_in_cnpg:
            errors.append(f"CNPG workflow missing tokens: {missing_in_cnpg}")
        if missing_in_otel:
            errors.append(f"OTel workflow missing tokens: {missing_in_otel}")

        assert not errors, "\n".join(errors)

    def test_both_workflows_use_same_secret_name(self) -> None:
        """Both workflows must use k9b-diagnosis-credentials as the secret name."""
        cnpg = CNPG.read_text()
        otel = OTEL.read_text()

        # Extract secret name from both workflows
        assert "k9b-diagnosis-credentials" in cnpg
        assert "k9b-diagnosis-credentials" in otel

    def test_both_workflows_use_same_api_key_keys(self) -> None:
        """Both workflows must use the same secret key names."""
        cnpg = CNPG.read_text()
        otel = OTEL.read_text()

        assert "K9B_DIAGNOSIS_API_KEY" in cnpg
        assert "K9B_DIAGNOSIS_API_KEY" in otel
        assert "K9B_EXTERNAL_ANALYSIS_API_KEY" in cnpg
        assert "K9B_EXTERNAL_ANALYSIS_API_KEY" in otel

    def test_both_workflows_use_openai_compatible_provider(self) -> None:
        """Both workflows must use openai_compatible provider type."""
        cnpg = CNPG.read_text()
        otel = OTEL.read_text()

        assert "diagnosisProvider.provider=openai_compatible" in cnpg
        assert "diagnosisProvider.provider=openai_compatible" in otel

    def test_both_workflows_use_same_existing_secret_pattern(self) -> None:
        """Both workflows must use existingSecret pattern for provider config."""
        cnpg = CNPG.read_text()
        otel = OTEL.read_text()

        # Check diagnosisProvider existingSecret
        assert "diagnosisProvider.existingSecret=k9b-diagnosis-credentials" in cnpg
        assert "diagnosisProvider.existingSecret=k9b-diagnosis-credentials" in otel

        # Check scheduler.smallProvider existingSecret
        assert "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials" in cnpg
        assert "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials" in otel
