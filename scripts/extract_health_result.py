#!/usr/bin/env python3
"""Extract backend health check result for CI output.

Usage:
    extract-health-result <health_result.json>

Examples:
    extract-health-result ./backend-health/health-check-result.json
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract backend health result")
    parser.add_argument("json_file", type=Path, help="Path to health result JSON")
    parser.add_argument("--field", "-f", default="failure_class",
                        help="Field to extract (default: failure_class)")
    args = parser.parse_args()

    try:
        data = json.loads(args.json_file.read_text())
        value = data.get(args.field, '')
        print(value)
        return 0
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
