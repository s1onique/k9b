"""OTel trace verification for OTel demo lab contract verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.otel_lab_contracts.constants import EXPECTED_OTEL_EVENTS, EXPECTED_OTEL_SPANS
from scripts.otel_lab_contracts.models import ContractCheck, OtelTracesMode, VerificationReport


def find_otel_trace_artifacts(artifact_dir: Path) -> list[Path]:
    """Find OTel trace artifacts."""
    patterns = [
        "**/traces*.json",
        "**/otel*.json",
        "**/spans*.json",
    ]
    found: list[Path] = []
    for pattern in patterns:
        found.extend(artifact_dir.glob(pattern))
    return found


def verify_otel_traces(artifact_dir: Path, mode: OtelTracesMode, report: VerificationReport) -> bool:
    """Verify OTel trace artifacts.

    When mode is:
    - skip: Do not inspect traces
    - auto: Inspect if present, skip if missing; warn if no expected names
    - require: Fail if missing OR if no expected k9b span/event names found

    If traces exist, verify expected span/event names.
    """
    if mode == OtelTracesMode.SKIP:
        report.add_check(
            ContractCheck(
                name="otel_traces",
                passed=True,
                phase="otel",
                reason="skipped",
            )
        )
        return True

    trace_artifacts = find_otel_trace_artifacts(artifact_dir)

    if not trace_artifacts:
        if mode == OtelTracesMode.REQUIRE:
            report.add_error("OTel traces required but not found")
            return False
        else:
            # auto mode - traces optional
            report.add_check(
                ContractCheck(
                    name="otel_traces",
                    passed=True,
                    phase="otel",
                    reason="skipped_missing",
                )
            )
            return True

    # Verify traces contain expected spans/events
    spans_found: set[str] = set()
    events_found: set[str] = set()

    for trace_path in trace_artifacts:
        try:
            content = trace_path.read_text()
            trace_data = json.loads(content)

            # Extract span/event names
            _extract_trace_names(trace_data, spans_found, events_found)

        except (json.JSONDecodeError, OSError):
            continue

    # Check for expected spans (at least some should be present)
    expected_spans_found = spans_found & EXPECTED_OTEL_SPANS
    expected_events_found = events_found & EXPECTED_OTEL_EVENTS

    if not expected_spans_found and not expected_events_found:
        error_msg = f"OTel traces found but no expected k9b span/event names. Spans found: {spans_found}, Events found: {events_found}. Expected spans: {EXPECTED_OTEL_SPANS}, Expected events: {EXPECTED_OTEL_EVENTS}"
        if mode == OtelTracesMode.REQUIRE:
            # require mode: fail if traces exist but have no expected names
            report.add_error(error_msg)
            return False
        else:
            # auto mode: warn but don't fail (API-only instrumentation may not export)
            report.add_warning(error_msg)

    report.add_check(
        ContractCheck(
            name="otel_traces",
            passed=True,
            phase="otel",
            reason="traces_present",
            details={
                "trace_files": [str(p) for p in trace_artifacts],
                "spans_found": list(spans_found),
                "events_found": list(events_found),
                "expected_spans_found": list(expected_spans_found),
                "expected_events_found": list(expected_events_found),
            },
        )
    )
    return True


def _extract_trace_names(data: Any, spans: set[str], events: set[str]) -> None:
    """Recursively extract span/event names from trace data."""
    if isinstance(data, dict):
        # Check for span name fields
        for key in ["name", "span_name", "display_name"]:
            if key in data and isinstance(data[key], str):
                spans.add(data[key])

        # Check for event names
        if "events" in data and isinstance(data["events"], list):
            for event in data["events"]:
                if isinstance(event, dict) and "name" in event:
                    events.add(str(event["name"]))

        # Recurse
        for value in data.values():
            _extract_trace_names(value, spans, events)

    elif isinstance(data, list):
        for item in data:
            _extract_trace_names(item, spans, events)
