"""Foundational contract tests for ``current_run_promotion_workset``.

Stable-collapse behavior is kept in the sibling
``test_current_run_promotion_workset_collapse`` module. Shared constants and
builders live in the non-collectable ``current_run_promotion_workset_test_support``
module.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.current_run_promotion_workset import (
    PROMOTABLE_PROVENANCE,
    CurrentRunPromotionWorkset,
    CurrentRunSignalProvenance,
    CurrentRunSignalRef,
    build_current_run_workset,
)

from .current_run_promotion_workset_test_support import RUN_ID


class TestCurrentRunSignalRef:
    def test_carries_run_signal_provenance(self) -> None:
        ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id="sha256:abc",
            provenance=CurrentRunSignalProvenance.INSERTED,
        )
        assert ref.run_id == RUN_ID
        assert ref.signal_id == "sha256:abc"
        assert ref.provenance is CurrentRunSignalProvenance.INSERTED


class TestPromotableProvenance:
    def test_inserted_is_promotable(self) -> None:
        assert CurrentRunSignalProvenance.INSERTED in PROMOTABLE_PROVENANCE

    def test_identity_matched_is_promotable(self) -> None:
        assert (
            CurrentRunSignalProvenance.IDENTITY_MATCHED
            in PROMOTABLE_PROVENANCE
        )


class TestWorksetConstruction:
    def test_empty_workset_is_distinguishable_from_absent(self) -> None:
        workset = CurrentRunPromotionWorkset.empty(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
        )
        assert workset.is_empty
        assert workset.total_count == 0
        assert workset.signal_ids == ()

    def test_inserted_signals_enter_workset(self) -> None:
        ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id="sha256:abc",
            provenance=CurrentRunSignalProvenance.INSERTED,
        )
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=(ref,),
        )
        assert workset.total_count == 1
        assert workset.inserted_count == 1
        assert workset.identity_matched_count == 0
        assert workset.signal_ids == ("sha256:abc",)

    def test_identity_matched_signals_enter_workset(self) -> None:
        ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id="sha256:abc",
            provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
        )
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=(ref,),
        )
        assert workset.identity_matched_count == 1
        assert workset.inserted_count == 0

    def test_conflicts_do_not_enter_workset(self) -> None:
        with pytest.raises(ValueError):
            CurrentRunSignalProvenance("conflict")
        ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id="sha256:abc",
            # type: ignore[arg-type]
            provenance="conflict_not_a_real_provenance",
        )
        with pytest.raises(ValueError):
            build_current_run_workset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                references=(ref,),
            )

    def test_persistence_failures_do_not_enter_workset(self) -> None:
        ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id="sha256:abc",
            # type: ignore[arg-type]
            provenance="persistence_failure",
        )
        with pytest.raises(ValueError):
            build_current_run_workset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                references=(ref,),
            )

    def test_mixed_inserted_and_matching_collapse(self) -> None:
        refs = tuple(
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=f"sha256:signal-{index:03d}",
                provenance=(
                    CurrentRunSignalProvenance.INSERTED
                    if index % 2 == 0
                    else CurrentRunSignalProvenance.IDENTITY_MATCHED
                ),
            )
            for index in range(10)
        )
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=refs,
        )
        assert workset.total_count == 10
        assert workset.inserted_count == 5
        assert workset.identity_matched_count == 5


class TestWorksetInvariants:
    def test_run_id_mismatch_rejected(self) -> None:
        ref = CurrentRunSignalRef(
            run_id="other-run",
            signal_id="sha256:abc",
            provenance=CurrentRunSignalProvenance.INSERTED,
        )
        with pytest.raises(ValueError):
            CurrentRunPromotionWorkset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                signals=(ref,),
            )

    def test_ordering_is_stable(self) -> None:
        refs = tuple(
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=f"sha256:signal-{index:03d}",
                provenance=CurrentRunSignalProvenance.INSERTED,
            )
            for index in range(5)
        )
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=tuple(reversed(refs)),
        )
        ids = [ref.signal_id for ref in workset.signals]
        assert ids == sorted(ids)

    def test_serialization_is_deterministic(self) -> None:
        refs = tuple(
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=f"sha256:signal-{index:03d}",
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            )
            for index in range(3)
        )
        a = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=refs,
        )
        b = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=refs,
        )
        assert a.signal_ids == b.signal_ids
        assert a.total_count == b.total_count

    def test_empty_workset_remains_distinguishable_from_absent(self) -> None:
        empty = CurrentRunPromotionWorkset.empty(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
        )
        assert empty.total_count == 0
        assert empty.is_empty


class TestProductionRegression:
    """The 33-identity-duplicate production regression."""

    def test_33_identity_matched_signals_admitted(self) -> None:
        refs = tuple(
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=f"sha256:alert-{index:03d}",
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            )
            for index in range(33)
        )
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=refs,
        )
        assert workset.total_count == 33
        assert workset.identity_matched_count == 33
        assert workset.inserted_count == 0
        assert workset.signal_ids == tuple(
            f"sha256:alert-{index:03d}" for index in range(33)
        )
