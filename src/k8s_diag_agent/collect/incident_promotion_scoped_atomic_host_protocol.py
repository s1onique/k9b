"""Typed host protocol for the scoped atomic recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
CORRECTION05-STRICT-TYPING-AND-ROLLBACK-CLOSURE01.
ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01.

The split atomic recorder (:mod:`incident_promotion_scoped_atomic_recorder`)
uses a :class:`Protocol` to type the host class without depending on
the concrete :class:`RunPromotionAccumulator` (which would close an
import cycle). The protocol declares every mutable field the
recorder inspects, plus the three private methods the recorder
calls:

* :meth:`_snapshot` -- capture the accumulator's canonical state
  into an immutable :class:`AccumulatorSnapshot` value.
* :meth:`_restore` -- put every field back to its captured state,
  preserving the identity of the existing mutable containers so
  external observers retain the same Python objects.
* :meth:`_apply_batch` -- the legacy batch applier used inside the
  atomic transaction.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
the protocol now also carries the single
:class:`ScopedPromotionRecordedAuthority` field. The recorder
stores ONE authority on the accumulator; ``scoped_promotion_handoff``
and ``scoped_promotion_batch`` are derived projections of that
authority. The general :attr:`batches` list is aggregate inventory
only -- the recorder NEVER indexes ``batches[-1]`` for the scoped
replay check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .incident_identity_hardening import PromotionRecord as _RecordType
    from .incident_promotion_batch import PromotionBatch
    from .incident_promotion_outcome_recorder import (
        PromotionOutcomeRecording,
    )
    from .incident_promotion_scoped_atomic_recording_authority import (
        ScopedPromotionRecordedAuthority,
    )
    from .promotion_outcomes import PromotionOutcome as _OutcomeType
    from .promotion_scoped_accumulator_handoff import (
        ScopedPromotionAccumulatorHandoff,
    )


@dataclass(frozen=True, slots=True)
class AccumulatorSnapshot:
    """Frozen, typed snapshot of every mutable accumulator field.

    Captured by :meth:`ScopedPromotionAccumulatorHost._snapshot` and
    consumed by :meth:`ScopedPromotionAccumulatorHost._restore`. The
    snapshot carries every authoritative field touched by the atomic
    recorder so a partial-batch rollback leaves no observable drift.

    ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
    the snapshot also carries the single
    :class:`ScopedPromotionRecordedAuthority` value so the
    recording authority is part of the atomic transaction.

    The mutable containers are stored as their frozen copies; the
    restore method writes them back IN PLACE so observers retain
    the original Python objects.
    """

    promotion_records: tuple[_RecordType, ...]
    seen_canonical_ids: frozenset[str]
    batches: tuple[PromotionBatch, ...]
    total_scanned: int
    total_firing: int
    total_opened_incidents: int
    total_updated_incidents: int
    total_skipped_duplicates: int
    total_errors: int
    total_unique_candidate_count: int
    last_promotion_mode: str
    last_incident_access_mode: str
    last_source_kind: str
    last_promotion_scan_scope: str
    promotion_outcome: _OutcomeType | None
    promotion_outcome_run_id: str
    scoped_promotion_handoff: ScopedPromotionAccumulatorHandoff | None
    scoped_promotion_recording: ScopedPromotionRecordedAuthority | None


@runtime_checkable
class ScopedPromotionAccumulatorHost(Protocol):
    """Structural type for the host class the atomic recorder mixes into.

    The protocol covers every field and method the recorder touches.
    ``runtime_checkable`` lets the architecture guard assert
    :class:`RunPromotionAccumulator` implements the protocol so a
    future drift between the dataclass fields and the recorder
    expectations fails the test suite.

    ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
    the host carries a single
    :class:`ScopedPromotionRecordedAuthority` field; the recorder
    derives ``scoped_promotion_handoff`` / ``scoped_promotion_batch``
    from it. The protocol uses the same private field names
    (``_seen_canonical_ids``) as the concrete accumulator so
    :func:`isinstance(acc, ScopedPromotionAccumulatorHost)` resolves
    against the real attribute.
    """

    promotion_outcome: _OutcomeType | None
    promotion_outcome_run_id: str
    # ``scoped_promotion_handoff`` is a derived property of the
    # scoped recording authority. Only the authority is part of
    # the structural Protocol here.
    scoped_promotion_recording: ScopedPromotionRecordedAuthority | None
    promotion_records: list[_RecordType]
    _seen_canonical_ids: set[str]
    batches: list[PromotionBatch]

    def _snapshot(self) -> AccumulatorSnapshot:
        """Return a frozen snapshot of every mutable accumulator field."""
        ...

    def _restore(self, snapshot: AccumulatorSnapshot) -> None:
        """Restore every mutable field from a previously taken snapshot.

        Implementations MUST restore the mutable containers in
        place so any external observer holding a reference to the
        original list/set sees the same Python object after the
        restore.
        """
        ...

    def _apply_batch(self, batch: PromotionBatch) -> None:
        """Apply a single batch (no rollback handling)."""
        ...

    def record_promotion_outcome(
        self,
        outcome: _OutcomeType,
    ) -> PromotionOutcomeRecording:
        """Record the typed outcome for the current run."""
        ...


__all__ = [
    "AccumulatorSnapshot",
    "ScopedPromotionAccumulatorHost",
]