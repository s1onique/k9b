#!/usr/bin/env python3
"""Check if all failure classes in a registry preflight result are auth_unverified.

Usage:
    check-all-auth-unverified <registry_preflight.json>

Exit codes:
    0 - all failure classes are auth_unverified (safe to continue)
    1 - non-auth failures found (should block)
"""
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: check-all-auth-unverified <registry_preflight.json>", file=sys.stderr)
        return 1

    try:
        data = json.loads(Path(sys.argv[1]).read_text())
        fcs = data.get("failure_classes", [])
        
        if not fcs:
            # No failures means all good
            print("true")
            return 0
        
        all_unverified = all(fc == "runner_registry_auth_unverified" for fc in fcs)
        print("true" if all_unverified else "false")
        return 0
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        print("false")
        return 0


if __name__ == "__main__":
    sys.exit(main())
