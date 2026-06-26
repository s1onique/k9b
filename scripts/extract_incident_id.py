#!/usr/bin/env python3
"""Extract incident ID from incidents API response.

Usage:
    extract-incident-id <incidents_response.json>

Examples:
    echo '{"incidents":[{"incident_id":"inc-123"}]}' | extract-incident-id
    extract-incident-id ./incidents.json
"""
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        # Read from stdin
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError:
            print("", file=sys.stderr)
            return 0
    else:
        try:
            data = json.loads(Path(sys.argv[1]).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            print("", file=sys.stderr)
            return 0

    incidents = data.get('incidents', [])
    if incidents:
        incident_id = incidents[0].get('incident_id', '')
        print(incident_id)
    else:
        print("")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
