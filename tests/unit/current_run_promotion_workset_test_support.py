"""Shared builders for current-run promotion workset tests.

This module is intentionally non-collectable: it defines no pytest test
functions and no ``Test*`` classes.
"""

from __future__ import annotations

from collections.abc import Iterable

from k8s_diag_agent.collect.current_run_promotion_workset import (
    CurrentRunPromotionWorkset,
    CurrentRunSignalRef,
    build_current_run_workset,
)

RUN_ID = "run-2026-07-15T03:30Z"
OTHER_RUN_ID = "run-2026-07-15T03:31Z"
SIGNAL_X = "sha256:signal-X"
SIGNAL_Y = "sha256:signal-Y"
SIGNAL_Z = "sha256:signal-Z"


def build_test_workset(
    references: Iterable[CurrentRunSignalRef],
) -> CurrentRunPromotionWorkset:
    """Build a workset using the shared deterministic test identity."""
    return build_current_run_workset(
        run_id=RUN_ID,
        source_identity="alertmanager-prod",
        references=tuple(references),
    )
