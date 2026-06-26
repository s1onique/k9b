"""Unit tests for the K3s CNPG incident lab verifier script."""

import json
import subprocess
import sys
from pathlib import Path

from tests.test_verify_k3s_cnpg_incident_lab_fixtures import (
    VERIFIER_SCRIPT,
    PASS_FIXTURE,
    FAIL_NO_INCIDENT_FIXTURE,
    FAIL_SECRET_FIXTURE,
)


class TestVerifierScriptExists:
    """Test that the verifier script exists and is executable."""

    def test_verifier_script_exists(self) -> None:
        assert VERIFIER_SCRIPT.exists(), f"Verifier script not found at {VERIFIER_SCRIPT}"

    def test_verifier_script_is_python(self) -> None:
        with open(VERIFIER_SCRIPT) as f:
            first_line = f.readline()
        assert first_line.startswith("#!"), "Verifier script missing shebang"


class TestVerifierPassFixture:
    """Test that the verifier passes for a complete, valid artifact directory."""

    def test_verifier_passes_on_complete_fixture(self) -> None:
        """A complete artifact directory should pass verification."""
        result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", str(PASS_FIXTURE)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Verifier failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "PASSED" in result.stdout

    def test_verifier_passes_with_verbose(self) -> None:
        """Verbose mode should work and show file checks."""
        result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", str(PASS_FIXTURE), "-v"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "✓ baseline/" in result.stdout


class TestVerifierFailNoIncident:
    """Test that the verifier fails when incident_detected=true but no k9b incidents exist."""

    def test_verifier_fails_on_missing_k9b_incidents(self) -> None:
        """When incident_detected=true but k9b-incidents.json is missing, should fail."""
        result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", str(FAIL_NO_INCIDENT_FIXTURE)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, f"Verifier should have failed but didn't:\nstdout: {result.stdout}"
        assert "FAILED" in result.stdout
        # Should mention the missing k9b incident evidence.
        assert "k9b-incidents.json" in result.stdout or "k9b incident evidence" in result.stdout


class TestVerifierFailSecret:
    """Test that the verifier fails when actual secrets are detected in artifacts."""

    def test_verifier_fails_on_secret_leakage(self) -> None:
        """When actual secrets are detected in artifacts, should fail."""
        result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", str(FAIL_SECRET_FIXTURE)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, f"Verifier should have failed but didn't:\nstdout: {result.stdout}"
        assert "FAILED" in result.stdout
        # Should mention actual credential patterns detected.
        assert "password" in result.stdout.lower() or "credential pattern" in result.stdout.lower()


class TestVerifierMissingFiles:
    """Test that the verifier fails when required files are missing."""

    def test_verifier_fails_on_missing_lab_result(self, tmp_path: Path) -> None:
        """When lab-result.json is missing, should fail."""
        # Create minimal structure without lab-result.json.
        artifact_dir = tmp_path / "no-result"
        artifact_dir.mkdir()
        (artifact_dir / "baseline").mkdir()
        (artifact_dir / "incident").mkdir()
        (artifact_dir / "recovery-or-final").mkdir()
        (artifact_dir / "logs").mkdir()

        result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", str(artifact_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "lab-result.json" in result.stdout

    def test_verifier_fails_on_missing_baseline(self, tmp_path: Path) -> None:
        """When baseline artifacts are missing, should fail."""
        artifact_dir = tmp_path / "no-baseline"
        artifact_dir.mkdir()
        (artifact_dir / "lab-result.json").write_text(json.dumps({
            "ok": True,
            "scenario": "pod-failure",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "cluster_mode": "local",
            "artifact_dir": str(artifact_dir),
        }))
        (artifact_dir / "baseline").mkdir()  # Empty baseline dir.
        (artifact_dir / "incident").mkdir()
        (artifact_dir / "recovery-or-final").mkdir()
        (artifact_dir / "logs").mkdir()

        result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", str(artifact_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Baseline artifact missing" in result.stdout


class TestVerifierMalformedJSON:
    """Test that the verifier handles malformed JSON gracefully."""

    def test_verifier_fails_on_malformed_lab_result(self, tmp_path: Path) -> None:
        """When lab-result.json is malformed JSON, should fail."""
        artifact_dir = tmp_path / "malformed"
        artifact_dir.mkdir()
        (artifact_dir / "lab-result.json").write_text("{ invalid json }")
        (artifact_dir / "baseline").mkdir()
        (artifact_dir / "incident").mkdir()
        (artifact_dir / "recovery-or-final").mkdir()
        (artifact_dir / "logs").mkdir()

        result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", str(artifact_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "malformed" in result.stdout.lower()


class TestVerifierMissingRequiredFields:
    """Test that the verifier validates required fields in lab-result.json."""

    def test_verifier_fails_on_missing_required_fields(self, tmp_path: Path) -> None:
        """When lab-result.json is missing required fields, should fail."""
        artifact_dir = tmp_path / "missing-fields"
        artifact_dir.mkdir()
        # Only include some required fields.
        (artifact_dir / "lab-result.json").write_text(json.dumps({
            "ok": True,
            "scenario": "pod-failure",
            # Missing: started_at, finished_at, cluster_mode, artifact_dir
        }))
        (artifact_dir / "baseline").mkdir()
        (artifact_dir / "incident").mkdir()
        (artifact_dir / "recovery-or-final").mkdir()
        (artifact_dir / "logs").mkdir()

        result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", str(artifact_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        # Should mention missing fields.
        assert "missing required field" in result.stdout


class TestVerifierInconsistentState:
    """Test that the verifier detects inconsistent states."""

    def test_verifier_fails_when_incident_detected_but_no_incidents(
        self, tmp_path: Path
    ) -> None:
        """When incident_detected=false but k9b-incidents.json has incidents, should fail."""
        artifact_dir = tmp_path / "inconsistent"
        artifact_dir.mkdir()
        (artifact_dir / "lab-result.json").write_text(json.dumps({
            "ok": True,
            "scenario": "pod-failure",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "cluster_mode": "local",
            "artifact_dir": str(artifact_dir),
            "incident_detected": False,  # Says no incident.
        }))
        (artifact_dir / "baseline").mkdir()
        (artifact_dir / "incident").mkdir()
        (artifact_dir / "incident" / "k9b-incidents.json").write_text(json.dumps([
            {"id": "inc-001", "title": "Test Incident"}
        ]))
        (artifact_dir / "recovery-or-final").mkdir()
        (artifact_dir / "logs").mkdir()

        result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", str(artifact_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "inconsistent" in result.stdout.lower()


class TestVerifierNonExistentDirectory:
    """Test that the verifier fails gracefully for non-existent directories."""

    def test_verifier_fails_on_nonexistent_dir(self) -> None:
        """When artifact directory doesn't exist, should fail."""
        result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", "/nonexistent/path"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "does not exist" in result.stdout
