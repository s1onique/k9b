"""Documentation claim candidate backlog reporter package."""

from __future__ import annotations

from .loader import read_candidates, read_dispositions, read_inventory
from .model import (
    BacklogEntry,
    CandidateData,
    compute_risk_score,
    has_act_5_0_marker,
    has_act_5_2_marker,
    has_any_act_marker,
    is_generic_low_value_note,
    is_high_value_doc,
    is_historical_disposition,
    is_historical_doc,
    is_stale_disposition,
    is_stale_doc,
)
from .planning import (
    compute_planning_summary,
    get_priority_band,
    print_planning_summary,
)
from .report import (
    build_backlog,
    compute_summary,
    print_recommended,
    print_summary,
    write_json,
    write_tsv,
)
from .selftest import run_self_test

__all__ = [
    "BacklogEntry",
    "CandidateData",
    "build_backlog",
    "compute_planning_summary",
    "compute_risk_score",
    "compute_summary",
    "get_priority_band",
    "has_act_5_0_marker",
    "has_act_5_2_marker",
    "has_any_act_marker",
    "is_generic_low_value_note",
    "is_high_value_doc",
    "is_historical_disposition",
    "is_historical_doc",
    "is_stale_disposition",
    "is_stale_doc",
    "print_planning_summary",
    "print_recommended",
    "print_summary",
    "read_candidates",
    "read_dispositions",
    "read_inventory",
    "run_self_test",
    "write_json",
    "write_tsv",
]
