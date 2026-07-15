"""Authoritative store-scan policy values.

ACT-K9B-HULK-CURRENT-RUN-PREAMOTION-SEAM01 domain model.

Store scanning is an explicit, named policy decision. It MUST NOT
arise from ``None``, from an empty tuple, from a failed promotion, or
from any generic exception path. The values in this enum are the only
states the orchestrator recognises when deciding whether to scan.
"""

from __future__ import annotations

from enum import StrEnum


class StoreScanPolicy(StrEnum):
    """Whether the diagnosis collector is permitted to store-scan.

    * :attr:`DISABLED` -- store scan is forbidden for this run.
      Defaults to forbidden after any rejected or commit-unknown
      promotion.
    * :attr:`EXPLICIT_NON_PROMOTION` -- the run legitimately had no
      promotion attempt (scheduled scan-only run). The collector may
      scan the global store.
    """

    DISABLED = "disabled"
    """Store scan is forbidden for this run."""

    EXPLICIT_NON_PROMOTION = "explicit_non_promotion"
    """A scheduled scan-only run that opted into store scanning."""


__all__ = ["StoreScanPolicy"]
