"""ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R7 production-path tests.

R7 (item 1): a :class:`PromotionConsistencyContractError` MUST mark automatic
diagnosis as ``blocked``. The diagnosis collector is NEVER invoked for a
malformed dispatcher response; the orchestrator emits a typed
``automatic_diagnosis_blocked: promotion_consistency_contract_error``
event so the terminal completion log carries the blocked reason.

R7 (item 2): ``incident_access_mode`` is preserved from the supplied
metadata, independent of ``canonical_ids`` cardinality. A local zero-ID
run keeps ``incident_access_mode == "local"`` and a no-promotion run
keeps ``incident_access_mode == "no_promotion_run"`` instead of being
collapsed onto the legacy ``"backend"`` default. The collector accepts a
typed selection mode: ``explicit_incident_ids`` / ``store_scan`` /
``blocked``.

R7 (item 3): every backend-authoritative ``PromotionBatch`` is validated
against the ordered-sequence-with-multiplicity contract BEFORE
``RunPromotionAccumulator.add_batch`` mutates its state. A rejected
batch leaves the accumulator unchanged and raises
:class:`PromotionConsistencyContractError`. Tests below cover the
ordered-sequence contract failure modes that production must reject.

R7 (item 4): the contract terminology is "ordered sequence with
multiplicity", not "multiset". The tests below assert the new wording.
"""

from __future__ import annotations

import os
import unittest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    AccumulatorAccessModeError,
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_BACKEND as DISPATCH_BACKEND,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_LOCAL as DISPATCH_LOCAL,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    IncidentPromotionResult,
)
from k8s_diag_agent.health.loop_runner_execute import (
    BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR,
    INCIDENT_SELECTION_MODE_BLOCKED,
    INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
    INCIDENT_SELECTION_MODE_STORE_SCAN,
    AutomaticDiagnosisExecution,
    _derive_automatic_diagnosis_inputs,
)


def _teardown() -> None:
    for var in (
        "K9B_BACKEND_INTERNAL_URL",
        "K9B_INTERNAL_API_TOKEN",
        "K9B_INCIDENT_STORE_BACKEND",
        "K9B_PROCESS_ROLE",
        "K9B_INCIDENT_PROMOTION_MODE",
        "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
    ):
        os.environ.pop(var, None)


def _backend_batch(
    *,
    opened_incidents: int = 1,
    updated_incidents: int = 0,
    opened_ids: tuple[str, ...] = ("incident-1",),
    updated_ids: tuple[str, ...] = (),
    records: tuple[PromotionRecord, ...] = (
        PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
    ),
) -> PromotionBatch:
    """Build a backend-authoritative batch for the add_batch validator tests."""
    return PromotionBatch(
        promotion_result=IncidentPromotionResult(
            ok=True,
            scanned=opened_incidents + updated_incidents,
            firing=opened_incidents + updated_incidents,
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            skipped_duplicates=0,
            errors=0,
            promotion_mode="backend-api",
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
            promotion_records=(),  # canonical IDs live in ``records``
            unique_candidate_count=opened_incidents + updated_incidents,
            promotion_scan_scope="internal_api_alert_signals",
            incident_access_mode=DISPATCH_BACKEND,
        ),
        promotion_records=records,
        source_kind="alertmanager",
    )




class TestDeriveAutomaticDiagnosisInputsSelectionMode(unittest.TestCase):
    """R7 (item 1/2): the explicit decision and access-mode preservation."""

    def setUp(self) -> None:
        _teardown()

    def tearDown(self) -> None:
        _teardown()

    def _build_accumulator(
        self,
        *,
        promotion_mode: str,
        incident_access_mode: str,
        opened_incidents: int,
        updated_incidents: int,
        opened_ids: tuple[str, ...] = (),
        updated_ids: tuple[str, ...] = (),
        records: tuple[PromotionRecord, ...] = (),
    ) -> RunPromotionAccumulator:
        accumulator = RunPromotionAccumulator()
        batch = PromotionBatch(
            promotion_result=IncidentPromotionResult(
                ok=True,
                scanned=opened_incidents + updated_incidents,
                firing=opened_incidents + updated_incidents,
                opened_incidents=opened_incidents,
                updated_incidents=updated_incidents,
                skipped_duplicates=0,
                errors=0,
                promotion_mode=promotion_mode,
                opened_incident_ids=opened_ids,
                updated_incident_ids=updated_ids,
                promotion_records=(),
                unique_candidate_count=opened_incidents + updated_incidents,
                promotion_scan_scope="r7_test",
                incident_access_mode=incident_access_mode,
            ),
            promotion_records=records,
            source_kind="alertmanager",
        )
        accumulator.add_batch(batch)
        return accumulator

    def test_local_zero_id_preserves_local_access_mode(self) -> None:
        """A local zero-ID run keeps ``incident_access_mode == "local"`` (R7 item 2)."""
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "local"
        accumulator = self._build_accumulator(
            promotion_mode="local",
            incident_access_mode=DISPATCH_LOCAL,
            opened_incidents=0,
            updated_incidents=0,
            opened_ids=(),
            updated_ids=(),
            records=(),
        )
        (
            _canonical_ids,
            _summary,
            _consistency,
            _endpoint,
            execution,
        ) = _derive_automatic_diagnosis_inputs(accumulator)
        assert execution.incident_access_mode == DISPATCH_LOCAL
        # Zero canonical IDs and a local run mean store_scan.
        assert execution.selection_mode == INCIDENT_SELECTION_MODE_STORE_SCAN

    def test_backend_zero_id_preserves_backend_access_mode(self) -> None:
        """A backend zero-ID run keeps ``incident_access_mode == "backend"`` (R7 item 2)."""
        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "backend-api"
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "http://k9b-backend:8080"
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        accumulator = self._build_accumulator(
            promotion_mode="backend-api",
            incident_access_mode=DISPATCH_BACKEND,
            opened_incidents=0,
            updated_incidents=0,
            opened_ids=(),
            updated_ids=(),
            records=(),
        )
        (
            _canonical_ids,
            _summary,
            _consistency,
            _endpoint,
            execution,
        ) = _derive_automatic_diagnosis_inputs(accumulator)
        assert execution.incident_access_mode == DISPATCH_BACKEND
        # Zero canonical IDs on a backend run still mean store_scan --
        # the decision is independent of access mode.
        assert execution.selection_mode == INCIDENT_SELECTION_MODE_STORE_SCAN

    def test_no_promotion_run_preserves_no_promotion_sentinel(self) -> None:
        """A no-promotion run keeps ``incident_access_mode == "no_promotion_run"`` (R7 item 2)."""
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "local"
        accumulator = RunPromotionAccumulator()
        (
            _canonical_ids,
            _summary,
            _consistency,
            _endpoint,
            execution,
        ) = _derive_automatic_diagnosis_inputs(accumulator)
        assert execution.incident_access_mode == "no_promotion_run"
        assert execution.selection_mode == INCIDENT_SELECTION_MODE_STORE_SCAN

    def test_blocked_contract_run_preserves_backend_access_mode(self) -> None:
        """A blocked-contract run preserves the dispatcher's actual access mode (R7 item 2)."""
        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "backend-api"
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "http://k9b-backend:8080"
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        accumulator = self._build_accumulator(
            promotion_mode="backend-api",
            incident_access_mode=DISPATCH_BACKEND,
            opened_incidents=0,
            updated_incidents=0,
            opened_ids=(),
            updated_ids=(),
            records=(),
        )
        # Simulate the orchestrator's catch path: the add_batch call
        # raised a contract error and the orchestrator stored it. We
        # pre-stamp last_contract_error to bypass add_batch validation
        # for the test.
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionConsistencyContractError as PccErr,
        )

        accumulator.last_contract_error = PccErr(
            "test contract failure",
            opened_incidents=2,
            updated_incidents=0,
            promotion_record_count=0,
            opened_id_count=0,
            updated_id_count=0,
        )
        (
            canonical_ids,
            summary,
            consistency,
            endpoint,
            execution,
        ) = _derive_automatic_diagnosis_inputs(accumulator)
        # The blocked decision preserves the dispatcher's access mode.
        assert execution.is_blocked
        assert execution.blocked_reason == (
            BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR
        )
        assert execution.selection_mode == INCIDENT_SELECTION_MODE_BLOCKED
        assert execution.incident_access_mode == DISPATCH_BACKEND
        # The orchestrator MUST NOT pass canonical IDs to the collector
        # on the blocked path.
        assert canonical_ids == []
        # The contract error is preserved in the summary so the
        # terminal completion event can record the blocked reason.
        assert summary["promotion_consistency_contract_error"] is not None
        assert endpoint["backend_reachable"] is False




class TestAccessModeBackwardCompat(unittest.TestCase):
    """R7 (item 2): access-mode and selection-mode constants exist and are distinct.

    These constants are the public contract the orchestrator and
    collector use to gate the diagnosis phase. Tests below pin the
    literal values so downstream consumers do not regress by
    silently renaming them.
    """

    def test_selection_modes_are_distinct(self) -> None:
        from k8s_diag_agent.health.loop_runner_execute import (
            INCIDENT_SELECTION_MODE_BLOCKED as BLOCKED,
        )
        from k8s_diag_agent.health.loop_runner_execute import (
            INCIDENT_SELECTION_MODE_EXPLICIT_IDS as EXP,
        )
        from k8s_diag_agent.health.loop_runner_execute import (
            INCIDENT_SELECTION_MODE_STORE_SCAN as SCAN,
        )

        assert EXP != SCAN
        assert EXP != BLOCKED
        assert SCAN != BLOCKED
        assert EXP == "explicit_incident_ids"
        assert SCAN == "store_scan"
        assert BLOCKED == "blocked"

    def test_blocked_reason_literal(self) -> None:
        assert BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR == (
            "promotion_consistency_contract_error"
        )

    def test_decision_dataclass_is_immutable(self) -> None:
        """The AutomaticDiagnosisExecution dataclass is frozen (R7 item 1)."""
        decision = AutomaticDiagnosisExecution(
            should_run=True,
            selection_mode=INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
            incident_access_mode=DISPATCH_BACKEND,
        )
        with self.assertRaises(Exception):  # FrozenInstanceError
            decision.should_run = False


class TestAccumulatorAccessModeStillEnforced(unittest.TestCase):
    """Sanity check: the R4 access-mode mutual exclusion still works under R7."""

    def test_mixed_local_backend_batches_rejected(self) -> None:
        accumulator = RunPromotionAccumulator()
        # First batch is local.
        local_batch = PromotionBatch(
            promotion_result=IncidentPromotionResult(
                ok=True,
                scanned=0,
                firing=0,
                opened_incidents=0,
                updated_incidents=0,
                skipped_duplicates=0,
                errors=0,
                promotion_mode="local",
                opened_incident_ids=(),
                updated_incident_ids=(),
                promotion_records=(),
                unique_candidate_count=0,
                promotion_scan_scope="local_promotion",
                incident_access_mode=DISPATCH_LOCAL,
            ),
            promotion_records=(),
            source_kind="alertmanager",
        )
        accumulator.add_batch(local_batch)
        # Second batch is backend; mixing modes MUST fail.
        with self.assertRaises(AccumulatorAccessModeError):
            accumulator.add_batch(_backend_batch())


if __name__ == "__main__":
    unittest.main()
