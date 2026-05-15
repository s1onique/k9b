"""Tests for debug_recent_runs_execution_state.sh script.

These tests verify:
1. Script help works and exits 0
2. Missing required args cause non-zero exit with useful message
3. run_id validation rejects path traversal
4. Script works with fake curl/jq to produce expected output files
5. Root-cause hint generation for various failure scenarios
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

# =============================================================================
# Test fixtures and helpers
# =============================================================================

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
SCRIPT = SCRIPT_DIR / "debug_recent_runs_execution_state.sh"


class TestDebugScriptHelp(unittest.TestCase):
    """Test --help output and basic script behavior."""

    def setUp(self) -> None:
        if not SCRIPT.exists():
            self.skipTest("debug_recent_runs_execution_state.sh not found")

    def test_script_is_executable(self) -> None:
        """Script should be executable."""
        mode = os.stat(SCRIPT).st_mode
        self.assertTrue(mode & 0o111, "script should be executable")

    def test_help_exits_zero(self) -> None:
        """--help should exit with code 0."""
        result = subprocess.run(
            [str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, f"Help should exit 0, got: {result.stderr}")

    def test_help_contains_usage(self) -> None:
        """--help should contain usage information."""
        result = subprocess.run(
            [str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout + result.stderr
        self.assertIn("--base-url", output)
        self.assertIn("--run-id", output)


class TestDebugScriptArgs(unittest.TestCase):
    """Test argument validation."""

    def setUp(self) -> None:
        if not SCRIPT.exists():
            self.skipTest("debug_recent_runs_execution_state.sh not found")

    def test_missing_base_url_exits_nonzero(self) -> None:
        """Missing --base-url should exit with code 2."""
        result = subprocess.run(
            [str(SCRIPT), "--run-id", "health-run-123"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0, "Should fail without --base-url")
        self.assertIn("--base-url", result.stderr + result.stdout)

    def test_missing_run_id_exits_nonzero(self) -> None:
        """Missing --run-id should exit with code 2."""
        result = subprocess.run(
            [str(SCRIPT), "--base-url", "http://localhost:8080"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0, "Should fail without --run-id")
        self.assertIn("--run-id", result.stderr + result.stdout)

    def test_unknown_option_exits_nonzero(self) -> None:
        """Unknown option should exit with code 2."""
        result = subprocess.run(
            [str(SCRIPT), "--unknown-option"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0, "Should fail with unknown option")
        self.assertIn("Unknown option", result.stderr)


class TestRunIdValidation(unittest.TestCase):
    """Test run_id validation."""

    def setUp(self) -> None:
        if not SCRIPT.exists():
            self.skipTest("debug_recent_runs_execution_state.sh not found")

    def _run_with_run_id(self, run_id: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), "--base-url", "http://localhost:8080", "--run-id", run_id],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_path_traversal_rejected(self) -> None:
        """Path traversal patterns like ../../x should be rejected."""
        result = self._run_with_run_id("../etc/passwd")
        self.assertNotEqual(result.returncode, 0, "Should reject path traversal")
        self.assertIn("path traversal", result.stderr.lower())

    def test_slash_rejected(self) -> None:
        """Forward slash in run_id should be rejected."""
        result = self._run_with_run_id("run/test")
        self.assertNotEqual(result.returncode, 0, "Should reject / in run_id")

    def test_backslash_rejected(self) -> None:
        """Backslash in run_id should be rejected."""
        result = self._run_with_run_id("run\\test")
        self.assertNotEqual(result.returncode, 0, "Should reject \\ in run_id")

    def test_empty_run_id_exits_nonzero(self) -> None:
        """Empty run_id should exit non-zero (caught by argument parser)."""
        result = self._run_with_run_id("")
        self.assertNotEqual(result.returncode, 0, "Should reject empty run_id")

    def test_valid_health_run_id_proceeds_to_api(self) -> None:
        """Valid health-run ID should proceed past validation (fail on API call)."""
        result = self._run_with_run_id("health-run-20260515T073859Z")
        # Should NOT fail on validation, should fail on API connection
        output = result.stderr + result.stdout
        # Either we get past validation and fail on API, or validation itself passes
        # The key is we should NOT see path traversal or invalid characters error
        self.assertNotIn("path traversal", output.lower())
        self.assertNotIn("invalid characters", output.lower())


class TestDebugScriptWithMockedEndpoints(unittest.TestCase):
    """Test script output file generation with mocked HTTP responses."""

    def setUp(self) -> None:
        if not SCRIPT.exists():
            self.skipTest("debug_recent_runs_execution_state.sh not found")

        # Create temp directory for fake tools and test output
        self._tmp_dir = tempfile.mkdtemp(prefix="test_debug_script_")
        self._bin_dir = os.path.join(self._tmp_dir, "bin")
        os.makedirs(self._bin_dir, exist_ok=True)

        # Create fake curl and jq
        self._create_fake_curl()
        self._create_fake_jq()

        # Add fake bin to PATH
        self._old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self._bin_dir + os.pathsep + self._old_path

    def tearDown(self) -> None:
        if hasattr(self, "_old_path"):
            os.environ["PATH"] = self._old_path
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _create_fake_curl(self) -> None:
        """Create a fake curl that returns canned JSON based on URL."""
        curl_fake = Path(self._bin_dir) / "curl"
        curl_fake.write_text(
            """#!/bin/bash
# Fake curl for testing - returns canned JSON based on URL
# Properly handles curl options with and without values

output_file=""
url=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        # Options with values
        -o)
            output_file="$2"
            shift 2
            ;;
        -o*)
            output_file="${1#-o}"
            shift
            ;;
        -w|--max-time|-H|-A|-e)
            # These take an argument
            shift 2
            ;;
        # Valueless flags - just shift 1
        -sS|-s|-S|-k|-v|-L|-f|-F|-I|-i|-#)
            shift
            ;;
        # Long options with values
        --max-time|--header|--user-agent|--referer|--cookie)
            shift 2
            ;;
        # URL
        http://*|https://*)
            url="$1"
            shift
            ;;
        # End of options
        --)
            shift
            ;;
        # Anything else
        *)
            shift
            ;;
    esac
done

# Return canned JSON based on URL pattern
if [[ "$url" == *"/api/runs"* ]]; then
    cat > "$output_file" <<'JSON'
{"runs": [
  {
    "runId": "health-run-20260515T073859Z",
    "reviewStatus": "no-executions",
    "batchEligibility": true,
    "batchExecutable": false,
    "batchEligibleCount": 5,
    "executionSummary": null
  }
], "_debug_execution_summary": {
  "selected_source": "ui_index",
  "plan_data_in_index": true,
  "execution_indices_in_index": false,
  "parsed_execution_indices_count": 0,
  "plan_candidate_count": 5,
  "computed_execution_summary": null,
  "stale_index_detected": true,
  "ui_index_generated_at": "2026-05-15T07:00:00Z",
  "ui_index_mtime": 1718352000,
  "newest_execution_artifact_mtime": 1718353200,
  "reason_execution_summary_missing": "execution indices missing from index"
}}
JSON
elif [[ "$url" == *"/api/debug/runs/"* ]]; then
    cat > "$output_file" <<'JSON'
{
  "selected_source": "ui_index",
  "plan_data_in_index": true,
  "execution_indices_in_index": false,
  "parsed_execution_indices_count": 0,
  "plan_candidate_count": 5,
  "computed_execution_summary": null,
  "stale_index_detected": true,
  "ui_index_generated_at": "2026-05-15T07:00:00Z",
  "ui_index_mtime": 1718352000,
  "newest_execution_artifact_mtime": 1718353200,
  "reason_execution_summary_missing": "execution indices missing from index"
}
JSON
elif [[ "$url" == *"/api/run"* ]]; then
    cat > "$output_file" <<'JSON'
{
  "runId": "health-run-20260515T073859Z",
  "label": "health-run-20260515T073859Z",
  "nextCheckCandidates": [
    {"candidateId": "c1", "status": "executed", "outcome": "success"},
    {"candidateId": "c2", "status": "executed", "outcome": "failed"}
  ]
}
JSON
else
    echo '{"error": "unknown endpoint"}' > "$output_file"
fi

echo -n "200"
exit 0
"""
        )
        os.chmod(curl_fake, 0o755)

    def _create_fake_jq(self) -> None:
        """Create a fake jq that uses real jq."""
        jq_fake = Path(self._bin_dir) / "jq"
        real_jq = shutil.which("jq")
        if real_jq:
            jq_fake.write_text(f"#!/bin/bash\nexec {real_jq} \"$@\"\n")
        else:
            # Fallback: minimal mock for simple cases
            jq_fake.write_text(
                """#!/bin/bash
# Minimal jq fallback
if [[ "$1" == "empty" ]]; then
    python3 -c "import json,sys; json.load(sys.stdin)" && exit 0 || exit 1
else
    exec cat "$@"
fi
"""
            )
        os.chmod(jq_fake, 0o755)

    def test_produces_recent_runs_debug_json(self) -> None:
        """Should produce recent-runs-debug.json."""
        output_dir = os.path.join(self._tmp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        result = subprocess.run(
            [
                str(SCRIPT),
                "--base-url", "http://localhost:8080",
                "--run-id", "health-run-20260515T073859Z",
                "--output-dir", output_dir,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        debug_file = Path(output_dir) / "recent-runs-debug.json"
        self.assertTrue(
            debug_file.exists(),
            f"recent-runs-debug.json should exist. stderr: {result.stderr}",
        )

        # Verify it's valid JSON
        try:
            data = json.loads(debug_file.read_text())
            self.assertIn("runs", data)
        except json.JSONDecodeError:
            self.fail("recent-runs-debug.json should be valid JSON")

    def test_produces_recent_runs_row_json(self) -> None:
        """Should produce recent-runs-row.json."""
        output_dir = os.path.join(self._tmp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        subprocess.run(
            [
                str(SCRIPT),
                "--base-url", "http://localhost:8080",
                "--run-id", "health-run-20260515T073859Z",
                "--output-dir", output_dir,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        row_file = Path(output_dir) / "recent-runs-row.json"
        self.assertTrue(row_file.exists(), "recent-runs-row.json should exist")

    def test_produces_execution_summary_diagnostics_json(self) -> None:
        """Should produce execution-summary-diagnostics.json."""
        output_dir = os.path.join(self._tmp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        subprocess.run(
            [
                str(SCRIPT),
                "--base-url", "http://localhost:8080",
                "--run-id", "health-run-20260515T073859Z",
                "--output-dir", output_dir,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        diag_file = Path(output_dir) / "execution-summary-diagnostics.json"
        self.assertTrue(diag_file.exists(), "execution-summary-diagnostics.json should exist")

    def test_produces_summary_md(self) -> None:
        """Should produce summary.md with root-cause hints."""
        output_dir = os.path.join(self._tmp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        subprocess.run(
            [
                str(SCRIPT),
                "--base-url", "http://localhost:8080",
                "--run-id", "health-run-20260515T073859Z",
                "--output-dir", output_dir,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        summary_file = Path(output_dir) / "summary.md"
        self.assertTrue(summary_file.exists(), "summary.md should exist")

        content = summary_file.read_text()
        self.assertIn("Run ID", content)
        self.assertIn("Recent Runs Row", content)
        self.assertIn("Root-Cause Hints", content)

    def test_summary_mentions_stale_index(self) -> None:
        """summary.md should mention stale index hint when detected."""
        output_dir = os.path.join(self._tmp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        subprocess.run(
            [
                str(SCRIPT),
                "--base-url", "http://localhost:8080",
                "--run-id", "health-run-20260515T073859Z",
                "--output-dir", output_dir,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        summary_file = Path(output_dir) / "summary.md"
        content = summary_file.read_text()
        # The fake data has stale_index_detected: true
        self.assertIn("stale", content.lower())

    def test_worklist_failure_is_graceful(self) -> None:
        """Work list fetch failure should warn but not fail the script."""
        output_dir = os.path.join(self._tmp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        # Create curl that fails on worklist endpoint
        curl_fake = Path(self._bin_dir) / "curl"
        curl_fake.write_text(
            """#!/bin/bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        -o)
            output_file="$2"
            shift 2
            ;;
        -o*)
            output_file="${1#-o}"
            shift
            ;;
        http://*|https://*)
            url="$1"
            shift
            ;;
        -*)
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [[ "$url" == *"/api/run"* ]]; then
    echo '{"error": "not found"}' > "$output_file"
    echo -n "404"
    exit 22
fi

# Return valid JSON for other endpoints
if [[ "$url" == *"/api/runs"* ]]; then
    cat > "$output_file" <<'JSON'
{"runs": [], "_debug_execution_summary": null}
JSON
elif [[ "$url" == *"/api/debug/runs/"* ]]; then
    cat > "$output_file" <<'JSON'
{"selected_source": null, "stale_index_detected": false}
JSON
fi

echo -n "200"
exit 0
"""
        )
        os.chmod(curl_fake, 0o755)

        result = subprocess.run(
            [
                str(SCRIPT),
                "--base-url", "http://localhost:8080",
                "--run-id", "health-run-20260515T073859Z",
                "--output-dir", output_dir,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Script should still exit 0 (partial success) or 5 (partial failure)
        # It should NOT exit 1 (missing tools) or 4 (all endpoints failed)
        self.assertIn(
            result.returncode,
            [0, 5],
            f"Script should not hard-fail on worklist error. Got: {result.returncode}",
        )


class TestRunIdValidationPatterns(unittest.TestCase):
    """Test specific run_id validation patterns."""

    def setUp(self) -> None:
        if not SCRIPT.exists():
            self.skipTest("debug_recent_runs_execution_state.sh not found")

    def _run_with_run_id(self, run_id: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), "--base-url", "http://localhost:8080", "--run-id", run_id],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_double_dot_rejected(self) -> None:
        """Double dot (..) should be rejected."""
        result = self._run_with_run_id("foo..bar")
        self.assertNotEqual(result.returncode, 0)

    def test_special_chars_rejected(self) -> None:
        """Special characters like $ and ; should be rejected."""
        result = self._run_with_run_id("run$test")
        self.assertNotEqual(result.returncode, 0)

    def test_underscore_accepted(self) -> None:
        """Underscore should be accepted in valid run_ids."""
        result = self._run_with_run_id("run_test_123")
        # Should pass validation (fail on API, not validation)
        output = result.stderr + result.stdout
        self.assertNotIn("path traversal", output.lower())
        self.assertNotIn("invalid characters", output.lower())


if __name__ == "__main__":
    unittest.main()