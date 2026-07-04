"""P4c forensic dump evidence: contract definitions.

This module provides constants and helper functions for evidence dumps.
Kept minimal to support the LLM-friendly line-count gate.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# =============================================================================
# Environment and Configuration
# =============================================================================

FORENSIC_DUMP_ENABLED = os.environ.get("K9B_P4C_FORENSIC_DUMP", "0") == "1"
FORENSIC_DUMP_DIR_ENV = os.environ.get("K9B_FORENSIC_DUMP_DIR", "")


# =============================================================================
# Mapping Summary Helpers (shared between forensic dump modules)
# =============================================================================


def _mapping_fields_present(value: object) -> list[str]:
    """Return sorted list of field names for Mapping values, [] otherwise.

    Args:
        value: Any Python object

    Returns:
        Sorted list of string keys if value is a Mapping, empty list otherwise
    """
    if not isinstance(value, Mapping):
        return []
    return sorted(str(key) for key in value.keys())


def _mapping_summary(
    value: object,
    *,
    fields_key: str = "fields_present",
) -> dict[str, Any]:
    """Create a stable summary dict for any value, mapping or not.

    This ensures forensic artifacts have stable JSON schemas even when
    the source value is malformed/non-mapping.

    Args:
        value: Any Python object (dict, None, list, str, int, etc.)
        fields_key: Key name for the fields_present list (default "fields_present")

    Returns:
        Dict with is_mapping, value_type, and fields_present keys
    """
    return {
        "is_mapping": isinstance(value, Mapping),
        "value_type": type(value).__name__,
        fields_key: _mapping_fields_present(value),
    }


def _get_forensic_dump_dir(artifact_dir: Path) -> Path:
    """Get the forensic dump directory path.

    Args:
        artifact_dir: Root artifact directory

    Returns:
        Path to forensic dump directory
    """
    if FORENSIC_DUMP_DIR_ENV:
        dump_dir = Path(FORENSIC_DUMP_DIR_ENV)
    else:
        dump_dir = artifact_dir / "phase4-diagnosis" / "p4c-debug"
    dump_dir.mkdir(parents=True, exist_ok=True)
    return dump_dir
