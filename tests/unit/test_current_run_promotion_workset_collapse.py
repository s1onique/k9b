"""Stable-collapse behavior tests for the current-run workset factory."""

from __future__ import annotations

from itertools import permutations

import pytest

from k8s_diag_agent.collect.current_run_promotion_workset import (
    CurrentRunPromotionWorkset,
    CurrentRunSignalProvenance,
    CurrentRunSignalRef,
)

from .current_run_promotion_workset_test_support import (
    OTHER_RUN_ID,
    RUN_ID,
    SIGNAL_X,
    SIGNAL_Y,
    SIGNAL_Z,
    build_test_workset,
)


class TestStableCollapseSemantics:
    """Repeated same-run references collapse deterministically.

    Provenance precedence is ``INSERTED > IDENTITY_MATCHED``. Validation
    occurs before collapse so invalid references cannot be concealed.
    """

    def test_inserted_and_matched_same_id_collapse_to_inserted(self) -> None:
        refs = (
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            ),
        )
        workset = build_test_workset(refs)
        assert workset.total_count == 1
        assert workset.inserted_count == 1
        assert workset.identity_matched_count == 0
        assert workset.signal_ids == (SIGNAL_X,)
        assert workset.signals[0].provenance == CurrentRunSignalProvenance.INSERTED

    def test_inserted_then_matched_equals_matched_then_inserted(self) -> None:
        forward = (
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            ),
        )
        reverse = (
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
        )
        forward_workset = build_test_workset(forward)
        reverse_workset = build_test_workset(reverse)
        assert forward_workset == reverse_workset
        assert forward_workset.signal_ids == reverse_workset.signal_ids
        assert forward_workset.inserted_count == reverse_workset.inserted_count
        assert (
            forward_workset.identity_matched_count
            == reverse_workset.identity_matched_count
        )
        assert forward_workset.total_count == reverse_workset.total_count

    def test_three_matched_references_collapse_to_one(self) -> None:
        refs = tuple(
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            )
            for _ in range(3)
        )
        workset = build_test_workset(refs)
        assert workset.total_count == 1
        assert workset.identity_matched_count == 1
        assert workset.inserted_count == 0
        assert len(refs) - workset.total_count == 2

    def test_two_inserted_references_collapse_to_one(self) -> None:
        refs = (
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
        )
        workset = build_test_workset(refs)
        assert workset.total_count == 1
        assert workset.inserted_count == 1
        assert workset.identity_matched_count == 0
        assert workset.signal_ids == (SIGNAL_X,)

    def test_different_signal_ids_do_not_collapse(self) -> None:
        refs = (
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_Y,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            ),
        )
        workset = build_test_workset(refs)
        assert workset.total_count == 2
        assert workset.inserted_count == 1
        assert workset.identity_matched_count == 1
        assert workset.signal_ids == (SIGNAL_X, SIGNAL_Y)

    def test_direct_aggregate_with_duplicates_remains_rejected(self) -> None:
        ref_x = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=SIGNAL_X,
            provenance=CurrentRunSignalProvenance.INSERTED,
        )
        duplicate_ref_x = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=SIGNAL_X,
            provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
        )
        with pytest.raises(ValueError):
            CurrentRunPromotionWorkset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                signals=(ref_x, duplicate_ref_x),
            )

    def test_run_id_mismatch_in_factory_is_rejected(self) -> None:
        refs = (
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
            CurrentRunSignalRef(
                run_id=OTHER_RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            ),
        )
        with pytest.raises(ValueError):
            build_test_workset(refs)

    def test_unsupported_provenance_cannot_be_concealed_by_duplicate(
        self,
    ) -> None:
        invalid_ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=SIGNAL_X,
            provenance="persistence_failure",
        )
        valid_ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=SIGNAL_X,
            provenance=CurrentRunSignalProvenance.INSERTED,
        )
        with pytest.raises(ValueError):
            build_test_workset((invalid_ref, valid_ref))

    def test_empty_signal_id_cannot_be_concealed_by_duplicate(self) -> None:
        invalid_ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id="",
            provenance=CurrentRunSignalProvenance.INSERTED,
        )
        valid_ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=SIGNAL_X,
            provenance=CurrentRunSignalProvenance.INSERTED,
        )
        with pytest.raises(ValueError):
            build_test_workset((invalid_ref, valid_ref))

    @pytest.mark.parametrize(
        "raw_provenance",
        ["inserted", "identity_matched"],
    )
    def test_raw_string_provenance_rejected_by_factory(
        self,
        raw_provenance: str,
    ) -> None:
        invalid_ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=SIGNAL_X,
            provenance=raw_provenance,  # type: ignore[arg-type]
        )
        with pytest.raises(ValueError):
            build_test_workset((invalid_ref,))

    @pytest.mark.parametrize(
        "raw_provenance",
        ["inserted", "identity_matched"],
    )
    def test_raw_string_provenance_rejected_by_direct_aggregate(
        self,
        raw_provenance: str,
    ) -> None:
        invalid_ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=SIGNAL_X,
            provenance=raw_provenance,  # type: ignore[arg-type]
        )
        with pytest.raises(ValueError):
            CurrentRunPromotionWorkset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                signals=(invalid_ref,),
            )

    def test_empty_signal_id_rejected_by_strict_aggregate(self) -> None:
        invalid_ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id="",
            provenance=CurrentRunSignalProvenance.INSERTED,
        )
        with pytest.raises(ValueError):
            CurrentRunPromotionWorkset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                signals=(invalid_ref,),
            )

    def test_permutations_produce_identical_worksets(self) -> None:
        fixtures = (
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_Y,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_Y,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_Z,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
        )
        baseline = build_test_workset(fixtures)
        for perm in permutations(fixtures):
            permuted = build_test_workset(perm)
            assert permuted == baseline
            assert permuted.signal_ids == baseline.signal_ids
            assert permuted.inserted_count == baseline.inserted_count
            assert (
                permuted.identity_matched_count
                == baseline.identity_matched_count
            )
            assert permuted.total_count == baseline.total_count
            assert permuted.run_id == baseline.run_id
            assert permuted.source_identity == baseline.source_identity

    def test_empty_input_builds_empty_workset(self) -> None:
        workset = build_test_workset(())
        assert workset.is_empty
        assert workset.total_count == 0
        assert workset.signal_ids == ()

    def test_single_unique_reference_builds_one_membership(self) -> None:
        ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=SIGNAL_X,
            provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
        )
        workset = build_test_workset((ref,))
        assert workset.total_count == 1
        assert workset.signal_ids == (SIGNAL_X,)

    def test_multiple_unique_references_build_deterministic_membership(
        self,
    ) -> None:
        refs = (
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_Y,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            ),
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_Z,
                provenance=CurrentRunSignalProvenance.INSERTED,
            ),
        )
        workset = build_test_workset(refs)
        assert workset.total_count == 3
        assert workset.signal_ids == (SIGNAL_X, SIGNAL_Z, SIGNAL_Y)
        assert workset.inserted_count == 2
        assert workset.identity_matched_count == 1

    def test_thirty_three_unique_identity_matched_references_remain_thirty_three(
        self,
    ) -> None:
        refs = tuple(
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=f"sha256:historical-{index:03d}",
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            )
            for index in range(33)
        )
        workset = build_test_workset(refs)
        assert workset.total_count == 33
        assert workset.identity_matched_count == 33
        assert workset.inserted_count == 0
        assert len(refs) - workset.total_count == 0
