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
from typing import TYPE_CHECKING

from .incident_identity_hardening import (
    PromotionConsistencyContractError,
    PromotionRecord,
)
from .incident_promotion_accumulator_compat import (
    record_scoped_promotion_compat,
)
from .incident_promotion_accumulator_errors import (
    AccumulatorAccessModeError,
    PromotionWorksetState,
)
from .incident_promotion_accumulator_mutation import (
    _local_skipped_duplicate_count_mutation,
    add_batch_mutation,
    add_record_mutation,
    add_records_mutation,
    record_promotion_result_mutation,
)
from .incident_promotion_accumulator_projection import (
    aggregated_error_messages,
    as_dict,
    has_promotion_activity,
    reject_derived_assignment,
    scoped_promotion_batch_projection,
    scoped_promotion_handoff_value,
    scoped_promotion_request_fingerprint_projection,
    scoped_promotion_request_id_projection,
)
from .incident_promotion_accumulator_snapshot import (
    restore_state,
    snapshot_state,
)
from .incident_promotion_batch import PromotionBatch
from .incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
    PromotionOutcomeRecorderMixin,
    PromotionOutcomeRecording,
)
from .incident_promotion_scoped_atomic_host_protocol import (
    AccumulatorSnapshot,
)
from .incident_promotion_scoped_atomic_recorder import (
    ScopedPromotionAtomicRecorderMixin,
)
from .incident_promotion_scoped_atomic_recording_authority import (
    ScopedPromotionRecordedAuthority,
)
from .promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorHandoff,
)

if TYPE_CHECKING:
    from .promotion_diagnosis_handoff import (
        PromotionDiagnosisHandoffError,
        PromotionPropagationResult,
    )
    from .promotion_outcomes import (
        PromotionOutcome,
    )


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

    # ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
    # The single scoped recording authority. The active scoped
    # dispatcher carries the typed ``ScopedPromotionAccumulatorHandoff``
    # together with its ``PromotionBatch``; downstream projections
    # MUST derive from this authority (or from the typed
    # ``promotion_outcome`` above) and MUST NOT infer commit
    # authority from ``promotion_records``,
    # ``promotion_record_count``, canonical incident counts,
    # diagnosis incident counts, or ``ok``/``errors`` fields. The
    # general ``batches`` list is aggregate inventory only -- the
    # recorder never indexes ``batches[-1]`` for the scoped replay
    # check.
    scoped_promotion_recording: ScopedPromotionRecordedAuthority | None = (
        field(default=None, repr=False)
    )
    # Request identity (``request_id`` / ``request_fingerprint``)
    # has ONE stored authority: the typed handoff above. The
    # string-shaped projections below are derived @property
    # accessors; assignment is structurally forbidden because the
    # dataclass no longer declares them as mutable fields.

    # ---------------- R4 atomic insertion helpers (validate-before-mutate) ----

    def _snapshot(self) -> AccumulatorSnapshot:
        """Delegate to :mod:`incident_promotion_accumulator_snapshot`.

        The single canonical implementation lives in
        :func:`snapshot_state` so the dataclass state remains
        declared in one canonical place while the snapshot
        logic lives in a focused module under the hard 500-line
        size cap.
        """
        return snapshot_state(self)

    def _restore(self, snap: AccumulatorSnapshot) -> None:
        """Delegate to :mod:`incident_promotion_accumulator_snapshot`.

        The single canonical implementation lives in
        :func:`restore_state` so the dataclass state remains
        declared in one canonical place while the restore logic
        lives in a focused module under the hard 500-line size
        cap.
        """
        restore_state(self, snap)

    def _local_skipped_duplicate_count(self) -> int:
        """Delegate to :mod:`incident_promotion_accumulator_mutation`."""
        return _local_skipped_duplicate_count_mutation(self)

    def add_record(self, record: PromotionRecord) -> None:
        """Delegate to :mod:."""
        add_record_mutation(self, record)

    def add_records(self, records: Iterable[PromotionRecord]) -> None:
        """Delegate to :mod:."""
        add_records_mutation(self, records)

    def record_promotion_result(
        self,
        *,
        source: str,
        incident_ids: tuple[str, ...],
    ) -> None:
        """Delegate to :mod:`incident_promotion_accumulator_mutation`.

        ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
        the canonical implementation lives in
        :func:`record_promotion_result_mutation`.
        """
        record_promotion_result_mutation(
            self, source=source, incident_ids=incident_ids
        )


    def add_batch(self, batch: PromotionBatch) -> None:
        """Delegate to :mod:`incident_promotion_accumulator_mutation`.

        ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
        the canonical implementation lives in
        :func:`add_batch_mutation`. The R4 / R3 / R7 contracts
        are documented on the canonical implementation.
        """
        add_batch_mutation(self, batch)

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
        """Delegate to :mod:`incident_promotion_accumulator_projection`.

        ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
        the canonical implementation lives in
        :func:`has_promotion_activity`.
        """
        return has_promotion_activity(self)

    def aggregated_error_messages(self) -> tuple[str, ...]:
        """Delegate to :mod:`incident_promotion_accumulator_projection`.

        ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
        the canonical implementation lives in
        :func:`aggregated_error_messages`.
        """
        return aggregated_error_messages(self)

    @property
    def scoped_promotion_handoff(
        self,
    ) -> ScopedPromotionAccumulatorHandoff | None:
        """Delegate to :mod:`incident_promotion_accumulator_projection`.

        Derived projection of the single scoped recording
        authority. The canonical implementation lives in
        :func:`scoped_promotion_handoff_value`.
        """
        return scoped_promotion_handoff_value(self)

    @property
    def scoped_promotion_batch(self) -> PromotionBatch | None:
        """Delegate to :mod:`incident_promotion_accumulator_projection`.

        Derived projection of the single scoped recording
        authority. The canonical implementation lives in
        :func:`scoped_promotion_batch_projection`.
        """
        return scoped_promotion_batch_projection(self)

    @property
    def scoped_promotion_request_id(self) -> str:
        """Delegate to :mod:`incident_promotion_accumulator_projection`.

        Derived projection of the scoped recording authority's
        handoff. The canonical implementation lives in
        :func:`scoped_promotion_request_id_projection`.
        """
        return scoped_promotion_request_id_projection(self)

    @property
    def scoped_promotion_request_fingerprint(self) -> str:
        """Delegate to :mod:`incident_promotion_accumulator_projection`.

        Derived projection of the scoped recording authority's
        handoff. The canonical implementation lives in
        :func:`scoped_promotion_request_fingerprint_projection`.
        """
        return scoped_promotion_request_fingerprint_projection(self)

    def __setattr__(self, name: str, value: object) -> None:
        """Reject writes to derived scoped-recording projections.

        The canonical list of forbidden derived names is owned by
        :mod:`incident_promotion_accumulator_projection` so a
        future derived projection is added in exactly one place.
        """
        reject_derived_assignment(name, value)
        super().__setattr__(name, value)

    def record_scoped_promotion(
        self,
        handoff: ScopedPromotionAccumulatorHandoff,
    ) -> None:
        """Delegate to :mod:`incident_promotion_accumulator_compat`.

        ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
        the canonical implementation of the legacy compatibility
        wrapper lives in
        :func:`record_scoped_promotion_compat` so the active
        recorder API stays under the hard 500-line size cap.
        """
        record_scoped_promotion_compat(self, handoff)

    def scoped_promotion_handoff_value(
        self,
    ) -> ScopedPromotionAccumulatorHandoff | None:
        """Delegate to :mod:`incident_promotion_accumulator_projection`.

        ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
        derived projection of the scoped recording authority. The
        canonical implementation lives in
        :func:`scoped_promotion_handoff_value`.
        """
        return scoped_promotion_handoff_value(self)


    def as_dict(self) -> dict[str, object]:
        """Delegate to :mod:`incident_promotion_accumulator_projection`.

        ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
        the canonical implementation lives in :func:`as_dict`.
        """
        return as_dict(self)


__all__ = [
    "AccumulatorAccessModeError",
    "PromotionOutcomeConflictError",
    "PromotionOutcomeRecording",
    "PromotionWorksetState",
    "RunPromotionAccumulator",
]
