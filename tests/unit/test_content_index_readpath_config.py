"""Tests for content index read path configuration.

Tests feature flag defaults and configuration loading.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k8s_diag_agent.content_index import (
    ContentIndexConfig,
    load_content_index_config_from_env,
)
from k8s_diag_agent.content_index.config import (
    CONTENT_INDEX_DB_PATH_ENV_VAR,
    CONTENT_INDEX_ENABLED_ENV_VAR,
    get_default_content_index_db_path,
)


class TestFeatureFlagDefaults:
    """Test that feature flag defaults to disabled."""

    def test_default_disabled_no_env(self) -> None:
        """Test that default config is disabled when no env var is set."""
        config = load_content_index_config_from_env({})
        assert config.enabled is False
        assert config.db_path is None

    def test_default_disabled_empty_string(self) -> None:
        """Test that empty string is treated as disabled."""
        config = load_content_index_config_from_env({
            CONTENT_INDEX_ENABLED_ENV_VAR: "",
        })
        assert config.enabled is False

    def test_explicit_false(self) -> None:
        """Test explicit false values."""
        for value in ["false", "False", "FALSE", "0", "no", "No", "NO"]:
            config = load_content_index_config_from_env({
                CONTENT_INDEX_ENABLED_ENV_VAR: value,
            })
            assert config.enabled is False, f"Expected False for {value!r}"

    def test_explicit_true(self) -> None:
        """Test explicit true values."""
        for value in ["true", "True", "TRUE", "1", "yes", "Yes", "YES"]:
            config = load_content_index_config_from_env({
                CONTENT_INDEX_ENABLED_ENV_VAR: value,
            })
            assert config.enabled is True, f"Expected True for {value!r}"

    def test_db_path_from_env(self) -> None:
        """Test that db path can be loaded from env."""
        config = load_content_index_config_from_env({
            CONTENT_INDEX_ENABLED_ENV_VAR: "true",
            CONTENT_INDEX_DB_PATH_ENV_VAR: "/custom/path/index.sqlite",
        })
        assert config.enabled is True
        assert config.db_path is not None
        assert str(config.db_path) == "/custom/path/index.sqlite"


class TestDefaultDBPath:
    """Test default database path computation."""

    def test_default_path_in_cwd(self) -> None:
        """Test that default path uses current directory."""
        path = get_default_content_index_db_path()
        assert path.name == "content-index.sqlite"

    def test_default_path_in_custom_dir(self) -> None:
        """Test that default path uses custom directory."""
        path = get_default_content_index_db_path(Path("/custom/data"))
        assert path == Path("/custom/data/content-index.sqlite")

    def test_config_disabled_class_method(self) -> None:
        """Test ContentIndexConfig.disabled() factory."""
        config = ContentIndexConfig.disabled()
        assert config.enabled is False
        assert config.db_path is None


class TestContentIndexConfig:
    """Test ContentIndexConfig dataclass."""

    def test_config_creation(self) -> None:
        """Test creating a config with explicit values."""
        config = ContentIndexConfig(
            enabled=True,
            db_path=Path("/test/path.sqlite"),
        )
        assert config.enabled is True
        assert config.db_path == Path("/test/path.sqlite")

    def test_config_immutable(self) -> None:
        """Test that config is frozen (immutable)."""
        config = ContentIndexConfig(enabled=True, db_path=None)
        with pytest.raises(AttributeError):
            config.enabled = False  # type: ignore[attr-defined]
