"""Collector-scoped review-packet creation budget.

Each new ``AutomaticDiagnosisCollectorRunId`` starts with a fresh
``ReviewPacketCreationBudget``. A unit of budget is consumed only when a
review packet is **persisted successfully** for the collector's run.

Budgets from previous collector runs (other run IDs, paused or
resumed executions) MUST NOT influence the new collector. The
authority is the in-memory state for synchronous collection; if a
collector is explicitly resumed, the previous collector's exact
``collector_run_id`` is used to reconstruct a single unit of
consumption by counting the matching successful artifacts on disk.
"""

from __future__ import annotations

import json as _json_for_match
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..domain.identifiers import AutomaticDiagnosisCollectorRunId
from .incident_diagnosis_review_packet import (
    REVIEW_PACKET_SUFFIX,
)

if TYPE_CHECKING:
    from .incident_diagnosis_auto_loop_config import (
        DiagnosisBudgetDiagnostic,
    )

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReviewPacketCreationBudget:
    """In-memory budget object keyed by collector run identity.

    The in-memory object is the authority during a synchronous
    collector execution. Callers MUST call :meth:`record_successful_write`
    exactly once per successfully-persisted review packet.
    """

    collector_run_id: AutomaticDiagnosisCollectorRunId
    limit: int
    used: int = 0

    def __post_init__(self) -> None:
        if self.limit < 0:
            raise ValueError("budget limit must be non-negative")
        if self.used < 0:
            raise ValueError("budget used must be non-negative")
        if self.used > self.limit:
            raise ValueError("budget used must not exceed limit")

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def can_attempt(self) -> bool:
        return self.used < self.limit

    def record_successful_write(self) -> None:
        """Record one successful review-packet write for this collector.

        Failed writes, ineligibility, reuse, and skips MUST NOT call
        this method. A successful write is the only consumption point.
        """
        if not self.can_attempt():
            raise RuntimeError(
                f"collector {self.collector_run_id!s} exhausted its "
                "review-packet creation budget"
            )
        self.used += 1

    def as_diagnostic(self) -> dict[str, object]:
        return {
            "name": "review_packet_creation_budget",
            "scope": "automatic_diagnosis_collector",
            "scope_id": str(self.collector_run_id),
            "used": self.used,
            "limit": self.limit,
            "remaining": self.remaining,
            "exhausted": self.exhausted,
            "source": "collector_run_accounting",
            "resettable": True,
        }

    def as_diagnostic_for_eligibility(self) -> DiagnosisBudgetDiagnostic:
        """Project the budget onto the eligibility ``DiagnosisBudgetDiagnostic``.

        The legacy review-packet-artifacts source label is replaced with
        the canonical ``collector_run_accounting`` so the eligibility
        path can prove the budget (not the filesystem count) is
        authoritative.
        """
        from .incident_diagnosis_auto_loop_config import (
            DiagnosisBudgetDiagnostic,
        )

        return DiagnosisBudgetDiagnostic(
            name="review_packet_budget",
            used=self.used,
            limit=self.limit,
            remaining=self.remaining,
            exhausted=self.exhausted,
            source="collector_run_accounting",
            resettable=True,
        )


_REVIEW_PACKET_NAME_RE = re.compile(
    r"^auto-(?P<incident_id>.+)-(?P<timestamp>\d{14})-[A-Za-z0-9]+-"
    + re.escape(REVIEW_PACKET_SUFFIX)
    + r"$"
)


def reconstruct_budget_from_existing_packets(
    *,
    collector_run_id: AutomaticDiagnosisCollectorRunId,
    limit: int,
    external_analysis_dir: Path,
) -> ReviewPacketCreationBudget:
    """Reconstruct budget usage for a resumed collector run.

    Only artifacts whose embedded ``collector_run_id`` matches the
    supplied identifier count toward consumption. The previous packet
    discovery heuristic (filename/health-run prefix) is intentionally
    NOT used; it cannot distinguish a current-collector packet from a
    historical packet of another collector.
    """
    budget = ReviewPacketCreationBudget(
        collector_run_id=collector_run_id,
        limit=limit,
    )
    consumed = _count_matching_packets(
        external_analysis_dir=external_analysis_dir,
        collector_run_id=collector_run_id,
    )
    if consumed <= 0:
        return budget
    # Clamp at the limit so a corrupt or overshot directory cannot
    # leave the budget permanently in a non-recoverable state.
    while not budget.exhausted and consumed > 0:
        budget.record_successful_write()
        consumed -= 1
    return budget


def _count_matching_packets(
    *,
    external_analysis_dir: Path,
    collector_run_id: AutomaticDiagnosisCollectorRunId,
) -> int:
    if not external_analysis_dir.exists():
        return 0
    count = 0
    try:
        paths = list(external_analysis_dir.rglob("*.json"))
    except OSError:
        return 0
    for path in paths:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        if not path.name.endswith(REVIEW_PACKET_SUFFIX):
            continue
        if not _packet_collector_run_id_matches(path, collector_run_id):
            continue
        count += 1
    return count


def _packet_collector_run_id_matches(
    path: Path,
    collector_run_id: AutomaticDiagnosisCollectorRunId,
) -> bool:
    """Return ``True`` iff the review packet's parsed ``collector_run_id`` equals the supplied value.

    The check is *structural* (parsed JSON ``dict.get("collector_run_id")``)
    rather than textual so:

    * compact JSON without spaces matches,
    * the same string cannot be confused for a different field,
    * escaped / differently formatted JSON matches on parsed value.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    try:
        payload = _json_for_match.loads(raw)
    except _json_for_match.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    return payload.get("collector_run_id") == str(collector_run_id)


def find_resumable_collector_run(
    *,
    external_analysis_dir: Path,
    expected_collector_run_id: AutomaticDiagnosisCollectorRunId,
) -> bool:
    """Return ``True`` when a matching collector packet exists on disk."""
    if not external_analysis_dir.exists():
        return False
    return _count_matching_packets(
        external_analysis_dir=external_analysis_dir,
        collector_run_id=expected_collector_run_id,
    ) > 0


__all__ = [
    "ReviewPacketCreationBudget",
    "find_resumable_collector_run",
    "reconstruct_budget_from_existing_packets",
]
