"""Self-tests for the ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 verifier.

The static verifier at
``scripts/verifiers/incident_current_run_promotion_workset01.py``
must PASS against the current production tree and every
negative fixture below MUST trigger at least one violation. The
self-tests are the verifier's only consumer: a green run against
the production tree is meaningful only when the detectors are
provably non-trivial.

R3 contract: every critical wiring detector declared in the
verifier has a paired negative fixture that proves the detector
is non-trivial. Removing the production sentinel detected by the
detector (or replacing it with a lookalike) MUST cause the
verifier to emit at least one violation when run against the
fixture.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_VERIFIER_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "verifiers"
    / "incident_current_run_promotion_workset01.py"
)


def _load_verifier() -> Any:
    spec = importlib.util.spec_from_file_location(
        "icr_workset01_verifier", _VERIFIER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier: Any = _load_verifier()


def _write_tmp(source: str) -> Path:
    path = Path("/tmp") / f"icr_workset01_{abs(hash(source))}.py"
    path.write_text(source)
    return path


class TestProductionPasses:
    def test_run_static_checks_is_clean(self) -> None:
        violations = verifier.run_static_checks()
        assert violations == [], f"unexpected violations: {violations}"

    def test_main_returns_zero(self) -> None:
        assert verifier.main([]) == 0


# ---------------------------------------------------------------------------
# Ingestion detector fixtures
# ---------------------------------------------------------------------------


class TestIngestionScopedPromotionDetector:
    def test_legacy_promotion_path_is_rejected(self) -> None:
        """Scheduler that still uses promote_alert_signals_for_accumulator."""
        src = (
            "def _ingest():\n"
            "    promote_alert_signals_for_accumulator(\n"
            "        runs_dir=runs_dir,\n"
            "        accumulator=None,\n"
            "    )\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_ingestion_uses_scoped_promotion(
                tree, path
            )
            assert violations
            assert any("scoped" in v for v in violations)
        finally:
            path.unlink()

    def test_global_scan_fallback_is_rejected(self) -> None:
        """A scheduler that calls scan_alert_signals_as_candidates."""
        src = (
            "def _ingest():\n"
            "    promote_alert_signals_scoped_for_accumulator(\n"
            "        runs_dir=runs_dir,\n"
            "        health_run_id=run_id,\n"
            "        source_identity=source,\n"
            "        signal_ids=ids,\n"
            "        accumulator=None,\n"
            "    )\n"
            "    return scan_alert_signals_as_candidates(runs_dir)\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_ingestion_forbids_global_scan_fallback(
                tree, path
            )
            assert violations
        finally:
            path.unlink()

    def test_missing_current_run_scope_log_is_rejected(self) -> None:
        """Scheduler log without promotion_scope=explicit_current_run_signal_ids."""
        src = (
            "def _ingest():\n"
            "    log_event('alert-signals-promoted', scope='legacy')\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_ingestion_logs_explicit_current_run_scope(
                tree, path
            )
            assert violations
        finally:
            path.unlink()

    def test_missing_artifact_identity_is_rejected(self) -> None:
        """Scheduler that does not extract artifact_identity."""
        src = (
            "def _ingest():\n"
            "    for persisted in written_signals:\n"
            "        ids.append(str(persisted.signal.signal_id))\n"
            "    return ids\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_ingestion_uses_artifact_identity(
                tree, path
            )
            assert violations
        finally:
            path.unlink()

    def test_signal_signal_id_usage_is_rejected(self) -> None:
        """Scheduler that still passes str(signal.signal_id) to the backend."""
        src = (
            "def _ingest():\n"
            "    for persisted in written_signals:\n"
            "        artifact_identity = persisted.artifact_identity\n"
            "        ids.append(str(persisted.signal.signal_id))\n"
            "    return ids\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_ingestion_uses_artifact_identity(
                tree, path
            )
            assert violations
        finally:
            path.unlink()

    def test_missing_dict_fromkeys_dedup_is_rejected(self) -> None:
        """Scheduler that does not stable-deduplicate via dict.fromkeys(...)."""
        src = (
            "def _ingest():\n"
            "    artifact_identity = persisted.artifact_identity\n"
            "    return [str(persisted.artifact_identity) for persisted in written_signals]\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = (
                verifier.check_ingestion_stable_deduplicates_artifact_workset(
                    tree, path
                )
            )
            assert violations
        finally:
            path.unlink()

    def test_dict_fromkeys_dedup_is_accepted(self) -> None:
        """The canonical stable-deduplication pattern is accepted."""
        src = (
            "def _ingest():\n"
            "    ids = list(dict.fromkeys(\n"
            "        str(persisted.artifact_identity) for persisted in written_signals\n"
            "    ))\n"
            "    return ids\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = (
                verifier.check_ingestion_stable_deduplicates_artifact_workset(
                    tree, path
                )
            )
            assert violations == []
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# Scoped promotion detector fixtures
# ---------------------------------------------------------------------------


class TestScopedPromotionDetector:
    def test_empty_scope_short_circuit_is_required(self) -> None:
        src = (
            "from .incident_alert_promotion_contract import IncidentPromotionResult\n"
            "def promote():\n"
            "    return IncidentPromotionResult()\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = (
                verifier.check_scoped_promotion_handles_empty_scope(
                    tree, path
                )
            )
            assert violations
            assert any("empty request.signal_ids" in v for v in violations)
        finally:
            path.unlink()

    def test_actionable_projection_is_required(self) -> None:
        src = "def promote():\n    return list(range(10))\n"
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = (
                verifier.check_scoped_promotion_owns_actionable_projection(
                    tree, path
                )
            )
            assert violations
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# Handler / backend client detector fixtures
# ---------------------------------------------------------------------------


class TestHandlerDetector:
    def test_legacy_request_parser_is_rejected(self) -> None:
        src = (
            "from .server_incident_internal_models import (\n"
            "    PromoteAlertSignalsRequest,\n"
            ")\n"
            "def handle():\n"
            "    request = PromoteAlertSignalsRequest.from_dict(data)\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_handler_rejects_missing_scope(
                tree, path
            )
            assert violations
        finally:
            path.unlink()

    def test_missing_promote_scoped_call_is_rejected(self) -> None:
        """Handler that does not call promote_scoped_alert_signals."""
        src = "def handle():\n    return None\n"
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_handler_uses_scoped_promotion_call(
                tree, path
            )
            assert violations
        finally:
            path.unlink()

    def test_missing_promote_alert_signals_scoped_client_is_rejected(self) -> None:
        """SchedulerClient without promote_alert_signals_scoped()."""
        src = "class SchedulerClient:\n    def promote_candidates(self):\n        return None\n"
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_backend_client_exposes_scoped_call(
                tree, path
            )
            assert violations
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# Backend adapter / contract detector fixtures
# ---------------------------------------------------------------------------


class TestBackendAdapterDetector:
    def test_missing_camel_case_wire_parse_is_rejected(self) -> None:
        """Backend adapter that does not parse the camelCase payload."""
        src = (
            "def _response_to_promotion_result(response):\n"
            "    return {'ok': True}\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_backend_adapter_parses_camel_case_wire(
                tree, path
            )
            assert violations
        finally:
            path.unlink()

    def test_contract_missing_from_wire_dict_is_rejected(self) -> None:
        """Contract that does not expose from_wire_dict or scannedSignalIds."""
        src = (
            "def some_helper():\n"
            "    return 1\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_contract_exposes_wire_parser(
                tree, path
            )
            assert violations
        finally:
            path.unlink()


class TestSnapshotAdapterDetector:
    def test_persist_missing_persisted_alert_signal_is_rejected(self) -> None:
        """persist_alert_signals that does not return PersistedAlertSignal."""
        src = (
            "def persist_alert_signals(signals, root):\n"
            "    return None, list(signals)\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = (
                verifier.check_persist_alert_signals_returns_artifact_identity(
                    tree, path
                )
            )
            assert violations
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# Processor / batch / budget detector fixtures
# ---------------------------------------------------------------------------


class TestProcessorDetector:
    def test_missing_record_successful_write_is_rejected(self) -> None:
        src = (
            "def _process_incident():\n"
            "    if budget.can_attempt():\n"
            "        write_diagnosis_review_packet(...)\n"
            "    return result\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_processor_records_successful_writes_only(
                tree, path
            )
            assert violations
        finally:
            path.unlink()

    def test_budget_consumption_before_successful_persistence_is_rejected(
        self,
    ) -> None:
        """Processor that records the budget inside a ``finally`` block.

        The R3 invariant is: a budget unit MUST be consumed only on a
        successful write. Recording the budget inside a ``finally``
        block consumes the unit even when the write fails.
        """
        src = (
            "def _process_incident():\n"
            "    try:\n"
            "        if budget.can_attempt():\n"
            "            write_diagnosis_review_packet(...)\n"
            "    finally:\n"
            "        budget.record_successful_write()\n"
            "    return result\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_processor_records_successful_writes_only(
                tree, path
            )
            assert violations
        finally:
            path.unlink()

    def test_missing_can_attempt_before_write_is_rejected(self) -> None:
        src = (
            "def _process_incident():\n"
            "    budget.record_successful_write()\n"
            "    write_diagnosis_review_packet(...)\n"
            "    return result\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = (
                verifier.check_processor_checks_budget_before_packet_write(
                    tree, path
                )
            )
            assert violations
        finally:
            path.unlink()

    def test_processor_not_passing_budget_to_eligibility_is_rejected(self) -> None:
        """Processor that drops the budget on its way to eligibility."""
        src = (
            "def _process_incident(\n"
            "    *, review_packet_budget=None, **_kwargs,\n"
            "):\n"
            "    eligible = evaluate_incident_eligibility(\n"
            "        incident_id='inc-1', config=config,\n"
            "    )\n"
            "    return eligible\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_processor_uses_budget_for_eligibility(
                tree, path
            )
            assert violations
        finally:
            path.unlink()


class TestBatchDetector:
    def test_batch_not_forwarding_budget_is_rejected(self) -> None:
        """Batch that does not forward the shared budget to _process_incident."""
        src = (
            "def process_incident_batch(\n"
            "    *, review_packet_budget=None, **_kwargs,\n"
            "):\n"
            "    for incident_id in all_scanned_ids:\n"
            "        _process_incident(\n"
            "            incident_id=incident_id,\n"
            "            config=config,\n"
            "        )\n"
            "    return outcome\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_batch_forwards_budget_to_processor(
                tree, path
            )
            assert violations
        finally:
            path.unlink()


class TestBudgetDetector:
    def test_budget_not_keyed_by_collector_run_id_is_rejected(self) -> None:
        src = "class ReviewPacketCreationBudget:\n    def __init__(self, limit):\n        self.limit = limit\n"
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = verifier.check_budget_keyed_by_collector_run_identity(
                tree, path
            )
            assert violations
        finally:
            path.unlink()

    def test_budget_using_forbidden_source_label_is_rejected(self) -> None:
        """Budget reconstruction that still uses review_packet_artifacts."""
        src = (
            "def reconstruct_budget_from_existing_packets(\n"
            "    collector_run_id, limit, external_analysis_dir,\n"
            "):\n"
            "    return ReviewPacketCreationBudget(\n"
            "        collector_run_id=collector_run_id,\n"
            "        limit=limit,\n"
            "    )\n"
            "def _some_helper():\n"
            "    return 'review_packet_artifacts'\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = (
                verifier.check_budget_reconstruction_filters_by_exact_collector_id(
                    tree, path
                )
            )
            assert violations
        finally:
            path.unlink()

    def test_budget_reconstruction_using_run_id_prefix_is_rejected(self) -> None:
        """Budget reconstruction that keys on run_id prefix."""
        src = (
            "def reconstruct_budget_from_existing_packets(\n"
            "    collector_run_id, limit, external_analysis_dir,\n"
            "):\n"
            "    budget = ReviewPacketCreationBudget(\n"
            "        collector_run_id=collector_run_id,\n"
            "        limit=limit,\n"
            "    )\n"
            "    for path in external_analysis_dir.rglob('*.json'):\n"
            "        if path.name.startswith(collector_run_id.run_id):\n"
            "            budget.record_successful_write()\n"
            "    return budget\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = (
                verifier.check_budget_reconstruction_filters_by_exact_collector_id(
                    tree, path
                )
            )
            assert violations
        finally:
            path.unlink()


class TestCollectorDetector:
    def test_collector_not_instantiating_budget_is_rejected(self) -> None:
        src = (
            "def run_automatic_diagnosis_loop_evidence_collection():\n"
            "    return AutoLoopCollectorResult()\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = (
                verifier.check_collector_instantiates_review_packet_budget(
                    tree, path
                )
            )
            assert violations
        finally:
            path.unlink()


class TestEligibilityDetector:
    def test_eligibility_consulting_filesystem_first_is_rejected(self) -> None:
        """Evaluator that consults the filesystem count before the budget."""
        src = (
            "def evaluate_incident_eligibility(\n"
            "    *, review_packet_budget=None,\n"
            "):\n"
            "    count = _count_files(external_analysis_dir)\n"
            "    return count < limit\n"
        )
        path = _write_tmp(src)
        try:
            tree = verifier._parse(path)
            violations = (
                verifier.check_eligibility_bypasses_historical_count_when_budget_present(
                    tree, path
                )
            )
            assert violations
        finally:
            path.unlink()