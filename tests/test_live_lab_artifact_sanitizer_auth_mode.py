"""Regression tests for auth.mode false positive in the sanitizer.

These tests verify that the sanitizer correctly handles auth.mode and other
non-secret auth configuration fields without flagging them as fatal secrets.

Previously, the sanitizer treated any field containing "auth" as a secret field,
causing auth.mode (e.g., "local", "oidc", "disabled") to be incorrectly
redacted and flagged as fatal.

Issue: helm/get-values.json and helm/status.json contained auth.mode like:
  auth.mode: "local"  -> incorrectly flagged as fatal "Credential data in auth.mode redacted"

Fix: Added _NON_SECRET_AUTH_PATHS allowlist and leaf-key-aware detection.
"""

import json
import subprocess
import sys
from pathlib import Path

# Path to the sanitizer script.
SANITIZER_SCRIPT = Path(__file__).parent.parent / "scripts" / "sanitize_live_lab_artifacts.py"


class TestAuthModeNonSecretHandling:
    """Regression tests for auth.mode false positive fix.

    These tests verify that auth.mode and other non-secret auth configuration
    fields are NOT flagged as fatal secrets when they contain safe values
    like "local", "oidc", "disabled", etc.
    """

    def test_auth_mode_local_preserved(self, tmp_path: Path) -> None:
        """auth.mode with 'local' value should not be flagged as fatal."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Simulate helm/get-values.json with auth.mode
        helm_dir = input_dir / "helm"
        helm_dir.mkdir()
        (helm_dir / "get-values.json").write_text(json.dumps({
            "auth": {
                "mode": "local",
                "enabled": True,
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should succeed (no fatal findings)
        assert result.returncode == 0, f"Sanitizer failed unexpectedly:\nstdout: {result.stdout}\nstderr: {result.stderr}"

        # Output should preserve auth.mode value
        output = json.loads((output_dir / "helm" / "get-values.json").read_text())
        assert output["auth"]["mode"] == "local", f"auth.mode was incorrectly redacted: {output}"
        assert output["auth"]["enabled"] is True

        # No fatal findings should be in the output
        assert "FATAL" not in result.stdout, f"Unexpected fatal finding: {result.stdout}"

    def test_auth_mode_oidc_preserved(self, tmp_path: Path) -> None:
        """auth.mode with 'oidc' value should not be flagged as fatal."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        helm_dir = input_dir / "helm"
        helm_dir.mkdir()
        (helm_dir / "status.json").write_text(json.dumps({
            "auth": {
                "mode": "oidc",
                "provider": "https://accounts.google.com",
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "FATAL" not in result.stdout, f"Unexpected fatal finding: {result.stdout}"

    def test_backend_auth_mode_preserved(self, tmp_path: Path) -> None:
        """backend.auth.mode should not be flagged as fatal."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        helm_dir = input_dir / "helm"
        helm_dir.mkdir()
        (helm_dir / "get-values.json").write_text(json.dumps({
            "backend": {
                "auth": {
                    "mode": "local",
                    "enabled": True,
                    "sessionMaxAgeSeconds": 3600,
                }
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "FATAL" not in result.stdout, f"Unexpected fatal finding: {result.stdout}"

    def test_auth_enabled_flag_preserved(self, tmp_path: Path) -> None:
        """auth.enabled should not be flagged as fatal."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "config.json").write_text(json.dumps({
            "auth": {
                "enabled": True,
                "secureCookie": True,
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "FATAL" not in result.stdout, f"Unexpected fatal finding: {result.stdout}"


class TestAuthPasswordStillFatal:
    """Verify that actual auth credentials ARE still redacted as fatal.

    The fix should only allow safe auth configuration fields like mode/enabled.
    Real credentials under auth.* should still be flagged as fatal.
    """

    def test_auth_password_still_fatal(self, tmp_path: Path) -> None:
        """auth.password with actual password value should still be redacted."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "config.json").write_text(json.dumps({
            "auth": {
                "password": "super-secret-password-123",
                "mode": "local",
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should fail due to fatal finding
        assert result.returncode == 1, f"Sanitizer should have failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "FATAL" in result.stdout, f"Expected fatal finding for auth.password: {result.stdout}"

        # Output should have redacted the password
        output = json.loads((output_dir / "config.json").read_text())
        assert output["auth"]["password"] == "<REDACTED>", f"Password not redacted: {output}"
        # But mode should be preserved
        assert output["auth"]["mode"] == "local", f"auth.mode incorrectly redacted: {output}"

    def test_auth_admin_password_hash_still_fatal(self, tmp_path: Path) -> None:
        """auth.adminPasswordHash should still be redacted as fatal."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "config.json").write_text(json.dumps({
            "auth": {
                "adminPasswordHash": "pbkdf2:sha256:600000$abc123...",
                "mode": "local",
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should fail due to fatal finding
        assert result.returncode == 1, f"Sanitizer should have failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "FATAL" in result.stdout, f"Expected fatal finding for auth.adminPasswordHash: {result.stdout}"

    def test_auth_token_still_fatal(self, tmp_path: Path) -> None:
        """auth.token should still be redacted as fatal."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "config.json").write_text(json.dumps({
            "auth": {
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjg",
                "mode": "local",
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should fail due to fatal finding
        assert result.returncode == 1, f"Sanitizer should have failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "FATAL" in result.stdout, f"Expected fatal finding for auth.token: {result.stdout}"


class TestKubernetesSecretStillFatal:
    """Verify that Kubernetes Secret objects are still properly redacted."""

    def test_secret_object_redacted(self, tmp_path: Path) -> None:
        """Kubernetes Secret manifests should still be redacted with WARNING.
        
        Note: Secret redactions generate WARNING (not FATAL), and the script
        exits with code 1 for warnings. This is intentional - the redaction
        happens correctly but the script fails closed for manual review.
        """
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "secret.json").write_text(json.dumps({
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "my-secret"},
            "type": "Opaque",
            "data": {
                "username": "dXNlcm5hbWU=",
                "password": "cGFzc3dvcmQ=",
            },
            "stringData": {
                "api-key": "sk-secret-key-12345",
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Secret redaction generates WARNING, so exit code is 1 (not 0)
        # This is expected behavior - the script fails closed for manual review
        assert result.returncode == 1, f"Sanitizer should have exited with 1 for warnings:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "WARNING" in result.stdout, f"Expected WARNING for Secret redaction: {result.stdout}"

        # Output should have redacted the Secret data
        output = json.loads((output_dir / "secret.json").read_text())
        assert output["data"] == {"<redacted>": "contains base64-encoded secret values"}, f"Secret.data not redacted: {output}"
        assert output["stringData"] == {"<redacted>": "contains plaintext secret values"}, f"Secret.stringData not redacted: {output}"
        assert output["_sanitized"] == "secret"


class TestSecretValuesUnderAllowlistedPaths:
    """Verify that allowlisted paths still catch secret-like values via pattern detection."""

    def test_auth_mode_jwt_token_still_fatal(self, tmp_path: Path) -> None:
        """auth.mode with JWT token value should still be flagged as fatal."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "config.json").write_text(json.dumps({
            "auth": {
                "mode": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjg",
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should fail due to JWT pattern detected
        assert result.returncode == 1, f"Sanitizer should have failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "FATAL" in result.stdout, f"Expected fatal finding for JWT pattern: {result.stdout}"

    def test_nested_values_auth_mode_preserved(self, tmp_path: Path) -> None:
        """values.auth.mode should be preserved (suffix matching for nested paths)."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "config.json").write_text(json.dumps({
            "values": {
                "auth": {
                    "mode": "oidc",
                }
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "FATAL" not in result.stdout, f"Unexpected fatal finding: {result.stdout}"

    def test_multiple_fatal_patterns_records_all_findings(self, tmp_path: Path) -> None:
        """String with multiple fatal patterns should record all findings, not just the first."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "config.json").write_text(json.dumps({
            "auth": {
                "mode": (
                    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                    "eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjg "
                    "-----BEGIN PRIVATE KEY-----"
                )
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "FATAL" in result.stdout

        findings = json.loads((output_dir / "_findings.json").read_text())
        fatal_findings = [f for f in findings["findings"] if f["kind"] == "fatal"]

        assert len(fatal_findings) >= 2, f"Expected at least 2 fatal findings, got: {fatal_findings}"


class TestFindingsJsonHasUploadSafe:
    """Verify that findings JSON includes the upload_safe field."""

    def test_findings_json_has_upload_safe_field(self, tmp_path: Path) -> None:
        """_findings.json should include upload_safe field."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "config.json").write_text(json.dumps({
            "auth": {"mode": "local"}
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

        # Check _findings.json
        findings_path = output_dir / "_findings.json"
        assert findings_path.exists(), "_findings.json not created"

        findings_data = json.loads(findings_path.read_text())
        assert "upload_safe" in findings_data, f"upload_safe field missing: {findings_data}"
        assert findings_data["upload_safe"] is True, f"upload_safe should be True: {findings_data}"
        assert "scan_completed" in findings_data, f"scan_completed field missing: {findings_data}"
        assert findings_data["scan_completed"] is True
        assert "fatal_count" in findings_data, f"fatal_count field missing: {findings_data}"
        assert findings_data["fatal_count"] == 0
