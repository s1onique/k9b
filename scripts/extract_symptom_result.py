#!/usr/bin/env python3
"""Extract and format symptom result data for display.

Usage:
    extract-symptom-result <symptom_result.json>

Examples:
    extract-symptom-result ./lab-artifacts/live/symptom-watch/pod-failure-symptom-result.json
"""
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: extract-symptom-result <symptom_result.json>", file=sys.stderr)
        return 1

    try:
        data = json.loads(Path(sys.argv[1]).read_text())
        
        print(f"Class: {data.get('symptom_class', 'unknown')}")
        print(f"Fatal: {data.get('fatal', False)}")
        print(f"Pod phase: {data.get('pod_phase', 'unknown')}")
        print(f"Pod ready: {data.get('pod_ready', 'unknown')}")
        print(f"Container state: {data.get('container_state', 'unknown')}")
        print(f"Failure reason: {data.get('failure_reason', 'none')}")
        print(f"Elapsed: {data.get('elapsed_seconds', 0)}s ({data.get('poll_count', 0)} polls)")
        
        return 0
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
