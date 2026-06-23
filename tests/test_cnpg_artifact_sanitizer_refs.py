"""Regression tests for CNPG Secret reference handling in the sanitizer.

These tests verify that:
1. CNPG Secret-reference fields are NOT treated as leaked credentials
2. Actual Secret payloads (kind: Secret with data/stringData) ARE redacted

CNPG uses fields like `superuserSecret` as references to Kubernetes Secret objects,
not as inline secret payloads.
See: https://cloudnative-pg.io/documentation/1.19/bootstrap/

Kubernetes Secret payloads are in data/stringData/binaryData on kind: Secret objects.
See: https://kubernetes.io/docs/concepts/configuration/secret/
"""

import json
import subprocess
import sys
from pathlib import Path

# Path to the sanitizer script.
SANITIZER_SCRIPT = Path(__file__).parent.parent / "scripts" / "sanitize_live_lab_artifacts.py"


class TestCNPGSecretReferenceFields:
    """CNPG Cluster Secret reference fields should be preserved as safe metadata."""

    def test_sanitizer_preserves_cnpg_cluster_secret_references(self, tmp_path: Path) -> None:
        """CNPG Cluster Secret reference fields should be preserved as safe metadata."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        cnpg_cluster = {
            "apiVersion": "postgresql.cnpg.io/v1",
            "kind": "Cluster",
            "metadata": {"name": "lab-cluster"},
            "spec": {
                "instances": 1,
                "superuserSecret": {"name": "cnpg-superuser"},
                "clientCASecret": "cnpg-client-ca",
                "serverCASecret": "cnpg-server-ca",
                "caSecret": "cnpg-ca",
                "imagePullSecrets": [{"name": "harbor-pull-secret"}],
            }
        }
        (input_dir / "cnpg-cluster.json").write_text(json.dumps(cnpg_cluster))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

        output_content = (output_dir / "cnpg-cluster.json").read_text()
        data = json.loads(output_content)
        assert data["spec"]["superuserSecret"]["name"] == "cnpg-superuser"
        assert data["spec"]["clientCASecret"] == "cnpg-client-ca"
        assert data["spec"]["serverCASecret"] == "cnpg-server-ca"
        assert data["spec"]["caSecret"] == "cnpg-ca"
        assert data["spec"]["imagePullSecrets"][0]["name"] == "harbor-pull-secret"

    def test_sanitizer_preserves_cnpg_replication_slots(self, tmp_path: Path) -> None:
        """CNPG replicationSlots.slotPrefix should be preserved as safe metadata."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        cnpg_cluster = {
            "apiVersion": "postgresql.cnpg.io/v1",
            "kind": "Cluster",
            "metadata": {"name": "lab-cluster"},
            "spec": {
                "instances": 3,
                "replicationSlots": {
                    "highAvailability": {
                        "slotPrefix": "_cnpg_"
                    }
                }
            }
        }
        (input_dir / "cnpg-cluster.json").write_text(json.dumps(cnpg_cluster))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

        output_content = (output_dir / "cnpg-cluster.json").read_text()
        data = json.loads(output_content)
        assert data["spec"]["replicationSlots"]["highAvailability"]["slotPrefix"] == "_cnpg_"

    def test_sanitizer_preserves_cnpg_replication_slot_long_prefix(self, tmp_path: Path) -> None:
        """CNPG slotPrefix with underscore-separated names should be preserved."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        cnpg_cluster = {
            "apiVersion": "postgresql.cnpg.io/v1",
            "kind": "Cluster",
            "metadata": {"name": "lab-cluster"},
            "spec": {
                "replicationSlots": {
                    "highAvailability": {
                        "slotPrefix": "_cnpg_replication_slot_"
                    }
                }
            }
        }
        (input_dir / "cnpg-cluster.json").write_text(json.dumps(cnpg_cluster))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

    def test_sanitizer_preserves_cnpg_imagepullsecrets(self, tmp_path: Path) -> None:
        """CNPG imagePullSecrets should be preserved."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        cnpg_cluster = {
            "apiVersion": "postgresql.cnpg.io/v1",
            "kind": "Cluster",
            "metadata": {"name": "lab-cluster"},
            "spec": {
                "imagePullSecrets": [
                    {"name": "harbor-secret"},
                    {"name": "ghcr-secret"},
                ]
            }
        }
        (input_dir / "cnpg-cluster.json").write_text(json.dumps(cnpg_cluster))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

        output_content = (output_dir / "cnpg-cluster.json").read_text()
        data = json.loads(output_content)
        assert len(data["spec"]["imagePullSecrets"]) == 2
        assert data["spec"]["imagePullSecrets"][0]["name"] == "harbor-secret"
        assert data["spec"]["imagePullSecrets"][1]["name"] == "ghcr-secret"


class TestActualSecretPayloads:
    """Regression tests confirming actual Secret payloads are still redacted.

    These tests verify the fix for CNPG references didn't weaken actual
    credential detection.
    """

    def test_sanitizer_redacts_kind_secret_with_data(self, tmp_path: Path) -> None:
        """kind: Secret with data field should be detected and redacted."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        secret_manifest = """apiVersion: v1
kind: Secret
metadata:
  name: my-secret
data:
  password: c3VwZXJzZWNyZXQ=
stringData:
  token: real-token-value
"""
        (input_dir / "secret.yaml").write_text(secret_manifest)

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, "Secret with data should fail sanitization"

        output_content = (output_dir / "secret.yaml").read_text()
        assert "_sanitized: secret" in output_content, "Secret should be marked as sanitized"
        assert "c3VwZXJzZWNyZXQ=" not in output_content, "Secret.data should be redacted"

    def test_sanitizer_redacts_jwt_in_text(self, tmp_path: Path) -> None:
        """JWT tokens in text should still be detected as FATAL."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "config.txt").write_text(
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, "JWT token should fail sanitization"
        assert "FATAL" in result.stdout or "credential pattern" in result.stdout.lower()

    def test_sanitizer_redacts_private_key_in_yaml(self, tmp_path: Path) -> None:
        """Private key blocks should still be detected as FATAL."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "key.txt").write_text("""-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt
LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JSUV2UUlCQURBTkJna3
-----END PRIVATE KEY-----
""")

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, "Private key should fail sanitization"

    def test_sanitizer_redacts_secret_data_not_name(self, tmp_path: Path) -> None:
        """Secret.data values (not field names) should be redacted."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # This is a Secret WITH actual data, not just references
        secret_with_data = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "pg-credentials"},
            "type": "Opaque",
            "data": {
                "password": "c3VwZXJzZWNyZXQ=",
                "username": "dXNlcm5hbWU="
            }
        }
        (input_dir / "secret.json").write_text(json.dumps(secret_with_data))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, "Secret with data should fail sanitization"

        output_content = (output_dir / "secret.json").read_text()
        # JSON format: "_sanitized": "secret" with quotes
        assert '"_sanitized"' in output_content, "Secret should be marked as sanitized in JSON output"
        assert "c3VwZXJzZWNyZXQ=" not in output_content
