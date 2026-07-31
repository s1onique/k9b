#!/usr/bin/env python3
"""Emit outputs from downloaded authorization record.

Reads auth record from artifacts/auth_extracted/ and emits GITHUB_OUTPUT.
"""
import json
import sys
from pathlib import Path


def main() -> None:
    paths = list(Path("artifacts/auth_extracted").glob("*.json"))
    if not paths:
        print("FATAL: no JSON in auth artifact")
        sys.exit(1)
    if len(paths) > 1:
        print("FATAL: multiple JSON files in auth artifact")
        sys.exit(1)

    data = json.loads(paths[0].read_text())

    with open("$GITHUB_OUTPUT", "a") as f:
        f.write(f"subject_sha={data['subject_sha']}\n")
        f.write(f"backend_image_ref={data['backend_image_ref']}\n")
        f.write(f"scheduler_image_ref={data['scheduler_image_ref']}\n")
        f.write(f"frontend_image_ref={data['frontend_image_ref']}\n")
        f.write(f"artifact_digest={data.get('artifact_digest', '')}\n")
        f.write(f"upstream_run_id={data['upstream_run_id']}\n")
        f.write(f"upstream_run_attempt={data['upstream_run_attempt']}\n")

    print("AUTH_OUTPUTS_EMITTED=ok")


if __name__ == "__main__":
    main()
