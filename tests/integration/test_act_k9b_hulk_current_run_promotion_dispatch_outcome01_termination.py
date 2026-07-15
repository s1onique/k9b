"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 termination tests.

Covers invariant O9 (BaseException propagation before classification).

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    MODE_BACKEND_API,
    IncidentPromotionResult,
)
from k8s_diag_agent.collect.promotion_dispatch_outcome import (
    classify_promotion_dispatch_result,
)
from k8s_diag_agent.health.loop_alertmanager_snapshot_signals import (
    _ingest_alert_signals,
)

from .incident_current_run_promotion_dispatch_outcome01_support import (
    RUN_ID,
    CapturingLog,
    build_alert,
    build_snapshot,
    build_source,
    persist_signals,
    stub_dispatch_raises,
    stub_dispatch_with_batch,
)


class TestTerminationPropagation:
    """``BaseException`` subclasses propagate BEFORE classification."""

    def _run_with_termination(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
        exc: BaseException,
    ) -> RunPromotionAccumulator:
        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 3)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")
        stub_dispatch_raises(monkeypatch, exc)
        return accumulator

    def _call_with_termination(
        self,
        accumulator: RunPromotionAccumulator,
        tmp_path: Any,
    ) -> Any:
        snapshot = build_snapshot([build_alert(i) for i in range(3)])
        return _ingest_alert_signals(
            snapshot=snapshot,
            selected_source=build_source(),
            snapshot_path=None,
            directories={"root": tmp_path / "runs"},
            incident_store=None,
            log_event=CapturingLog(),
            run_id=RUN_ID,
            run_label="run-2026-07-15T0340Z",
            effective_cluster_context=None,
            promotion_accumulator=accumulator,
        )

    def test_keyboard_interrupt_propagates_unchanged(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        accumulator = self._run_with_termination(
            tmp_path, monkeypatch, KeyboardInterrupt(),
        )
        with pytest.raises(KeyboardInterrupt):
            self._call_with_termination(accumulator, tmp_path)
        assert accumulator.promotion_outcome is None

    def test_system_exit_propagates_unchanged(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        accumulator = self._run_with_termination(
            tmp_path, monkeypatch, SystemExit(1),
        )
        with pytest.raises(SystemExit):
            self._call_with_termination(accumulator, tmp_path)
        assert accumulator.promotion_outcome is None

    def test_generator_exit_propagates_unchanged(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        accumulator = self._run_with_termination(
            tmp_path, monkeypatch, GeneratorExit(),
        )
        with pytest.raises(GeneratorExit):
            self._call_with_termination(accumulator, tmp_path)
        assert accumulator.promotion_outcome is None

    def test_termination_skips_fingerprint_construction(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from k8s_diag_agent.collect import (
            promotion_dispatch_outcome as cls_module,
        )

        calls: list = []

        original = cast(Callable[[Any], str], cls_module._stable_fingerprint)

        def spy(payload: Any) -> str:
            calls.append(payload)
            return original(payload)

        monkeypatch.setattr(cls_module, "_stable_fingerprint", spy)

        with pytest.raises(KeyboardInterrupt):
            classify_promotion_dispatch_result(
                run_id=RUN_ID,
                requested_signal_ids=("sha256:a",),
                requested_signal_payload={"runId": RUN_ID},
                outcome=KeyboardInterrupt(),
            )
        assert calls == []


# Inherit the BaseException propagation fingerprint test from the
# split; the unit-level test below mirrors the integration version.


def test_unit_termination_skips_fingerprint_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from k8s_diag_agent.collect import (
        promotion_dispatch_outcome as cls_module,
    )

    calls: list = []

    original = cast(Callable[[Any], str], cls_module._stable_fingerprint)

    def spy(payload: Any) -> str:
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(cls_module, "_stable_fingerprint", spy)

    with pytest.raises(KeyboardInterrupt):
        classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": RUN_ID},
            outcome=KeyboardInterrupt(),
        )
    assert calls == []


def test_unit_system_exit_skips_fingerprint_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from k8s_diag_agent.collect import (
        promotion_dispatch_outcome as cls_module,
    )

    calls: list = []

    original = cast(Callable[[Any], str], cls_module._stable_fingerprint)

    def spy(payload: Any) -> str:
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(cls_module, "_stable_fingerprint", spy)

    with pytest.raises(SystemExit):
        classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": RUN_ID},
            outcome=SystemExit(1),
        )
    assert calls == []


def test_unit_generator_exit_skips_fingerprint_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from k8s_diag_agent.collect import (
        promotion_dispatch_outcome as cls_module,
    )

    calls: list = []

    original = cast(Callable[[Any], str], cls_module._stable_fingerprint)

    def spy(payload: Any) -> str:
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(cls_module, "_stable_fingerprint", spy)

    with pytest.raises(GeneratorExit):
        classify_promotion_dispatch_result(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            requested_signal_payload={"runId": RUN_ID},
            outcome=GeneratorExit(),
        )
    assert calls == []


def test_unit_inherited_scoped_dispatch_signature_unchanged() -> None:
    """Inherited SEAM01 verifier signature scope is preserved."""
    import inspect

    from k8s_diag_agent.collect import (
        incident_promotion_dispatch as dispatch_module,
    )

    sig = inspect.signature(
        dispatch_module.promote_alert_signals_scoped_for_accumulator
    )
    expected_params = {
        "runs_dir",
        "health_run_id",
        "source_identity",
        "signal_ids",
        "accumulator",
        "cluster_context",
    }
    assert expected_params.issubset(set(sig.parameters.keys())), (
        "Inherited scoped dispatch signature was modified; "
        "SEAM01 verifier expects these parameter names"
    )

class TestDiagnosisNotInvoked:
    """O15: Item 3 does not invoke diagnosis. Item 4 will.

    The test asserts a real ``assert_not_called()`` against the
    diagnosis entry point (``run_automatic_diagnosis_loop``) so the
    evidence is no longer just a literal telemetry value.
    """

    def test_ingest_does_not_invoke_diagnosis(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop as auto_loop_module,
        )
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionSucceeded,
        )
        from k8s_diag_agent.health.loop_alertmanager_snapshot_signals import (
            AlertSignalPromotionDispatchResult,
        )

        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 3)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        successful_result = IncidentPromotionResult(
            ok=True,
            scanned=3,
            firing=3,
            opened_incidents=1,
            updated_incidents=0,
            opened_incident_ids=("inc-1",),
            promotion_mode=MODE_BACKEND_API,
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode="backend",
        )
        stub_dispatch_with_batch(monkeypatch, successful_result)

        # Spy on the real diagnosis entry point.
        spy_calls: list[dict] = []

        def fake_diagnosis(*args: Any, **kwargs: Any) -> Any:
            spy_calls.append({"args": args, "kwargs": kwargs})
            raise AssertionError(
                "Item 3 MUST NOT invoke the diagnosis entry point"
            )

        monkeypatch.setattr(
            auto_loop_module,
            "run_automatic_diagnosis_loop_evidence_collection",
            fake_diagnosis,
        )

        snapshot = build_snapshot([build_alert(i) for i in range(3)])
        result = _ingest_alert_signals(
            snapshot=snapshot,
            selected_source=build_source(),
            snapshot_path=None,
            directories={"root": runs_dir},
            incident_store=None,
            log_event=CapturingLog(),
            run_id=RUN_ID,
            run_label="run-2026-07-15T0340Z",
            effective_cluster_context=None,
            promotion_accumulator=accumulator,
        )

        # The classifier succeeded and recorded the typed outcome.
        assert isinstance(result, AlertSignalPromotionDispatchResult)
        assert isinstance(result.outcome, PromotionSucceeded)
        # The diagnosis entry point was NOT invoked.
        assert spy_calls == [], (
            "Item 3 must not call run_automatic_diagnosis_loop; "
            f"got {len(spy_calls)} call(s)"
        )
