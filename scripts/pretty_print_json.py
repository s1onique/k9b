#!/usr/bin/env python3
"""Pretty-print JSON from stdin or file.

Usage:
    pretty-print-json [--file <json_file>]

Examples:
    cat artifacts/result.json | pretty-print-json
    pretty-print-json --file artifacts/result.json
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Pretty-print JSON")
    parser.add_argument("--file", "-f", type=Path, help="Path to JSON file (default: stdin)")
    args = parser.parse_args()

    try:
        if args.file:
            data = json.loads(args.file.read_text())
        else:
            data = json.load(sys.stdin)
        print(json.dumps(data, indent=2))
        return 0
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
