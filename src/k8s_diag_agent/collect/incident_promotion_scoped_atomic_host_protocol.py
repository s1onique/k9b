"""Typed host protocol for the scoped atomic recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
CORRECTION05-STRICT-TYPING-AND-ROLLBACK-CLOSURE01.

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

The :class:`AccumulatorSnapshot` value object is a frozen dataclass
that carries every authoritative mutable field of the accumulator.
``_restore`` reconstructs each container in place so ``is``
identity is preserved for ``batches``, ``promotion_records``, and
``_seen_canonical_ids``.

The host class also exposes the typed-outcome recorder
(:meth:`record_promotion_outcome`) as a Protocol method so the
recorder can call it through a typed boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .incident_identity_hardening import PromotionRecord
    from .incident_promotion_batch import PromotionBatch
    from .incident_promotion_outcome_recorder import (
        PromotionOutcomeRecording,
    )
    from .promotion_outcomes import PromotionOutcome
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

    The mutable containers are stored as their frozen copies; the
    restore method writes them back IN PLACE so observers retain
    the original Python objects.
    """

    promotion_records: tuple[PromotionRecord, ...]
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
    promotion_outcome: PromotionOutcome | None
    promotion_outcome_run_id: str
    scoped_promotion_handoff: ScopedPromotionAccumulatorHandoff | None


@runtime_checkable
class ScopedPromotionAccumulatorHost(Protocol):
    """Structural type for the host class the atomic recorder mixes into.

    The protocol covers every field and method the recorder touches.
    ``runtime_checkable`` lets the architecture guard
    :func:`test_run_promotion_accumulator_conforms_to_host_protocol`
    assert :class:`RunPromotionAccumulator` implements the protocol
    so a future drift between the dataclass fields and the
    recorder expectations fails the test suite.

    The protocol uses the same private field names
    (``_seen_canonical_ids``) as the concrete accumulator so
    :func:`isinstance(acc, ScopedPromotionAccumulatorHost)` resolves
    against the real attribute.
    """

    promotion_outcome: PromotionOutcome | None
    promotion_outcome_run_id: str
    scoped_promotion_handoff: ScopedPromotionAccumulatorHandoff | None
    promotion_records: list[PromotionRecord]
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
        outcome: PromotionOutcome,
    ) -> PromotionOutcomeRecording:
        """Record the typed outcome for the current run."""
        ...


__all__ = [
    "AccumulatorSnapshot",
    "ScopedPromotionAccumulatorHost",
]