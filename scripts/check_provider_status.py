#!/usr/bin/env python3
"""Extract provider status fields from diagnosis response.

Usage:
    check-provider-status <response.json> [--field <field>]

Examples:
    check-provider-status ./response.json --field provider_invocation_attempted
    check-provider-status ./response.json --field provider_configured
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check provider status in response")
    parser.add_argument("json_file", type=Path, help="Path to response JSON file")
    parser.add_argument("--field", "-f", default="provider_invocation_attempted",
                        choices=["provider_invocation_attempted", "provider_configured"],
                        help="Field to check")
    args = parser.parse_args()

    try:
        data = json.loads(args.json_file.read_text())
        value = data.get(args.field, False)
        print("true" if value else "false")
        return 0
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        print("unknown")
        return 0


if __name__ == "__main__":
    sys.exit(main())
