#!/usr/bin/env python3
"""Parse OTel Collector debug exporter logs into OTLP JSONL format.

This script handles the text format output from the OTel Collector's
debug exporter and converts it to OTLP-compatible JSONL format.
"""

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Span:
    trace_id: str = ""
    span_id: str = ""
    parent_id: str = ""
    name: str = ""
    kind: str = ""
    start_time: str = ""
    end_time: str = ""
    status_code: str = ""
    status_message: str = ""
    attributes: dict = field(default_factory=dict)

    def to_otlp(self) -> dict:
        """Convert to OTLP-compatible JSON format."""
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "parentSpanId": self.parent_id if self.parent_id else "",
            "name": self.name,
            "kind": self.kind,
            "startTimeUnixNano": self._parse_timestamp(self.start_time),
            "endTimeUnixNano": self._parse_timestamp(self.end_time),
            "attributes": [{"key": k, "value": {"stringValue": str(v)}} for k, v in self.attributes.items()],
        }

    def _parse_timestamp(self, ts: str) -> str:
        """Parse ISO timestamp to nanoseconds since epoch."""
        if not ts:
            return "0"
        try:
            # Format: 2026-07-06 09:49:36.952271804 +0000 UTC
            ts = ts.strip()
            dt = datetime.strptime(ts[:26], "%Y-%m-%d %H:%M:%S.%f")
            return str(int(dt.timestamp() * 1e9))
        except Exception:
            return "0"


def parse_spans_from_logs(log_content: str) -> list[Span]:
    """Parse spans from debug exporter logs."""
    spans: list[Span] = []
    current_span: Span | None = None
    in_attributes = False

    lines = log_content.split("\n")
    for line in lines:
        line = line.rstrip()

        # Start of a new span
        if match := re.match(r"^Span #(\d+)", line):
            if current_span and current_span.trace_id:
                spans.append(current_span)
            current_span = Span()
            in_attributes = False
            continue

        if current_span is None:
            continue

        # Parse fields - strip leading whitespace
        line_stripped = line.lstrip()
        
        if line_stripped.startswith("Trace ID"):
            current_span.trace_id = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("Parent ID"):
            pid = line_stripped.split(":", 1)[1].strip()
            if pid:
                current_span.parent_id = pid
        elif line_stripped.startswith("ID"):
            # Match standalone "ID" not "Parent ID" or "Trace ID"
            if not line_stripped.startswith("Parent") and not line_stripped.startswith("Trace"):
                current_span.span_id = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("Name"):
            current_span.name = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("Kind"):
            current_span.kind = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("Start time"):
            current_span.start_time = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("End time"):
            current_span.end_time = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("Status code"):
            current_span.status_code = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("Status message"):
            current_span.status_message = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("Attributes:"):
            in_attributes = True
            continue
        elif in_attributes and line_stripped.startswith("->"):
            # Parse attribute: -> k9b.api.route: Str(GET /api/incidents)
            attr_match = re.match(r"->\s*([a-zA-Z0-9._-]+)\s*:\s*(.+)", line_stripped)
            if attr_match:
                key = attr_match.group(1)
                value = attr_match.group(2).strip()
                # Remove quotes wrapper if present: Str(...), Bool(...), Int(...)
                if match := re.match(r"(\w+)\((.+)\)", value):
                    value = match.group(2)
                current_span.attributes[key] = value
        elif line_stripped and not line_stripped.startswith("->"):
            in_attributes = False

    # Don't forget the last span
    if current_span and current_span.trace_id:
        spans.append(current_span)

    return spans


def main() -> None:
    if len(sys.argv) < 2:
        input_file = "/dev/stdin"
    else:
        input_file = sys.argv[1]

    with open(input_file) as f:
        log_content = f.read()

    spans = parse_spans_from_logs(log_content)

    for span in spans:
        print(json.dumps(span.to_otlp()))


if __name__ == "__main__":
    main()
