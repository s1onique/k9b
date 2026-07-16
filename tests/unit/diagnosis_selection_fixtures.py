"""Reusable test fixtures and factories for :class:`DiagnosisSelection`.

ACT-K9B-SEAM01-DIAGNOSIS-SELECTION-CONSUMPTION01 contract:

Tests that exercise ``run_automatic_diagnosis_loop`` MUST supply an
explicit, internally consistent :class:`DiagnosisSelection`. The
canonical pattern is to declare the SEMANTIC variant being tested
through one of the explicit constructors:

* :func:`make_promotion_selection` -- ``DiagnosisSelectionFromPromotion``
  carrying a promotion run id and canonical incident IDs.
* :func:`make_store_scan_selection` -- ``DiagnosisSelectionWithoutPromotion``
  with an explicit bounded reason.
* :func:`make_unavailable_selection` -- ``DiagnosisSelectionUnavailable``
  wrapping the actual typed ``PromotionRejected`` or
  ``PromotionCommitUnknown`` outcome recorded by the dispatcher.

There is intentionally NO ``make_diagnosis_selection`` umbrella
factory. Each variant has its own contract (run identity, expected
counter shape, semantic meaning), and silent fall-through between
variants would let tests pass for the wrong reason. Tests that need a
selection must declare the variant under test explicitly so the test
intent is unambiguous.

The shared-fixture approach itself is sound -- pytest fixtures are
intended to provide reusable, consistent test contexts -- but the
fixture must preserve each test's actual semantic mode rather than
collapsing to a default. (``tests/unit/diagnosis_selection_fixtures.py``
is the canonical fixture module; pytest fixtures here are importable
via ``from tests.unit.diagnosis_selection_fixtures import ...``.)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from k8s_diag_agent.collect.diagnosis_selection import DiagnosisSelection
    from k8s_diag_agent.collect.promotion_outcomes import (
        PromotionCommitUnknown,
        PromotionRejected,
        PromotionSucceeded,
    )


def make_promotion_selection(
    *,
    scheduler_run_id: str,
    incident_ids: Iterable[str] = (),
    promotion_outcome: PromotionSucceeded | None = None,
) -> DiagnosisSelection:
    """Build a :class:`DiagnosisSelectionFromPromotion`.

    Args:
        scheduler_run_id: The scheduler run id used to validate
            identity against the selection. The selection's
            ``promotion_run_id`` matches this value so the seam
            validator passes.
        incident_ids: Canonical incident IDs (empty default = the
            authoritative-zero-work ``current_run_empty`` semantic).
        promotion_outcome: Optional :class:`PromotionSucceeded` whose
            ``run_id`` overrides ``scheduler_run_id`` when the
            dispatcher recorded one. The selection's
            ``promotion_run_id`` then matches the dispatcher's view
            rather than the scheduler view, which is the correct
            identity for ``explicit_incident_ids`` runs.

    Returns:
        A :class:`DiagnosisSelectionFromPromotion` carrying the
        promotion-derived ``run_id`` and the canonical incident IDs.
    """
    from k8s_diag_agent.collect.diagnosis_selection import (
        DiagnosisSelectionFromPromotion,
    )

    promotion_run_id = (
        promotion_outcome.run_id
        if promotion_outcome is not None
        else scheduler_run_id
    )
    return DiagnosisSelectionFromPromotion(
        promotion_run_id=promotion_run_id,
        incident_ids=tuple(incident_ids),
    )


def make_store_scan_selection(
    *,
    reason: str = "scheduled_scan_run",
) -> DiagnosisSelection:
    """Build a :class:`DiagnosisSelectionWithoutPromotion`.

    Args:
        reason: The bounded :class:`NoPromotionSelectionReason`
            value. The default is ``scheduled_scan_run``. Invalid
            strings raise ``ValueError`` (the underlying enum rejects
            them); we do NOT silently fall back to the default so a
            test that names the wrong reason fails fast and obviously.

    Returns:
        A :class:`DiagnosisSelectionWithoutPromotion` carrying the
        explicit no-promotion reason.
    """
    from k8s_diag_agent.collect.diagnosis_selection import (
        DiagnosisSelectionWithoutPromotion,
        NoPromotionSelectionReason,
    )

    try:
        resolved = NoPromotionSelectionReason(reason)
    except ValueError as exc:
        raise ValueError(
            f"make_store_scan_selection: {reason!r} is not a bounded "
            "NoPromotionSelectionReason; supply one of "
            f"{sorted(r.value for r in NoPromotionSelectionReason)}."
        ) from exc
    return DiagnosisSelectionWithoutPromotion(reason=resolved)


def make_unavailable_selection(
    *,
    outcome: PromotionRejected | PromotionCommitUnknown,
) -> DiagnosisSelection:
    """Build a :class:`DiagnosisSelectionUnavailable` from a typed outcome.

    The carried outcome is forwarded verbatim. The factory does NOT
    rewrite ``outcome.run_id`` -- the dispatcher's run identity is the
    authority. If you need to test identity mismatch, build the
    outcome manually with the wrong run id and assert that the seam
    raises :class:`DiagnosisRunIdentityMismatchError`.

    Args:
        outcome: The typed :class:`PromotionRejected` or
            :class:`PromotionCommitUnknown` outcome recorded by the
            dispatcher.

    Returns:
        A :class:`DiagnosisSelectionUnavailable` wrapping the outcome.

    Raises:
        TypeError: When ``outcome`` is not a
            :class:`PromotionRejected` or :class:`PromotionCommitUnknown`.
    """
    from k8s_diag_agent.collect.diagnosis_selection import (
        DiagnosisSelectionUnavailable,
    )
    from k8s_diag_agent.collect.promotion_outcomes import (
        PromotionCommitUnknown,
        PromotionRejected,
    )

    if not isinstance(outcome, (PromotionRejected, PromotionCommitUnknown)):
        raise TypeError(
            "make_unavailable_selection: outcome must be a "
            "PromotionRejected or PromotionCommitUnknown; got "
            f"{type(outcome).__name__}"
        )
    return DiagnosisSelectionUnavailable(outcome=outcome)


@pytest.fixture
def promotion_selection_factory():
    """Provide the canonical :func:`make_promotion_selection` factory."""
    return make_promotion_selection


@pytest.fixture
def store_scan_selection_factory():
    """Provide the canonical :func:`make_store_scan_selection` factory."""
    return make_store_scan_selection


@pytest.fixture
def unavailable_selection_factory():
    """Provide the canonical :func:`make_unavailable_selection` factory."""
    return make_unavailable_selection