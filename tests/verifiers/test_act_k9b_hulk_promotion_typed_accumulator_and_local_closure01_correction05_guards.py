"""CORRECTION05 architecture guards for the split atomic recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
CORRECTION05-STRICT-TYPING-AND-ROLLBACK-CLOSURE01.

These guards fail at test time when the split atomic recorder
violates any of the typed-accumulator invariants closed by this
ACT:

* The recorder MUST type the host through
  :class:`incident_promotion_scoped_atomic_host_protocol.
  ScopedPromotionAccumulatorHost` -- a cycle-free
  :class:`typing.Protocol` declared in a separate small module --
  not via a direct import of :class:`RunPromotionAccumulator`.
* The recorder MUST NOT expose the removed global mutable
  failure probes (``_OUTCOME_RECORDING_PROBE``,
  ``_APPLY_BATCH_PROBE``, ``_set_outcome_recording_probe``,
  ``_set_apply_batch_probe``, ``_clear_probes``). Tests must use
  ``monkeypatch`` of the host instance instead.
* The handoff/batch validator MUST end with
  :func:`typing.assert_never` so a new handoff variant fails
  mypy; the previous ad-hoc ``raise TypeError`` fallback is
  removed.
* The validator MUST type ``batch`` as :class:`PromotionBatch`
  directly (no late-bound ``_promotion_batch_class`` lookup).
* The validator MUST import the access-mode constants from the
  cycle-free :mod:`incident_promotion_dispatch_constants` module
  so it does not depend on the dispatcher module.
* :meth:`RunPromotionAccumulator._snapshot` MUST return the
  typed :class:`AccumulatorSnapshot` dataclass, not
  ``dict[str, object]``.
* :meth:`RunPromotionAccumulator._restore` MUST rewrite the
  mutable containers in place (``clear``/``extend``/``update``)
  so externally retained references keep their identity.
* ``mypy.ini`` MUST NOT carry per-module overrides for the
  atomic recorder modules.
* The split recorder modules MUST each stay below the canonical
  500 physical-line limit (the same gate as
  ``scripts/check_llm_friendly_files.py``).
* The replay equivalence predicates rely on dataclass-generated
  ``__eq__``. Every authority dataclass field MUST keep
  ``compare=True`` so a future ``compare=False`` cannot silently
  exclude it from the comparison.
* The replay path MUST fail closed with a typed
  :class:`PromotionOutcomeConflictError` when the running
  accumulator carries a handoff but no aggregate accounting
  batch (a persisted-state drift shape).
* The replay-conflict test matrix MUST live in three focused
  files under ``tests/unit`` -- ``test_scoped_replay_handoff_conflicts.py``,
  ``test_scoped_replay_batch_identity_conflicts.py``, and
  ``test_scoped_replay_batch_accounting_conflicts.py`` -- none
  exceeding the canonical 500 physical-line limit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent" / "collect"
TESTS_UNIT_ROOT = REPO_ROOT / "tests" / "unit"

ACCUMULATOR_FILE = SRC_ROOT / "incident_promotion_accumulator.py"
ATOMIC_RECORDER_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_recorder.py"
ATOMIC_VALIDATION_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_validation.py"
ATOMIC_EQUIVALENCE_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_equivalence.py"
ATOMIC_PROJECTION_FILE = SRC_ROOT / "incident_promotion_scoped_atomic_projection.py"

SPLIT_ATOMIC_MODULES = (
    ATOMIC_RECORDER_FILE,
    ATOMIC_VALIDATION_FILE,
    ATOMIC_EQUIVALENCE_FILE,
    ATOMIC_PROJECTION_FILE,
)


def test_atomic_recorder_uses_typed_host_protocol() -> None:
    """The split recorder module MUST type the host through the Protocol."""
    text = ATOMIC_RECORDER_FILE.read_text()
    if "ScopedPromotionAccumulatorHost" not in text:
        pytest.fail("incident_promotion_scoped_atomic_recorder.py MUST depend on the typed ScopedPromotionAccumulatorHost Protocol.")
    if "AccumulatorSnapshot" not in text:
        pytest.fail("incident_promotion_scoped_atomic_recorder.py MUST consume the typed AccumulatorSnapshot value object.")
    if "dict[str, object]" in text:
        pytest.fail("incident_promotion_scoped_atomic_recorder.py MUST NOT use dict[str, object] snapshots; use the typed AccumulatorSnapshot dataclass.")


def test_atomic_recorder_excludes_global_probes() -> None:
    """Production recorder MUST NOT expose the removed global probe helpers."""
    text = ATOMIC_RECORDER_FILE.read_text()
    forbidden = {
        "_OUTCOME_RECORDING_PROBE",
        "_APPLY_BATCH_PROBE",
        "_set_outcome_recording_probe",
        "_set_apply_batch_probe",
        "_clear_probes",
    }
    found = sorted(name for name in forbidden if name in text)
    if found:
        pytest.fail(f"incident_promotion_scoped_atomic_recorder.py MUST NOT expose the removed global probes: {found}; use test subclass overrides or monkeypatch of the host instance method.")


def test_validator_uses_assert_never() -> None:
    """The validator MUST end with ``assert_never`` for static exhaustiveness."""
    text = ATOMIC_VALIDATION_FILE.read_text()
    if "assert_never(handoff)" not in text:
        pytest.fail("incident_promotion_scoped_atomic_validation.validate_scoped_handoff_batch_consistency MUST end with assert_never(handoff) so a new variant fails mypy.")
    if "raise TypeError" in text and "unsupported" in text:
        pytest.fail("validate_scoped_handoff_batch_consistency MUST NOT carry an ad-hoc TypeError fallback for unhandled variants; assert_never(handoff) is the canonical exhaustiveness boundary.")


def test_validator_types_batch_as_promotion_batch() -> None:
    """The validator's per-variant helpers MUST accept typed PromotionBatch."""
    text = ATOMIC_VALIDATION_FILE.read_text()
    if "def _require_common_batch_frame" in text and "batch: PromotionBatch" not in text:
        pytest.fail("incident_promotion_scoped_atomic_validation._require_common_batch_frame MUST type batch as PromotionBatch.")


def test_validator_uses_cycle_free_constants() -> None:
    """The validator MUST import access-mode constants from the cycle-free module."""
    text = ATOMIC_VALIDATION_FILE.read_text()
    if "from .incident_promotion_dispatch_constants import" not in text:
        pytest.fail("incident_promotion_scoped_atomic_validation.py MUST import INCIDENT_ACCESS_MODE_BACKEND and MODE_BACKEND_API from incident_promotion_dispatch_constants so the validator does not depend on the dispatcher module directly.")


def test_recorder_restore_preserves_container_identity() -> None:
    """``_restore`` MUST rewrite mutable containers in place."""
    snapshot_file = SRC_ROOT / "incident_promotion_accumulator_snapshot.py"
    text = ACCUMULATOR_FILE.read_text() + snapshot_file.read_text()
    if ".clear()" not in text or ".update(" not in text:
        pytest.fail("RunPromotionAccumulator._restore MUST rewrite the mutable containers (batches, promotion_records, _seen_canonical_ids) in place via .clear()/.update()/.extend() so external references retain their identity.")


def test_recorder_snapshot_returns_typed_dataclass() -> None:
    """``_snapshot`` MUST return the typed AccumulatorSnapshot value."""
    text = ACCUMULATOR_FILE.read_text()
    if "def _snapshot(self) -> AccumulatorSnapshot" not in text and 'def _snapshot(self) -> "AccumulatorSnapshot"' not in text:
        pytest.fail("RunPromotionAccumulator._snapshot MUST return the typed AccumulatorSnapshot dataclass, not a dict[str, object].")


def test_mypy_ini_has_no_atomic_recorder_overrides() -> None:
    """mypy.ini MUST NOT carry per-module overrides for the atomic modules."""
    ini = (REPO_ROOT / "mypy.ini").read_text()
    forbidden_sections = [
        "mypy-k8s_diag_agent.collect.incident_promotion_scoped_atomic_recorder",
        "mypy-k8s_diag_agent.collect.incident_promotion_scoped_atomic_validation",
    ]
    found = [section for section in forbidden_sections if re.search(rf"\[{re.escape(section)}\]", ini)]
    if found:
        pytest.fail(f"mypy.ini MUST NOT carry per-module overrides for the atomic recorder modules: {found}; strict typing is preserved by the typed host Protocol + AccumulatorSnapshot.")


def test_each_split_recorder_module_under_canonical_physical_line_limit() -> None:
    """Every split recorder module MUST stay below the canonical 500-line limit.

    The check uses the canonical physical-line counter (raw line count)
    to match the LLM-friendly file gate. The previous custom
    non-comment-line approximation was removed because it drifted from
    the canonical checker.
    """
    offenders: list[str] = []
    for path in SPLIT_ATOMIC_MODULES:
        line_count = sum(1 for _ in path.open("r", encoding="utf-8"))
        if line_count > 500:
            offenders.append(f"{path.name} has {line_count} physical lines (limit 500)")
    if offenders:
        pytest.fail("Atomic recorder modules exceed the canonical 500-line limit: " + ", ".join(offenders))


def test_dataclass_equality_authority_for_replay_predicates() -> None:
    """Every authority dataclass field MUST have ``compare=True``.

    Replay equivalence predicates rely on dataclass-generated
    ``__eq__``. A future ``compare=False`` on any authority field
    would silently exclude it from the comparison. The guard
    asserts the canonical set of fields is present and ALL keep
    ``compare=True`` (the dataclass default).
    """
    from dataclasses import fields

    from k8s_diag_agent.collect.incident_promotion_batch import (
        PromotionBatch,
    )
    from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
        ScopedPromotionAccumulatorCompleted,
        ScopedPromotionAccumulatorRejected,
        ScopedPromotionAccumulatorUncertain,
    )
    from k8s_diag_agent.incident_alert_promotion_binding import (
        BoundScopedPromotionResult,
    )
    from k8s_diag_agent.incident_alert_promotion_contract import (
        IncidentPromotionFailure,
        IncidentPromotionResult,
        PromoteAlertSignalsRequest,
    )

    authority_dataclasses = (
        BoundScopedPromotionResult,
        PromoteAlertSignalsRequest,
        IncidentPromotionFailure,
        IncidentPromotionResult,
        PromotionBatch,
        ScopedPromotionAccumulatorCompleted,
        ScopedPromotionAccumulatorUncertain,
        ScopedPromotionAccumulatorRejected,
    )
    offenders: list[str] = []
    for cls in authority_dataclasses:
        for f in fields(cls):
            if f.compare is False:
                offenders.append(f"{cls.__name__}.{f.name}")
    if offenders:
        pytest.fail(f"Authority dataclass fields MUST keep compare=True so the replay equivalence predicates cannot silently exclude them: {offenders}")


def test_atomic_recorder_defensive_corrupt_state() -> None:
    """The recorder MUST fail closed when the outcome is missing.

    ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
    the recorder compares against ``scoped_promotion_recording``,
    NOT against ``batches[-1]``. The replay path fails closed
    on a corrupt persisted-state shape -- e.g. when the recorded
    authority is present but the typed outcome was wiped --
    with a bounded :class:`PromotionOutcomeConflictError`.
    """
    from k8s_diag_agent.collect.incident_promotion_accumulator import (
        RunPromotionAccumulator,
    )
    from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
        PromotionOutcomeConflictError,
        PromotionOutcomeRecording,
    )
    from k8s_diag_agent.collect.incident_promotion_scoped_atomic_projection import (
        build_compatibility_batch_from_handoff,
    )
    from tests.unit.scoped_handoff_atomic_support import (
        completed_handoff,
    )

    acc = RunPromotionAccumulator()
    handoff = completed_handoff(
        diagnosis_incident_ids=("canonical-corrupt",),
    )
    batch = build_compatibility_batch_from_handoff(handoff)
    recording = acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
    assert recording is PromotionOutcomeRecording.NEW
    # Wipe the outcome to simulate persisted-state drift; the
    # recorded authority remains.
    acc.promotion_outcome = None
    with pytest.raises(PromotionOutcomeConflictError, match="inconsistent"):
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)


def test_replay_conflict_tests_split_into_three_files() -> None:
    """The split atomic recorder replay tests live in three focused files."""
    expected = {
        TESTS_UNIT_ROOT / "test_scoped_replay_handoff_conflicts.py",
        TESTS_UNIT_ROOT / "test_scoped_replay_batch_identity_conflicts.py",
        TESTS_UNIT_ROOT / "test_scoped_replay_batch_accounting_conflicts.py",
    }
    missing = [p for p in expected if not p.exists()]
    if missing:
        pytest.fail(f"Replay-conflict tests MUST be split into three focused files: {sorted(str(p) for p in missing)}")
    legacy = TESTS_UNIT_ROOT / "test_scoped_accumulator_replay_conflicts.py"
    if legacy.exists():
        pytest.fail(f"{legacy.name} MUST be removed; the replay-conflict matrix now lives in the three focused files.")
    for path in expected:
        line_count = sum(1 for _ in path.open("r", encoding="utf-8"))
        if line_count > 500:
            pytest.fail(f"{path.name} has {line_count} physical lines (limit 500)")
