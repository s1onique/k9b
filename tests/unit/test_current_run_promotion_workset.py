"""Closed union tests for ``current_run_promotion_workset``.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 invariant coverage +
ACT-K9B-HULK-CURRENT-RUN-WORKSET-STABLE-COLLAPSE01 collapse coverage.

The workset is the authoritative representation of which alert signals
are admitted to current-run promotion. The producer of the workset
MUST validate run-id matching, signal uniqueness, deterministic
ordering, and provenance admissibility -- and the validated factory
MUST collapse repeated same-run references for the same canonical
signal identity.
"""

from __future__ import annotations

from itertools import permutations

import pytest

from k8s_diag_agent.collect.current_run_promotion_workset import (
    PROMOTABLE_PROVENANCE,
    CurrentRunPromotionWorkset,
    CurrentRunSignalProvenance,
    CurrentRunSignalRef,
    build_current_run_workset,
)

RUN_ID = "run-2026-07-15T03:30Z"
OTHER_RUN_ID = "run-2026-07-15T03:31Z"
SIGNAL_X = "sha256:signal-X"
SIGNAL_Y = "sha256:signal-Y"
SIGNAL_Z = "sha256:signal-Z"


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
        assert (
            CurrentRunSignalProvenance.INSERTED in PROMOTABLE_PROVENANCE
        )

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
        # The workset itself does not have a ``CONFLICT`` provenance,
        # so a conflict-producing reference cannot be admitted through
        # :func:`build_current_run_workset`.
        with pytest.raises(ValueError):
            CurrentRunSignalProvenance("conflict")
        # The provenance enum is closed; the construction helper
        # rejects any non-promotable provenance value because the
        # dataclass init is type-checked.
        # Equivalently, attempting to bypass via raw construction:
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
        # Failures do not produce a workset reference at all; the
        # producer of the workset filters them out.
        # Here we simulate by trying to construct a workset that
        # references "failed" via a non-promotable provenance string.
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
                signal_id=f"sha256:signal-{i:03d}",
                provenance=(
                    CurrentRunSignalProvenance.INSERTED
                    if i % 2 == 0
                    else CurrentRunSignalProvenance.IDENTITY_MATCHED
                ),
            )
            for i in range(10)
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
                signal_id=f"sha256:signal-{i:03d}",
                provenance=CurrentRunSignalProvenance.INSERTED,
            )
            for i in range(5)
        )
        # Reverse the input order; output should be sorted by
        # (provenance_rank, signal_id) deterministically.
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
                signal_id=f"sha256:signal-{i:03d}",
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            )
            for i in range(3)
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
        # An empty workset is a valid state that says "valid empty".
        # An absent / unavailable workset must surface as a different
        # domain outcome (e.g. ``PromotionCommitUnknown``).
        empty = CurrentRunPromotionWorkset.empty(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
        )
        assert empty.total_count == 0
        assert empty.is_empty


class TestStableCollapseSemantics:
    """ACT-K9B-HULK-CURRENT-RUN-WORKSET-STABLE-COLLAPSE01 coverage.

    Repeated same-run references for the same canonical signal
    identity must collapse to a single deterministic membership.
    Provenance precedence is ``INSERTED > IDENTITY_MATCHED``. Run-id
    mismatches, empty signal_ids, and unsupported provenance values
    fail closed before collapse can mask them.
    """

    # 8.1 Inserted plus matched collapse
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
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=refs,
        )
        assert workset.total_count == 1
        assert workset.inserted_count == 1
        assert workset.identity_matched_count == 0
        assert workset.signal_ids == (SIGNAL_X,)
        assert workset.signals[0].provenance == CurrentRunSignalProvenance.INSERTED

    # 8.2 Reverse-order equivalence
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
        forward_workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=forward,
        )
        reverse_workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=reverse,
        )
        assert forward_workset == reverse_workset
        assert forward_workset.signal_ids == reverse_workset.signal_ids
        assert (
            forward_workset.inserted_count == reverse_workset.inserted_count
        )
        assert (
            forward_workset.identity_matched_count
            == reverse_workset.identity_matched_count
        )
        assert forward_workset.total_count == reverse_workset.total_count

    # 8.3 Repeated matched collapse
    def test_three_matched_references_collapse_to_one(self) -> None:
        refs = tuple(
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=SIGNAL_X,
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            )
            for _ in range(3)
        )
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=refs,
        )
        assert workset.total_count == 1
        assert workset.identity_matched_count == 1
        assert workset.inserted_count == 0
        # Implied collapse count: 3 raw observations, 1 collapsed.
        assert len(refs) - workset.total_count == 2

    # 8.4 Repeated inserted collapse
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
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=refs,
        )
        assert workset.total_count == 1
        assert workset.inserted_count == 1
        assert workset.identity_matched_count == 0
        assert workset.signal_ids == (SIGNAL_X,)

    # 8.5 Different IDs do not collapse
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
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=refs,
        )
        assert workset.total_count == 2
        assert workset.inserted_count == 1
        assert workset.identity_matched_count == 1
        assert workset.signal_ids == (SIGNAL_X, SIGNAL_Y)

    # 8.6 Direct aggregate construction remains invalid
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

    # 8.7 Run mismatch remains fail-closed
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
            build_current_run_workset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                references=refs,
            )

    # 8.8 Unsupported provenance remains fail-closed
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
            build_current_run_workset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                references=(invalid_ref, valid_ref),
            )

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
            build_current_run_workset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                references=(invalid_ref, valid_ref),
            )

    # D7 hardening: StrEnum value-equivalence bypass
    @pytest.mark.parametrize(
        "raw_provenance",
        ["inserted", "identity_matched"],
    )
    def test_raw_string_provenance_rejected_by_factory(
        self, raw_provenance: str
    ) -> None:
        # ``CurrentRunSignalProvenance`` is a :class:`StrEnum`, so
        # raw strings that value-equal a member are not members at
        # runtime. The factory MUST reject them; the precedent test
        # that used "persistence_failure" only exercised the
        # unknown-string path.
        invalid_ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=SIGNAL_X,
            provenance=raw_provenance,  # type: ignore[arg-type]
        )
        with pytest.raises(ValueError):
            build_current_run_workset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                references=(invalid_ref,),
            )

    @pytest.mark.parametrize(
        "raw_provenance",
        ["inserted", "identity_matched"],
    )
    def test_raw_string_provenance_rejected_by_direct_aggregate(
        self, raw_provenance: str
    ) -> None:
        # The strict aggregate applies the same runtime guard; the
        # bypass must be closed there too.
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

    # D9 enforcement: the strict aggregate rejects empty
    # ``signal_id`` so a duplicate valid reference cannot be used
    # to conceal an invalid one. The metric-site raise-now-clamp
    # regression test lives at the producer arithmetic site in
    # ``tests/unit/test_loop_alertmanager_identity_collapse.py``
    # rather than here -- it must invoke the production helper
    # rather than a manual ``raise CurrentRunWorksetCardinalityError(...)``
    # so a future regression that decoupled the metric from the
    # raise would actually fail the test.
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


    # 8.9 Permutation stability
    def test_permutations_produce_identical_worksets(self) -> None:
        # Bounded fixture with repeated IDs across provenances.
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
        baseline = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=fixtures,
        )
        # 5 items -> 120 permutations; build every one and assert
        # the resulting workset is identical to the baseline.
        for perm in permutations(fixtures):
            permuted = build_current_run_workset(
                run_id=RUN_ID,
                source_identity="alertmanager-prod",
                references=tuple(perm),
            )
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

    # 8.10 Empty and unique worksets remain unchanged
    def test_empty_input_builds_empty_workset(self) -> None:
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=tuple(),
        )
        assert workset.is_empty
        assert workset.total_count == 0
        assert workset.signal_ids == ()

    def test_single_unique_reference_builds_one_membership(self) -> None:
        ref = CurrentRunSignalRef(
            run_id=RUN_ID,
            signal_id=SIGNAL_X,
            provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
        )
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=(ref,),
        )
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
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=refs,
        )
        # Ordering is ``(provenance_rank, signal_id)``: INSERTED (rank
        # 0) wins, then IDENTITY_MATCHED (rank 1). Within the INSERTED
        # group the signal_ids sort alphabetically: X, Z. Y follows
        # because it is IDENTITY_MATCHED.
        assert workset.total_count == 3
        assert workset.signal_ids == (SIGNAL_X, SIGNAL_Z, SIGNAL_Y)
        assert workset.inserted_count == 2
        assert workset.identity_matched_count == 1

    def test_thirty_three_unique_identity_matched_references_remain_thirty_three(
        self,
    ) -> None:
        # Historical-duplicate non-regression: 33 distinct identity-matched
        # observations must still produce 33 workset members, with a
        # collapse count of zero.
        refs = tuple(
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=f"sha256:historical-{i:03d}",
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            )
            for i in range(33)
        )
        workset = build_current_run_workset(
            run_id=RUN_ID,
            source_identity="alertmanager-prod",
            references=refs,
        )
        assert workset.total_count == 33
        assert workset.identity_matched_count == 33
        assert workset.inserted_count == 0
        assert len(refs) - workset.total_count == 0


class TestProductionRegression:
    """The 33-identity-duplicate production regression.

    33 adapted alert signals with 0 new inserts and 33 identity-matched
    duplicates. The old counter projection reported zero actionable
    signals; the new workset admits all 33 into the current-run scope.
    """

    def test_33_identity_matched_signals_admitted(self) -> None:
        refs = tuple(
            CurrentRunSignalRef(
                run_id=RUN_ID,
                signal_id=f"sha256:alert-{i:03d}",
                provenance=CurrentRunSignalProvenance.IDENTITY_MATCHED,
            )
            for i in range(33)
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
            f"sha256:alert-{i:03d}" for i in range(33)
        )
