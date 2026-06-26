#!/usr/bin/env python3
"""Extract the first non-empty failure class from a preflight result.

Usage:
    extract-failure-class <preflight_result.json> [--default <default>]

Examples:
    extract-failure-class ./image-preflight/node-pull-preflight.json
    extract-failure-class ./image-preflight/node-pull-preflight.json --default "unknown"
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract first failure class from preflight result")
    parser.add_argument("json_file", type=Path, help="Path to preflight JSON file")
    parser.add_argument("--default", "-d", default="unknown",
                        help="Default value if no failure class found")
    args = parser.parse_args()

    try:
        data = json.loads(args.json_file.read_text())
        fcs = data.get("failure_classes", [])
        
        # Find first non-empty failure class
        for fc in fcs:
            if fc:
                print(fc)
                return 0
        
        print(args.default)
        return 0
    except (FileNotFoundError, json.JSONDecodeError):
        print(args.default, file=sys.stderr)
        print(args.default)
        return 0


if __name__ == "__main__":
    sys.exit(main())
