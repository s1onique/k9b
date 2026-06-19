"""Tests for authentication configuration module.

These tests verify that auth_config.py correctly loads and validates
authentication configuration from environment variables.
"""

from __future__ import annotations

# Import the module under test
from k8s_diag_agent.ui.auth_config import (
    AuthConfig,
    _parse_bool,
    _parse_int,
)


class TestParseBool:
    """Tests for _parse_bool function."""

    def test_parse_bool_true_values(self) -> None:
        """Test that various true-like values parse correctly."""
        for value in ("true", "True", "TRUE", "1", "yes", "Yes", "on", "ON"):
            assert _parse_bool(value, default=False) is True

    def test_parse_bool_false_values(self) -> None:
        """Test that various false-like values parse correctly."""
        for value in ("false", "False", "FALSE", "0", "no", "No", "off", "OFF"):
            assert _parse_bool(value, default=False) is False

    def test_parse_bool_none_returns_default(self) -> None:
        """Test that None returns the default value."""
        assert _parse_bool(None, default=False) is False
        assert _parse_bool(None, default=True) is True

    def test_parse_bool_unknown_returns_false(self) -> None:
        """Test that unknown values return False."""
        assert _parse_bool("unknown", default=False) is False
        assert _parse_bool("maybe", default=False) is False


class TestParseInt:
    """Tests for _parse_int function."""

    def test_parse_int_valid_values(self) -> None:
        """Test parsing of valid integer strings."""
        assert _parse_int("42", default=0) == 42
        assert _parse_int("0", default=1) == 0
        assert _parse_int("-10", default=0) == -10

    def test_parse_int_none_returns_default(self) -> None:
        """Test that None returns the default value."""
        assert _parse_int(None, default=100) == 100
        assert _parse_int(None, default=0) == 0

    def test_parse_int_invalid_returns_default(self) -> None:
        """Test that invalid strings return the default value."""
        assert _parse_int("abc", default=10) == 10
        assert _parse_int("12.34", default=0) == 0
        assert _parse_int("", default=5) == 5


class TestAuthConfigValidation:
    """Tests for AuthConfig.validate method."""

    def test_validate_enabled_requires_username(self) -> None:
        """Test that enabled config requires username."""
        config = AuthConfig(
            enabled=True,
            admin_username="",
            admin_password_hash="hash",
            session_cookie_name="session",
            session_max_age=3600,
            session_idle_timeout=1800,
            secure_cookie=False,
            is_development_mode=False,
        )
        issues = config.validate()
        assert any("username" in issue.lower() for issue in issues)

    def test_validate_enabled_requires_password_hash(self) -> None:
        """Test that enabled config requires password hash."""
        config = AuthConfig(
            enabled=True,
            admin_username="admin",
            admin_password_hash=None,
            session_cookie_name="session",
            session_max_age=3600,
            session_idle_timeout=1800,
            secure_cookie=False,
            is_development_mode=False,
        )
        issues = config.validate()
        assert any("password" in issue.lower() or "hash" in issue.lower() for issue in issues)

    def test_validate_disabled_warns_insecure(self) -> None:
        """Test that disabled auth warns about insecurity."""
        config = AuthConfig(
            enabled=False,
            admin_username="admin",
            admin_password_hash=None,
            session_cookie_name="session",
            session_max_age=3600,
            session_idle_timeout=1800,
            secure_cookie=False,
            is_development_mode=True,
        )
        issues = config.validate()
        assert any("insecure" in issue.lower() or "disabled" in issue.lower() for issue in issues)

    def test_validate_valid_config_no_issues(self) -> None:
        """Test that valid config has no issues."""
        config = AuthConfig(
            enabled=True,
            admin_username="admin",
            admin_password_hash="valid_hash",
            session_cookie_name="k9b_session",
            session_max_age=3600,
            session_idle_timeout=1800,
            secure_cookie=False,
            is_development_mode=False,
        )
        issues = config.validate()
        assert len(issues) == 0


class TestAuthConfigDefaults:
    """Tests for AuthConfig default values."""

    def test_default_session_cookie_name(self) -> None:
        """Test default session cookie name."""
        config = AuthConfig(
            enabled=True,
            admin_username="admin",
            admin_password_hash="hash",
            session_cookie_name="k9b_session",  # This should be the default
            session_max_age=8 * 60 * 60,  # 8 hours
            session_idle_timeout=30 * 60,  # 30 minutes
            secure_cookie=False,
            is_development_mode=False,
        )
        assert config.session_cookie_name == "k9b_session"

    def test_default_session_max_age(self) -> None:
        """Test default session max age is 8 hours."""
        config = AuthConfig(
            enabled=True,
            admin_username="admin",
            admin_password_hash="hash",
            session_cookie_name="session",
            session_max_age=8 * 60 * 60,
            session_idle_timeout=30 * 60,
            secure_cookie=False,
            is_development_mode=False,
        )
        assert config.session_max_age == 8 * 60 * 60

    def test_default_session_idle_timeout(self) -> None:
        """Test default session idle timeout is 30 minutes."""
        config = AuthConfig(
            enabled=True,
            admin_username="admin",
            admin_password_hash="hash",
            session_cookie_name="session",
            session_max_age=3600,
            session_idle_timeout=30 * 60,
            secure_cookie=False,
            is_development_mode=False,
        )
        assert config.session_idle_timeout == 30 * 60


class TestSecureCookieConfig:
    """Tests for secure cookie configuration via K9B_SECURE_COOKIE env var.

    Evidence for DOC-CLAIM-0024: Secure cookie flag is configurable via
    K9B_SECURE_COOKIE=true environment variable.
    """

    def test_secure_cookie_false_by_default(self) -> None:
        """Test that secure_cookie defaults to False when env var is not set."""
        import os

        from k8s_diag_agent.ui.auth_config import load_auth_config, reset_auth_config

        # Ensure env var is not set
        reset_auth_config()
        original = os.environ.pop("K9B_SECURE_COOKIE", None)
        try:
            config = load_auth_config()
            assert config.secure_cookie is False
        finally:
            reset_auth_config()
            if original is not None:
                os.environ["K9B_SECURE_COOKIE"] = original

    def test_secure_cookie_true_when_env_set(self) -> None:
        """Test that secure_cookie is True when K9B_SECURE_COOKIE=true."""
        import os

        from k8s_diag_agent.ui.auth_config import load_auth_config, reset_auth_config

        reset_auth_config()
        original = os.environ.get("K9B_SECURE_COOKIE")
        try:
            os.environ["K9B_SECURE_COOKIE"] = "true"
            config = load_auth_config()
            assert config.secure_cookie is True
        finally:
            reset_auth_config()
            if original is not None:
                os.environ["K9B_SECURE_COOKIE"] = original
            elif "K9B_SECURE_COOKIE" in os.environ:
                del os.environ["K9B_SECURE_COOKIE"]

    def test_secure_cookie_parses_various_true_values(self) -> None:
        """Test that various true-like values are accepted."""
        import os

        from k8s_diag_agent.ui.auth_config import load_auth_config, reset_auth_config

        for true_value in ("1", "yes", "on", "True", "TRUE"):
            reset_auth_config()
            os.environ["K9B_SECURE_COOKIE"] = true_value
            try:
                config = load_auth_config()
                assert config.secure_cookie is True, f"Failed for value: {true_value}"
            finally:
                reset_auth_config()
                if "K9B_SECURE_COOKIE" in os.environ:
                    del os.environ["K9B_SECURE_COOKIE"]

    def test_secure_cookie_false_for_invalid_values(self) -> None:
        """Test that invalid values result in secure_cookie=False."""
        import os

        from k8s_diag_agent.ui.auth_config import load_auth_config, reset_auth_config

        reset_auth_config()
        original = os.environ.get("K9B_SECURE_COOKIE")
        try:
            os.environ["K9B_SECURE_COOKIE"] = "invalid"
            config = load_auth_config()
            assert config.secure_cookie is False
        finally:
            reset_auth_config()
            if original is not None:
                os.environ["K9B_SECURE_COOKIE"] = original
            elif "K9B_SECURE_COOKIE" in os.environ:
                del os.environ["K9B_SECURE_COOKIE"]
