"""Produce findings and hypotheses from normalized signals."""
from __future__ import annotations

import uuid
from typing import Dict, Iterable, List, Tuple

from ..models import ConfidenceLevel, Finding, Hypothesis, Layer, Signal


def build_findings_and_hypotheses(
    signals: Iterable[Signal], correlated_layers: Dict[str, List[str]]
) -> Tuple[List[Finding], List[Hypothesis]]:
    findings: List[Finding] = []
    hypotheses: List[Hypothesis] = []
    high_severity_signals = [sig for sig in signals if sig.severity == "high"]

    if high_severity_signals:
        signal_ids = [sig.id for sig in high_severity_signals]
        findings.append(
            Finding(
                id=_random_id(),
                description="Workload is repeatedly restarting with CrashLoopBackOff.",
                supporting_signals=signal_ids,
                layer=Layer.WORKLOAD,
            )
        )
        hypotheses.append(
            Hypothesis(
                id=_random_id(),
                description="Startup or image issue is causing CrashLoopBackOff; missing logs/current rollout history keep evidence incomplete.",
                confidence=ConfidenceLevel.LOW,
                probable_layer=Layer.WORKLOAD,
                what_would_falsify="Logs show the container starts cleanly and recent rollout info shows no change.",
            )
        )
    else:
        dominant_layer = Layer.WORKLOAD
        if correlated_layers:
            first_layer = next(iter(correlated_layers))
            try:
                dominant_layer = Layer(first_layer)
            except ValueError:
                dominant_layer = Layer.WORKLOAD
        findings.append(
            Finding(
                id=_random_id(),
                description="Signals are present but no high-severity evidence yet.",
                supporting_signals=[sig.id for sig in signals],
                layer=dominant_layer,
            )
        )
        hypotheses.append(
            Hypothesis(
                id=_random_id(),
                description="Evidence is inconclusive; need logs or node info to confirm the layer of failure.",
                confidence=ConfidenceLevel.LOW,
                probable_layer=dominant_layer,
                what_would_falsify="Missing telemetry appears and shows healthy startup, removing suspicion.",
            )
        )
    return findings, hypotheses


def _random_id() -> str:
    return uuid.uuid4().hex
