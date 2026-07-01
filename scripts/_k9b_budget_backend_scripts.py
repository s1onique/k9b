"""Backend container budget reset/status scripts.

These scripts run INSIDE the k9b backend container to perform budget operations.
They are passed via kubectl exec -- python -c.
"""

from __future__ import annotations

_BACKEND_RESET_SCRIPT = """
import json
import sys
from pathlib import Path

incident_id = sys.argv[1]
backend_runs_dir = sys.argv[2]
external_dir = Path(backend_runs_dir) / "health" / "external-analysis"

suffixes = (
    "-diagnosis-review-packet.json",
    "-diagnosis-loop-pass.json",
    "-read-only-check-result.json",
    "-next-check-budget.json",
)

def matches_artifact(name):
    if not name.startswith(f"auto-{incident_id}-"):
        return False
    return name.endswith(suffixes)

removed = []
if external_dir.exists():
    for path in external_dir.rglob("*"):
        if path.is_file() and matches_artifact(path.name):
            try:
                path.unlink()
                removed.append(str(path.relative_to(external_dir)))
            except OSError:
                pass

result = {
    "removed_count": len(removed),
    "removed_paths": removed,
    "external_dir_exists": external_dir.exists(),
}
print(json.dumps(result))
"""

_BACKEND_STATUS_SCRIPT = """
import json
import sys
from pathlib import Path

incident_id = sys.argv[1]
backend_runs_dir = sys.argv[2]
external_dir = Path(backend_runs_dir) / "health" / "external-analysis"

suffixes = (
    "-diagnosis-review-packet.json",
    "-diagnosis-loop-pass.json",
    "-read-only-check-result.json",
    "-next-check-budget.json",
)

def matches_artifact(name):
    if not name.startswith(f"auto-{incident_id}-"):
        return False
    return name.endswith(suffixes)

review_packet_count = 0
loop_pass_count = 0
other_count = 0
review_packet_paths = []
loop_pass_paths = []
other_paths = []

if external_dir.exists():
    for path in external_dir.rglob("*"):
        if path.is_file() and matches_artifact(path.name):
            name = path.name
            if name.endswith("-diagnosis-review-packet.json"):
                review_packet_count += 1
                review_packet_paths.append(str(path.relative_to(external_dir)))
            elif name.endswith("-diagnosis-loop-pass.json"):
                loop_pass_count += 1
                loop_pass_paths.append(str(path.relative_to(external_dir)))
            else:
                other_count += 1
                other_paths.append(str(path.relative_to(external_dir)))

budget_exhausted = review_packet_count > 0
result = {
    "exists": external_dir.exists(),
    "review_packet_count": review_packet_count,
    "loop_pass_count": loop_pass_count,
    "other_auto_count": other_count,
    "budget_exhausted": budget_exhausted,
    "review_packet_paths": review_packet_paths,
    "loop_pass_paths": loop_pass_paths,
    "other_paths": other_paths,
}
print(json.dumps(result))
"""
