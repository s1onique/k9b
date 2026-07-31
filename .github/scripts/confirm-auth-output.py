#!/usr/bin/env python3
"""Emit outputs from downloaded authorization record."""
import json
import os
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        print("FATAL: expected 2 args", file=sys.stderr)
        sys.exit(1)

    current_main = sys.argv[1]
    paths = list(Path("artifacts/auth_extracted").glob("experimental-lab-deploy-authorization.json"))

    if not paths:
        print("FATAL: no auth JSON")
        sys.exit(1)

    data = json.loads(paths[0].read_text())

    if data.get("current_main_sha") != current_main:
        print("FATAL: main SHA mismatch in second barrier")
        sys.exit(1)

    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
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
