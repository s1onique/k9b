#!/usr/bin/env python3
"""Export k9b OpenAPI schema to a deterministic JSON file.

This script generates the canonical OpenAPI schema from the backend registry
and writes it to a stable output path. The schema is used for:
- TypeScript client generation
- API contract documentation
- CI freshness gates

Run:
    .venv/bin/python scripts/export_openapi_schema.py [--output PATH]

Exit codes:
    0 - Success
    1 - Import or serialization failure
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from k8s_diag_agent.ui.api_contract import build_openapi_schema
except ImportError as e:
    print(f"Error: Failed to import build_openapi_schema: {e}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export k9b OpenAPI schema to JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    .venv/bin/python scripts/export_openapi_schema.py
    .venv/bin/python scripts/export_openapi_schema.py --output build/openapi/k9b-openapi.json
        """,
    )
    parser.add_argument(
        "--output",
        default="build/openapi/k9b-openapi.json",
        help="Output path for the generated OpenAPI JSON schema (default: build/openapi/k9b-openapi.json)",
    )
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        schema = build_openapi_schema()
    except Exception as e:
        print(f"Error: Failed to build OpenAPI schema: {e}", file=sys.stderr)
        return 1

    try:
        # Write deterministic JSON with sorted keys and stable indentation
        output.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"Error: Failed to write schema to {output}: {e}", file=sys.stderr)
        return 1

    print(f"Wrote OpenAPI schema to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
