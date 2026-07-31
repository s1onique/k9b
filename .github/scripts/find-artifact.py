#!/usr/bin/env python3
"""Find artifact by exact name.

Usage:
    find-artifact.py <run_id> <artifact_name> <repo>

Outputs artifact_id to GITHUB_OUTPUT.
"""
import json
import sys
import urllib.request


def main() -> None:
    if len(sys.argv) != 4:
        print("FATAL: wrong number of arguments", file=sys.stderr)
        sys.exit(1)

    run_id = sys.argv[1]
    artifact_name = sys.argv[2]
    repo = sys.argv[3]

    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/artifacts",
        headers={
            "Authorization": f"Bearer {sys.argv[5]}" if len(sys.argv) > 5 else "",
            "Accept": "application/vnd.github.v3+json"
        }
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    for a in data.get("artifacts", []):
        if a["name"] == artifact_name:
            with open("$GITHUB_OUTPUT", "a") as f:
                f.write(f"artifact_id={a['id']}\n")
            return

    print("FATAL: no exact artifact match", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
