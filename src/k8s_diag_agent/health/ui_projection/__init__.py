"""UI projection modules extracted from health/ui.py.

This package contains focused projection helpers organized by concern:
- review_enrichment: Review enrichment serialization and status building
- runs: Recent runs summary projection
- external_sources: Alertmanager/vmalert source serialization (future)

Extracted to keep health/ui.py under LLM-friendly size limits while
preserving the public compatibility surface.
"""

from __future__ import annotations

# Re-export from review_enrichment for backward compatibility
from .review_enrichment import (
    _adapter_registered,
    _build_review_enrichment_status,
    _find_review_enrichment_artifact,
    _serialize_review_enrichment,
    _serialize_review_enrichment_policy,
)

# Re-export from runs for backward compatibility
from .runs import (
    EXECUTION_INDEX_COLLECTOR_VERSION,
    _build_recent_runs_summary,
    _compute_batch_eligibility_indexed,
    _extract_run_ids_from_filename,
)

__all__ = [
    "_adapter_registered",
    "_build_review_enrichment_status",
    "_find_review_enrichment_artifact",
    "_serialize_review_enrichment",
    "_serialize_review_enrichment_policy",
    "_build_recent_runs_summary",
    "_compute_batch_eligibility_indexed",
    "_extract_run_ids_from_filename",
    "EXECUTION_INDEX_COLLECTOR_VERSION",
]
