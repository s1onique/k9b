#!/usr/bin/env python3
"""Extract a single value from a JSON file.

Usage:
    extract-json-value <json_file> [--key <key> [--key ...]]

Examples:
    extract-json-value ./artifacts/result.json --key failure_class
    extract-json-value ./artifacts/result.json --key data.status --default "unknown"
"""
import argparse
import json
import sys
from pathlib import Path


def get_nested(data: dict[str, object], key_path: str) -> object | None:
    """Get a nested value from dict using dot notation."""
    keys = key_path.split('.')
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)  # type: ignore[assignment]
        else:
            return None
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract value from JSON file")
    parser.add_argument("json_file", type=Path, help="Path to JSON file")
    parser.add_argument("--key", "-k", default="failure_class",
                        help="Key to extract (dot notation for nested)")
    parser.add_argument("--default", "-d", default="",
                        help="Default value if key not found")
    args = parser.parse_args()

    try:
        data = json.loads(args.json_file.read_text())
        value = get_nested(data, args.key)
        if value is None:
            print(args.default)
        else:
            print(value)
        return 0
    except (FileNotFoundError, json.JSONDecodeError):
        print(args.default, file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
