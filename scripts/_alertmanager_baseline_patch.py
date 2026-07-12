#!/usr/bin/env python3
"""Surgically patch the OpenAPI baseline with only the AlertManager-source
changes.

This avoids the unrelated baseline drift that would result from regenerating
the entire OpenAPI schema. Only the following Alertmanager-source changes are
applied:

* ``perform_alertmanager_source_action`` path key changes from
  ``/api/runs/{run_id}/alertmanager-sources/{source_id}/action`` to
  ``/api/runs/{run_id}/alertmanager-sources/action`` (sourceId moves into
  the JSON request body and the tag changes from ``incidents`` to
  ``alertmanager``).
* New paths are added:
    - ``/api/runs/{run_id}/alertmanager-sources/review-packet``
    - ``/api/runs/{run_id}/alertmanager-sources/debug-packet``
    - ``/api/runs/{run_id}/alertmanager-sources/debug-packet/probe``
    - ``/api/runs/{run_id}/alertmanager-sources/promotion-review``
* The ``alertmanager`` tag description is added to the schema's top-level
  ``tags`` array (no other tag entries are touched).

All other paths and operations in the baseline are preserved exactly as they
appear in the previous committed snapshot. Unrelated baseline drift
(e.g. descriptions for unrelated request bodies) is intentionally NOT
included in this ACT.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "docs/api/openapi/k9b-openapi-baseline.json"
SOURCE = REPO_ROOT / "build/openapi/k9b-openapi.json"

OLD_ACTION_PATH = "/api/runs/{run_id}/alertmanager-sources/{source_id}/action"
NEW_ACTION_PATH = "/api/runs/{run_id}/alertmanager-sources/action"

NEW_PATHS: tuple[str, ...] = (
    "/api/runs/{run_id}/alertmanager-sources/review-packet",
    "/api/runs/{run_id}/alertmanager-sources/debug-packet",
    "/api/runs/{run_id}/alertmanager-sources/debug-packet/probe",
    "/api/runs/{run_id}/alertmanager-sources/promotion-review",
)


def main() -> int:
    if not BASELINE.exists():
        print(f"baseline not found: {BASELINE}", file=sys.stderr)
        return 1
    if not SOURCE.exists():
        print(f"current schema not found: {SOURCE}", file=sys.stderr)
        return 1

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = json.loads(SOURCE.read_text(encoding="utf-8"))

    paths = baseline.setdefault("paths", {})

    # Move/rename perform_alertmanager_source_action from the old source_id
    # path to the new body-based path.
    if OLD_ACTION_PATH in paths:
        new_action = current["paths"].get(NEW_ACTION_PATH)
        if new_action is None:
            print(
                f"current schema missing {NEW_ACTION_PATH}; "
                f"refusing to patch baseline",
                file=sys.stderr,
            )
            return 1
        paths.pop(OLD_ACTION_PATH)
        paths[NEW_ACTION_PATH] = new_action

    # Add the other four Alertmanager-source paths from the current schema.
    for path in NEW_PATHS:
        new_op = current["paths"].get(path)
        if new_op is None:
            print(
                f"current schema missing {path}; refusing to patch baseline",
                file=sys.stderr,
            )
            return 1
        paths[path] = new_op

    # Add (or update) the alertmanager tag description without touching any
    # other tag entry.
    tag_names = {t["name"] for t in baseline.get("tags", [])}
    if "alertmanager" not in tag_names:
        baseline.setdefault("tags", []).append(
            {
                "name": "alertmanager",
                "description": (
                    "AlertManager source discovery, review, debug, and action "
                    "endpoints. All AlertManager-source operations live under "
                    "this single tag."
                ),
            }
        )

    # Re-emit deterministically: sorted keys, two-space indent, trailing
    # newline. Matches the format used by ``export_openapi_schema.py``.
    BASELINE.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Patched baseline at {BASELINE}")
    print(f"  - moved {OLD_ACTION_PATH} -> {NEW_ACTION_PATH}")
    print(f"  - added {len(NEW_PATHS)} new alertmanager-source paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
