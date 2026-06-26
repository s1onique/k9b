#!/usr/bin/env python3
"""Format polling history snapshots for display.

Usage:
    format-polling-history <snapshots.json>

Examples:
    format-polling-history ./lab-artifacts/live/symptom-watch/pod-failure-symptom-snapshots.json
"""
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: format-polling-history <snapshots.json>", file=sys.stderr)
        return 1

    try:
        snapshots = json.loads(Path(sys.argv[1]).read_text())
        
        for s in snapshots:
            poll = s.get('poll_count', 0)
            elapsed = s.get('elapsed_seconds', 0)
            phase = s.get('pod_phase', 'unknown')
            ready = s.get('pod_ready', 'unknown')
            reason = s.get('container_waiting_reason') or 'none'
            print(f"poll {poll}: {elapsed}s - phase={phase} ready={ready} reason={reason}")
        
        return 0
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
