"""P4c forensic dump: contract definitions.

This module provides constants and re-exports from the evidence module.
Kept minimal to support the LLM-friendly line-count gate.
"""

from __future__ import annotations

# Re-export environment/config from evidence module
from scripts.k9b_otel_demo_lab_p4c_forensic_dump_evidence import (  # noqa: F401
    FORENSIC_DUMP_DIR_ENV,
    FORENSIC_DUMP_ENABLED,
    _get_forensic_dump_dir,
    _mapping_summary,
)
