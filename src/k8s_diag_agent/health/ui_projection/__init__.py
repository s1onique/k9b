"""UI projection modules extracted from health/ui.py.

This package contains focused projection helpers organized by concern:
- review_enrichment: Review enrichment serialization and status building
- runs: Recent runs summary projection
- auto_drilldown: Auto-drilldown policy and interpretation serialization
- notification_index: Notification/promotion index projections

Extracted to keep health/ui.py under LLM-friendly size limits while
preserving the public compatibility surface.
"""

from __future__ import annotations

# Re-export from auto_drilldown for backward compatibility
from .auto_drilldown import (
    _serialize_auto_drilldown_interpretations,
    _serialize_auto_drilldown_policy,
)

# Re-export from notification_index for backward compatibility
from .notification_index import (
    NotificationRecord,
    _build_notification_index,
    _build_promotions_index,
    _write_proposal_status_summary_to_review,
)

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
    "_build_notification_index",
    "_build_promotions_index",
    "_build_review_enrichment_status",
    "_build_recent_runs_summary",
    "_compute_batch_eligibility_indexed",
    "_extract_run_ids_from_filename",
    "_find_review_enrichment_artifact",
    "_serialize_auto_drilldown_interpretations",
    "_serialize_auto_drilldown_policy",
    "_serialize_review_enrichment",
    "_serialize_review_enrichment_policy",
    "_write_proposal_status_summary_to_review",
    "EXECUTION_INDEX_COLLECTOR_VERSION",
    "NotificationRecord",
]
