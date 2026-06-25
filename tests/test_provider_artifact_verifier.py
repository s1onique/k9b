"""Tests for diagnosis provider artifact verifier.

These tests verify:
- Secret detection (API keys, tokens, credentials)
- Internal network pattern detection
- Blocked field content detection (mutation commands)
- Raw-like filename rejection
- Fail-closed behavior (rejects bad artifacts)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts.verify_diagnosis_provider_artifacts import (
    _check_blocked_field_content,
    _check_internal_patterns,
    _check_raw_like_filename,
    _check_secret_patterns,
    _classify_and_redact,
    verify_artifact,
    verify_directory,
)


class TestSecretPatternDetection:
    """Tests for API key and credential detection."""

    def test_detects_openai_key(self) -> None:
        """Detects OpenAI sk- key format."""
        content = 'Bearer sk-1234567890abcdefghijklmnop'
        findings = _check_secret_patterns(content)
        assert len(findings) > 0
        assert any("Bearer token" in f for f in findings)

    def test_detects_sk_proj_key(self) -> None:
        """Detects OpenAI project key."""
        content = '{"api_key": "sk-proj-1234567890abcdefghijklmnop"}'
        findings = _check_secret_patterns(content)
        assert len(findings) > 0

    def test_detects_github_token(self) -> None:
        """Detects GitHub personal access token."""
        content = "ghp_1234567890abcdefghijklmnopqrstuvwxyz1234"
        findings = _check_secret_patterns(content)
        assert len(findings) > 0
        assert any("GitHub" in f for f in findings)

    def test_detects_jwt(self) -> None:
        """Detects JWT tokens."""
        content = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        findings = _check_secret_patterns(content)
        assert len(findings) > 0

    def test_detects_aws_key(self) -> None:
        """Detects AWS access key ID."""
        content = "AKIAIOSFODNN7EXAMPLE"
        findings = _check_secret_patterns(content)
        assert len(findings) > 0
        assert any("AWS" in f for f in findings)

    def test_no_false_positives_on_clean_content(self) -> None:
        """Clean content should not trigger findings."""
        content = '{"summary": "High CPU usage", "confidence": "high"}'
        findings = _check_secret_patterns(content)
        assert len(findings) == 0


class TestInternalPatternDetection:
    """Tests for internal network pattern detection."""

    def test_detects_10_network(self) -> None:
        """Detects 10.x.x.x internal IPs."""
        content = "Connected to 10.0.0.5:8080"
        findings = _check_internal_patterns(content)
        assert len(findings) > 0
        assert any("10.x.x.x" in f for f in findings)

    def test_detects_172_network(self) -> None:
        """Detects 172.16-31.x.x internal IPs."""
        content = "Service at 172.17.0.2"
        findings = _check_internal_patterns(content)
        assert len(findings) > 0
        assert any("172.16-31" in f for f in findings)

    def test_detects_192_network(self) -> None:
        """Detects 192.168.x.x internal IPs."""
        content = "Router at 192.168.1.1"
        findings = _check_internal_patterns(content)
        assert len(findings) > 0
        assert any("192.168" in f for f in findings)

    def test_detects_k8s_internal_dns(self) -> None:
        """Detects Kubernetes internal DNS names."""
        content = "Backend at backend.default.svc.cluster.local"
        findings = _check_internal_patterns(content)
        assert len(findings) > 0
        assert any("Kubernetes internal DNS" in f for f in findings)

    def test_no_false_positives_on_public_ips(self) -> None:
        """Public IPs should not trigger findings."""
        content = "Server at 8.8.8.8 or api.cloudprovider.com"
        findings = _check_internal_patterns(content)
        assert len(findings) == 0


class TestBlockedFieldContent:
    """Tests for blocked mutation command detection."""

    def test_detects_kubectl_exec(self) -> None:
        """Detects kubectl exec commands."""
        obj = {"command": "kubectl exec -it pod-xyz -- /bin/bash"}
        findings = _check_blocked_field_content(obj)
        assert len(findings) > 0
        assert any("kubectl mutation" in f for f in findings)

    def test_detects_kubectl_apply(self) -> None:
        """Detects kubectl apply commands."""
        obj = {"action": "Run kubectl apply -f deployment.yaml"}
        findings = _check_blocked_field_content(obj)
        assert len(findings) > 0
        assert any("kubectl mutation" in f for f in findings)

    def test_detects_helm_install(self) -> None:
        """Detects helm install commands."""
        obj = {"recommended_action": "helm install my-release bitnami/nginx"}
        findings = _check_blocked_field_content(obj)
        assert len(findings) > 0
        assert any("helm mutation" in f for f in findings)

    def test_detects_docker_run(self) -> None:
        """Detects docker run commands."""
        obj = {"suggestion": "Try docker run -d nginx"}
        findings = _check_blocked_field_content(obj)
        assert len(findings) > 0
        assert any("docker mutation" in f for f in findings)

    def test_allows_read_only_commands(self) -> None:
        """Read-only kubectl commands are allowed."""
        obj = {"investigation": "kubectl get pods -n default"}
        findings = _check_blocked_field_content(obj)
        assert len(findings) == 0


class TestClassifyAndRedact:
    """Tests for content redaction."""

    def test_redacts_api_keys(self) -> None:
        """API keys are redacted in output."""
        content = "Using API key sk-1234567890abcdefghijklmnop"
        _, redacted = _classify_and_redact(content)
        assert "sk-1234567890" not in redacted
        assert "<REDACTED:API_KEY>" in redacted

    def test_preserves_clean_content(self) -> None:
        """Clean content is preserved."""
        content = '{"summary": "Test diagnosis", "confidence": "high"}'
        _, redacted = _classify_and_redact(content)
        assert "summary" in redacted
        assert "Test diagnosis" in redacted


class TestVerifyArtifact:
    """Integration tests for artifact verification."""

    def test_passes_clean_artifact(self) -> None:
        """Clean artifact passes validation."""
        artifact = {
            "summary": "High CPU usage detected",
            "confidence": "high",
            "hypotheses": [
                {
                    "id": "h1",
                    "description": "Resource exhaustion",
                    "evidence": ["CPU at 95%"],
                    "next_checks": ["kubectl top pods"],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(artifact, f)
            path = Path(f.name)

        try:
            result = verify_artifact(path)
            assert result is True
        finally:
            path.unlink(missing_ok=True)

    def test_fails_artifact_with_api_key(self) -> None:
        """Artifact with API key fails validation."""
        artifact = {
            "summary": "API call failed",
            "error": "Invalid API key sk-1234567890abcdefghijklmnop",
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(artifact, f)
            path = Path(f.name)

        try:
            result = verify_artifact(path)
            assert result is False
        finally:
            path.unlink(missing_ok=True)

    def test_fails_artifact_with_internal_ip(self) -> None:
        """Artifact with internal IP fails validation."""
        artifact = {
            "summary": "Connection failed",
            "endpoint": "10.0.0.5:8080",
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(artifact, f)
            path = Path(f.name)

        try:
            result = verify_artifact(path)
            assert result is False
        finally:
            path.unlink(missing_ok=True)

    def test_fails_artifact_with_mutation_command(self) -> None:
        """Artifact with mutation command fails validation."""
        artifact = {
            "summary": "Remediation suggestion",
            "recommended_action": "kubectl apply -f fix.yaml",
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(artifact, f)
            path = Path(f.name)

        try:
            result = verify_artifact(path)
            assert result is False
        finally:
            path.unlink(missing_ok=True)


class TestRawLikeFilenameRejection:
    """Tests for raw-like filename rejection."""

    def test_detects_raw_json_extension(self) -> None:
        """Rejects .raw.json filename."""
        findings = _check_raw_like_filename("response.raw.json")
        assert len(findings) > 0
        assert any("raw JSON file" in f for f in findings)

    def test_detects_payload_json_extension(self) -> None:
        """Rejects .payload.json filename."""
        findings = _check_raw_like_filename("request.payload.json")
        assert len(findings) > 0
        assert any("payload JSON file" in f for f in findings)

    def test_detects_request_json_extension(self) -> None:
        """Rejects .request.json filename."""
        findings = _check_raw_like_filename("api.request.json")
        assert len(findings) > 0
        assert any("request JSON file" in f for f in findings)

    def test_detects_response_json_extension(self) -> None:
        """Rejects .response.json filename."""
        findings = _check_raw_like_filename("api.response.json")
        assert len(findings) > 0
        assert any("response JSON file" in f for f in findings)

    def test_detects_secret_suffix(self) -> None:
        """Rejects files with .secret suffix."""
        findings = _check_raw_like_filename("credentials.secret")
        assert len(findings) > 0
        assert any("secret file" in f for f in findings)

    def test_detects_credential_suffix(self) -> None:
        """Rejects files with .credential suffix."""
        findings = _check_raw_like_filename("oauth.credential")
        assert len(findings) > 0
        assert any("credential file" in f for f in findings)

    def test_detects_token_suffix(self) -> None:
        """Rejects files with .token suffix."""
        findings = _check_raw_like_filename("access.token")
        assert len(findings) > 0
        assert any("token file" in f for f in findings)

    def test_detects_apikey_suffix(self) -> None:
        """Rejects files with .apikey suffix."""
        findings = _check_raw_like_filename("service.apikey")
        assert len(findings) > 0
        assert any("API key file" in f for f in findings)

    def test_detects_key_extension(self) -> None:
        """Rejects files with .key extension."""
        findings = _check_raw_like_filename("private.key")
        assert len(findings) > 0
        assert any("key file" in f for f in findings)

    def test_allows_normal_filename(self) -> None:
        """Allows normal artifact filenames."""
        findings = _check_raw_like_filename("diagnosis-summary.json")
        assert len(findings) == 0

    def test_allows_safe_extensions(self) -> None:
        """Allows safe file extensions."""
        findings = _check_raw_like_filename("symptom-report.txt")
        assert len(findings) == 0

    def test_fails_artifact_with_raw_filename(self) -> None:
        """Artifact with raw-like filename fails validation."""
        artifact = {"summary": "Test diagnosis"}

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".raw.json", delete=False
        ) as f:
            json.dump(artifact, f)
            path = Path(f.name)

        try:
            result = verify_artifact(path)
            assert result is False
        finally:
            path.unlink(missing_ok=True)


class TestDirectoryVerification:
    """Tests for directory verification."""

    def test_verifies_clean_directory(self) -> None:
        """Clean directory passes verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create clean artifacts
            for name in ["diagnosis-1.json", "diagnosis-2.json"]:
                path = Path(tmpdir) / name
                json.dump({"summary": "Clean diagnosis"}, path.open("w"))

            all_passed, results = verify_directory(Path(tmpdir))
            assert all_passed is True
            assert len(results) == 2
            assert all("PASS" in r for r in results)

    def test_rejects_directory_with_raw_files(self) -> None:
        """Directory with raw-like files fails verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create clean artifact
            clean_path = Path(tmpdir) / "clean.json"
            json.dump({"summary": "Clean"}, clean_path.open("w"))

            # Create raw-like artifact
            raw_path = Path(tmpdir) / "response.raw.json"
            json.dump({"summary": "Raw"}, raw_path.open("w"))

            all_passed, results = verify_directory(Path(tmpdir))
            assert all_passed is False
            assert len(results) == 2
            # Check that raw file failed
            raw_result = next(r for r in results if "raw.json" in r)
            assert "FAIL" in raw_result

    def test_fails_on_subdirectory(self) -> None:
        """Directory with subdirectory fails verification (fail-closed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create subdirectory
            subdir = Path(tmpdir) / "nested"
            subdir.mkdir()
            subpath = subdir / "raw.json"
            json.dump({"summary": "Hidden raw file"}, subpath.open("w"))

            # Create top-level artifact
            top_path = Path(tmpdir) / "clean.json"
            json.dump({"summary": "Clean"}, top_path.open("w"))

            all_passed, results = verify_directory(Path(tmpdir))
            # Should fail because subdirectory exists
            assert all_passed is False
            # Check that subdirectory was flagged
            subdir_result = next((r for r in results if "nested/" in r), None)
            assert subdir_result is not None
            assert "FAIL" in subdir_result
            assert "subdirectory_not_allowed" in subdir_result

    def test_directory_with_output_copy(self) -> None:
        """Directory verification with output copy works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir) / "output"
            indir = Path(tmpdir) / "input"
            indir.mkdir()

            # Create clean artifact
            in_path = indir / "diagnosis.json"
            json.dump({"summary": "Test"}, in_path.open("w"))

            all_passed, results = verify_directory(indir, outdir)
            assert all_passed is True
            # Output file should be created
            assert (outdir / "diagnosis.json").exists()
