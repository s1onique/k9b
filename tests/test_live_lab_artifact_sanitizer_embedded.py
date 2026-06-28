"""Test cases for embedded Kubernetes manifest sanitization.

This module tests the sanitization of Kubernetes manifests embedded as YAML strings
within JSON fields (e.g., helm/status.json with info.manifest containing YAML).
"""

import sys
from pathlib import Path

# Add scripts directory to path for imports (must precede the import below)
_scripts_path = Path(__file__).parent.parent / "scripts"
if _scripts_path.exists() and str(_scripts_path) not in sys.path:
    sys.path.insert(0, str(_scripts_path))

from sanitize_live_lab_artifacts_embedded import (  # noqa: E402
    _sanitize_embedded_manifest_string,
)


class TestEmbeddedSecretSanitization:
    """Test cases for embedded Secret manifests."""

    def test_top_level_secret_is_sanitized(self) -> None:
        """Test that top-level Secret manifests are sanitized."""
        yaml_doc = """
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
data:
  username: YWRtaW4=
  password: cGFzc3dvcmQ=
"""
        result, findings = _sanitize_embedded_manifest_string(
            yaml_doc, file_path="test.yaml"
        )
        assert "_sanitized" in result
        assert "<redacted>" in result
        assert "data:" not in result.lower() or "<redacted>" in result.lower()

    def test_secret_in_list_items_is_sanitized(self) -> None:
        """Test that Secret objects nested inside List.items are sanitized.

        This tests the case where Helm status includes a List wrapper:
        ```yaml
        apiVersion: v1
        kind: List
        items:
          - apiVersion: v1
            kind: Secret
            data:
              token: ...
        ```
        """
        yaml_doc = """
apiVersion: v1
kind: List
items:
  - apiVersion: v1
    kind: Secret
    metadata:
      name: my-secret
    data:
      username: YWRtaW4=
      password: cGFzc3dvcmQ=
  - apiVersion: v1
    kind: ConfigMap
    metadata:
      name: my-config
    data:
      key: value
"""
        result, findings = _sanitize_embedded_manifest_string(
            yaml_doc, file_path="test.yaml"
        )
        # The result should contain sanitized Secret data
        assert "_sanitized" in result or "<redacted>" in result.lower()

    def test_secret_in_resources_array_is_sanitized(self) -> None:
        """Test that Secret objects in resources arrays are sanitized."""
        yaml_doc = """
apiVersion: v1
kind: Secret
metadata:
  name: tls-secret
type: kubernetes.io/tls
data:
  tls.crt: LS0tLS1CRUdJTi...
  tls.key: LS0tLS1CRUdJTi...
"""
        result, findings = _sanitize_embedded_manifest_string(
            yaml_doc, file_path="test.yaml"
        )
        assert "_sanitized" in result
        # Check that actual base64 data is redacted
        assert "LS0tLS1CRUdJTi" not in result

    def test_string_data_is_sanitized(self) -> None:
        """Test that Secret.stringData field is sanitized."""
        yaml_doc = """
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
type: Opaque
stringData:
  username: admin
  password: secret123
"""
        result, findings = _sanitize_embedded_manifest_string(
            yaml_doc, file_path="test.yaml"
        )
        assert "_sanitized" in result
        assert "stringData" in result  # Field name should remain
        assert "admin" not in result
        assert "secret123" not in result

    def test_binary_data_is_sanitized(self) -> None:
        """Test that Secret.binaryData field is sanitized."""
        yaml_doc = """
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
binaryData:
  keyfile: SGVsbG8gV29ybGQ=
"""
        result, findings = _sanitize_embedded_manifest_string(
            yaml_doc, file_path="test.yaml"
        )
        assert "_sanitized" in result
        assert "SGVsbG8gV29ybGQ=" not in result

    def test_non_secret_manifest_unchanged(self) -> None:
        """Test that non-Secret manifests are not modified."""
        yaml_doc = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
data:
  key: value
"""
        result, findings = _sanitize_embedded_manifest_string(
            yaml_doc, file_path="test.yaml"
        )
        assert result == yaml_doc
        assert len(findings) == 0

    def test_secret_with_only_metadata_is_not_flagged(self) -> None:
        """Test that Secret objects without data/stringData/binaryData are safe."""
        yaml_doc = """
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
type: kubernetes.io/tls
"""
        result, findings = _sanitize_embedded_manifest_string(
            yaml_doc, file_path="test.yaml"
        )
        # No data fields to sanitize, so no findings expected
        assert len(findings) == 0

    def test_findings_include_file_path(self) -> None:
        """Test that findings include the file path context."""
        yaml_doc = """
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
data:
  key: dmFsdWU=
"""
        result, findings = _sanitize_embedded_manifest_string(
            yaml_doc, file_path="helm/status.json"
        )
        assert len(findings) > 0
        for finding in findings:
            assert "helm/status.json" in finding.file

    def test_multiple_secrets_in_document(self) -> None:
        """Test that multiple Secret objects in one document are all sanitized."""
        yaml_doc = """
apiVersion: v1
kind: Secret
metadata:
  name: secret-1
data:
  key1: dmFsdWUx
---
apiVersion: v1
kind: Secret
metadata:
  name: secret-2
stringData:
  key2: value2
"""
        result, findings = _sanitize_embedded_manifest_string(
            yaml_doc, file_path="test.yaml"
        )
        assert len(findings) >= 2  # At least 2 findings (one per secret)
        assert "_sanitized" in result

    def test_json_format_secret_is_sanitized(self) -> None:
        """Test that JSON-formatted Secret embedded as string is sanitized."""
        # JSON-style Secret (single document, no YAML separators)
        json_doc = '{"apiVersion":"v1","kind":"Secret","metadata":{"name":"my-secret"},"data":{"username":"YWRtaW4="}}'
        result, findings = _sanitize_embedded_manifest_string(
            json_doc, file_path="test.json"
        )
        assert "_sanitized" in result or "<redacted>" in result.lower()

    def test_top_level_yaml_list_with_secret_is_sanitized(self) -> None:
        """Test that top-level YAML list containing Secret objects is sanitized."""
        yaml_doc = """
- apiVersion: v1
  kind: Secret
  metadata:
    name: list-secret
  data:
    token: dmFsdWU=
- apiVersion: v1
  kind: ConfigMap
  metadata:
    name: list-config
  data:
    key: value
"""
        result, findings = _sanitize_embedded_manifest_string(
            yaml_doc,
            file_path="helm/status.json",
        )
        assert findings
        assert "dmFsdWU=" not in result
        assert "_sanitized" in result
        assert "kind: ConfigMap" in result
