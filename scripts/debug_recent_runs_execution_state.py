#!/usr/bin/env python3
"""
debug_recent_runs_execution_state.py

Python implementation of the debug diagnostic script for Recent Runs vs Work List
execution state discrepancies in k9b.

Usage:
    python scripts/debug_recent_runs_execution_state.py --base-url https://preprod... --run-id health-run-...

Exit codes:
    0   Success (diagnostics collected)
    2   Missing required arguments
    3   Invalid run_id
    4   API errors (all endpoints failed)
    5   Partial failure (some endpoints failed, check summary.md)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.scripts.debug_http_client import HttpClient, fetch_and_save

DEFAULT_TIMEOUT = 30


def validate_run_id(run_id: str) -> tuple[bool, str | None]:
    """Validate run_id to prevent path traversal."""
    if not run_id:
        return False, "ERROR: run_id cannot be empty"
    
    if ".." in run_id or "/" in run_id or "\\" in run_id:
        return False, f"ERROR: run_id contains path traversal pattern: {run_id}"
    
    if "\0" in run_id:
        return False, "ERROR: run_id contains null byte"
    
    if not re.match(r'^[a-zA-Z0-9_-]+$', run_id):
        return False, (
            f"ERROR: run_id contains invalid characters: {run_id}\n"
            f"       Allowed: alphanumeric, hyphen, underscore"
        )
    
    return True, None


def has_value(value: object) -> bool:
    """Check if value is present (not null/empty)."""
    if value is None:
        return False
    if value == "null":
        return False
    if value == "empty":
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def generate_summary(
    run_id: str,
    base_url: str,
    timestamp: str,
    output_dir: Path,
) -> None:
    """Generate summary.md with root-cause hints."""
    summary_file = output_dir / "summary.md"
    
    recent_runs_debug_file = output_dir / "recent-runs-debug.json"
    execution_summary_file = output_dir / "execution-summary-diagnostics.json"
    worklist_file = output_dir / "worklist-run-payload.json"
    
    recent_runs_debug = {}
    execution_summary = {}
    worklist_available = False
    
    try:
        if recent_runs_debug_file.exists():
            recent_runs_debug = json.loads(recent_runs_debug_file.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    
    try:
        if execution_summary_file.exists():
            execution_summary = json.loads(execution_summary_file.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    
    try:
        if worklist_file.exists():
            json.loads(worklist_file.read_text())
            worklist_available = True
    except (json.JSONDecodeError, OSError):
        pass
    
    runs: list[dict[str, object]] = recent_runs_debug.get('runs', [])
    run_row: dict[str, object] = next((r for r in runs if r.get('runId') == run_id), {})
    
    diag_selected_source = execution_summary.get('selected_source')
    diag_plan_data = execution_summary.get('plan_data_in_index')
    diag_execution_indices = execution_summary.get('execution_indices_in_index')
    diag_parsed_count = execution_summary.get('parsed_execution_indices_count', 0)
    diag_plan_count = execution_summary.get('plan_candidate_count', 0)
    diag_computed_summary = execution_summary.get('computed_execution_summary')
    diag_stale_index = execution_summary.get('stale_index_detected', False)
    diag_ui_index_gen = execution_summary.get('ui_index_generated_at')
    diag_ui_index_mtime = execution_summary.get('ui_index_mtime')
    diag_newest_exec_mtime = execution_summary.get('newest_execution_artifact_mtime')
    diag_missing_reason = execution_summary.get('reason_execution_summary_missing')
    
    rr_run_id = run_row.get('runId')
    rr_review_status = run_row.get('reviewStatus')
    rr_batch_eligible = run_row.get('batchEligibility')
    rr_batch_executable = run_row.get('batchExecutable')
    rr_batch_eligible_count = run_row.get('batchEligibleCount')
    rr_execution_summary = run_row.get('executionSummary')
    
    lines = [
        "# Recent Runs Execution State Diagnostic Summary",
        "",
        f"**Generated:** {timestamp}",
        f"**Run ID:** `{run_id}`",
        f"**Base URL:** `{base_url}`",
        "",
        "---",
        "",
        "## Recent Runs Row",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| runId | `{rr_run_id}` |",
        f"| reviewStatus | `{rr_review_status}` |",
        f"| batchEligibility | `{rr_batch_eligible}` |",
        f"| batchExecutable | `{rr_batch_executable}` |",
        f"| batchEligibleCount | `{rr_batch_eligible_count}` |",
        f"| executionSummary | `{rr_execution_summary}` |",
        "",
        "## Diagnostic Fields (from /api/debug/runs/{run_id}/execution-summary)",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| selected_source | `{diag_selected_source}` |",
        f"| plan_data_in_index | `{diag_plan_data}` |",
        f"| execution_indices_in_index | `{diag_execution_indices}` |",
        f"| parsed_execution_indices_count | `{diag_parsed_count}` |",
        f"| plan_candidate_count | `{diag_plan_count}` |",
        f"| computed_execution_summary | `{diag_computed_summary}` |",
        f"| stale_index_detected | `{diag_stale_index}` |",
        f"| ui_index_generated_at | `{diag_ui_index_gen}` |",
        f"| ui_index_mtime | `{diag_ui_index_mtime}` |",
        f"| newest_execution_artifact_mtime | `{diag_newest_exec_mtime}` |",
        f"| reason_execution_summary_missing | `{diag_missing_reason}` |",
        "",
        "---",
        "",
        "## Root-Cause Hints",
        "",
        "Check the conditions below that apply to your situation:",
        "",
        "### Likely Causes (check if TRUE)",
        "",
    ]
    
    if not has_value(diag_selected_source):
        lines.extend([
            "- **debug endpoint disabled**: The /api/debug/runs/{run_id}/execution-summary",
            "  endpoint returned no data. Verify that K9B_ENABLE_DEBUG_ENDPOINTS=true in preprod.",
            "",
        ])
    
    if diag_stale_index:
        lines.extend([
            "- **stale index suspected**: The UI index appears to be stale relative to",
            "  execution artifacts. Check ui_index_generated_at vs newest_execution_artifact_mtime.",
            "  Consider running: scripts/update_ui_index.py --runs-dir runs/health",
            "",
        ])
    
    if not has_value(diag_plan_data) or diag_plan_data is False:
        lines.extend([
            "- **plan data missing**: The next-check plan is not in the UI index.",
            "  Without plan data, execution summary cannot be computed.",
            "",
        ])
    
    if not has_value(diag_execution_indices) or diag_execution_indices is False:
        lines.extend([
            "- **execution indices missing**: Execution artifacts are not indexed.",
            "  The UI index may be stale or not properly updated after execution.",
            "",
        ])
    
    if not has_value(rr_run_id):
        lines.extend([
            f"- **Recent Runs row missing**: The run ID {run_id} was not found in Recent Runs.",
            "  The run may have been cleaned up or the list is stale.",
            "",
        ])
    
    if has_value(diag_computed_summary) and not has_value(rr_execution_summary):
        lines.extend([
            "- **backend summary correct but frontend may be stale**: The debug endpoint",
            "  computed a valid execution_summary but Recent Runs row shows null.",
            "  This suggests a caching or synchronization issue.",
            "",
        ])
    
    lines.extend([
        "### Files Collected",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| recent-runs-debug.json | Full /api/runs payload with debug params |",
        "| recent-runs-row.json | Row for target run from Recent Runs list |",
        "| runs-debug-block.json | _debug_execution_summary block from Recent Runs |",
        "| execution-summary-diagnostics.json | Dedicated debug endpoint payload |",
        f"| worklist-run-payload.json | Selected run / Work list payload "
        f"{'(available)' if worklist_available else '(not available)'} |",
        "",
        "### Next Steps",
        "",
        "1. Review the root-cause hints above that apply to your situation",
        "2. Check the raw JSON files for detailed field values",
        "3. If debug endpoint is disabled, enable it with: K9B_ENABLE_DEBUG_ENDPOINTS=true",
        "4. If stale index, consider rebuilding the UI index:",
        "   ```bash",
        "   .venv/bin/python scripts/update_ui_index.py --runs-dir runs/health",
        "   ```",
        "5. Attach this summary and relevant JSON files to any issue or ACT response",
    ])
    
    summary_file.write_text('\n'.join(lines))
    print(f"[{datetime.now(UTC).isoformat()}] Summary written to: {summary_file}")


def run_debug(
    base_url: str,
    run_id: str,
    worklist_url: str | None = None,
    output_dir: Path | None = None,
    insecure: bool = False,
    token: str | None = None,
    headers: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> int:
    """Run the debug diagnostic collection."""
    client = HttpClient(
        timeout=timeout,
        insecure=insecure,
        headers=headers,
        token=token,
        verbose=verbose,
    )
    
    timestamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S')
    if output_dir is None:
        output_dir = Path(f"runs/debug/recent-runs-execution/{timestamp}-{run_id}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{datetime.now(UTC).isoformat()}] Output directory: {output_dir}")
    
    timestamp_iso = datetime.now(UTC).isoformat()
    failed_count = 0
    
    # Recent Runs payload
    recent_runs_url = f"{base_url.rstrip('/')}/api/runs?include_batch_eligibility=true&debug_execution_summary=true"
    recent_runs_debug_file = output_dir / "recent-runs-debug.json"
    ok, failed_count = fetch_and_save(client, recent_runs_url, recent_runs_debug_file, "Recent Runs debug payload", failed_count)
    
    # Extract run row
    recent_runs_row_file = output_dir / "recent-runs-row.json"
    if recent_runs_debug_file.exists():
        try:
            data = json.loads(recent_runs_debug_file.read_text())
            run_row = next((r for r in data.get('runs', []) if r.get('runId') == run_id), None)
            if run_row:
                recent_runs_row_file.write_text(json.dumps(run_row, indent=2))
                print(f"[{datetime.now(UTC).isoformat()}]   OK: row saved to {recent_runs_row_file}")
            else:
                recent_runs_row_file.write_text(json.dumps({}))
                print(f"[{datetime.now(UTC).isoformat()}]   WARNING: Run ID not found in Recent Runs list")
        except (json.JSONDecodeError, OSError):
            recent_runs_row_file.write_text(json.dumps({}))
    else:
        recent_runs_row_file.write_text(json.dumps({}))
    
    # Extract debug block
    runs_debug_block_file = output_dir / "runs-debug-block.json"
    if recent_runs_debug_file.exists():
        try:
            data = json.loads(recent_runs_debug_file.read_text())
            debug_block = data.get('_debug_execution_summary')
            runs_debug_block_file.write_text(json.dumps(debug_block, indent=2) if debug_block is not None else "null")
        except (json.JSONDecodeError, OSError):
            runs_debug_block_file.write_text("null")
    else:
        runs_debug_block_file.write_text("null")
    
    # Execution summary diagnostics
    diag_url = f"{base_url.rstrip('/')}/api/debug/runs/{run_id}/execution-summary"
    diag_file = output_dir / "execution-summary-diagnostics.json"
    _, failed_count = fetch_and_save(client, diag_url, diag_file, "Execution summary diagnostics", failed_count)
    
    # Worklist payload
    worklist_file = output_dir / "worklist-run-payload.json"
    if worklist_url is None:
        worklist_url = f"{base_url.rstrip('/')}/api/run?run_id={run_id}"
    
    print(f"[{datetime.now(UTC).isoformat()}] Fetching: Work list / selected run payload")
    data, http_code, error = client.fetch_json(worklist_url)
    
    if error and http_code == 0:
        print(f"[{datetime.now(UTC).isoformat()}]   WARNING: Work list fetch failed ({error}), continuing...")
        worklist_file.write_text(json.dumps({"error": error}, indent=2))
    elif http_code >= 400:
        print(f"[{datetime.now(UTC).isoformat()}]   WARNING: Work list returned HTTP {http_code}, continuing...")
        worklist_file.write_text(json.dumps({"error": f"HTTP {http_code}"}, indent=2))
    elif data is None:
        print(f"[{datetime.now(UTC).isoformat()}]   WARNING: Work list output is not valid JSON")
        worklist_file.write_text(json.dumps({"error": "Invalid JSON response"}, indent=2))
    else:
        worklist_file.write_text(json.dumps(data if data else {}, indent=2))
        print(f"[{datetime.now(UTC).isoformat()}]   OK: saved to {worklist_file}")
    
    generate_summary(run_id, base_url, timestamp_iso, output_dir)
    
    print("", file=sys.stderr)
    print(f"[{datetime.now(UTC).isoformat()}] ==============================================", file=sys.stderr)
    
    if failed_count == 0:
        print(f"[{datetime.now(UTC).isoformat()}] Diagnostics collected successfully")
        print(f"[{datetime.now(UTC).isoformat()}] Summary: {output_dir / 'summary.md'}")
        return 0
    elif failed_count < 4:
        print(f"[{datetime.now(UTC).isoformat()}] Partial success: {failed_count} endpoint(s) failed")
        print(f"[{datetime.now(UTC).isoformat()}] Summary: {output_dir / 'summary.md'}")
        return 5
    else:
        print(f"[{datetime.now(UTC).isoformat()}] All endpoints failed - check connectivity and K9B_ENABLE_DEBUG_ENDPOINTS=true")
        return 4


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Debug Recent Runs vs Work List execution state discrepancies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/debug_recent_runs_execution_state.py --base-url https://preprod.example.com --run-id health-run-20260515T073859Z
  python scripts/debug_recent_runs_execution_state.py --base-url https://preprod.example.com --run-id health-run-... --token "$K9B_TOKEN"
  python scripts/debug_recent_runs_execution_state.py --base-url https://preprod.example.com --run-id health-run-... --insecure
        """,
    )
    
    parser.add_argument('--base-url', required=True, help='Backend base URL (required)')
    parser.add_argument('--run-id', required=True, help='Target run ID (required)')
    parser.add_argument('--worklist-url', help='Work list endpoint (optional, auto-detected)')
    parser.add_argument('--output-dir', type=Path, help='Output directory')
    parser.add_argument('--insecure', action='store_true', help='Skip TLS verification (-k)')
    parser.add_argument('--token', help='Bearer token for auth')
    parser.add_argument('--bearer-token', dest='bearer_token', help='Alias for --token')
    parser.add_argument('--header', action='append', default=[], help='Additional header (repeatable)')
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT, help='Request timeout in seconds')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    
    args = parser.parse_args()
    token = args.token or args.bearer_token
    
    is_valid, error_msg = validate_run_id(args.run_id)
    if not is_valid:
        print(error_msg, file=sys.stderr)
        return 3
    
    return run_debug(
        base_url=args.base_url,
        run_id=args.run_id,
        worklist_url=args.worklist_url,
        output_dir=args.output_dir,
        insecure=args.insecure,
        token=token,
        headers=args.header,
        timeout=args.timeout,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    sys.exit(main())
