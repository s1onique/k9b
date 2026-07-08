"""Tests for incident promotion dispatch configuration.

These tests verify the IncidentPromotionDispatchConfig class behavior.
"""

from __future__ import annotations

import os
from pathlib import Path

from k8s_diag_agent.collect.incident_promotion_dispatch import (
    MODE_AUTO,
    MODE_BACKEND_API,
    MODE_LOCAL,
    IncidentPromotionDispatchConfig,
)


class TestIncidentPromotionDispatchConfig:
    """Tests for IncidentPromotionDispatchConfig."""

    def test_auto_resolves_to_backend_api_when_sqlite_backend(self) -> None:
        """Auto mode should resolve to backend-api when store_backend=sqlite."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_AUTO,
            backend_url="http://localhost:8080",
            internal_api_token="secret",
            store_backend="sqlite",
            process_role="scheduler",
        )
        assert config.resolved_mode() == MODE_BACKEND_API

    def test_auto_resolves_to_backend_api_when_scheduler_role(self) -> None:
        """Auto mode should resolve to backend-api when process_role=scheduler."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_AUTO,
            backend_url="http://localhost:8080",
            internal_api_token="secret",
            store_backend="memory",
            process_role="scheduler",
        )
        assert config.resolved_mode() == MODE_BACKEND_API

    def test_auto_resolves_to_local_when_memory_and_not_scheduler(self) -> None:
        """Auto mode should resolve to local when memory backend and non-scheduler."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_AUTO,
            backend_url=None,
            internal_api_token=None,
            store_backend="memory",
            process_role="backend",
        )
        assert config.resolved_mode() == MODE_LOCAL

    def test_local_mode_stays_local(self) -> None:
        """Local mode should stay local regardless of backend."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_LOCAL,
            backend_url=None,
            internal_api_token=None,
            store_backend="sqlite",
            process_role="scheduler",
        )
        assert config.resolved_mode() == MODE_LOCAL

    def test_backend_api_mode_stays_backend_api(self) -> None:
        """Backend-api mode should stay backend-api regardless of backend."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_BACKEND_API,
            backend_url="http://localhost:8080",
            internal_api_token="secret",
            store_backend="memory",
            process_role="backend",
        )
        assert config.resolved_mode() == MODE_BACKEND_API

    def test_local_allowed_for_memory_backend(self) -> None:
        """Local promotion should be allowed for memory backend."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_LOCAL,
            backend_url=None,
            internal_api_token=None,
            store_backend="memory",
            process_role="backend",
        )
        assert config.can_use_local() is True

    def test_local_allowed_for_file_backend(self) -> None:
        """Local promotion should be allowed for file backend."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_LOCAL,
            backend_url=None,
            internal_api_token=None,
            store_backend="file",
            process_role="backend",
        )
        assert config.can_use_local() is True

    def test_local_forbidden_for_scheduler_and_sqlite(self) -> None:
        """Local promotion should be forbidden for scheduler+sqlite."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_LOCAL,
            backend_url=None,
            internal_api_token=None,
            store_backend="sqlite",
            process_role="scheduler",
        )
        assert config.can_use_local() is False

    def test_local_allowed_for_scheduler_with_memory(self) -> None:
        """Local promotion should be allowed for scheduler with memory backend."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_LOCAL,
            backend_url=None,
            internal_api_token=None,
            store_backend="memory",
            process_role="scheduler",
        )
        assert config.can_use_local() is True

    def test_backend_api_requires_backend_url(self) -> None:
        """Backend-api mode should require backend_url."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_BACKEND_API,
            backend_url=None,
            internal_api_token="secret",
            store_backend="sqlite",
            process_role="scheduler",
        )
        is_valid, error = config.is_config_valid()
        assert is_valid is False
        assert error == "missing_backend_url"

    def test_backend_api_requires_token(self) -> None:
        """Backend-api mode should require internal_api_token."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_BACKEND_API,
            backend_url="http://localhost:8080",
            internal_api_token=None,
            store_backend="sqlite",
            process_role="scheduler",
        )
        is_valid, error = config.is_config_valid()
        assert is_valid is False
        assert error == "missing_internal_api_token"

    def test_backend_api_valid_with_url_and_token(self) -> None:
        """Backend-api mode should be valid with both URL and token."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_BACKEND_API,
            backend_url="http://localhost:8080",
            internal_api_token="secret",
            store_backend="sqlite",
            process_role="scheduler",
        )
        is_valid, error = config.is_config_valid()
        assert is_valid is True
        assert error is None

    def test_local_mode_always_valid(self) -> None:
        """Local mode should always be valid (URL/token not required)."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_LOCAL,
            backend_url=None,
            internal_api_token=None,
            store_backend="memory",
            process_role="backend",
        )
        is_valid, error = config.is_config_valid()
        assert is_valid is True
        assert error is None

    def test_auto_mode_resolves_correctly_for_sqlite(self) -> None:
        """Auto mode should resolve to backend-api for sqlite."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_AUTO,
            backend_url="http://localhost:8080",
            internal_api_token="secret",
            store_backend="sqlite",
            process_role="backend",
        )
        assert config.resolved_mode() == MODE_BACKEND_API
        assert config.requires_backend_api() is True

    def test_auto_mode_resolves_correctly_for_memory(self) -> None:
        """Auto mode should resolve to local for memory."""
        config = IncidentPromotionDispatchConfig(
            mode=MODE_AUTO,
            backend_url="http://localhost:8080",
            internal_api_token="secret",
            store_backend="memory",
            process_role="backend",
        )
        assert config.resolved_mode() == MODE_LOCAL
        assert config.requires_backend_api() is False


class TestDispatchConfigFromEnv:
    """Tests for dispatch config from environment variables."""

    def teardown_method(self) -> None:
        """Clean up environment variables after each test."""
        for var in [
            "K9B_INCIDENT_PROMOTION_MODE",
            "K9B_BACKEND_INTERNAL_URL",
            "K9B_INTERNAL_API_TOKEN",
            "K9B_INCIDENT_STORE_BACKEND",
            "K9B_PROCESS_ROLE",
        ]:
            os.environ.pop(var, None)

    def test_default_mode_is_auto(self) -> None:
        """Default promotion mode should be auto."""
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            _get_dispatch_config,
        )

        config = _get_dispatch_config()
        assert config.mode == MODE_AUTO

    def test_explicit_local_mode(self) -> None:
        """Explicit local mode should be respected."""
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "local"
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            _get_dispatch_config,
        )

        config = _get_dispatch_config()
        assert config.mode == MODE_LOCAL

    def test_explicit_backend_api_mode(self) -> None:
        """Explicit backend-api mode should be respected."""
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "backend-api"
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            _get_dispatch_config,
        )

        config = _get_dispatch_config()
        assert config.mode == MODE_BACKEND_API

    def test_env_backend_url(self) -> None:
        """Backend URL should be read from environment."""
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "http://k9b-backend:8080"
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            _get_dispatch_config,
        )

        config = _get_dispatch_config()
        assert config.backend_url == "http://k9b-backend:8080"

    def test_env_internal_api_token(self) -> None:
        """Internal API token should be read from environment."""
        os.environ["K9B_INTERNAL_API_TOKEN"] = "my-secret-token"
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            _get_dispatch_config,
        )

        config = _get_dispatch_config()
        assert config.internal_api_token == "my-secret-token"

    def test_env_store_backend(self) -> None:
        """Store backend should be read from environment."""
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            _get_dispatch_config,
        )

        config = _get_dispatch_config()
        assert config.store_backend == "sqlite"

    def test_env_process_role(self) -> None:
        """Process role should be read from environment."""
        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            _get_dispatch_config,
        )

        config = _get_dispatch_config()
        assert config.process_role == "scheduler"


class TestAlertClassifierImportRegression:
    """Regression tests for alert classifier module imports.

    These tests verify that the dispatcher correctly imports the canonical alert classifier
    module (incident_alert_classifier.py) and not a nonexistent module.
    """

    def test_canonical_alert_classifier_importable(self) -> None:
        """Regression: dispatcher must import the canonical alert classifier module.

        The canonical module is incident_alert_classifier.py (not incident_alert_classification.py).
        """
        from k8s_diag_agent.incident_alert_classifier import classify_alert_signal

        assert callable(classify_alert_signal)

    def test_scan_alert_signals_as_candidates_imports_existing_classifier(
        self, tmp_path: Path
    ) -> None:
        """Regression: execute lazy import inside scan_alert_signals_as_candidates().

        This test exercises the lazy import of classify_alert_signal inside
        scan_alert_signals_as_candidates() to verify that the correct module is found.
        """
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            scan_alert_signals_as_candidates,
        )

        # Should return empty list with no artifacts (empty runs_dir)
        # This implicitly exercises the lazy import of classify_alert_signal
        result = scan_alert_signals_as_candidates(tmp_path)
        assert result == []
