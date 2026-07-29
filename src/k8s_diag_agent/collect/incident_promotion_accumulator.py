"""Typed run-scoped promotion accumulator.

This module provides ``RunPromotionAccumulator`` -- a single object that
collects ``PromotionRecord`` values from every cluster / source participating
in a health run. It replaces the legacy ``directories["__last_promotion_result__"]``
magic handoff so:

* promotion results are no longer smuggled through a ``dict[str, Path]``;
* we never lose data when a run has multiple Alertmanager sources;
* ``canonical_incident_ids`` are deduped and order-stabilised at the run
  boundary, eliminating post-hoc ``zip`` correlation between candidate and
  incident lists.

R7 (item 3): every backend-authoritative ``PromotionBatch`` is validated
against the ordered-sequence-with-multiplicity contract BEFORE the
accumulator mutates its state. A rejected batch leaves the accumulator
unchanged and surfaces a typed :class:`PromotionConsistencyContractError`
that the orchestrator can route to the audit log.

SEAM01 R2 contract:
* Workset state (VALID/INVALID/NOT_APPLICABLE) is tracked explicitly.
* ``record_promotion_result()`` applies promotion results atomically.
* ``last_handoff_error`` captures handoff failures for downstream blocking.
* The accumulator preserves original promotion outcomes from ``PromotionBatch``.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 contract:
* The accumulator is the single owner of the typed :class:`PromotionOutcome`
  (recording, conflict detection, and typed-outcome projection are
  delegated to :class:`PromotionOutcomeRecorderMixin` in
  :mod:`incident_promotion_outcome_recorder`).
* The accumulator is the single owner of the typed :class:`PromotionOutcome`
  for a health run via :meth:`record_promotion_outcome`. Recording a
  second outcome for a different ``run_id`` or a materially different
  variant raises :class:`PromotionOutcomeConflictError`; an identical
  repeated assignment is idempotent.
* Once a typed outcome is recorded, :meth:`canonical_incident_ids`,
  :meth:`promotion_records`, and the compatibility booleans
  (``promotion_may_have_committed``,
  ``promotion_consistency_error_recorded``,
  ``diagnosis_handoff_available``) DERIVE from the recorded outcome
  rather than from legacy counter projections. Legacy accumulation is
  the fallback only when no typed outcome is recorded.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R1
Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01-R2
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from .incident_identity_hardening import (
    INCIDENT_ACCESS_MODE_BACKEND,
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_SKIPPED_DUPLICATE,
    PromotionConsistencyContractError,
    PromotionRecord,
    _validate_response_contracts,
)
from .incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
    PromotionOutcomeRecorderMixin,
    PromotionOutcomeRecording,
)
from .incident_promotion_scoped_atomic_recorder import (
    ScopedPromotionAtomicRecorderMixin,
)
from .promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorHandoff,
)

if TYPE_CHECKING:
    from .incident_promotion_batch import PromotionBatch
    from .promotion_diagnosis_handoff import (
        PromotionDiagnosisHandoffError,
        PromotionPropagationResult,
    )
    from .promotion_outcomes import (
        PromotionOutcome,
    )


class PromotionWorksetState(StrEnum):
    """Explicit workset state for promotion-to-diagnosis propagation.

    SEAM01 R2: State is EXPLICIT, not inferred from ID tuple emptiness.

    State matrix:
    - VALID + IDs:     explicit current-run diagnosis
    - VALID + empty:   successful stop; zero store operations
    - INVALID:         blocked diagnosis; zero store operations
    - NOT_APPLICABLE: store scan only when explicitly configured
    """

    VALID = "valid"
    """Workset is valid for diagnosis propagation."""

    INVALID = "invalid"
    """Workset is invalid; diagnosis must be blocked."""

    NOT_APPLICABLE = "not_applicable"
    """Workset not applicable; store scan may be used if configured."""


class AccumulatorAccessModeError(ValueError):
    """Raised when a batch violates the run-scoped access-mode contract.

    The accumulator refuses to accept a batch whose ``incident_access_mode``
    disagrees with the running value. The dispatcher is responsible for
    routing every batch through a single access-mode boundary; mixing
    backend and local batches in one run is a fail-closed contract
    violation. The exception carries the rejected batch and the running
    state so callers can introspect the drift.
    """

    def __init__(
        self,
        message: str,
        *,
        running_mode: str,
        rejected_mode: str,
    ) -> None:
        super().__init__(message)
        self.running_mode = running_mode
        self.rejected_mode = rejected_mode


@dataclass
class RunPromotionAccumulator(
    PromotionOutcomeRecorderMixin,
    ScopedPromotionAtomicRecorderMixin,
):
    """Aggregates promotion results from every cluster / source in a run.

    The accumulator is intentionally a value object so it can be passed
    around the orchestrator without leaking through untyped dictionaries.
    Methods are ``mutator-only`` on the accumulator itself: callers add
    records via :meth:`add_record` / :meth:`add_batch` and consume
    canonical IDs via :meth:`canonical_incident_ids` and
    :meth:`promotion_records`.

    The accumulator dedupes canonical IDs by deterministic first-seen
    order. The ``promotion_records`` list preserves the input order so
    the verifier can reproduce the same diagnostic on multiple runs.

    R3: the accumulator also collects typed ``PromotionBatch`` values
    via :meth:`add_batch`. The batch preserves aggregate errors, scan
    counts, firing counts, promotion modes, access modes, and source
    provenance. The accumulator MUST NOT infer ``promotion_mode``
    from whether records are empty.

    R4: :meth:`add_batch` is validate-before-mutate. The batch's
    ``incident_access_mode`` is checked against the running value
    BEFORE any field on the accumulator is mutated. A rejected batch
    leaves ``batches``, ``promotion_records``,
    ``_seen_canonical_ids``, ``total_*``, and the ``last_*`` fields
    exactly as they were, so the orchestrator can never observe a
    partial-batch state.

    ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01: the
    accumulator is the single owner of the typed
    :class:`PromotionOutcome` for the run. ``promotion_outcome``
    carries the typed result, ``promotion_outcome_run_id`` carries the
    cross-check identity, and :meth:`promotion_outcome_variant_label`
    projects the variant for telemetry.

    Once a typed outcome is recorded, :meth:`canonical_incident_ids`
    and :meth:`promotion_records` derive from it -- NOT from the
    legacy counter projections. The legacy accumulation is the
    fallback only when no typed outcome has been recorded.
    """

    promotion_records: list[PromotionRecord] = field(default_factory=list)
    _seen_canonical_ids: set[str] = field(default_factory=set, repr=False)
    # R3: track every batch handed to the accumulator so downstream
    # callers can introspect the dispatcher outcome (mode, errors,
    # scan scope) without re-deriving it.
    batches: list[PromotionBatch] = field(default_factory=list, repr=False)
    # Aggregated batch metrics across every batch the accumulator has
    # received. These are the canonical numbers the health-run log
    # emits; ``promotion_mode`` and ``incident_access_mode`` are
    # derived from the latest batch's values to avoid silent drift.
    total_scanned: int = 0
    total_firing: int = 0
    total_opened_incidents: int = 0
    total_updated_incidents: int = 0
    total_skipped_duplicates: int = 0
    total_errors: int = 0
    # R5 (item 5): sum the per-batch ``unique_candidate_count`` so the
    # structured log never conflates candidate-source counts with the
    # backend-side ``scanned`` counter.
    total_unique_candidate_count: int = 0
    last_promotion_mode: str = ""
    last_incident_access_mode: str = ""
    last_source_kind: str = ""
    last_promotion_scan_scope: str = ""
    # R7 (item 1): a typed contract failure captured by the
    # orchestrator's ``_run_monitoring_discovery`` path. The accumulator
    # itself refuses to mutate when a backend-authoritative batch
    # violates the ordered-sequence-with-multiplicity contract; the
    # orchestrator catches the
    # :class:`PromotionConsistencyContractError` raised by
    # :meth:`add_batch`, stores it here, and continues so the rest of
    # the health run can still emit its terminal-completion event.
    # ``_derive_automatic_diagnosis_inputs`` reads this field and
    # short-circuits to the ``blocked`` decision when set.
    last_contract_error: PromotionConsistencyContractError | None = None

    # SEAM01 R2: Explicit workset state for promotion-to-diagnosis propagation.
    # The state is set by ``propagate_promotion_result_to_run()`` and read
    # by ``_derive_automatic_diagnosis_inputs()`` to drive selection mode.
    workset_state: PromotionWorksetState = PromotionWorksetState.NOT_APPLICABLE

    # SEAM01 R2: Last handoff error from ``propagate_promotion_result_to_run()``.
    # When set, the workset is marked INVALID and automatic diagnosis is blocked.
    last_handoff_error: PromotionDiagnosisHandoffError | None = None

    # SEAM01 R2: Last propagation result from successful handoff.
    # Captured for production telemetry.
    last_propagation_result: PromotionPropagationResult | None = None

    # ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01: typed
    # promotion-outcome ownership. ``promotion_outcome`` is the
    # authoritative typed outcome once the orchestrator has classified
    # the dispatcher result. ``promotion_outcome_run_id`` is the
    # cross-check identity that ``record_promotion_outcome`` uses to
    # fail closed on cross-run laundry.
    promotion_outcome: PromotionOutcome | None = field(default=None, repr=False)
    promotion_outcome_run_id: str = ""

    # ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION01-FINALIZATION01:
    # The typed scoped promotion handoff. ``scoped_promotion_handoff`` is
    # the closed authority carried directly from the active scoped
    # dispatcher; downstream projections MUST derive from it (or from
    # the typed ``promotion_outcome`` above) and MUST NOT infer
    # commit authority from ``promotion_records``,
    # ``promotion_record_count``, canonical incident counts, diagnosis
    # incident counts, or ``ok``/``errors`` fields.
    scoped_promotion_handoff: ScopedPromotionAccumulatorHandoff | None = (
        field(default=None, repr=False)
    )
    # Request identity (``request_id`` / ``request_fingerprint``)
    # has ONE stored authority: the typed handoff above. The
    # string-shaped projections below are derived @property
    # accessors; assignment is structurally forbidden because the
    # dataclass no longer declares them as mutable fields.

    # ---------------- R4 atomic insertion helpers (validate-before-mutate) ----

    def _snapshot(self) -> dict[str, object]:
        """Return a deep snapshot of the accumulator's mutable state.

        Used by :meth:`add_batch` AND by the atomic
        :meth:`record_scoped_promotion_batch` transaction to
        guarantee that a rejected call leaves the accumulator
        unchanged. The snapshot MUST include every mutable field
        that the atomic recorder can touch (including
        :attr:`scoped_promotion_handoff`) or the rollback
        transaction will leave the handoff slot stale.
        """
        return {
            "promotion_records": list(self.promotion_records),
            "_seen_canonical_ids": set(self._seen_canonical_ids),
            "batches": list(self.batches),
            "total_scanned": self.total_scanned,
            "total_firing": self.total_firing,
            "total_opened_incidents": self.total_opened_incidents,
            "total_updated_incidents": self.total_updated_incidents,
            "total_skipped_duplicates": self.total_skipped_duplicates,
            "total_errors": self.total_errors,
            "total_unique_candidate_count": self.total_unique_candidate_count,
            "last_promotion_mode": self.last_promotion_mode,
            "last_incident_access_mode": self.last_incident_access_mode,
            "last_source_kind": self.last_source_kind,
            "last_promotion_scan_scope": self.last_promotion_scan_scope,
            "promotion_outcome": self.promotion_outcome,
            "promotion_outcome_run_id": self.promotion_outcome_run_id,
            "scoped_promotion_handoff": self.scoped_promotion_handoff,
        }

    def _restore(self, snap: dict[str, object]) -> None:
        """Restore mutable state from a previously taken snapshot.

        ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
        CORRECTION04-REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01: the
        restore path MUST also reset
        :attr:`scoped_promotion_handoff` so the rollback transaction
        leaves the handoff slot in its pre-call state.
        """
        self.promotion_records = cast("list[PromotionRecord]", snap["promotion_records"])
        self._seen_canonical_ids = cast("set[str]", snap["_seen_canonical_ids"])
        self.batches = cast("list[PromotionBatch]", snap["batches"])
        self.total_scanned = cast(int, snap["total_scanned"])
        self.total_firing = cast(int, snap["total_firing"])
        self.total_opened_incidents = cast(int, snap["total_opened_incidents"])
        self.total_updated_incidents = cast(int, snap["total_updated_incidents"])
        self.total_skipped_duplicates = cast(int, snap["total_skipped_duplicates"])
        self.total_errors = cast(int, snap["total_errors"])
        self.total_unique_candidate_count = cast(
            int, snap["total_unique_candidate_count"]
        )
        self.last_promotion_mode = cast(str, snap["last_promotion_mode"])
        self.last_incident_access_mode = cast(str, snap["last_incident_access_mode"])
        self.last_source_kind = cast(str, snap["last_source_kind"])
        self.last_promotion_scan_scope = cast(str, snap["last_promotion_scan_scope"])
        self.promotion_outcome = cast(
            "PromotionOutcome | None", snap["promotion_outcome"]
        )
        self.promotion_outcome_run_id = cast(
            str, snap["promotion_outcome_run_id"]
        )
        self.scoped_promotion_handoff = cast(
            "ScopedPromotionAccumulatorHandoff | None",
            snap["scoped_promotion_handoff"],
        )

    def _local_skipped_duplicate_count(self) -> int:
        """Count ``skipped_duplicate`` outcomes from local records.

        R5 (item 5): the batch-level ``skipped_duplicates`` aggregate
        is sourced from the dispatcher's authoritative count, but
        ``local`` promotion only knows about :class:`PromotionRecord`
        values. Counting the local records directly means the
        accumulator surfaces the same number whichever path produced the
        batch.
        """
        return sum(
            1
            for record in self.promotion_records
            if record.promotion_outcome
            == PROMOTION_OUTCOME_SKIPPED_DUPLICATE
        )

    def add_record(self, record: PromotionRecord) -> None:
        """Append a single ``PromotionRecord`` to the accumulator.

        Records with a ``None`` canonical incident ID do NOT populate the
        dedup set so they can never mask a later authoritative
        ``canonical_incident_id`` with the same value.

        Note: this method only mutates the legacy accumulator state.
        The typed outcome (when recorded) is the single source of
        truth for downstream projections; legacy state is the fallback
        only when no typed outcome is recorded.
        """
        self.promotion_records.append(record)
        if record.canonical_incident_id:
            self._seen_canonical_ids.add(record.canonical_incident_id)

    def add_records(self, records: Iterable[PromotionRecord]) -> None:
        for record in records:
            self.add_record(record)

    def record_promotion_result(
        self,
        *,
        source: str,
        incident_ids: tuple[str, ...],
    ) -> None:
        """Record canonical incident IDs from a promotion result atomically.

        This method provides the canonical atomic API for recording promotion
        results into the accumulator. It should be used instead of directly
        mutating ``_seen_canonical_ids`` to ensure consistent behavior.

        Each ID is recorded with a synthetic ``PromotionRecord`` using the
        "opened" outcome (since we only record actionable IDs from promotion).

        If any ID is already in the accumulator, it is not duplicated.

        Args:
            source: The source of the promotion (e.g. 'alertmanager').
            incident_ids: The actionable canonical incident IDs to record.
        """
        for incident_id in incident_ids:
            if incident_id not in self._seen_canonical_ids:
                self._seen_canonical_ids.add(incident_id)
                self.promotion_records.append(
                    PromotionRecord(
                        source_candidate_id=f"<{source}>",
                        canonical_incident_id=incident_id,
                        promotion_outcome=PROMOTION_OUTCOME_OPENED,
                    )
                )


    def add_batch(self, batch: PromotionBatch) -> None:
        """Consume a typed ``PromotionBatch`` and aggregate it atomically.

        R4 contract: ``add_batch`` is validate-before-mutate. The batch's
        ``incident_access_mode`` MUST agree with the running value (or
        with the empty accumulator's absent value). If the running
        accumulator has been seeded with one mode and a subsequent batch
        disagrees, the call raises :class:`AccumulatorAccessModeError`
        and restores the accumulator to the exact state it had before
        the call. ``promotion_records``, ``_seen_canonical_ids``,
        ``batches``, ``total_*``, and ``last_*`` are all preserved.

        R3 contract (carried forward): batch records are added via
        :meth:`add_record` so canonical-ID dedup stays consistent. The
        aggregate metrics are added to the running totals and the
        latest batch's ``promotion_mode`` / ``incident_access_mode`` /
        ``source_kind`` / ``promotion_scan_scope`` are stored verbatim
        for downstream structured logging.

        R7 contract (item 3): every backend-authoritative batch is
        validated against the ordered-sequence-with-multiplicity
        contract BEFORE any field on the accumulator is mutated. The
        authoritative ``opened_incident_ids`` /
        ``updated_incident_ids`` arrays carried by the dispatcher's
        ``IncidentPromotionResult`` MUST match the ordered sequence of
        ``canonical_incident_id`` values on the ``promotion_records``
        list (with multiplicity). The legacy-backend regression --
        nonzero counts, empty records, empty IDs -- is one of the
        failure shapes that surfaces here. Local-mode batches are NOT
        validated here because local promotion uses the legacy
        synthesized-aggregate records shape which is intentionally not
        subject to the strict contract; local batches that introduce
        authoritative canonical IDs (the future R8 path) will be
        validated through a future contract expansion.
        """
        snap = self._snapshot()
        try:
            if batch.incident_access_mode == INCIDENT_ACCESS_MODE_BACKEND:
                _validate_response_contracts(
                    promotion_records=list(batch.promotion_records),
                    opened_incidents=batch.opened_incidents,
                    updated_incidents=batch.updated_incidents,
                    opened_incident_ids=batch.opened_incident_ids,
                    updated_incident_ids=batch.updated_incident_ids,
                )
            self._apply_batch(batch)
        except AccumulatorAccessModeError:
            self._restore(snap)
            raise
        except PromotionConsistencyContractError:
            self._restore(snap)
            raise

    def _apply_batch(self, batch: PromotionBatch) -> None:
        """Internal: actually merge a batch (no rollback handling)."""
        if (
            self.last_incident_access_mode
            and self.last_incident_access_mode != batch.incident_access_mode
        ):
            raise AccumulatorAccessModeError(
                f"Conflicting access modes within one run: "
                f"{self.last_incident_access_mode!r} vs "
                f"{batch.incident_access_mode!r}",
                running_mode=self.last_incident_access_mode,
                rejected_mode=batch.incident_access_mode,
            )
        self.batches.append(batch)
        for record in batch.promotion_records:
            self.add_record(record)
        self.total_scanned += batch.scanned
        self.total_firing += batch.firing
        self.total_opened_incidents += batch.opened_incidents
        self.total_updated_incidents += batch.updated_incidents
        # R5 (item 5): count ``skipped_duplicate`` outcomes from local
        # records whenever the batch did not publish a dispatcher-side
        # aggregate (e.g. ``local`` promotion). This guarantees the
        # summary surfaces the same number whichever path produced the
        # batch.
        record_skipped = self._local_skipped_duplicate_count()
        self.total_skipped_duplicates = max(
            self.total_skipped_duplicates + batch.skipped_duplicates,
            record_skipped,
        )
        # R5 (item 5): sum the per-batch ``unique_candidate_count`` so
        # the structured log does NOT collapse this counter into
        # ``total_scanned`` and lose per-source provenance.
        self.total_unique_candidate_count += batch.unique_candidate_count
        self.total_errors += batch.errors
        self.last_promotion_mode = batch.promotion_mode
        self.last_incident_access_mode = batch.incident_access_mode
        self.last_source_kind = batch.source_kind
        self.last_promotion_scan_scope = batch.promotion_scan_scope

    # ---------------- R4 consume-accumulator-truth helpers --------------------

    def has_promotion_activity(self) -> bool:
        """Return True if at least one batch has been accepted.

        The orchestrator uses this to distinguish a deliberate
        empty promotion run from one that never reached promotion.
        """
        return bool(self.batches)

    def aggregated_error_messages(self) -> tuple[str, ...]:
        """Return bounded error messages from every accepted batch."""
        messages: list[str] = []
        for batch in self.batches:
            messages.extend(batch.error_messages)
        return tuple(messages)

    @property
    def scoped_promotion_request_id(self) -> str:
        """Return the recorded handoff's request id, or ``""`` when absent.

        Derived projection of :attr:`scoped_promotion_handoff`. The
        accumulator does NOT store a mutable copy of this value;
        callers MUST NOT assign to the property.
        """
        handoff = self.scoped_promotion_handoff
        return "" if handoff is None else handoff.request_id

    @property
    def scoped_promotion_request_fingerprint(self) -> str:
        """Return the recorded handoff's fingerprint, or ``""`` when absent.

        Derived projection of :attr:`scoped_promotion_handoff`. The
        accumulator does NOT store a mutable copy of this value;
        callers MUST NOT assign to the property.
        """
        handoff = self.scoped_promotion_handoff
        return "" if handoff is None else handoff.request_fingerprint

    def __setattr__(self, name: str, value: object) -> None:
        """Reject writes to derived request-identity projections."""
        if name in {
            "scoped_promotion_request_id",
            "scoped_promotion_request_fingerprint",
        }:
            raise AttributeError(
                f"{name} is a derived projection of "
                "scoped_promotion_handoff; assignment is forbidden."
            )
        super().__setattr__(name, value)

    def record_scoped_promotion(
        self,
        handoff: ScopedPromotionAccumulatorHandoff,
    ) -> None:
        """Compatibility wrapper around :meth:`record_scoped_promotion_batch`.

        ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
        CORRECTION03-ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01.

        The active scoped dispatcher MUST call
        :meth:`record_scoped_promotion_batch` with both the typed
        handoff and the dispatcher's accounting batch. This wrapper
        exists only so existing unit tests that exercise
        ``record_scoped_promotion(handoff)`` still record the typed
        handoff and outcome; it routes through the new atomic
        operation so the single-request-identity-authority invariant
        is preserved.

        The wrapper builds the bounded accounting batch from the
        handoff itself (the dispatcher's projection has already
        produced the canonical ``IncidentPromotionResult``); it
        then forwards everything through the atomic recorder. When
        the caller has its own batch (the production dispatcher
        path) it MUST bypass this wrapper and call the atomic
        method directly.

        The handoff is the only authority for the active scoped
        path. The original :class:`PromotionOutcome` reaches the
        accumulator unchanged by identity. Receipt presence is
        governed by the handoff variant: only the completed variant
        carries a receipt; uncertain and rejected variants are
        structurally incapable of carrying one. Commit authority
        is derived from :attr:`commit_disposition`; the function
        MUST NOT infer whether promotion ran from
        ``promotion_records``, ``promotion_record_count``, canonical
        incident counts, diagnosis incident counts, or
        ``ok``/``errors`` fields.
        """
        from .incident_promotion_scoped_atomic_projection import (
            build_compatibility_batch_from_handoff,
        )

        accounting_batch = build_compatibility_batch_from_handoff(
            handoff
        )
        # Forward through the atomic path. The return value is
        # discarded for backward compatibility with the prior
        # signature, which returned ``None``.
        self.record_scoped_promotion_batch(
            handoff=handoff,
            batch=accounting_batch,
        )

    def scoped_promotion_handoff_value(
        self,
    ) -> ScopedPromotionAccumulatorHandoff | None:
        """Return the recorded scoped promotion handoff, if any.

        The accessor returns the typed authority verbatim. It MUST
        NOT be reconstructed from legacy counters or aggregate
        incident IDs.
        """
        return self.scoped_promotion_handoff


    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly snapshot of the accumulator.

        The shape mirrors the existing ``promotion_summary_propagated``
        dict consumed by ``loop_automatic_diagnosis.run_automatic_diagnosis_loop``
        so we can keep the existing structured-log paths intact.
        """
        return {
            "promotion_records": [
                record.to_dict() for record in self.promotion_records
            ],
            "opened_incident_ids": self.canonical_incident_ids(),
            "promotion_outcomes": list(self.promotion_outcomes()),
            "unique_candidate_count": len({
                record.source_candidate_id
                for record in self.promotion_records
            }),
        }


__all__ = [
    "AccumulatorAccessModeError",
    "PromotionOutcomeConflictError",
    "PromotionOutcomeRecording",
    "PromotionWorksetState",
    "RunPromotionAccumulator",
]
