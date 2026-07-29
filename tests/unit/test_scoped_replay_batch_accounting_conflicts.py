"""Replay-conflict field tests -- accounting field mismatches.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.
ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION05-
STRICT-TYPING-AND-ROLLBACK-CLOSURE01.

Split out of the original
:mod:`test_scoped_accumulator_replay_conflicts` matrix (CORRECTION05
file-size guard). The exhaustive equivalence predicates
(:func:`_receipt_equivalent`, :func:`_batch_accounting_equivalent`)
are built on dataclass equality. Each test in this matrix mutates
ONE authoritative accounting field on the candidate batch and
confirms the atomic recorder raises the bounded exception.

This module covers fields the validator checks exhaustively and
rejects with :class:`ValueError` BEFORE the equivalence check
runs.

* **Replay conflict** (covered by the handoff / batch identity
  split files) -- a replay that changes a field the validator
  does NOT check directly.
* **Validation rejection** -- a replay that breaks a field the
  validator DOES check exhaustively (source_kind,
  promotion_scan_scope, promotion_mode, opened/updated counts,
  error_messages, unique_candidate_count, scanned, firing,
  etc.).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_projection import (
    build_compatibility_batch_from_handoff,
)
from tests.unit.scoped_handoff_atomic_support import (
    completed_handoff,
    make_completed_batch,
)


def _seed_completed(acc: RunPromotionAccumulator) -> None:
    """Seed the accumulator with a completed handoff/batch."""
    from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
        PromotionOutcomeRecording,
    )

    handoff = completed_handoff(
        diagnosis_incident_ids=("canonical-conflict",),
    )
    batch = make_completed_batch(handoff=handoff)
    recording = acc.record_scoped_promotion_batch(
        handoff=handoff, batch=batch
    )
    assert recording is PromotionOutcomeRecording.NEW


class TestBatchAccountingConflict:
    """Replay mutations the validator rejects with ``ValueError``.

    The validator's bounded cross-variant envelope rejects every
    per-batch aggregate drift BEFORE the equivalence check runs.
    Each test pins one bounded field and the bounded error
    message so the focused matrix stays complete even when the
    equivalence predicates evolve.
    """

    def test_invalid_source_kind_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_batch = replace(new_batch, source_kind="not_alertmanager")
        with pytest.raises(ValueError, match="source_kind"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_promotion_scan_scope_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            promotion_scan_scope="mutated_scan_scope",
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="promotion_scan_scope"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_promotion_mode_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            promotion_mode="local",
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="promotion_mode"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_incident_access_mode_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            incident_access_mode="local",
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="incident_access_mode"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_opened_incident_ids_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            opened_incident_ids=("canonical-replay-mutated",),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="opened_incident_ids"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_updated_incident_ids_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            updated_incident_ids=("canonical-replay-mutated",),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="updated_incident_ids"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_observation_refreshed_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            observation_refreshed_incident_ids=(
                "canonical-replay-mutated",
            ),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(
            ValueError, match="observation_refreshed_incident_ids"
        ):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_unchanged_incident_ids_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            unchanged_incident_ids=("canonical-replay-mutated",),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="unchanged_incident_ids"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_error_messages_rejected_by_validator(self) -> None:
        """Completed batches MUST carry empty error_messages."""
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            error_messages=("replay-mutated-error",),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="error_messages"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_unique_candidate_count_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            unique_candidate_count=(
                new_batch.promotion_result.unique_candidate_count + 1
            ),
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="unique_candidate_count"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_scanned_count_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            scanned=new_batch.promotion_result.scanned + 1,
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="scanned"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_firing_count_rejected_by_validator(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        new_pr = replace(
            new_batch.promotion_result,
            firing=new_batch.promotion_result.firing + 1,
        )
        new_batch = replace(new_batch, promotion_result=new_pr)
        with pytest.raises(ValueError, match="firing"):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_invalid_promotion_records_rejected_by_validator(self) -> None:
        """The completed validator MUST reject non-empty records."""
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )
        from k8s_diag_agent.collect.incident_promotion_batch import (
            PromotionBatch,
        )

        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        handoff = completed_handoff(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        bad_batch = PromotionBatch(
            promotion_result=build_compatibility_batch_from_handoff(
                handoff
            ).promotion_result,
            promotion_records=(
                PromotionRecord(
                    source_candidate_id="<smuggled>",
                    canonical_incident_id="c-smuggled",
                    promotion_outcome="opened",
                ),
            ),
            source_kind="alertmanager",
        )
        with pytest.raises(ValueError, match="promotion_records"):
            acc.record_scoped_promotion_batch(
                handoff=handoff, batch=bad_batch
            )

    def test_replay_with_uncertain_handoff_rejected(self) -> None:
        """Switching the closed-union variant raises the bounded conflict."""
        from tests.unit.scoped_handoff_atomic_support import (
            uncertain_handoff,
        )

        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = uncertain_handoff(
            requested_signal_ids=tuple(
                f"sig-{i:02d}" for i in range(5)
            ),
        )
        new_batch = build_compatibility_batch_from_handoff(new_handoff)
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )