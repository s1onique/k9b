"""LLM allowlist policy enforcement package.

This package provides verification that:
1. No new entries are added to the LLM-friendly allowlist
2. No baseline entries are added
3. Modified allowlisted files are removed from the active allowlist
4. Changes to allowlist files are not comment-only when there are effective changes
"""

from __future__ import annotations

from .baseline import normalize_path, parse_baseline_csv
from .changed_files import get_changed_files
from .comment_classifier import (
    check_allowlist_change_is_comment_only,
    is_llm_allowlist_file,
)
from .sources import get_current_allowlist_entries
from .verify import run_verification

__all__ = [
    "normalize_path",
    "parse_baseline_csv",
    "get_changed_files",
    "get_current_allowlist_entries",
    "run_verification",
    "is_llm_allowlist_file",
    "check_allowlist_change_is_comment_only",
]
