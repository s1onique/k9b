"""Normalize fixture inputs into internal evidence structures."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from ..datetime_utils import ensure_utc, now_utc, parse_iso_to_utc
from ..models import EvidenceRecord, Layer, Signal


def _parse_datetime(value: object | None) -> datetime:
    """Parse timestamp to timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        return ensure_utc(value)
    parsed = parse_iso_to_utc(value)
    return parsed if parsed is not None else now_utc()


def normalize_signals(input_data: dict[str, object]) -> tuple[list[EvidenceRecord], list[Signal]]:
    scenario_ts = _parse_datetime(input_data.get("timestamp", datetime.now(UTC).isoformat()))
    signals_section = input_data.get("signals", {})
    evidence_records: list[EvidenceRecord] = []
    signals: list[Signal] = []

    pod_items = signals_section.get("pods", [])
    for idx, pod in enumerate(_iter_dicts(pod_items)):
        pod_id = f"pod:{pod['name']}:{idx}"
        record = EvidenceRecord(
            id=pod_id,
            kind="pod_status",
            layer=Layer.WORKLOAD,
            timestamp=_parse_datetime(pod.get("timestamp", scenario_ts.isoformat())),
            payload={
                "name": pod.get("name"),
                "status": pod.get("status"),
                "restart_count": pod.get("restart_count"),
            },
        )
        evidence_records.append(record)
        severity = _pod_severity(pod.get("status", ""))
        signals.append(
            Signal(
                id=f"signal:{pod_id}",
                description=f"Pod {pod.get('name')} is {pod.get('status')}",
                layer=Layer.WORKLOAD,
                evidence_id=pod_id,
                severity=severity,
            )
        )

    event_items = signals_section.get("events", [])
    for idx, event in enumerate(_iter_dicts(event_items)):
        event_id = f"event:{event['reason']}:{idx}"
        record = EvidenceRecord(
            id=event_id,
            kind="event",
            layer=Layer.OBSERVABILITY,
            timestamp=_parse_datetime(event.get("timestamp", scenario_ts.isoformat())),
            payload={
                "type": event.get("type"),
                "reason": event.get("reason"),
                "message": event.get("message"),
            },
        )
        evidence_records.append(record)
        signals.append(
            Signal(
                id=f"signal:{event_id}",
                description=f"Event {event.get('reason')} ({event.get('type')})",
                layer=Layer.OBSERVABILITY,
                evidence_id=event_id,
                severity="medium" if event.get("type") == "Warning" else "low",
            )
        )

    return evidence_records, signals


def _pod_severity(status: object) -> str:
    status_str = (str(status) if status is not None else "").lower()
    if status_str == "crashloopbackoff":
        return "high"
    if status_str in {"pending"}:
        return "medium"
    return "low"


def _iter_dicts(items: Iterable[object]) -> Iterable[dict[str, object]]:
    for item in items or []:
        if isinstance(item, dict):
            yield item
