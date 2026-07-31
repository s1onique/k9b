#!/usr/bin/env python3
"""Write authorization record with full provenance.

Usage:
    write-auth-record.py <record_sha> <current_main> <auth_status>
        <backend_ref> <scheduler_ref> <frontend_ref> <upstream_sha>
        <upstream_run_id> <upstream_run_attempt>

All values passed via argv to avoid GitHub expression syntax in source.
"""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 10:
        print("FATAL: wrong number of arguments", file=sys.stderr)
        sys.exit(1)

    record_sha, current_main, auth_status, backend_ref, scheduler_ref, \
        frontend_ref, upstream_sha, upstream_run_id, upstream_run_attempt = sys.argv[1:]

    record = {
        "schema_version": "1.0",
        "authorization_status": auth_status,
        "subject_sha": upstream_sha,
        "upstream_run_id": upstream_run_id,
        "upstream_run_attempt": upstream_run_attempt,
        "current_main_sha": current_main,
        "backend_image_ref": backend_ref,
        "scheduler_image_ref": scheduler_ref,
        "frontend_image_ref": frontend_ref,
        "record_sha256": record_sha,
        "bridge_sha": Path(".git/HEAD").read_text().strip(),
        "bridge_run_id": datetime.now(UTC).isoformat(),
        "authorization_time": datetime.now(UTC).isoformat(),
    }

    output_path = Path("artifacts/experimental-lab-deploy-authorization.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2) + "\n")
    print(f"AUTH_RECORD_WRITTEN={output_path}")

if __name__ == "__main__":
    main()
