#!/usr/bin/env python3
"""Extract summary from rendered-images.json for display.

Usage:
    extract-rendered-images-summary [--file <rendered_images.json>]

Examples:
    extract-rendered-images-summary --file ./artifacts/rendered-images.json
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract summary from rendered-images.json")
    parser.add_argument("--file", "-f", type=Path, help="Path to rendered-images.json file")
    args = parser.parse_args()

    try:
        if args.file:
            data = json.loads(args.file.read_text())
        else:
            data = json.load(sys.stdin)
        summary = data.get('summary', {})
        print(json.dumps(summary, indent=2))
        return 0
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
