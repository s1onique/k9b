"""ACT-K9B-HULK-CURRENT-RUN-WORKSET-STABLE-COLLAPSE01 metric helper tests.

This file exercises the production cardinality helper
:meth:`_calculate_identity_collapse_count` directly. A
regression in the helper would silently misrepresent the
``current_batch_identity_collapse_count`` event field, so each
test runs the helper as production does (same argument shape,
same arithmetic) instead of merely round-tripping the
:class:`CurrentRunWorksetCardinalityError`.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.current_run_promotion_workset import (
    CurrentRunWorksetCardinalityError,
)
from k8s_diag_agent.health.loop_alertmanager_snapshot_signals import (
    _calculate_identity_collapse_count,
)


class TestCalculateIdentityCollapseCount:
    """Direct tests of the production cardinality arithmetic.

    These tests deliberately invoke the helper rather than a
    manual raise so a future regression that decouples the helper
    from the raise (e.g. ``max(0, ...)`` sneak-back, or a
    try/except swallow) is caught here.
    """

    @pytest.mark.parametrize(
        ("raw", "unique", "expected"),
        [
            (0, 0, 0),
            (1, 1, 0),
            (2, 1, 1),
            (3, 1, 2),
            (5, 5, 0),
            (10, 3, 7),
            (33, 1, 32),
        ],
    )
    def test_valid_cases_return_raw_minus_unique(
        self, raw: int, unique: int, expected: int,
    ) -> None:
        # Valid cases must reduce to the standard arithmetic.
        assert (
            _calculate_identity_collapse_count(
                raw_reference_count=raw,
                unique_workset_signal_count=unique,
            )
            == expected
        )

    def test_cardinality_violation_raises_at_metric_site(self) -> None:
        # The metric site MUST raise rather than clamp when the
        # cardinality invariant is violated. Unlike the previous
        # manual ``raise CurrentRunWorksetCardinalityError(...)``
        # test, this exercises the production arithmetic directly.
        with pytest.raises(CurrentRunWorksetCardinalityError) as info:
            _calculate_identity_collapse_count(
                raw_reference_count=1,
                unique_workset_signal_count=2,
            )
        assert info.value.raw_reference_count == 1
        assert info.value.unique_workset_signal_count == 2

    def test_zero_raw_with_zero_unique_does_not_raise(self) -> None:
        # Boundary: an empty observation batch (no signals) MUST
        # not raise when the unique count is also zero.
        assert (
            _calculate_identity_collapse_count(
                raw_reference_count=0,
                unique_workset_signal_count=0,
            )
            == 0
        )

    def test_raw_equals_unique_does_not_raise(self) -> None:
        # Boundary: every reference is unique, so collapse_count=0
        # and the cardinality invariant is exactly equal -- not
        # violating (the check is a strict greater-than).
        assert (
            _calculate_identity_collapse_count(
                raw_reference_count=5,
                unique_workset_signal_count=5,
            )
            == 0
        )
