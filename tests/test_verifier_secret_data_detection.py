"""Regression tests for verifier detecting unsanitized Secret data fields.

These tests ensure the verifier properly rejects Secret manifests where:
- The sensitive field (data, stringData, binaryData) still contains actual values
- A redaction marker exists elsewhere but the sensitive field itself is not redacted

This addresses the sanitizer false-negative bug where helm/status.json Secret.data
was not properly sanitized, causing the verifier to fail with:
"FATAL: Secret manifest with data field not sanitized"
"""

import json
import sys
from pathlib import Path

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from verify_k3s_cnpg_incident_lab_artifact_contract import VerificationContext
from verify_k3s_cnpg_incident_lab_artifact_validators import (
    _check_structured_secrets_in_file,
)


class TestVerifierSecretDataDetection:
    """Regression tests for verifier detecting unsanitized Secret data fields."""

    def test_verifier_rejects_secret_with_unredacted_data_field(self, tmp_path: Path) -> None:
        """Verifier should reject Secret with data field not containing <redacted>.

        This tests the core detection: if Secret.data exists but doesn't have
        the redaction marker, the verifier must fail.
        """
        # Create artifact dir structure
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        helm_dir = artifact_dir / "helm"
        helm_dir.mkdir()

        status_file = helm_dir / "status.json"
        status_file.write_text(
            json.dumps(
                {
                    "name": "test",
                    "manifest": """\
apiVersion: v1
kind: Secret
metadata:
  name: test-secret
data:
  password: cGFzc3dvcmQ=
""",
                }
            )
        )

        ctx = VerificationContext(artifact_dir=artifact_dir, verbose=False)
        found_secret = _check_structured_secrets_in_file(ctx, status_file)

        # Verifier should find unsanitized secret data
        assert found_secret, "Verifier should detect unredacted Secret.data"
        fatal_findings = [f for f in ctx.findings if f.kind == "fatal"]
        assert len(fatal_findings) > 0, "Should have fatal finding for unredacted Secret.data"

    def test_verifier_rejects_secret_with_unredacted_stringdata_field(self, tmp_path: Path) -> None:
        """Verifier should reject Secret with stringData field not containing <redacted>."""
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        helm_dir = artifact_dir / "helm"
        helm_dir.mkdir()

        status_file = helm_dir / "status.json"
        status_file.write_text(
            """\
apiVersion: v1
kind: Secret
metadata:
  name: test-secret
stringData:
  username: admin
  password: secret123
"""
        )

        ctx = VerificationContext(artifact_dir=artifact_dir, verbose=False)
        found_secret = _check_structured_secrets_in_file(ctx, status_file)

        # Verifier should find unsanitized stringData
        assert found_secret, "Verifier should detect unredacted Secret.stringData"

    def test_verifier_rejects_secret_with_unrelated_redaction_marker(self, tmp_path: Path) -> None:
        """Verifier should reject Secret when <redacted> appears elsewhere but data is unredacted.

        This prevents false negatives where a Secret passes because an unrelated
        redaction marker exists somewhere in the content.
        """
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        helm_dir = artifact_dir / "helm"
        helm_dir.mkdir()

        status_file = helm_dir / "status.json"
        # The <redacted> is in the metadata.name, but data.password is still unredacted
        status_file.write_text(
            """\
apiVersion: v1
kind: Secret
metadata:
  name: "<redacted>"
data:
  password: cGFzc3dvcmQ=
"""
        )

        ctx = VerificationContext(artifact_dir=artifact_dir, verbose=False)
        found_secret = _check_structured_secrets_in_file(ctx, status_file)

        # Verifier should detect that data.password is not redacted
        assert found_secret, (
            "Verifier should reject Secret with unredacted data even with unrelated redaction marker"
        )

    def test_verifier_accepts_properly_sanitized_secret(self, tmp_path: Path) -> None:
        """Verifier should accept Secret where data field contains <redacted>.

        The sanitizer replaces the entire data dict with the simple string '<redacted>',
        producing output like: 'data: <redacted>' (not indented under data).
        """
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        helm_dir = artifact_dir / "helm"
        helm_dir.mkdir()

        status_file = helm_dir / "status.json"
        # This matches the actual sanitizer output format where data dict is replaced
        # with the simple string '<redacted>'
        status_file.write_text(
            """\
apiVersion: v1
kind: Secret
metadata:
  name: test-secret
data: <redacted>
"""
        )

        ctx = VerificationContext(artifact_dir=artifact_dir, verbose=False)
        found_secret = _check_structured_secrets_in_file(ctx, status_file)

        # Verifier should NOT find unsanitized secrets
        assert not found_secret, "Verifier should accept properly sanitized Secret.data"

    def test_verifier_accepts_secret_metadata_only_reference(self, tmp_path: Path) -> None:
        """Verifier should accept Secret with only metadata (no data/stringData/binaryData).

        This prevents false positives where metadata-only Secrets are rejected because
        the string "data:" appears in "metadata:" substring matching.
        """
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()

        status_file = artifact_dir / "secret-ref.yaml"
        status_file.write_text(
            """\
apiVersion: v1
kind: Secret
metadata:
  name: test-secret
"""
        )

        ctx = VerificationContext(artifact_dir=artifact_dir, verbose=False)
        found_secret = _check_structured_secrets_in_file(ctx, status_file)

        assert not found_secret, "Verifier should accept metadata-only Secret reference"
