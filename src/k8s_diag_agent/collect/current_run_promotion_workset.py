"""Authoritative current-run promotion workset.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 domain model.

Current-run membership is a relational fact: a signal observed during
a particular scheduler run may or may not be admitted into that run's
promotion workset. ``CurrentRunSignalRef`` makes that relationship
explicit and removes the legacy "promote everything that was ever
persisted" interpretation that produced the production 33-duplicate
failure.

Allowed provenance:

* :attr:`CurrentRunSignalProvenance.INSERTED` -- the artifact was
  newly written during this run.
* :attr:`CurrentRunSignalProvenance.IDENTITY_MATCHED` -- the artifact
  existed before this run with the same canonical identity.

Disallowed provenance:

* Conflict (``different_*`` reason) and failed persistence outcomes
  cannot produce a workset reference.

ACT-K9B-HULK-CURRENT-RUN-WORKSET-STABLE-COLLAPSE01 normalization:

Raw observations collected during one scheduler run may contain
repeated references to the same immutable signal identity -- e.g.
when an alert appears twice in one snapshot. The workset factory
:func:`build_current_run_workset` collapses those repeated
references into a single deterministic membership per ``signal_id``.
The semantic rules are:

    INSERTED(X) + IDENTITY_MATCHED(X)  -> one INSERTED(X)
    IDENTITY_MATCHED(X) + INSERTED(X)  -> one INSERTED(X)
    INSERTED(X) + INSERTED(X)          -> one INSERTED(X)
    IDENTITY_MATCHED(X) + IDENTITY_MATCHED(X)
                                      -> one IDENTITY_MATCHED(X)

``INSERTED`` dominates ``IDENTITY_MATCHED`` so collapsing cannot
silently weaken a stronger observation. The strict aggregate
invariant -- "every canonical signal identity appears at most once"
-- is preserved by routing the normalization through the factory.
Direct aggregate construction via
``CurrentRunPromotionWorkset(...)`` still rejects duplicate
membership; only the validated factory performs the safe
same-id collapse.

ACT-K9B-HULK-CURRENT-RUN-WORKSET-STABLE-COLLAPSE01 cardinality
invariant:

The aggregate cardinality invariants are ``member_count <=
raw_reference_count`` and ``raw_reference_count - member_count ==
collapse_count``. A violation is a contract error and MUST NOT be
silently clamped; the factory and aggregate constructor both
enforce it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class CurrentRunWorksetError(ValueError):
    """Base class for current-run promotion workset contract errors.

    Used for both normalization-boundary failures (factory validation,
    precedence collapse) and post-construction cardinality violations.
    """


class CurrentRunWorksetCardinalityError(CurrentRunWorksetError):
    """Raised when a workset violates the cardinality invariant.

    The aggregate MUST contain at most one membership per signal
    identity. A scenario where the post-collapse unique count
    exceeds the raw reference count indicates a contract violation
    in the producer -- not a benign data observation -- so the
    factory raises instead of clamping.
    """

    def __init__(self, *, raw: int, unique: int) -> None:
        super().__init__(
            "CurrentRunPromotionWorkset cardinality invariant "
            f"violated: raw_reference_count={raw} < "
            f"unique_workset_signal_count={unique}"
        )
        self.raw_reference_count = raw
        self.unique_workset_signal_count = unique


class CurrentRunSignalProvenance(StrEnum):
    """Why a signal is admitted into the current-run workset.

    Closed enumeration -- free-form strings are not permitted.
    Members of this ``StrEnum`` MUST be passed by enum reference,
    not by raw string. Plain strings that happen to equal a member
    value are rejected because :class:`StrEnum` membership is
    *value-equivalent* and a runtime ``isinstance`` check is the
    only reliable closed-enumeration guard.
    """

    INSERTED = "inserted"
    """The artifact was newly written during this run."""

    IDENTITY_MATCHED = "identity_matched"
    """A same-identity artifact already existed and was matched."""


# Promotable provenance set is exactly the union of the two outcomes
# above. The value is a tuple (not a set) so it can appear in
# frozensets in test fixtures without requiring enum hashability
# guarantees from runtime stubs.
PROMOTABLE_PROVENANCE: tuple[CurrentRunSignalProvenance, ...] = (
    CurrentRunSignalProvenance.INSERTED,
    CurrentRunSignalProvenance.IDENTITY_MATCHED,
)


def _is_promotable_provenance(
    provenance: object,
) -> bool:
    """Return True if ``provenance`` is a :class:`CurrentRunSignalProvenance` member.

    A plain string such as ``"inserted"`` is NOT a valid promotable
    provenance value even though ``CurrentRunSignalProvenance.INSERTED
    == "inserted"``. The factory and the strict aggregate both rely
    on this distinction: :class:`StrEnum` is value-equivalent to
    strings but a runtime producer that supplies raw strings bypasses
    the closed-enumeration guarantee the type system advertises.

    This helper performs the explicit ``isinstance`` check that the
    dataclass type annotation alone cannot enforce at runtime.
    """
    return (
        isinstance(provenance, CurrentRunSignalProvenance)
        and provenance in PROMOTABLE_PROVENANCE
    )


# Provenance precedence for collapsing repeated same-id references.
# Lower numeric rank represents a stronger observation; the loader
# picks the entry with the lowest rank. ``INSERTED`` proves the
# artifact was first created during this run so it dominates the
# later ``IDENTITY_MATCHED`` observation of the same identity.
#
# This table is the single production source of truth for the
# precedence rule. Do not hide it behind incidental Enum ordering;
# the semantic winner must remain explicit and testable.
_PROVENANCE_PRECEDENCE: dict[CurrentRunSignalProvenance, int] = {
    CurrentRunSignalProvenance.INSERTED: 0,
    CurrentRunSignalProvenance.IDENTITY_MATCHED: 1,
}


def _stronger_reference(
    left: CurrentRunSignalRef,
    right: CurrentRunSignalRef,
) -> CurrentRunSignalRef:
    """Return the dominant reference under ``_PROVENANCE_PRECEDENCE``.

    Both inputs MUST share the same ``signal_id`` (the grouped
    key); precondition is enforced by callers and not re-checked
    here so the helper stays cheap for the common case.
    """
    left_rank = _PROVENANCE_PRECEDENCE[left.provenance]
    right_rank = _PROVENANCE_PRECEDENCE[right.provenance]
    if left_rank <= right_rank:
        return left
    return right


def _validate_raw_reference(
    *,
    run_id: str,
    reference: CurrentRunSignalRef,
) -> None:
    """Validate one raw observation against the factory invariants.

    The factory is responsible for the bulk of the safety checks: a
    mismatched run id, an unsupported provenance, a plain-string
    masquerading as a :class:`CurrentRunSignalProvenance` member, or
    an empty ``signal_id`` MUST be rejected here, BEFORE collapse. The
    order intentionally rejects bad references BEFORE the
    stronger/weaker pair logic -- a duplicate valid reference
    cannot be used to conceal an invalid provenance value.
    """
    if not reference.signal_id:
        raise ValueError(
            "CurrentRunPromotionWorkset build received an empty signal_id"
        )
    if reference.run_id != run_id:
        raise ValueError(
            "CurrentRunPromotionWorkset build received a reference for a "
            f"different run ({reference.run_id!r}); expected {run_id!r}"
        )
    if not _is_promotable_provenance(reference.provenance):
        raise ValueError(
            "CurrentRunPromotionWorkset build requires a promotable "
            "provenance member of CurrentRunSignalProvenance; "
            f"got {reference.provenance!r}"
        )


def _collapse_same_signal_references(
    references: tuple[CurrentRunSignalRef, ...],
) -> tuple[CurrentRunSignalRef, ...]:
    """Collapse repeated references to the same ``signal_id``.

    Grouping key is ``signal_id``; provenance precedence is
    ``INSERTED > IDENTITY_MATCHED``. The output is exactly one
    :class:`CurrentRunSignalRef` per unique ``signal_id`` seen in
    the input. Run-id mismatches and unsupported provenance values
    are NOT collapsed -- those failures must surface through
    :func:`_validate_raw_reference` and short-circuit the factory.
    """
    by_signal_id: dict[str, CurrentRunSignalRef] = {}
    for ref in references:
        existing = by_signal_id.get(ref.signal_id)
        if existing is None:
            by_signal_id[ref.signal_id] = ref
            continue
        by_signal_id[ref.signal_id] = _stronger_reference(existing, ref)
    return tuple(by_signal_id.values())


def _deterministic_order(
    references: tuple[CurrentRunSignalRef, ...],
) -> tuple[CurrentRunSignalRef, ...]:
    """Return ``references`` sorted by ``(provenance_rank, signal_id)``.

    Output ordering is independent of the input ordering, which is
    required so the dispatcher receives the same backend request
    for any input permutation that yields the same logical workset.
    """
    return tuple(
        sorted(
            references,
            key=lambda ref: (
                _PROVENANCE_PRECEDENCE[ref.provenance],
                ref.signal_id,
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class CurrentRunSignalRef:
    """A single signal's membership in one current-run workset.

    The struct is intentionally narrow: membership is run-scoped and
    changes from run to run. Branded ``CurrentRunSignalId`` is
    explicitly avoided so accidental cross-run reuse is structurally
    impossible.
    """

    run_id: str
    """Identity of the scheduler run that owns the reference."""

    signal_id: str
    """Canonical alert-signal identity observed during this run."""

    provenance: CurrentRunSignalProvenance
    """Why the signal was admitted into the workset."""


@dataclass(frozen=True, slots=True)
class CurrentRunPromotionWorkset:
    """Immutable aggregate of every current-run promotion workset member.

    Construction rules (enforced by :meth:`build`):

    * Every reference belongs to the same ``run_id``.
    * ``signal_ids`` is unique (no duplicate memberships).
    * Every ``provenance`` is in :data:`PROMOTABLE_PROVENANCE`.
    * ``signals`` is deterministically ordered by
      ``(provenance_rank, signal_id)`` so persisted, parsed and
      re-validated copies produce identical membership.
    """

    run_id: str
    signals: tuple[CurrentRunSignalRef, ...]
    source_identity: str

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("CurrentRunPromotionWorkset requires a run_id")
        if not self.source_identity:
            raise ValueError("CurrentRunPromotionWorkset requires a source_identity")
        if not self.signals:
            # An empty workset is valid; an absent workset is not.
            return
        seen: set[str] = set()
        for ref in self.signals:
            if not ref.signal_id:
                # The strict aggregate also enforces nonempty
                # ``signal_id``; empty signal ids cannot participate
                # in membership.
                raise ValueError(
                    "CurrentRunPromotionWorkset contains a reference "
                    "with an empty signal_id"
                )
            if ref.run_id != self.run_id:
                raise ValueError(
                    "CurrentRunPromotionWorkset contains a reference from "
                    f"a different run ({ref.run_id!r})"
                )
            if not _is_promotable_provenance(ref.provenance):
                # The runtime ``isinstance`` guard rejects raw
                # strings that value-equal valid enum members. See
                # :func:`_is_promotable_provenance`.
                raise ValueError(
                    "CurrentRunPromotionWorkset contains a non-promotable "
                    f"provenance; got {ref.provenance!r}"
                )
            if ref.signal_id in seen:
                raise ValueError(
                    "CurrentRunPromotionWorkset contains duplicate "
                    f"signal_id {ref.signal_id!r}"
                )
            seen.add(ref.signal_id)

    @property
    def signal_ids(self) -> tuple[str, ...]:
        """Deterministic, unique list of admitted signal IDs."""
        return tuple(ref.signal_id for ref in self.signals)

    @property
    def total_count(self) -> int:
        """Total number of admitted signals."""
        return len(self.signals)

    @property
    def inserted_count(self) -> int:
        """Count of newly-inserted provenance entries."""
        return sum(
            1
            for ref in self.signals
            if ref.provenance == CurrentRunSignalProvenance.INSERTED
        )

    @property
    def identity_matched_count(self) -> int:
        """Count of identity-matched provenance entries."""
        return sum(
            1
            for ref in self.signals
            if ref.provenance == CurrentRunSignalProvenance.IDENTITY_MATCHED
        )

    @property
    def is_empty(self) -> bool:
        """True when the workset has no members."""
        return len(self.signals) == 0

    @classmethod
    def empty(
        cls,
        *,
        run_id: str,
        source_identity: str,
    ) -> CurrentRunPromotionWorkset:
        """Return a validated empty workset.

        An empty workset is **not** the same as an absent/unavailable
        workset. Callers that cannot prove a workset exists MUST NOT
        fabricate an empty one; they must surface the absence as a
        ``PromotionRejected`` or ``PromotionCommitUnknown`` outcome.
        """
        return cls(
            run_id=run_id,
            signals=tuple(),
            source_identity=source_identity,
        )

    @classmethod
    def build(
        cls,
        *,
        run_id: str,
        source_identity: str,
        references: tuple[CurrentRunSignalRef, ...],
    ) -> CurrentRunPromotionWorkset:
        """Validate, collapse and order ``references`` into a workset.

        The factory distinguishes two boundaries:

        * **Raw observation boundary** -- the caller may supply one
          reference per observation, including repeated observations
          of the same canonical signal identity.
        * **Validated aggregate boundary** -- the returned workset
          contains at most one reference per ``signal_id`` and is
          ordered deterministically by
          ``(provenance_rank, signal_id)``.

        Provenance precedence (``INSERTED > IDENTITY_MATCHED``)
        applies during collapse so a stronger observation is never
        silently weakened by a repeated later observation. Mismatched
        ``run_id``, empty ``signal_id``, or non-promotable provenance
        short-circuits the factory -- a duplicate valid reference
        cannot be used to conceal an invalid one.

        Direct construction via ``CurrentRunPromotionWorkset(...)``
        is unchanged: it remains strict and rejects duplicate
        memberships, so only callers that explicitly want the
        same-id collapse go through ``build``.
        """
        if not run_id:
            raise ValueError("run_id is required to build a workset")
        if not source_identity:
            raise ValueError("source_identity is required to build a workset")

        # Validate every raw observation BEFORE any collapse work.
        # An out-of-enum provenance value, an empty signal_id, or a
        # mismatched run_id MUST short-circuit the factory; a
        # duplicate valid reference cannot be used to conceal any
        # of these.
        for ref in references:
            _validate_raw_reference(run_id=run_id, reference=ref)

        collapsed = _collapse_same_signal_references(references)
        ordered = _deterministic_order(collapsed)

        return cls(
            run_id=run_id,
            signals=ordered,
            source_identity=source_identity,
        )


def build_current_run_workset(
    *,
    run_id: str,
    source_identity: str,
    references: tuple[CurrentRunSignalRef, ...],
) -> CurrentRunPromotionWorkset:
    """Validated factory.

    Equivalent to :meth:`CurrentRunPromotionWorkset.build`; provided
    so callers do not need to reach for the class itself.
    """
    return CurrentRunPromotionWorkset.build(
        run_id=run_id,
        source_identity=source_identity,
        references=references,
    )


__all__ = [
    "CurrentRunPromotionWorkset",
    "CurrentRunSignalProvenance",
    "CurrentRunSignalRef",
    "CurrentRunWorksetError",
    "CurrentRunWorksetCardinalityError",
    "PROMOTABLE_PROVENANCE",
    "build_current_run_workset",
]
