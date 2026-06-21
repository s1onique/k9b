#!/usr/bin/env python3
"""
Profile runner - executes verification steps from the plan.

The shell calls this to run steps from the Python-generated plan.
Handles step execution, result recording, and JSON-mode output.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add scripts to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))



def run_step(
    lane: str,
    step_id: str,
    command: str,
    description: str,
    plan_file: str,
    skipped_ids: set[str],
    step_log_dir: str,
    lane_state_file: str,
    timestamp: str,
    json_mode: bool = False,
) -> tuple[str, int, int]:
    """
    Run a single verification step.
    
    Returns: (status, duration_ms, exit_code)
    """
    # Check if skipped
    if step_id in skipped_ids:
        record_result(lane_state_file, lane, step_id, "SKIP", 0, 0, step_log_dir, timestamp)
        return "SKIP", 0, 0
    
    log_file = f"{step_log_dir}/{timestamp}-{step_id}.log"
    
    # Run the command
    start = time.time()
    try:
        # Handle different command types
        if command.startswith("bash "):
            cmd = command[5:].strip()
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(SCRIPT_DIR.parent),
                capture_output=True,
                text=True,
            )
        elif command.startswith("npm "):
            # npm commands need bash -c for proper shell handling
            cmd = command  # Keep full command
            result = subprocess.run(
                ["bash", "-c", cmd],
                cwd=str(SCRIPT_DIR.parent / "frontend"),
                capture_output=True,
                text=True,
            )
        elif command.startswith("env "):
            # Parse env variables
            parts = command[4:].split()
            env = {}
            cmd_parts = []
            for part in parts:
                if "=" in part:
                    k, v = part.split("=", 1)
                    env[k] = v
                else:
                    cmd_parts.append(part)
            result = subprocess.run(
                cmd_parts,
                env={**os.environ, **env},
                capture_output=True,
                text=True,
            )
        else:
            # Direct command - parse properly
            import shlex
            cmd_parts = shlex.split(command)
            result = subprocess.run(
                cmd_parts,
                cwd=str(SCRIPT_DIR.parent),
                capture_output=True,
                text=True,
            )
        
        exit_code = result.returncode
        
        # Write log
        with open(log_file, "w") as f:
            f.write(result.stdout)
            if result.stderr:
                f.write("\n--- STDERR ---\n")
                f.write(result.stderr)
        
    except Exception as e:
        with open(log_file, "w") as f:
            f.write(f"ERROR: {e}\n")
        exit_code = 1
    
    duration_ms = int((time.time() - start) * 1000)
    status = "PASS" if exit_code == 0 else "FAIL"
    
    record_result(lane_state_file, lane, step_id, status, duration_ms, exit_code, step_log_dir, timestamp)
    
    return status, duration_ms, exit_code


def record_result(
    lane_state_file: str,
    lane: str,
    step_id: str,
    status: str,
    duration_ms: int,
    exit_code: int,
    step_log_dir: str,
    timestamp: str,
) -> None:
    """Record step result to the shared lane state file with SHARED locking."""
    log_file = f"{step_log_dir}/{timestamp}-{step_id}.log"
    
    step_data = {
        "id": step_id,
        "status": status,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "log_file": log_file,
    }
    
    # Use ONE shared lock file for the state file (not per-lane)
    lock_file = f"{lane_state_file}.lock"
    lock_fd = open(lock_file, "w")
    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
    
    try:
        # Read existing state
        if os.path.exists(lane_state_file):
            try:
                with open(lane_state_file) as f:
                    state = json.load(f)
            except Exception:
                state = {"python": [], "frontend": [], "helm": []}
        else:
            state = {"python": [], "frontend": [], "helm": []}
        
        # Add step to lane
        if lane not in state:
            state[lane] = []
        
        # Check if step already exists
        existing = [i for i, s in enumerate(state[lane]) if s["id"] == step_id]
        if existing:
            state[lane][existing[0]] = step_data
        else:
            state[lane].append(step_data)
        
        # Write back atomically
        tmp_file = f"{lane_state_file}.{os.getpid()}.tmp"
        with open(tmp_file, "w") as f:
            json.dump(state, f)
        os.replace(tmp_file, lane_state_file)
    finally:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
        try:
            os.unlink(lock_file)
        except OSError:
            pass


def main():
    if len(sys.argv) < 3:
        print("Usage: verify_profile_runner.py <lane> <plan_file>", file=sys.stderr)
        sys.exit(1)
    
    lane = sys.argv[1]
    plan_file = sys.argv[2]
    
    # Get environment
    repo_root = os.environ.get("REPO_ROOT", str(SCRIPT_DIR.parent))
    step_log_dir = os.environ.get("STEP_LOG_DIR", f"{repo_root}/runs/verification")
    timestamp = os.environ.get("STEP_RUN_TIMESTAMP", time.strftime("%Y%m%d-%H%M%S"))
    json_mode = os.environ.get("STEP_JSON_MODE") == "1"
    
    lane_state_file = f"{step_log_dir}/{timestamp}-lane-state.json"
    
    # Load plan
    with open(plan_file) as f:
        plan = json.load(f)
    
    # Get skipped steps
    skipped_ids = {s["id"] for s in plan.get("skipped", [])}
    
    # Run each step
    for step in plan.get("lanes", {}).get(lane, []):
        step_id = step["id"]
        command = step["command"]
        description = step["description"]
        
        status, duration_ms, exit_code = run_step(
            lane=lane,
            step_id=step_id,
            command=command,
            description=description,
            plan_file=plan_file,
            skipped_ids=skipped_ids,
            step_log_dir=step_log_dir,
            lane_state_file=lane_state_file,
            timestamp=timestamp,
            json_mode=json_mode,
        )
        
        # Only print human-readable output if not in JSON mode
        if not json_mode:
            if status == "PASS":
                print(f"[{step_id}] PASS ({duration_ms}ms) - {description}")
            elif status == "FAIL":
                print(f"[{step_id}] FAIL ({duration_ms}ms) - {description}", file=sys.stderr)
            else:
                print(f"[{step_id}] SKIP - Skipped by profile")


if __name__ == "__main__":
    main()
