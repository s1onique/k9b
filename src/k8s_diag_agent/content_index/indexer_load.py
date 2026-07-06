"""Content indexer file loading.

This module handles loading and parsing of source files.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_json_file(file_path: Path) -> dict[str, Any] | None:
    """Load and parse a JSON file.

    Args:
        file_path: Path to the JSON file.

    Returns:
        Parsed JSON data or None on error.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            result: dict[str, Any] = json.load(f)
            return result
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load JSON file {file_path}: {e}")
        return None
