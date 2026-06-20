"""Documentation claim candidate backlog reporter package."""

from __future__ import annotations

from .loader import read_candidates, read_dispositions, read_inventory
from .model import (
    ALL_REVIEW_CLASSES,
    REVIEW_CLASS_CLAIM_CANDIDATE,
    REVIEW_CLASS_COVERED_OR_REGISTERED,
    REVIEW_CLASS_NON_NORMATIVE_PROSE,
    REVIEW_CLASS_REVIEWED_LOW_VALUE,
    REVIEW_CLASS_STALE_OR_HISTORICAL,
    REVIEW_CLASS_STRUCTURAL_FRAGMENT,
    REVIEW_CLASS_UNKNOWN,
    BacklogEntry,
    CandidateData,
    classify_review_class,
    compute_calibrated_score,
    compute_risk_score,
    has_act_5_0_marker,
    has_act_5_2_marker,
    has_any_act_marker,
    is_cleanup_class,
    is_generic_low_value_note,
    is_high_value_doc,
    is_historical_disposition,
    is_historical_doc,
    is_stale_disposition,
    is_stale_doc,
)
from .planning import (
    CAVEAT_CLAIM_CANDIDATE_HEAVY,
    CAVEAT_CLEANUP_HEAVY,
    CAVEAT_LOW_BACKLOG,
    CAVEAT_MIXED,
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
    "compute_calibrated_score",
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
    # Review class constants
    "ALL_REVIEW_CLASSES",
    "REVIEW_CLASS_CLAIM_CANDIDATE",
    "REVIEW_CLASS_COVERED_OR_REGISTERED",
    "REVIEW_CLASS_NON_NORMATIVE_PROSE",
    "REVIEW_CLASS_REVIEWED_LOW_VALUE",
    "REVIEW_CLASS_STRUCTURAL_FRAGMENT",
    "REVIEW_CLASS_STALE_OR_HISTORICAL",
    "REVIEW_CLASS_UNKNOWN",
    # Classification functions
    "classify_review_class",
    "is_cleanup_class",
    # Caveat constants
    "CAVEAT_CLEANUP_HEAVY",
    "CAVEAT_CLAIM_CANDIDATE_HEAVY",
    "CAVEAT_LOW_BACKLOG",
    "CAVEAT_MIXED",
]
