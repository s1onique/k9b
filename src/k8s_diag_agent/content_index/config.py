"""Content index read path configuration.

This module provides configuration loading for the disabled-by-default
content index read path for k9b UI APIs.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


# =============================================================================
# Feature Flag
# =============================================================================

CONTENT_INDEX_ENABLED_ENV_VAR = "K9B_CONTENT_INDEX_ENABLED"
CONTENT_INDEX_DB_PATH_ENV_VAR = "K9B_CONTENT_INDEX_DB_PATH"


# =============================================================================
# Configuration Dataclass
# =============================================================================


@dataclass(frozen=True)
class ContentIndexConfig:
    """Configuration for the content index read path.

    Attributes:
        enabled: Whether the content index read path is enabled.
            When False, only the direct read path is used.
        db_path: Path to the SQLite content index database.
            If None and enabled, uses the default location.
    """

    enabled: bool
    db_path: Path | None

    @classmethod
    def disabled(cls) -> ContentIndexConfig:
        """Create a disabled configuration."""
        return cls(enabled=False, db_path=None)


# =============================================================================
# Configuration Loading
# =============================================================================


def load_content_index_config_from_env(
    env: Mapping[str, str] | None = None,
) -> ContentIndexConfig:
    """Load content index configuration from environment variables.

    The content index read path is disabled by default for safety.
    It must be explicitly enabled via the K9B_CONTENT_INDEX_ENABLED environment
    variable.

    When enabled, the index database is opened read-only. The path defaults to
    "content-index.sqlite" in the k9b data directory if not specified.

    Args:
        env: Optional environment mapping. Defaults to os.environ.

    Returns:
        ContentIndexConfig with enabled/disabled state and db_path.
    """
    if env is None:
        import os as _os

        env = _os.environ

    # Check feature flag (default: disabled)
    enabled_str = env.get(CONTENT_INDEX_ENABLED_ENV_VAR, "false").lower()
    enabled = enabled_str in ("true", "1", "yes")

    # Get optional database path
    db_path_str = env.get(CONTENT_INDEX_DB_PATH_ENV_VAR)
    db_path: Path | None = None
    if db_path_str:
        db_path = Path(db_path_str)

    return ContentIndexConfig(enabled=enabled, db_path=db_path)


# =============================================================================
# Default DB Path
# =============================================================================


def get_default_content_index_db_path(data_dir: Path | None = None) -> Path:
    """Get the default content index database path.

    Args:
        data_dir: Optional data directory. If None, uses current directory.

    Returns:
        Path to the default content index database.
    """
    if data_dir is None:
        data_dir = Path.cwd()
    return data_dir / "content-index.sqlite"
