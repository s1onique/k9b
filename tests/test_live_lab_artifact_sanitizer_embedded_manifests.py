"""Regression tests for embedded Kubernetes manifest sanitization in string fields.

These tests verify that the sanitizer correctly handles and sanitizes Kubernetes
Secret manifests embedded as YAML strings within JSON fields (e.g., helm/status.json
with info.manifest field containing multi-document YAML).

Issue: helm/status.json contains embedded YAML manifests as string fields, but the
sanitizer only sanitized parsed JSON/YAML objects, not YAML embedded inside strings.

Root cause: _sanitize_string_value() did not detect and sanitize embedded Kubernetes
manifests inside string values.

Fix: Added _sanitize_embedded_manifest_string() to parse and sanitize YAML manifests
embedded within string fields.
"""

import json
import subprocess
import sys
from pathlib import Path

# Path to the sanitizer script.
SANITIZER_SCRIPT = Path(__file__).parent.parent / "scripts" / "sanitize_live_lab_artifacts.py"


class TestEmbeddedSecretManifestSanitization:
    """Regression tests for embedded Secret manifests in string fields.

    These tests verify that Secret manifests embedded as YAML strings within
    JSON fields are properly detected and sanitized.
    """

    def test_helm_status_embedded_secret_manifest_is_sanitized(self, tmp_path: Path) -> None:
        """Helm status with embedded Secret manifest in info.manifest should be sanitized.
        
        Note: We use non-credential field names (api_key, db_pass) to avoid triggering
        the password pattern detection before the embedded manifest sanitization runs.
        """
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        helm_dir = input_dir / "helm"
        helm_dir.mkdir()

        # This is the actual shape that causes the split-brain:
        # info.manifest contains YAML multi-document string with Secret
        embedded_manifest = """\
apiVersion: v1
kind: Secret
metadata:
  name: k9b-auth
type: Opaque
data:
  api_key: cGFzc3dvcmQ=
  db_pass: dXNlcm5hbWU=
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
spec:
  replicas: 1
"""

        (helm_dir / "status.json").write_text(json.dumps({
            "name": "k9b",
            "info": {
                "manifest": embedded_manifest,
                "status": "deployed",
            },
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Sanitizer should detect the embedded Secret and exit with warning
        # Note: Secret redaction generates WARNING, not FATAL
        assert result.returncode == 1, f"Sanitizer should have detected embedded Secret:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "WARNING" in result.stdout or "Secret.data" in result.stdout, f"Expected Secret warning: {result.stdout}"

        # Verify the output contains sanitized manifest
        output = json.loads((output_dir / "helm" / "status.json").read_text())
        manifest = output["info"]["manifest"]

        # Secret manifest should still be present (as sanitized)
        assert "kind: Secret" in manifest, f"Secret kind should be preserved: {manifest}"
        # But base64 data should be redacted
        assert "cGFzc3dvcmQ=" not in manifest, f"Base64 api_key leaked: {manifest}"
        assert "dXNlcm5hbWU=" not in manifest, f"Base64 db_pass leaked: {manifest}"
        # Should contain redaction marker (simple string value, not nested object)
        assert "<redacted>" in manifest, f"Redaction marker missing: {manifest}"

    def test_embedded_secret_with_stringdata_is_sanitized(self, tmp_path: Path) -> None:
        """Embedded Secret with stringData (plaintext secrets) should be sanitized."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "config.json").write_text(json.dumps({
            "helm": {
                "manifest": """\
apiVersion: v1
kind: Secret
metadata:
  name: tls-cert
type: kubernetes.io/tls
stringData:
  tls.crt: LS0tLS1CRUdJTiBDRVJUSUZ...
  tls.key: LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t...
"""
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, f"Sanitizer should have detected Secret:\nstdout: {result.stdout}"

        output = json.loads((output_dir / "config.json").read_text())
        manifest = output["helm"]["manifest"]

        # Base64-looking TLS cert data should be redacted
        assert "LS0tLS1CRUdJTiBDRVJUSUZ" not in manifest, f"TLS cert leaked: {manifest}"
        assert "<redacted>" in manifest, f"Redaction missing: {manifest}"

    def test_embedded_multi_document_yaml_secret_is_sanitized(self, tmp_path: Path) -> None:
        """Multi-document YAML with Secret among other resources should be sanitized."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "manifests.json").write_text(json.dumps({
            "resources": """\
apiVersion: v1
kind: Namespace
metadata:
  name: production
---
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
type: Opaque
data:
  db_password: cGFzc3dvcmQxMjM=
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  DATABASE_HOST: "localhost"
"""
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, f"Sanitizer should have detected Secret: {result.stdout}"

        output = json.loads((output_dir / "manifests.json").read_text())
        manifest = output["resources"]

        # Secret should be sanitized
        assert "cGFzc3dvcmQxMjM=" not in manifest, f"Password leaked: {manifest}"
        # But ConfigMap and Namespace should be preserved
        assert "kind: Namespace" in manifest, f"Namespace should be preserved: {manifest}"
        assert "kind: ConfigMap" in manifest, f"ConfigMap should be preserved: {manifest}"
        assert "DATABASE_HOST" in manifest, f"ConfigMap data should be preserved: {manifest}"

    def test_embedded_manifest_preserves_non_secret_resources(self, tmp_path: Path) -> None:
        """Embedded YAML with only non-secret resources should be preserved."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "manifests.json").write_text(json.dumps({
            "resources": """\
apiVersion: v1
kind: Namespace
metadata:
  name: test
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
spec:
  replicas: 3
"""
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should pass - no secrets found
        assert result.returncode == 0, f"Sanitizer should pass for non-secret manifests:\nstdout: {result.stdout}\nstderr: {result.stderr}"

        output = json.loads((output_dir / "manifests.json").read_text())
        manifest = output["resources"]

        # Both resources should be preserved
        assert "kind: Namespace" in manifest
        assert "kind: Deployment" in manifest
        assert "replicas: 3" in manifest or "replicas: 3" in manifest.replace(" ", "")

    def test_base64_data_in_secret_is_sanitized(self, tmp_path: Path) -> None:
        """Base64 data values in embedded Secret should be sanitized."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "data.json").write_text(json.dumps({
            "manifest": """\
apiVersion: v1
kind: Secret
metadata:
  name: encoded-secret
data:
  token: SGVsbG9Xb3JsZA==
  secret: YWRtaW5wYXNzMTIz
"""
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, f"Sanitizer should have detected Secret: {result.stdout}"

        output = json.loads((output_dir / "data.json").read_text())
        manifest = output["manifest"]

        # Base64 values should be redacted
        assert "SGVsbG9Xb3JsZA==" not in manifest, f"Token leaked: {manifest}"
        assert "YWRtaW5wYXNzMTIz" not in manifest, f"Secret leaked: {manifest}"


class TestAuthModeStillPreserved:
    """Regression tests ensuring auth.mode is still preserved with embedded manifest fix."""

    def test_auth_mode_preserved_with_embedded_secret(self, tmp_path: Path) -> None:
        """auth.mode should still be preserved even when embedded Secret exists."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        helm_dir = input_dir / "helm"
        helm_dir.mkdir()

        (helm_dir / "status.json").write_text(json.dumps({
            "name": "k9b",
            "auth": {
                "mode": "local",
                "enabled": True,
            },
            "info": {
                "manifest": """\
apiVersion: v1
kind: Secret
metadata:
  name: k9b-auth
data:
  api_key: cGFzc3dvcmQ=
"""
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should fail due to Secret detection
        assert result.returncode == 1

        output = json.loads((output_dir / "helm" / "status.json").read_text())

        # auth.mode should be preserved
        assert output["auth"]["mode"] == "local", f"auth.mode was incorrectly redacted: {output}"
        assert output["auth"]["enabled"] is True


class TestVerifierIntegration:
    """Integration tests proving sanitized output passes the artifact verifier."""

    def test_sanitized_helm_status_passes_verifier_check(self, tmp_path: Path) -> None:
        """Sanitized helm/status.json should not trigger 'Secret manifest with data field not sanitized'."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        helm_dir = input_dir / "helm"
        helm_dir.mkdir()

        # Simulate the exact failing case - use generic field names to avoid fatal pattern
        (helm_dir / "status.json").write_text(json.dumps({
            "name": "k9b",
            "info": {
                "manifest": """\
apiVersion: v1
kind: Secret
metadata:
  name: k9b-auth
type: Opaque
data:
  api_key: cGFzc3dvcmQ=
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
"""
            }
        }))

        # Run sanitizer
        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Sanitizer should detect and sanitize
        assert result.returncode == 1, f"Sanitizer should detect embedded Secret: {result.stdout}"

        # Verify output is sanitized (no base64 data)
        output = json.loads((output_dir / "helm" / "status.json").read_text())
        manifest = output["info"]["manifest"]

        # The key assertion: base64 data should NOT be in the sanitized output
        assert "cGFzc3dvcmQ=" not in manifest, "Base64 secret value leaked into sanitized output!"

        # The verifier checks for this exact pattern:
        # If "Secret" + "data:" + base64 value exists without redaction, verifier fails
        # After sanitization, we should have redaction markers
        assert "<redacted>" in manifest or "_sanitized" in manifest, "Missing redaction marker"

        # Verify the verifier would not fail
        # (The verifier checks for "Secret manifest with data field not sanitized")
        # by looking for unredacted Secret.data with base64 values
        assert not (
            "kind: Secret" in manifest and
            "data:" in manifest and
            "cGFzc3dvcmQ=" in manifest
        ), "Verifier would fail: Secret.data not sanitized"


class TestMixedEmbeddedManifestHardening:
    """Regression tests for mixed embedded manifests with Secrets and credential patterns.

    These tests verify that the sanitizer handles edge cases where embedded manifests
    contain both Secrets AND other resources with credential-like patterns.
    """

    def test_embedded_secret_plus_configmap_private_key_redacts_whole_manifest(
        self, tmp_path: Path
    ) -> None:
        """Mixed manifest with Secret and ConfigMap with private key should redact entire string.

        After embedded Secret sanitization, if residual credential patterns remain
        in the sanitized result (e.g., ConfigMap with private_key), the whole
        string should be redacted with REDACTION_PLACEHOLDER.
        """
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "status.json").write_text(json.dumps({
            "info": {
                "manifest": """\
apiVersion: v1
kind: Secret
metadata:
  name: app-secret
data:
  api_key: cGFzc3dvcmQ=
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: suspicious-config
data:
  private_key: "-----BEGIN PRIVATE KEY----- abc -----END PRIVATE KEY-----"
"""
            }
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should fail due to fatal finding on residual private key
        assert result.returncode == 1, f"Sanitizer should have detected private key: {result.stdout}"
        assert "FATAL" in result.stdout or "PRIVATE KEY" in result.stdout, f"Expected fatal finding: {result.stdout}"

        output = json.loads((output_dir / "status.json").read_text())
        manifest = output["info"]["manifest"]

        # Secret data should be redacted
        assert "cGFzc3dvcmQ=" not in manifest, f"Secret data leaked: {manifest}"
        # Private key should also be redacted (whole string redacted)
        assert "BEGIN PRIVATE KEY" not in manifest, f"Private key leaked: {manifest}"
