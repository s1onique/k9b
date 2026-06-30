"""Parity tests ensuring CNPG and OTel live labs share the LLM secret contract.

These tests verify that both live lab workflows (CNPG and OTel) use the same
provider secret contract, preventing drift over time.

Contract tokens that MUST be present in BOTH live lab workflows:
- GitHub secrets: K9B_DIAGNOSIS_API_KEY, K9B_DIAGNOSIS_BASE_URL, K9B_DIAGNOSIS_MODEL
- Cluster secret: k9b-diagnosis-credentials
- Secret keys: K9B_DIAGNOSIS_API_KEY, K9B_EXTERNAL_ANALYSIS_API_KEY
- Provider: openai_compatible
- existingSecret pattern for both diagnosisProvider and scheduler.smallProvider

NOTE: OTel CI-only workflow (k9b-otel-demo-incident-lab.yml) is scaffold-only.
Live-lab contract assertions target k9b-otel-demo-live-lab.yml.
"""

from pathlib import Path

CNPG = Path(".github/workflows/k9b-cnpg-incident-lab-live.yml")
OTEL_CI = Path(".github/workflows/k9b-otel-demo-incident-lab.yml")
OTEL_LIVE = Path(".github/workflows/k9b-otel-demo-live-lab.yml")

# Note: Both CNPG and OTel live labs use the same GitHub secrets:
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

    def test_otel_live_workflow_exists(self) -> None:
        """OTel live lab workflow should exist."""
        assert OTEL_LIVE.exists(), f"OTel live lab workflow not found at {OTEL_LIVE}"

    def test_otel_ci_workflow_is_ci_only(self) -> None:
        """OTel CI-only workflow should exist but NOT contain live-lab markers."""
        assert OTEL_CI.exists(), f"OTel CI workflow not found at {OTEL_CI}"
        content = OTEL_CI.read_text()
        # CI-only workflow should have CI markers
        assert "K3s OTel Demo Incident Lab CI" in content
        assert "build-and-verify" in content
        # CI-only workflow should NOT have live-lab markers
        assert "live-k3s-lab" not in content
        assert "harbor-pve1.spbnix.local" not in content
        assert "diagnosisProvider.existingSecret=k9b-diagnosis-credentials" not in content

    def test_cnpg_and_otel_live_labs_share_llm_secret_contract(self) -> None:
        """Both live lab workflows must contain all required provider secret tokens."""
        cnpg = CNPG.read_text()
        otel_live = OTEL_LIVE.read_text()

        missing_in_cnpg = []
        missing_in_otel_live = []

        for token in REQUIRED_PROVIDER_TOKENS:
            if token not in cnpg:
                missing_in_cnpg.append(token)
            if token not in otel_live:
                missing_in_otel_live.append(token)

        errors = []
        if missing_in_cnpg:
            errors.append(f"CNPG workflow missing tokens: {missing_in_cnpg}")
        if missing_in_otel_live:
            errors.append(f"OTel live workflow missing tokens: {missing_in_otel_live}")

        assert not errors, "\n".join(errors)

    def test_both_live_labs_use_same_secret_name(self) -> None:
        """Both live lab workflows must use k9b-diagnosis-credentials as the secret name."""
        cnpg = CNPG.read_text()
        otel_live = OTEL_LIVE.read_text()

        # Extract secret name from both workflows
        assert "k9b-diagnosis-credentials" in cnpg
        assert "k9b-diagnosis-credentials" in otel_live

    def test_both_live_labs_use_same_api_key_keys(self) -> None:
        """Both live lab workflows must use the same secret key names."""
        cnpg = CNPG.read_text()
        otel_live = OTEL_LIVE.read_text()

        assert "K9B_DIAGNOSIS_API_KEY" in cnpg
        assert "K9B_DIAGNOSIS_API_KEY" in otel_live
        assert "K9B_EXTERNAL_ANALYSIS_API_KEY" in cnpg
        assert "K9B_EXTERNAL_ANALYSIS_API_KEY" in otel_live

    def test_both_live_labs_use_openai_compatible_provider(self) -> None:
        """Both live lab workflows must use openai_compatible provider type."""
        cnpg = CNPG.read_text()
        otel_live = OTEL_LIVE.read_text()

        assert "diagnosisProvider.provider=openai_compatible" in cnpg
        assert "diagnosisProvider.provider=openai_compatible" in otel_live

    def test_both_live_labs_use_same_existing_secret_pattern(self) -> None:
        """Both live lab workflows must use existingSecret pattern for provider config."""
        cnpg = CNPG.read_text()
        otel_live = OTEL_LIVE.read_text()

        # Check diagnosisProvider existingSecret
        assert "diagnosisProvider.existingSecret=k9b-diagnosis-credentials" in cnpg
        assert "diagnosisProvider.existingSecret=k9b-diagnosis-credentials" in otel_live

        # Check scheduler.smallProvider existingSecret
        assert "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials" in cnpg
        assert "scheduler.smallProvider.existingSecret=k9b-diagnosis-credentials" in otel_live


class TestOtelLiveLabContractMarkers:
    """Test that OTel live lab workflow contains expected live deployment markers."""

    def test_otel_live_lab_workflow_has_live_k3s_job(self) -> None:
        """OTel live lab should have live-k3s-lab job."""
        content = OTEL_LIVE.read_text()
        assert "live-k3s-lab:" in content
        assert "runs-on: spbnix-k8s" in content

    def test_otel_live_lab_workflow_has_harbor_registry(self) -> None:
        """OTel live lab should use Harbor registry."""
        content = OTEL_LIVE.read_text()
        assert "harbor-pve1.spbnix.local" in content

    def test_otel_live_lab_workflow_has_baseline_step(self) -> None:
        """OTel live lab should have Ensure k9b lab baseline step."""
        content = OTEL_LIVE.read_text()
        assert "Ensure k9b lab baseline" in content

    def test_otel_live_lab_workflow_has_diagnosis_provider_secret(self) -> None:
        """OTel live lab should wire diagnosisProvider.existingSecret."""
        content = OTEL_LIVE.read_text()
        assert "diagnosisProvider.existingSecret=k9b-diagnosis-credentials" in content

    def test_otel_live_lab_workflow_has_automatic_diagnosis_loop(self) -> None:
        """OTel live lab should enable automatic diagnosis loop."""
        content = OTEL_LIVE.read_text()
        assert "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true" in content
