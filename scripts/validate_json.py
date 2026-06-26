#!/usr/bin/env python3
"""Validate JSON and exit 0 if valid, 1 if invalid.

Usage:
    validate-json [--file <json_file>]

Examples:
    echo '{"key": "value"}' | validate-json
    validate-json --file ./response.json
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate JSON")
    parser.add_argument("--file", "-f", type=Path, help="Path to JSON file (default: stdin)")
    args = parser.parse_args()

    try:
        if args.file:
            json.loads(args.file.read_text())
        else:
            json.load(sys.stdin)
        return 0
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
