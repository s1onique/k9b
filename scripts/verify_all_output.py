#!/usr/bin/env python3
"""
Verification output formatting - human footer, timing summary, JSON summary.

This module handles:
- Human-readable profile footer display
- Timing summary and .gate-timings.json output
- JSON summary output (stdout purity)
- Failure diagnostics
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from verify_all_orchestrator import VerificationResult


def format_timing_summary(result: VerificationResult) -> str:
    """Format timing summary for human output."""
    lines = []
    
    # Collect all steps with timing info
    all_steps = []
    for lane_data in result.lane_state.values():
        if isinstance(lane_data, list):
            for step in lane_data:
                if isinstance(step, dict):
                    all_steps.append({
                        "id": step.get("id", "unknown"),
                        "lane": list(result.lane_state.keys())[
                            list(result.lane_state.values()).index(lane_data)
                        ],
                        "duration_ms": step.get("duration_ms", 0),
                        "exit_code": step.get("exit_code", -1),
                        "status": step.get("status", "UNKNOWN"),
                    })
    
    # Sort by duration (descending)
    all_steps.sort(key=lambda x: x.get("duration_ms", 0), reverse=True)
    
    total = sum(s.get("duration_ms", 0) for s in all_steps)
    
    lines.append("")
    lines.append("=== Gate Timing Summary ===")
    lines.append(f"Total steps: {len(all_steps)}")
    lines.append(f"Total time: {total}ms ({total/1000:.1f}s)")
    lines.append("")
    lines.append(f"{'Step':<35} {'Duration':>10} {'Lane':<10} {'Exit':>5}")
    lines.append("-" * 65)
    
    for step in all_steps[:10]:
        step_id = step.get("id", "unknown")
        lane = step.get("lane", "?")
        duration_ms = step.get("duration_ms", 0)
        exit_code = step.get("exit_code", -1)
        
        dur = f"{duration_ms}ms"
        if duration_ms >= 1000:
            dur = f"{duration_ms/1000:.1f}s"
        
        lines.append(f"{step_id:<35} {dur:>10} {lane:<10} {exit_code:>5}")
    
    return "\n".join(lines)


def format_profile_footer(result: VerificationResult) -> str:
    """Format the profile footer for human output."""
    lines = []
    
    lines.append("")
    lines.append("═" * 57)
    lines.append(f"VERIFICATION PROFILE: {result.profile}")
    lines.append("═" * 57)
    lines.append(f"Profile: {result.profile}")
    lines.append(f"Steps: {result.step_count}")
    
    # Show skipped if not full gate
    if not result.is_full_gate and result.skipped:
        lines.append("")
        lines.append(f"Skipped ({result.profile} profile excludes expensive suites):")
        for skip in result.skipped:
            step_id = skip.get("id", "unknown") if isinstance(skip, dict) else skip
            reason = skip.get("reason", "Excluded by profile") if isinstance(skip, dict) else "Excluded by profile"
            lines.append(f"  - {step_id} ({reason})")
        
        lines.append("")
        lines.append("For merge-grade verification:")
        lines.append("  ./scripts/verify_all.sh --full")
    
    lines.append("═" * 57)
    lines.append("")
    
    return "\n".join(lines)


def write_gate_timings(result: VerificationResult, repo_root: Path | str) -> None:
    """Write .gate-timings.json file."""
    repo_root = Path(repo_root)
    timings_file = repo_root / ".gate-timings.json"
    
    # Collect all steps
    steps = []
    for lane, lane_data in result.lane_state.items():
        if isinstance(lane_data, list):
            for step in lane_data:
                if isinstance(step, dict):
                    steps.append({
                        "id": step.get("id", "unknown"),
                        "lane": lane,
                        "exit_code": step.get("exit_code", -1),
                        "duration_ms": step.get("duration_ms", 0),
                        "status": step.get("status", "UNKNOWN"),
                    })
    
    total = sum(s.get("duration_ms", 0) for s in steps)
    
    try:
        with open(timings_file, "w") as f:
            json.dump({
                "steps": steps,
                "total_ms": total,
                "profile": result.profile,
                "scope": result.scope,
            }, f, indent=2)
    except OSError as e:
        print(f"WARNING: Failed to write timings file: {e}", file=sys.stderr)


def format_json_output(result: VerificationResult) -> str:
    """Format the JSON output for stdout."""
    output = {
        "run_id": result.timestamp if hasattr(result, 'timestamp') else None,
        "profile": result.profile,
        "scope": result.scope,
        "is_full_gate": result.is_full_gate,
        "is_full_lane": result.is_full_lane,
        "success": result.success,
        "step_count": result.step_count,
        "skipped_count": result.skipped_count,
        "total_duration_ms": result.total_duration_ms,
        "lanes": {},
        "skipped": result.skipped,
    }
    
    # Add lane results
    for lr in result.lane_results:
        output["lanes"][lr.lane] = {
            "success": lr.success,
            "exit_code": lr.exit_code,
            "duration_ms": lr.duration_ms,
            "step_count": lr.step_count,
            "failed_count": lr.failed_count,
        }
    
    return json.dumps(output)


def print_result(
    result: VerificationResult,
    repo_root: Path | str,
    json_mode: bool = False,
) -> None:
    """
    Print the verification result.
    
    In JSON mode, only emit valid JSON to stdout.
    In human mode, emit timing summary, profile footer, and status.
    """
    if json_mode:
        # JSON mode: only stdout is valid JSON
        print(format_json_output(result))
    else:
        # Human mode: timing summary + profile footer + status
        print(format_timing_summary(result))
        print(format_profile_footer(result))
        
        if result.success:
            print(f"VERIFICATION GATE [{result.profile}]: PASSED")
        else:
            print(f"VERIFICATION GATE [{result.profile}]: FAILED", file=sys.stderr)
        
        # Write timings file
        write_gate_timings(result, repo_root)


def emit_final_status(result: VerificationResult) -> int:
    """
    Emit final status and return exit code.
    
    Returns 0 on success, non-zero on failure.
    """
    if result.success:
        print("VERIFICATION GATE: PASSED")
        return 0
    else:
        print("VERIFICATION GATE: FAILED", file=sys.stderr)
        return 1