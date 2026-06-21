#!/usr/bin/env python3
"""
Verification orchestrator - plan execution and lane process orchestration.

This module handles:
- Plan generation via verify_profile_plan.emit_full_plan
- Parallel lane execution
- Runner failure propagation
- Lane-state initialization and final state loading
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

# Add scripts to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from verify_profile_plan import emit_full_plan


@dataclass
class LaneResult:
    """Result from a single lane execution."""
    lane: str
    success: bool
    exit_code: int
    duration_ms: int
    step_count: int = 0
    failed_count: int = 0


@dataclass
class VerificationResult:
    """Result from full verification run."""
    success: bool
    profile: str
    scope: str
    is_full_gate: bool
    is_full_lane: bool
    step_count: int
    skipped_count: int
    total_duration_ms: int
    lane_results: list[LaneResult] = field(default_factory=list)
    lane_state: dict = field(default_factory=dict)
    skipped: list[dict] = field(default_factory=list)
    error_message: str | None = None
    
    def to_json(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "profile": self.profile,
            "scope": self.scope,
            "is_full_gate": self.is_full_gate,
            "is_full_lane": self.is_full_lane,
            "success": self.success,
            "step_count": self.step_count,
            "skipped_count": self.skipped_count,
            "total_duration_ms": self.total_duration_ms,
            "lanes": {
                lr.lane: {
                    "success": lr.success,
                    "exit_code": lr.exit_code,
                    "duration_ms": lr.duration_ms,
                    "step_count": lr.step_count,
                    "failed_count": lr.failed_count,
                }
                for lr in self.lane_results
            },
            "skipped": self.skipped,
        }


class VerificationOrchestrator:
    """
    Orchestrates verification plan execution across lanes.
    
    Handles:
    - Plan generation and validation
    - Parallel lane execution via subprocess
    - Lane state tracking and aggregation
    - Failure propagation
    """
    
    def __init__(
        self,
        repo_root: str | Path,
        profile: str = "fast",
        scope: str = "all",
        json_mode: bool = False,
    ):
        self.repo_root = Path(repo_root)
        self.profile = profile
        self.scope = scope
        self.json_mode = json_mode
        self.timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.plan_file: Path | None = None
        self.lane_state_file: Path | None = None
        self.step_log_dir = self.repo_root / "runs" / "verification"
        self._plan: dict | None = None
        self._start_time: float | None = None
    
    def setup(self) -> None:
        """Set up the verification run (directories, plan, state)."""
        # Ensure directories exist
        self.step_log_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate plan
        self._generate_plan()
        
        # Initialize lane state file
        self._init_lane_state()
    
    def _generate_plan(self) -> None:
        """Generate and validate the execution plan."""
        try:
            self._plan = emit_full_plan(self.profile, self.scope)
        except Exception as e:
            print(f"ERROR: Failed to generate plan: {e}", file=sys.stderr)
            sys.exit(1)
        
        # Write plan to temp file for lane runners
        fd, plan_file_str = tempfile.mkstemp(suffix=".json", prefix=".verify_plan_")
        self.plan_file = Path(plan_file_str)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._plan, f)
        except Exception as e:
            if self.plan_file:
                os.unlink(self.plan_file)
            print(f"ERROR: Failed to write plan file: {e}", file=sys.stderr)
            sys.exit(1)
    
    def _init_lane_state(self) -> None:
        """Initialize the lane state file."""
        state_dir = self.step_log_dir
        self.lane_state_file = state_dir / f"{self.timestamp}-lane-state.json"
        
        # Write initial empty state
        initial_state = {"python": [], "frontend": [], "helm": []}
        try:
            with open(self.lane_state_file, "w") as f:
                json.dump(initial_state, f)
        except Exception as e:
            print(f"ERROR: Failed to initialize lane state: {e}", file=sys.stderr)
            sys.exit(1)
    
    def get_lanes_to_run(self) -> list[str]:
        """Get the list of lanes to run based on scope."""
        if self.scope == "all":
            return ["python", "frontend", "helm"]
        return [self.scope]
    
    def execute(self) -> VerificationResult:
        """
        Execute the verification plan.
        
        Returns VerificationResult with aggregated results.
        """
        self._start_time = time.time()
        
        lanes = self.get_lanes_to_run()
        lane_processes: list[tuple[str, subprocess.Popen]] = []
        lane_results: list[LaneResult] = []
        
        # Set environment for lane runners
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = str(self.step_log_dir)
        env["STEP_RUN_TIMESTAMP"] = self.timestamp
        if self.json_mode:
            env["STEP_JSON_MODE"] = "1"
        
        # Spawn lane runners in parallel
        for lane in lanes:
            try:
                process = self._spawn_lane_runner(lane, env)
                lane_processes.append((lane, process))
            except Exception as e:
                print(f"ERROR: Failed to spawn {lane} lane: {e}", file=sys.stderr)
                lane_results.append(LaneResult(
                    lane=lane,
                    success=False,
                    exit_code=1,
                    duration_ms=0,
                    step_count=0,
                    failed_count=0,
                ))
        
        # Wait for all lanes to complete
        for lane, process in lane_processes:
            try:
                exit_code = process.wait()
                success = exit_code == 0
                
                # Calculate duration (approximation based on file timestamps)
                duration_ms = self._get_lane_duration(lane)
                
                # Get step counts from lane state
                step_count, failed_count = self._get_lane_stats(lane)
                
                lane_results.append(LaneResult(
                    lane=lane,
                    success=success,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    step_count=step_count,
                    failed_count=failed_count,
                ))
            except Exception as e:
                print(f"ERROR: Waiting for {lane} lane: {e}", file=sys.stderr)
                lane_results.append(LaneResult(
                    lane=lane,
                    success=False,
                    exit_code=1,
                    duration_ms=0,
                    step_count=0,
                    failed_count=0,
                ))
        
        # Load final lane state
        lane_state = self._load_lane_state()
        
        # Calculate total duration
        total_duration_ms = int((time.time() - self._start_time) * 1000) if self._start_time else 0
        
        # Determine overall success
        overall_success = all(lr.success for lr in lane_results)
        
        # Check for any failures in lane state
        total_failed = sum(
            1 for lane_data in lane_state.values()
            for step in (lane_data if isinstance(lane_data, list) else [])
            if isinstance(step, dict) and step.get("status") == "FAIL"
        )
        if total_failed > 0:
            overall_success = False
        
        # Build result
        result = VerificationResult(
            success=overall_success,
            profile=self._plan.get("profile", self.profile) if self._plan else self.profile,
            scope=self._plan.get("scope", self.scope) if self._plan else self.scope,
            is_full_gate=self._plan.get("is_full_gate", False) if self._plan else False,
            is_full_lane=self._plan.get("is_full_lane", False) if self._plan else False,
            step_count=self._plan.get("step_count", 0) if self._plan else 0,
            skipped_count=self._plan.get("skipped_count", 0) if self._plan else 0,
            total_duration_ms=total_duration_ms,
            lane_results=lane_results,
            lane_state=lane_state,
            skipped=self._plan.get("skipped", []) if self._plan else [],
        )
        
        # Cleanup plan file
        if self.plan_file and self.plan_file.exists():
            try:
                self.plan_file.unlink()
            except OSError:
                pass
        
        return result
    
    def _spawn_lane_runner(self, lane: str, env: dict) -> subprocess.Popen:
        """Spawn a lane runner process."""
        python = self.repo_root / ".venv" / "bin" / "python"
        
        # Fallback to system python if venv not available
        if not python.exists():
            python = Path(sys.executable)
        
        cmd = [
            str(python),
            str(SCRIPT_DIR / "verify_profile_runner.py"),
            lane,
            str(self.plan_file),
        ]
        
        return subprocess.Popen(
            cmd,
            env=env,
            cwd=str(self.repo_root),
            stdout=subprocess.PIPE if self.json_mode else None,
            stderr=subprocess.PIPE if self.json_mode else None,
        )
    
    def _load_lane_state(self) -> dict:
        """Load the final lane state from file.
        
        FAIL-CLOSED: Missing or corrupt lane state is a hard failure.
        """
        if not self.lane_state_file:
            raise RuntimeError("Lane state file not initialized")
        
        if not self.lane_state_file.exists():
            raise RuntimeError(f"Lane state file not found: {self.lane_state_file}")
        
        try:
            with open(self.lane_state_file) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Lane state file is corrupt (invalid JSON): {self.lane_state_file}: {e}")
        except OSError as e:
            raise RuntimeError(f"Failed to read lane state file: {self.lane_state_file}: {e}")
    
    def _get_lane_stats(self, lane: str) -> tuple[int, int]:
        """Get step and failure counts for a lane from lane state."""
        state = self._load_lane_state()
        lane_data = state.get(lane, [])
        if not isinstance(lane_data, list):
            return 0, 0
        
        step_count = len(lane_data)
        failed_count = sum(1 for s in lane_data if isinstance(s, dict) and s.get("status") == "FAIL")
        return step_count, failed_count
    
    def _get_lane_duration(self, lane: str) -> int:
        """Get total duration for a lane in milliseconds."""
        state = self._load_lane_state()
        lane_data = state.get(lane, [])
        if not isinstance(lane_data, list):
            return 0
        
        return sum(
            s.get("duration_ms", 0)
            for s in lane_data
            if isinstance(s, dict)
        )


def run_verification(
    repo_root: str | Path,
    profile: str = "fast",
    scope: str = "all",
    json_mode: bool = False,
) -> VerificationResult:
    """
    Run the verification gate.
    
    Args:
        repo_root: Repository root directory
        profile: Verification profile (fast or full)
        scope: Lane scope (all, python, frontend, helm)
        json_mode: If True, suppress human-readable output
        
    Returns:
        VerificationResult with aggregated results
    """
    orchestrator = VerificationOrchestrator(
        repo_root=repo_root,
        profile=profile,
        scope=scope,
        json_mode=json_mode,
    )
    orchestrator.setup()
    return orchestrator.execute()


# Main entry point for lane runner (called by orchestrator)
if __name__ == "__main__":
    # This can be run directly for lane debugging
    if len(sys.argv) < 3:
        print("Usage: verify_all_orchestrator.py <repo_root> <profile> [scope] [json_mode]")
        sys.exit(1)
    
    repo_root = sys.argv[1]
    profile = sys.argv[2] if len(sys.argv) > 2 else "fast"
    scope = sys.argv[3] if len(sys.argv) > 3 else "all"
    json_mode = len(sys.argv) > 4 and sys.argv[4] == "1"
    
    result = run_verification(
        repo_root=repo_root,
        profile=profile,
        scope=scope,
        json_mode=json_mode,
    )
    
    if json_mode:
        print(json.dumps(result.to_json()))
    else:
        if result.success:
            print(f"VERIFICATION GATE [{result.profile}]: PASSED")
        else:
            print(f"VERIFICATION GATE [{result.profile}]: FAILED", file=sys.stderr)
    
    sys.exit(0 if result.success else 1)