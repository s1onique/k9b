"""ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R1 root-cause regression.

ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R1
"""

from __future__ import annotations

from datetime import UTC
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentSignal,
    IncidentStatus,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    _result_from_dict,
    promotion_records_from_result,
)
from k8s_diag_agent.health.loop_automatic_diagnosis import (
    run_automatic_diagnosis_loop,
)


@pytest.fixture
def backend_authoritative_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    env = {
        "K9B_PROCESS_ROLE": "scheduler",
        "K9B_INCIDENT_STORE_BACKEND": "sqlite",
        "K9B_INCIDENT_PROMOTION_MODE": "backend-api",
        "K9B_BACKEND_INTERNAL_URL": "http://k9b-backend:8080",
        "K9B_INTERNAL_API_TOKEN": "test-token",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


@pytest.fixture
def backend_canonical_incident() -> Incident:
    from datetime import datetime as _dt

    first = _dt(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
    last = _dt(2026, 7, 10, 13, 0, 0, tzinfo=UTC)
    return Incident(
        incident_id="incident-canonical-7f3a",
        source_candidate_id="k8s-namespace/Pod/my-pod",
        namespace="default",
        object_kind="Pod",
        object_name="my-pod",
        raw_object_kind=None,
        candidate_class="PodCrashLoop",
        severity="high",
        status=IncidentStatus.OPEN,
        first_observed_at=first,
        last_observed_at=last,
        signals=[
            IncidentSignal(
                source="alert",
                reason="CrashLoopBackOff",
                message="Container crashed",
                captured_at=first,
                fingerprint="alert-signal-1",
            ),
        ],
        evidence_needed=["alert_evidence"],
        evidence_links=[],
        signal_count=1,
        events=[],
    )


class TestRootCauseRegression:
    def test_backend_promotion_returns_canonical_id_different_from_candidate(
        self,
        backend_authoritative_env: dict[str, str],
        backend_canonical_incident: Incident,
    ) -> None:
        result = _result_from_dict(
            {
                "ok": True,
                "scanned": 1,
                "firing": 1,
                "opened_incidents": 0,
                "updated_incidents": 1,
                "skipped_duplicates": 0,
                "errors": 0,
                "error_messages": [],
                "promotion_mode": "backend-api",
                "opened_incident_ids": [],
                "updated_incident_ids": ["incident-canonical-7f3a"],
                "promotion_records": [
                    {
                        "source_candidate_id": "k8s-namespace/Pod/my-pod",
                        "canonical_incident_id": "incident-canonical-7f3a",
                        "promotion_outcome": "updated",
                    }
                ],
                "unique_candidate_count": 1,
                "promotion_scan_scope": "internal_api_alert_signals",
                "incident_access_mode": "backend",
            },
            promotion_mode="backend-api",
        )

        assert tuple(result.updated_incident_ids) == ("incident-canonical-7f3a",)
        records = list(result.promotion_records)
        assert records[0]["canonical_incident_id"] == "incident-canonical-7f3a"
        assert records[0]["source_candidate_id"] == "k8s-namespace/Pod/my-pod"
        assert records[0]["canonical_incident_id"] != records[0]["source_candidate_id"]

    def test_run_promotion_accumulator_dedupes_canonical_ids(self) -> None:
        accumulator = RunPromotionAccumulator()
        for i in range(5):
            accumulator.add_record(
                PromotionRecord(
                    source_candidate_id=f"cand-{i}",
                    canonical_incident_id="incident-collapse",
                    promotion_outcome="opened",
                )
            )
        accumulator.add_record(
            PromotionRecord(
                source_candidate_id="cand-X",
                canonical_incident_id="incident-distinct",
                promotion_outcome="opened",
            )
        )
        assert accumulator.canonical_incident_ids() == [
            "incident-collapse",
            "incident-distinct",
        ]
        assert len(accumulator.promotion_records) == 6

    def test_promotion_records_from_result_handles_collapsed_outcomes(self) -> None:
        result = _result_from_dict(
            {
                "ok": True,
                "scanned": 5,
                "firing": 5,
                "opened_incidents": 1,
                "updated_incidents": 0,
                "skipped_duplicates": 0,
                "errors": 0,
                "error_messages": [],
                "promotion_mode": "backend-api",
                "opened_incident_ids": ["incident-canonical-1"],
                "updated_incident_ids": [],
                "promotion_records": [
                    {
                        "source_candidate_id": f"cand-{i}",
                        "canonical_incident_id": "incident-canonical-1",
                        "promotion_outcome": "opened",
                    }
                    for i in range(5)
                ],
                "unique_candidate_count": 5,
                "promotion_scan_scope": "internal_api_alert_signals",
                "incident_access_mode": "backend",
            },
            promotion_mode="backend-api",
        )
        records = promotion_records_from_result(result)
        assert len(records) == 5
        for record in records:
            assert record.canonical_incident_id == "incident-canonical-1"
            assert record.promotion_outcome == "opened"

    def test_run_diagnosis_enters_eligible_path_with_canonical_ids(
        self,
        backend_authoritative_env: dict[str, str],
        backend_canonical_incident: Incident,
        tmp_path: Any,
    ) -> None:
        captured: dict[str, Any] = {}

        def collector_stub(
            external_analysis_dir: Any,
            config: Any = None,
            incident_ids: list[str] | None = None,
            scheduler_run_id: str | None = None,
        ) -> Any:
            captured["incident_ids"] = list(incident_ids or [])
            result = MagicMock()
            result.incidents_processed = 0
            result.incidents_eligible = 0
            result.incidents_skipped = 1
            result.incidents_ineligible = 0
            result.incidents_with_errors = 0
            result.total_review_packets_written = 0
            result.disposition_summary = MagicMock(
                skip_reasons={"incident_not_found": 1},
                ineligible_reasons={},
                error_reasons={},
            )
            result.run_id = "test-run"
            return result

        with (
            patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop.run_automatic_diagnosis_loop_evidence_collection",
                side_effect=collector_stub,
            ),
            patch(
                "k8s_diag_agent.health.loop_automatic_diagnosis.is_automatic_diagnosis_loop_enabled",
                return_value=True,
            ),
        ):
            result = run_automatic_diagnosis_loop(
                external_analysis_dir=tmp_path,
                log_event_fn=lambda *a, **kw: None,
                canonical_incident_ids=["incident-canonical-7f3a"],
                scheduler_run_id="legacy_run",
                promotion_result_summary={
                    "opened_incident_ids": ["incident-canonical-7f3a"],
                    "updated_incident_ids": [],
                    "promotion_records": [
                        {
                            "source_candidate_id": "k8s-namespace/Pod/my-pod",
                            "canonical_incident_id": "incident-canonical-7f3a",
                            "promotion_outcome": "updated",
                        }
                    ],
                },
                backend_endpoint_identity={
                    "base_url": "http://k9b-backend:8080",
                    "internal_api_path_prefix": "/api/internal",
                    "backend_reachable": True,
                    "incident_access_mode": "backend",
                },
            )

        assert captured["incident_ids"] == ["incident-canonical-7f3a"]
        assert result["promotion_propagated_to_diagnosis"] is True
        assert result["explicit_canonical_id_count"] == 1

    def test_scheduler_local_store_remains_unread(
        self,
        backend_authoritative_env: dict[str, str],
        backend_canonical_incident: Incident,
    ) -> None:
        assert backend_canonical_incident.incident_id != backend_canonical_incident.source_candidate_id
        assert "/" not in backend_canonical_incident.incident_id
        assert "default" not in backend_canonical_incident.incident_id
        assert "my-pod" not in backend_canonical_incident.incident_id
        assert "k8s-namespace" not in backend_canonical_incident.incident_id
