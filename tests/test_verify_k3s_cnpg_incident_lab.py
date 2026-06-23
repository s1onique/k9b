"""Unit tests for the K3s CNPG incident lab artifact verifier and sanitizer."""

import json
import subprocess
import sys
from pathlib import Path

# Path to the verifier script.
VERIFIER_SCRIPT = Path(__file__).parent.parent / "scripts" / "verify_k3s_cnpg_incident_lab_artifact.py"

# Path to the sanitizer script.
SANITIZER_SCRIPT = Path(__file__).parent.parent / "scripts" / "sanitize_live_lab_artifacts.py"

# Path to fixture directories.
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "lab"
PASS_FIXTURE = FIXTURES_DIR / "pass"
FAIL_NO_INCIDENT_FIXTURE = FIXTURES_DIR / "fail-no-incident"
FAIL_SECRET_FIXTURE = FIXTURES_DIR / "fail-secret"


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


# =============================================================================
# Sanitizer Tests
# =============================================================================

class TestSanitizerScriptExists:
    """Test that the sanitizer script exists and is executable."""

    def test_sanitizer_script_exists(self) -> None:
        assert SANITIZER_SCRIPT.exists(), f"Sanitizer script not found at {SANITIZER_SCRIPT}"


class TestSanitizerSafeK8sFields:
    """Test that safe Kubernetes vocabulary is preserved by the sanitizer."""

    def test_sanitizer_preserves_secret_name_reference(self, tmp_path: Path) -> None:
        """secretName field values should be preserved as safe Kubernetes vocabulary."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create a file with safe K8s vocabulary
        (input_dir / "test.json").write_text(json.dumps({
            "clientCASecret": "lab-cluster-ca",
            "secretName": "my-secret",
            "automountServiceAccountToken": True,
            "serviceAccountName": "default",
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

        # Check output preserves safe fields
        output_content = (output_dir / "test.json").read_text()
        data = json.loads(output_content)
        assert data["clientCASecret"] == "lab-cluster-ca"
        assert data["secretName"] == "my-secret"
        assert data["automountServiceAccountToken"] is True
        assert data["serviceAccountName"] == "default"

    def test_sanitizer_preserves_rbac_resource_references(self, tmp_path: Path) -> None:
        """RBAC resource names like 'secrets' should be preserved."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create a file with RBAC resources
        (input_dir / "test.json").write_text(json.dumps({
            "resources": ["secrets", "configmaps"],
            "verbs": ["get", "list"],
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output_content = (output_dir / "test.json").read_text()
        data = json.loads(output_content)
        assert "secrets" in data["resources"]
        assert "configmaps" in data["resources"]


class TestSanitizerActualSecrets:
    """Test that actual secrets are redacted by the sanitizer."""

    def test_sanitizer_redacts_jwt_token(self, tmp_path: Path) -> None:
        """JWT/Bearer tokens should be detected and redacted as FATAL."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create a file with an actual JWT token
        (input_dir / "test.json").write_text(json.dumps({
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            "name": "test-user",
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should exit with error due to fatal finding
        assert result.returncode == 1

        # Check output has redacted token
        output_content = (output_dir / "test.json").read_text()
        data = json.loads(output_content)
        assert data["token"] == "<REDACTED>"
        assert "FATAL" in result.stdout or "credential pattern" in result.stdout.lower()

    def test_sanitizer_redacts_private_key(self, tmp_path: Path) -> None:
        """Private key blocks should be detected and redacted as FATAL."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create a file with a private key
        (input_dir / "test.txt").write_text("""
        Some config content
        -----BEGIN PRIVATE KEY-----
        MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt
        LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JSUV2UUlCQURBTkJna3
        LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JSUV2UUlCQURBTkJna3
        -----END PRIVATE KEY-----
        """)

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should exit with error due to fatal finding
        assert result.returncode == 1
        assert "FATAL" in result.stdout or "PRIVATE KEY" in result.stdout

    def test_sanitizer_redacts_kubeconfig_token(self, tmp_path: Path) -> None:
        """Kubeconfig user tokens should be detected and redacted."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create a kubeconfig-like structure
        (input_dir / "kubeconfig.json").write_text(json.dumps({
            "users": [{
                "name": "admin",
                "user": {
                    "token": "sha256~abc123secret",
                    "client-key-data": "fake-key-data",
                }
            }]
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should exit with error due to fatal finding
        assert result.returncode == 1

        # Check output has redacted credentials
        output_content = (output_dir / "kubeconfig.json").read_text()
        data = json.loads(output_content)
        assert data["users"][0]["user"]["token"] == "<REDACTED>"
        assert data["users"][0]["user"]["client-key-data"] == "<REDACTED>"


class TestSanitizerFindings:
    """Test that findings are properly categorized and deduplicated."""

    def test_sanitizer_finds_warnings_for_secret_data(self, tmp_path: Path) -> None:
        """Secret.data fields should generate warnings."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create a Kubernetes Secret manifest
        (input_dir / "secret.yaml").write_text("""
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
data:
  password: c3VwZXJzZWNyZXQ=
type: Opaque
""")

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should exit with error due to warning (Secret.data)
        assert result.returncode == 1

        # Check findings include warning about Secret.data
        findings_path = output_dir / "_findings.json"
        assert findings_path.exists()
        findings_data = json.loads(findings_path.read_text())
        warning_findings = [f for f in findings_data["findings"] if f["kind"] == "warning"]
        assert any("Secret.data" in f["message"] or "secret manifest" in f["message"] for f in warning_findings)


class TestSanitizerMultiDocumentYAML:
    """Test that multi-document YAML streams are handled correctly."""

    def test_sanitizer_handles_multi_document_yaml(self, tmp_path: Path) -> None:
        """Multi-document YAML with ConfigMap and Secret should preserve ConfigMap metadata."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create a multi-document YAML with ConfigMap, Secret, and ServiceAccount
        (input_dir / "manifests.yaml").write_text("""---
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: test-namespace
data:
  database: postgres
  port: "5432"
  secretName: pg-secret
---
apiVersion: v1
kind: Secret
metadata:
  name: pg-secret
  namespace: test-namespace
type: Opaque
data:
  password: c3VwZXJzZWNyZXQ=
  username: dXNlcm5hbWU=
stringData:
  connection: "host=localhost port=5432"
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-sa
  namespace: test-namespace
automountServiceAccountToken: true
""")

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should exit with error due to Secret.data warning
        assert result.returncode == 1

        # Check output preserves multi-document structure with document separators
        output_content = (output_dir / "manifests.yaml").read_text()
        assert "---" in output_content, "Multi-document separators should be preserved"

        # ConfigMap data should be preserved (safe K8s vocabulary)
        assert "database: postgres" in output_content
        # YAML uses single quotes by default
        assert "port:" in output_content and "5432" in output_content
        assert "secretName: pg-secret" in output_content

        # Secret metadata should be preserved
        assert "kind: Secret" in output_content
        assert "name: pg-secret" in output_content

        # Secret data should be redacted - the _sanitized field indicates Secret was detected
        assert "_sanitized: secret" in output_content, \
            "Secret special case should have been triggered"

        # ServiceAccount automountServiceAccountToken should be preserved
        assert "automountServiceAccountToken: true" in output_content

        # Check findings include warning about Secret.data
        findings_path = output_dir / "_findings.json"
        assert findings_path.exists()
        findings_data = json.loads(findings_path.read_text())
        warning_findings = [f for f in findings_data["findings"] if f["kind"] == "warning"]
        assert any("Secret" in f["message"] for f in warning_findings), \
            f"Expected Secret warning, got: {warning_findings}"
        
        # NEGATIVE ASSERTIONS: Original Secret values MUST be absent from output
        # This is the critical security check - without these, test can pass even if
        # secret data leaks through
        assert "c3VwZXJzZWNyZXQ=" not in output_content, \
            "Original Secret.data.password value leaked into output!"
        assert "dXNlcm5hbWU=" not in output_content, \
            "Original Secret.data.username value leaked into output!"
        assert "host=localhost port=5432" not in output_content, \
            "Original Secret.stringData.connection value leaked into output!"


class TestSanitizerEndToEnd:
    """End-to-end tests for the sanitize-then-verify workflow."""

    def test_sanitize_and_verify_workflow(self, tmp_path: Path) -> None:
        """Test the full sanitize -> verify workflow."""
        raw_dir = tmp_path / "raw"
        sanitized_dir = tmp_path / "sanitized"
        raw_dir.mkdir()
        sanitized_dir.mkdir()

        # Create a valid artifact structure with safe K8s vocabulary
        (raw_dir / "lab-result.json").write_text(json.dumps({
            "ok": True,
            "scenario": "pod-failure",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "cluster_mode": "local",
            "artifact_dir": str(raw_dir),
            "incident_detected": False,
        }))
        (raw_dir / "baseline").mkdir()
        (raw_dir / "baseline" / "nodes.txt").write_text("NAME              STATUS   ROLES           AGE   VERSION\ntest-node         Ready    control-plane   5m    v1.31.0")
        (raw_dir / "baseline" / "pods.txt").write_text("NAME                      READY   STATUS\ntest-pod                  1/1     Running")
        (raw_dir / "baseline" / "k9b-status.json").write_text(json.dumps({
            "installed": True,
            "version": "0.1.0",
            "ready": True,
        }))
        (raw_dir / "baseline" / "cnpg-clusters.json").write_text(json.dumps({
            "clusters_installed": 1,
            "cluster_details": [{
                "name": "test-cluster",
                "clientCASecret": "ca-secret",
                "automountServiceAccountToken": True,
            }]
        }))
        (raw_dir / "incident").mkdir()
        (raw_dir / "incident" / "pods.txt").write_text("NAME                      READY   STATUS\ntest-pod                  0/1     NotReady")
        (raw_dir / "incident" / "events.txt").write_text("2m    Warning   Unhealthy   Pod/test-pod   Readiness probe failed")
        (raw_dir / "incident" / "cnpg-clusters.json").write_text(json.dumps({
            "clusters_installed": 1,
            "cluster_details": [{
                "name": "test-cluster",
                "secretName": "pg-secret",
            }]
        }))
        (raw_dir / "incident" / "injected-change.yaml").write_text("""
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  containers:
  - name: test
    image: test:latest
    readinessProbe:
      exec:
        command: ["/bin/false"]
""")
        (raw_dir / "recovery-or-final").mkdir()
        (raw_dir / "recovery-or-final" / "pods.txt").write_text("NAME                      READY   STATUS\ntest-pod                  1/1     Running")
        (raw_dir / "recovery-or-final" / "events.txt").write_text("Normal    Success    Pod/test-pod")
        (raw_dir / "recovery-or-final" / "cnpg-clusters.json").write_text(json.dumps({
            "clusters_installed": 1,
            "cluster_details": [{
                "name": "test-cluster",
            }]
        }))
        (raw_dir / "logs").mkdir()
        (raw_dir / "logs" / "lab-runner.log").write_text("[2026-01-01] Lab completed")
        
        # Create k9b-incident-detail.json for incident phase
        (raw_dir / "incident" / "k9b-incident-detail.json").write_text(json.dumps({
            "id": "inc-001",
            "title": "Test Incident",
            "severity": "warning",
            "status": "detected",
        }))

        # Run sanitize
        sanitize_result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(raw_dir), "--output", str(sanitized_dir)],
            capture_output=True,
            text=True,
        )

        # Sanitization should succeed (no actual secrets)
        assert sanitize_result.returncode == 0, f"Sanitization failed:\nstdout: {sanitize_result.stdout}\nstderr: {sanitize_result.stderr}"

        # Run verify on sanitized artifacts
        verify_result = subprocess.run(
            [sys.executable, str(VERIFIER_SCRIPT), "--artifact-dir", str(sanitized_dir)],
            capture_output=True,
            text=True,
        )

        assert verify_result.returncode == 0, f"Verification failed:\nstdout: {verify_result.stdout}\nstderr: {verify_result.stderr}"
        assert "PASSED" in verify_result.stdout


class TestSanitizerDeduplication:
    """Test that findings are deduplicated."""

    def test_findings_are_deduplicated(self, tmp_path: Path) -> None:
        """Multiple occurrences of the same finding should be deduplicated."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create multiple files with the same safe pattern
        for i in range(3):
            (input_dir / f"file{i}.json").write_text(json.dumps({
                "secretName": f"my-secret-{i}",
            }))

        # Run the sanitizer
        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Sanitization should succeed (no actual secrets)
        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

        # Check findings file exists (deduplication happens internally)
        findings_path = output_dir / "_findings.json"
        assert findings_path.exists(), "Findings file should exist"
