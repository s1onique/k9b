"""Frozen ``ScopedPromotionRecordedAuthority`` value object.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01.

The split scoped atomic recorder stores a single
:class:`ScopedPromotionRecordedAuthority` value on
:class:`RunPromotionAccumulator`. The authority bundles the
typed :class:`ScopedPromotionAccumulatorHandoff` and the
canonical :class:`PromotionBatch` together so the recorder can
use the batch directly during replay (instead of indexing
into the general ``batches`` aggregate inventory).

Construction re-validates the same handoff/batch consistency
enforced by
:func:`incident_promotion_scoped_atomic_validation.validate_scoped_handoff_batch_consistency`
so a future caller cannot smuggle a mismatched pair through
the authority constructor. The :class:`Protocol` type for
the recorder host is updated so the recorder types the
authority directly instead of indexing ``batches[-1]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_promotion_batch import PromotionBatch
    from .promotion_scoped_accumulator_handoff import (
        ScopedPromotionAccumulatorHandoff,
    )


@dataclass(frozen=True, slots=True)
class ScopedPromotionRecordedAuthority:
    """Single canonical scoped recording authority.

    The accumulator MUST carry exactly one of these per active
    scoped run. The recorder compares a candidate against
    ``self.scoped_promotion_recording.batch`` (never against
    ``self.batches[-1]``) so a later, unrelated
    :meth:`RunPromotionAccumulator.add_batch` call cannot be
    mistaken for the scoped replay batch.

    Constructor validation runs the closed handoff/batch
    consistency checks BEFORE the field is assigned; a
    mismatched pair raises :class:`ValueError` from the same
    bounded validator path the recorder uses.
    """

    handoff: ScopedPromotionAccumulatorHandoff
    batch: PromotionBatch

    def __post_init__(self) -> None:
        # Lazy import: keeps this cycle-free contract module free
        # of a runtime dependency on the dispatcher.
        from .incident_promotion_scoped_atomic_validation import (
            validate_scoped_handoff_batch_consistency,
        )

        validate_scoped_handoff_batch_consistency(
            self.handoff, self.batch
        )


__all__ = [
    "ScopedPromotionRecordedAuthority",
]