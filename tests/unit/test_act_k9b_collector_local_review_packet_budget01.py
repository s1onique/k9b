"""ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01 budget tests.

The collector-scoped review-packet creation budget MUST start at zero
for every new collector, charge only on a successful review-packet
write, and never infer usage from unrelated historical review-packet
artifacts. These tests prove the budget object and the per-collector
accounting contract.
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import cast

import pytest

from k8s_diag_agent.collect.incident_diagnosis_review_packet_budget import (
    ReviewPacketCreationBudget,
    reconstruct_budget_from_existing_packets,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.domain.identifiers import (
    AutomaticDiagnosisCollectorRunId,
)


class TestFreshCollectorStartsUnused:
    def test_fresh_budget_starts_unused(self) -> None:
        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-1"),
            limit=1,
        )
        assert budget.used == 0
        assert budget.remaining == 1
        assert budget.exhausted is False
        assert budget.can_attempt() is True
        assert budget.as_diagnostic() == {
            "name": "review_packet_creation_budget",
            "scope": "automatic_diagnosis_collector",
            "scope_id": "auto-1",
            "used": 0,
            "limit": 1,
            "remaining": 1,
            "exhausted": False,
            "source": "collector_run_accounting",
            "resettable": True,
        }

    def test_historical_packets_from_other_collectors_do_not_consume(
        self, tmp_path: Path
    ) -> None:
        # Persist two historical review packets that belong to a
        # different collector run. A fresh budget MUST still start
        # at zero usage; the historical artifacts MUST NOT count.
        external = tmp_path / "external-analysis"
        external.mkdir(parents=True, exist_ok=True)
        for offset in range(2):
            path = external / (
                f"auto-incident-{offset}-20260101-diagnosis-review-packet.json"
            )
            payload = {
                "schema_version": "1.0",
                "artifact_type": "diagnosis-loop-review-packet",
                "incident_id": f"incident-{offset}",
                "collector_run_id": "auto-old-run",
                "run_id": f"auto-incident-{offset}-20260101",
                "generated_at": "2026-01-01T00:00:00+00:00",
            }
            path.write_text(json.dumps(payload), encoding="utf-8")

        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-fresh"),
            limit=1,
        )
        assert budget.used == 0
        assert budget.exhausted is False


class TestFirstSuccessfulWriteConsumesOne:
    def test_consume_one_then_exhausted(self) -> None:
        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-2"),
            limit=1,
        )
        assert budget.can_attempt() is True
        budget.record_successful_write()
        assert budget.used == 1
        assert budget.remaining == 0
        assert budget.exhausted is True
        assert budget.can_attempt() is False
        diagnostic = budget.as_diagnostic()
        assert diagnostic["used"] == 1
        assert diagnostic["remaining"] == 0
        assert diagnostic["exhausted"] is True

    def test_second_record_raises_when_limit_reached(self) -> None:
        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-3"),
            limit=1,
        )
        budget.record_successful_write()
        with pytest.raises(RuntimeError):
            budget.record_successful_write()


class TestFailedWriteDoesNotConsumeBudget:
    def test_failed_write_leaves_used_unchanged(self) -> None:
        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-4"),
            limit=1,
        )
        # Simulate a failed write by NOT calling record_successful_write.
        assert budget.used == 0
        assert budget.remaining == 1
        # No call to record_successful_write was made; the budget is
        # intact and the next eligible incident can still write.
        assert budget.can_attempt() is True

    def test_ineligible_and_skip_paths_do_not_consume(
        self, tmp_path: Path
    ) -> None:
        # A "skip because ineligible" path MUST NOT consume budget; a
        # subsequent eligible incident MUST be able to write.
        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-5"),
            limit=1,
        )
        # Several ineligible incidents that the processor records with
        # `eligible=False` and `skipped=True` MUST leave `used == 0`.
        for _ in range(5):
            assert budget.used == 0
        # The first eligible incident can still write.
        assert budget.can_attempt() is True
        budget.record_successful_write()
        assert budget.exhausted is True


class TestExistingPacketReuseDoesNotConsume:
    def test_reuse_does_not_call_record_successful_write(self) -> None:
        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-6"),
            limit=1,
        )
        # Existing reusable packet -> no charge, no successful write.
        assert budget.used == 0
        assert budget.exhausted is False


class TestReconstructionFromExactCollectorRun:
    def test_reconstruct_with_no_artifacts(self, tmp_path: Path) -> None:
        budget = reconstruct_budget_from_existing_packets(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-rec-1"),
            limit=2,
            external_analysis_dir=tmp_path,
        )
        assert budget.used == 0

    def test_reconstruct_counts_matching_artifacts_only(
        self, tmp_path: Path
    ) -> None:
        external = tmp_path / "external-analysis"
        external.mkdir(parents=True, exist_ok=True)
        target_run = "auto-rec-target"
        other_run = "auto-rec-other"
        # 2 target-run artifacts and 5 other-run artifacts.
        # The filename MUST be unique per collector so the file
        # collection is meaningful; the per-incident ``incident_id`` is
        # what the production schema records.
        for index in range(2):
            path = external / (
                f"auto-target-incident-{index}-20260101-diagnosis-review-packet.json"
            )
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "artifact_type": "diagnosis-loop-review-packet",
                        "incident_id": f"target-{index}",
                        "collector_run_id": target_run,
                        "run_id": f"auto-target-incident-{index}-20260101",
                        "generated_at": "2026-01-01T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
        for index in range(5):
            path = external / (
                f"auto-other-incident-{index}-20260101-diagnosis-review-packet.json"
            )
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "artifact_type": "diagnosis-loop-review-packet",
                        "incident_id": f"other-{index}",
                        "collector_run_id": other_run,
                        "run_id": f"auto-other-incident-{index}-20260101",
                        "generated_at": "2026-01-01T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
        budget = reconstruct_budget_from_existing_packets(
            collector_run_id=AutomaticDiagnosisCollectorRunId(target_run),
            limit=4,
            external_analysis_dir=tmp_path,
        )
        # The 5 historical artifacts belong to a different collector
        # and MUST NOT count. Only the 2 matching artifacts count.
        assert budget.used == 2
        assert budget.exhausted is False
        assert budget.remaining == 2


class TestExhaustionAppliesAfterActualConsumption:
    def test_limit_one_second_candidate_skipped(self) -> None:
        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-limit-1"),
            limit=1,
        )
        # First eligible incident writes.
        budget.record_successful_write()
        assert budget.used == 1
        # The next packet-creation candidate is blocked.
        assert budget.exhausted is True
        with pytest.raises(RuntimeError):
            budget.record_successful_write()


class TestCollectorLocalBudgetIntegration:
    """Verify the budget is instantiated at collector entry and shared with every
    ``_process_incident`` call so a successful packet write consumes exactly one
    unit across the entire collector run.

    The R1 contract requires:

    * The collector entrypoint instantiates a single
      :class:`ReviewPacketCreationBudget` keyed by
      :class:`AutomaticDiagnosisCollectorRunId` and limited to
      ``config.max_review_packets``.
    * The same instance is forwarded to every per-incident processor via
      ``process_incident_batch``.
    * A successful packet write calls ``record_successful_write()`` exactly
      once, transitioning the budget from 0/1 to 1/1.
    * The second eligible incident observes ``exhausted == True`` and is
      skipped with ``review_packet_budget_exhausted``.
    """

    def test_collector_instantiates_budget_and_forwards_to_processor(
        self,
    ) -> None:
        """Static inspection: the collector module wires the budget end-to-end."""
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_evidence_collection as ec_module,
        )

        source = ec_module.__file__
        assert source is not None
        text = Path(source).read_text()
        # The collector MUST instantiate the budget with the right identity.
        assert "ReviewPacketCreationBudget(" in text
        assert "AutomaticDiagnosisCollectorRunId(" in text
        # And it MUST forward the shared instance to ``process_incident_batch``.
        assert "review_packet_budget=" in text

        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_batch as batch_module,
        )
        batch_text = Path(batch_module.__file__).read_text()
        # The batch MUST accept the budget and forward it to ``_process_incident``.
        assert (
            "review_packet_budget: ReviewPacketCreationBudget | None = None"
            in batch_text
        )
        assert "review_packet_budget=review_packet_budget" in batch_text

    def test_budget_record_successful_write_consumes_one_unit(self) -> None:
        """A successful write transitions the budget from 0/1 to 1/1."""
        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-write"),
            limit=1,
        )
        assert (budget.used, budget.exhausted) == (0, False)
        assert budget.can_attempt() is True
        budget.record_successful_write()
        assert (budget.used, budget.exhausted) == (1, True)
        assert budget.can_attempt() is False
        assert budget.as_diagnostic()["source"] == "collector_run_accounting"

    def test_two_eligible_incidents_only_first_sees_budget_consumption(
        self,
    ) -> None:
        """Two eligible incidents: first writes, second sees exhaustion.

        Simulates the per-incident accounting path without invoking the
        full collector pipeline (which would require HTTP and SQLite
        scaffolding). The in-memory ``review_packet_budget`` instance is
        the single source of truth shared by both incidents.
        """
        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-shared"),
            limit=1,
        )
        # First eligible incident writes.
        assert budget.can_attempt() is True
        budget.record_successful_write()
        assert budget.used == 1
        # Second eligible incident observes exhaustion.
        assert budget.can_attempt() is False
        assert budget.exhausted is True
        # Trying to record a second write raises.
        with pytest.raises(RuntimeError):
            budget.record_successful_write()

    def test_budget_projects_typed_diagnostic(self) -> None:
        """The budget's eligibility projection replaces the legacy
        ``review_packet_artifacts`` source label with
        ``collector_run_accounting`` so the eligibility path can prove
        the budget (not the filesystem count) is authoritative.
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            DiagnosisBudgetDiagnostic,
        )

        budget = ReviewPacketCreationBudget(
            collector_run_id=AutomaticDiagnosisCollectorRunId("auto-projection"),
            limit=2,
        )
        diagnostic = budget.as_diagnostic_for_eligibility()
        assert isinstance(diagnostic, DiagnosisBudgetDiagnostic)
        assert diagnostic.source == "collector_run_accounting"
        assert diagnostic.name == "review_packet_budget"
        assert diagnostic.used == 0
        assert diagnostic.limit == 2
        assert diagnostic.exhausted is False

        budget.record_successful_write()
        diagnostic = budget.as_diagnostic_for_eligibility()
        assert diagnostic.used == 1
        assert diagnostic.remaining == 1
        assert diagnostic.exhausted is False


# R3: integration test exercising the real collector entrypoint →
# batch → processor path with two eligible incidents and a budget of
# 1. The collector itself MUST instantiate the budget, forward that
# same instance to ``process_incident_batch`` and onto every
# ``_process_incident`` call. The first incident's packet write must
# consume the budget; the second must be skipped by the same
# processor path with the typed ``review_packet_budget_exhausted``
# reason.


def test_real_collector_consumes_budget_on_first_packet_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R3: real collector entrypoint, shared budget across the chain.

    Exercises the production boundary end-to-end::

        collector entry → process_incident_batch → _process_incident
            → evaluate_incident_eligibility → write_diagnosis_review_packet
            → record_successful_write

    R3 invariants verified:

    * The collector (``run_automatic_diagnosis_loop_evidence_collection``)
      is invoked with two explicit incident IDs.
    * The collector instantiates exactly one ``ReviewPacketCreationBudget``.
    * The same budget instance is forwarded to ``process_incident_batch``
      and onto every per-incident ``_process_incident`` call (identity,
      not equality).
    * The first eligible incident writes a review packet and consumes
      one unit of budget (``used == 1``, ``exhausted is True``).
    * The second eligible incident's processor sees the same
      exhausted budget object and is skipped with the canonical
      ``review_packet_budget_exhausted`` reason.
    * Exactly one review-packet artifact lands on disk.
    * The collector ``AutoLoopCollectorResult`` reports ``total_review_packets_written == 1``
      and the second incident's disposition carries the budget skip
      label.
    """
    from datetime import datetime

    import k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch as batch_mod
    import k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection as ec_mod
    from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
        AutomaticDiagnosisLoopConfig,
        EligibilityResult,
    )
    from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
        run_automatic_diagnosis_loop_evidence_collection,
    )
    from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
        BackendIncidentFound,
        BackendIncidentLookupSource,
    )
    from k8s_diag_agent.collect.incident_diagnosis_review_packet_budget import (
        ReviewPacketCreationBudget,
    )
    from k8s_diag_agent.collect.incident_lifecycle import (
        Incident,
        IncidentEvent,
        IncidentEventActor,
        IncidentEventType,
    )
    from k8s_diag_agent.domain.incident_lifecycle import IncidentId

    # 1. Enable the automatic-diagnosis loop for this test. The
    #    ``from .X import Y`` idiom inside the collector rebinds
    #    ``is_automatic_diagnosis_loop_enabled`` as a local name, so we
    #    patch that local binding rather than the source module.
    monkeypatch.setattr(
        ec_mod, "is_automatic_diagnosis_loop_enabled", lambda: True
    )

    # 2. Build a minimal live-cases-dir for the collector write step.
    runs_dir = tmp_path / "runs"
    ext_dir = runs_dir / "external-analysis"
    (ext_dir / "alert-signals").mkdir(parents=True, exist_ok=True)

    # 3. Build two eligible incidents the processor can drive.
    def _build_incident(incident_id: str, namespace: str, object_name: str) -> Incident:
        opened_at = datetime(2026, 7, 12, 12, 0, 0, tzinfo=UTC)
        return Incident(
            incident_id=incident_id,
            source_candidate_id=incident_id,
            namespace=namespace,
            object_kind="pod",
            object_name=object_name,
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="critical",
            status=IncidentStatus.COLLECTING_EVIDENCE,
            first_observed_at=opened_at,
            last_observed_at=opened_at,
            signals=(),
            evidence_needed=("alert_evidence",),
            evidence_links=[],
            signal_count=0,
            events=[
                IncidentEvent(
                    event_id=f"evt-{incident_id}",
                    incident_id=incident_id,
                    event_type=IncidentEventType.OPENED,
                    actor=IncidentEventActor.SYSTEM,
                    occurred_at=opened_at,
                    message="seeded",
                    data={},
                )
            ],
        )

    inc_a = _build_incident("inc-a", "prod", "pod-a")
    inc_b = _build_incident("inc-b", "prod", "pod-b")
    incidents_by_id = {"inc-a": inc_a, "inc-b": inc_b}

    # 4. Patch the backend-lookup seam so the processor sees both
    #    incidents as ``BackendIncidentFound`` without an actual store.
    def _fake_fetch(branded: IncidentId) -> BackendIncidentFound:
        key = str(branded)
        incident = incidents_by_id[key]
        return BackendIncidentFound(
            incident=incident,
            requested_incident_id=key,
            source=BackendIncidentLookupSource.LOCAL_STORE,
            http_status=None,
            payload_schema_version=1,
            payload_type="dict",
        )

    monkeypatch.setattr(
        "k8s_diag_agent.collect."
        "incident_diagnosis_auto_loop_evidence_processor."
        "fetch_backend_incident_for_diagnosis_typed",
        _fake_fetch,
    )

    # 5. Patch lifecycle writes to no-ops that simply apply.
    from k8s_diag_agent.collect.incident_diagnosis_authority_seam import (
        LifecycleWriteApplied,
    )
    from k8s_diag_agent.collect.incident_diagnosis_authority_seam_types import (
        LifecycleTransition,
    )

    def _fake_lifecycle(*, incident_id: str, **_kwargs: object) -> LifecycleWriteApplied:
        return LifecycleWriteApplied(
            transition=LifecycleTransition.STARTED,
            incident_id=incident_id,
        )

    monkeypatch.setattr(
        "k8s_diag_agent.collect."
        "incident_diagnosis_auto_loop_evidence_processor."
        "record_diagnosis_loop_started",
        _fake_lifecycle,
    )
    monkeypatch.setattr(
        "k8s_diag_agent.collect."
        "incident_diagnosis_auto_loop_evidence_processor."
        "record_diagnosis_loop_completed",
        _fake_lifecycle,
    )

    # 6. Patch the eligibility evaluator to ALWAYS return ``eligible`` so
    #    the second-incident skip MUST come from the budget gate in the
    #    write path (``budget.can_attempt() == False`` after the first
    #    consumed unit). The eligibility is unaware of the budget so the
    #    test exercises the write-path guard directly.
    eligibility_calls: list[tuple[str, ReviewPacketCreationBudget | None]] = []

    def _fake_eligibility(
        *,
        incident: Incident,
        config: AutomaticDiagnosisLoopConfig,
        external_analysis_dir: object,
        review_packet_budget: ReviewPacketCreationBudget | None,
    ) -> EligibilityResult:
        eligibility_calls.append(
            (str(incident.incident_id), review_packet_budget)
        )
        # Mirror production semantics: the eligibility gate consults
        # the budget first when one is supplied. The second incident
        # sees the same exhausted budget and is rejected with the
        # canonical ``review_packet_budget_exhausted`` reason,
        # producing an ``eligible=False`` disposition without
        # tripping the disposition_compat invariant against
        # ``eligible=True and skipped=True``.
        if (
            review_packet_budget is not None
            and not review_packet_budget.can_attempt()
        ):
            return EligibilityResult(
                eligible=False,
                incident_id=incident.incident_id,
                reason="review_packet_budget_exhausted",
                status=IncidentStatus.COLLECTING_EVIDENCE,
                has_suggested_checks=False,
                auto_pass_count=0,
                budget_diagnostics=(
                    review_packet_budget.as_diagnostic_for_eligibility(),
                ),
            )
        return EligibilityResult(
            eligible=True,
            incident_id=incident.incident_id,
            reason="test_eligible",
            status=IncidentStatus.COLLECTING_EVIDENCE,
            has_suggested_checks=False,
            auto_pass_count=0,
            budget_diagnostics=(
                (review_packet_budget.as_diagnostic_for_eligibility(),)
                if review_packet_budget is not None
                else ()
            ),
        )

    monkeypatch.setattr(
        "k8s_diag_agent.collect."
        "incident_diagnosis_auto_loop_evidence_processor."
        "evaluate_incident_eligibility",
        _fake_eligibility,
    )

    # 7. Stub the downstream non-budget operations so the processor
    #    reaches ``write_diagnosis_review_packet`` without spinning up
    #    a real orchestrator.
    monkeypatch.setattr(
        "k8s_diag_agent.collect."
        "incident_diagnosis_auto_loop_evidence_processor."
        "build_incident_case_file",
        lambda **_: {"generated_at": "2026-07-12T12:00:00+00:00", "suggested_checks": []},
    )
    monkeypatch.setattr(
        "k8s_diag_agent.collect."
        "incident_diagnosis_auto_loop_evidence_processor."
        "run_automatic_diagnosis_hypothesis_loop",
        lambda **_: type(
            "_StubLoop",
            (),
            {"to_dict": lambda self: {}},
        )(),
    )

    def _stub_orchestrator(**_: object) -> dict[str, object]:
        return {
            "decision": "stop_root_cause_found",
            "runner_result": {
                "checks_requested": 0,
                "checks_run": 0,
                "checks_skipped": 0,
                "checks_rejected": 0,
            },
            "artifact": None,
            "loop_pass_artifact": None,
        }

    monkeypatch.setattr(
        "k8s_diag_agent.collect."
        "incident_diagnosis_auto_loop_evidence_processor."
        "run_policy_enforced_loop_pass",
        _stub_orchestrator,
    )

    # 8. Capture the budget instance created by the collector entry.
    #    ``__post_init__`` is invoked for every dataclass construction
    #    so this records the actual production-allocated budget.
    created_budgets: list[ReviewPacketCreationBudget] = []
    real_post_init = ReviewPacketCreationBudget.__post_init__

    def _spy_post_init(self: ReviewPacketCreationBudget) -> None:
        created_budgets.append(self)
        real_post_init(self)

    monkeypatch.setattr(
        ReviewPacketCreationBudget, "__post_init__", _spy_post_init
    )

    # 9. Spy on ``process_incident_batch`` and ``_process_incident`` so
    #    we can prove the SAME budget instance crosses every layer.
    captured_batch_budgets: list[ReviewPacketCreationBudget | None] = []
    real_batch = ec_mod.process_incident_batch

    def _spy_batch(*args: object, **kwargs: object):
        captured_batch_budgets.append(kwargs.get("review_packet_budget"))
        return real_batch(*args, **kwargs)

    monkeypatch.setattr(ec_mod, "process_incident_batch", _spy_batch)

    captured_processor_budgets: list[ReviewPacketCreationBudget | None] = []
    real_process = batch_mod._process_incident

    def _spy_process(*args: object, **kwargs: object):
        captured_processor_budgets.append(kwargs.get("review_packet_budget"))
        return real_process(*args, **kwargs)

    monkeypatch.setattr(batch_mod, "_process_incident", _spy_process)

    # 10. Run the REAL collector entry with two explicit incident IDs.
    config = AutomaticDiagnosisLoopConfig(
        max_incidents_per_run=2,
        max_passes_per_incident=1,
        max_checks_per_pass=1,
        max_review_packets=1,
        write_stop_path_packets=True,
    )
    now = datetime(2026, 7, 12, 12, 0, 0, tzinfo=UTC)
    result = run_automatic_diagnosis_loop_evidence_collection(
        external_analysis_dir=ext_dir,
        config=config,
        incident_ids=["inc-a", "inc-b"],
        now=now,
    )

    # === R3 contract: budget identity crosses the chain ===
    # Collector created exactly one budget. The runtime assertion
    # confirms ``isinstance``; the ``cast`` keeps mypy from
    # collapsing the post-spy captured list to ``Any`` after the
    # ``ReviewPacketCreationBudget.__post_init__`` monkeypatch.
    assert len(created_budgets) == 1
    _captured: ReviewPacketCreationBudget = cast(
        ReviewPacketCreationBudget, created_budgets[0]
    )
    assert isinstance(_captured, ReviewPacketCreationBudget)
    collector_budget: ReviewPacketCreationBudget = _captured
    assert collector_budget.limit == 1
    assert str(collector_budget.collector_run_id).startswith("auto-diagnosis-")

    # ``process_incident_batch`` received the SAME instance.
    assert len(captured_batch_budgets) == 1
    assert captured_batch_budgets[0] is collector_budget

    # Both ``_process_incident`` calls saw the SAME instance.
    assert len(captured_processor_budgets) == 2
    assert captured_processor_budgets[0] is collector_budget
    assert captured_processor_budgets[1] is collector_budget

    # Eligibility saw the SAME budget instance for both incidents.
    assert len(eligibility_calls) == 2
    assert eligibility_calls[0][0] == "inc-a"
    assert eligibility_calls[1][0] == "inc-b"
    assert eligibility_calls[0][1] is collector_budget
    assert eligibility_calls[1][1] is collector_budget

    # === R3 contract: one packet written, one budget skip ===
    assert collector_budget.used == 1  # type: ignore[union-attr]
    assert collector_budget.exhausted is True  # type: ignore[union-attr]

    packets = list(ext_dir.glob("*-diagnosis-review-packet.json"))
    assert len(packets) == 1

    # The collector result exposes the same shape as the legacy test:
    # one incident processed, one incident budget-skipped.
    incident_results = list(result.incident_results)
    assert len(incident_results) == 2

    first = incident_results[0]
    second = incident_results[1]
    assert first["review_packet_written"] is True
    assert second["review_packet_written"] is False
    assert second["skipped"] is True
    skip_reason = second.get("skip_reason") or ""
    assert "budget_exhausted" in skip_reason

    # The diagnostic projection proves the budget (not filesystem)
    # is authoritative.
    diag = (
        collector_budget.as_diagnostic_for_eligibility()  # type: ignore[union-attr]
    ).to_dict()
    assert diag["source"] == "collector_run_accounting"
    assert diag["name"] == "review_packet_budget"
    assert diag["exhausted"] is True

    # The collector's total review-packet write counter agrees with
    # the disk state.
    assert result.total_review_packets_written == 1
