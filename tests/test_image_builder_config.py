"""Unit tests for k9b-image-builder.yml workflow configuration."""

from pathlib import Path

# Path to the workflow file
IMAGE_BUILDER_FILE = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-image-builder.yml"


class TestImageBuilderDigestOutputs:
    """Test that k9b-image-builder.yml uses docker/build-push-action digest outputs."""

    def test_image_builder_uses_build_action_digest_outputs(self) -> None:
        """Image builder should use docker/build-push-action digest outputs."""
        content = IMAGE_BUILDER_FILE.read_text()
        assert "id: build-backend" in content, \
            "Backend build step should have id: build-backend"
        assert "id: build-frontend" in content, \
            "Frontend build step should have id: build-frontend"
        assert "steps.build-backend.outputs.digest" in content, \
            "Backend digest step should read steps.build-backend.outputs.digest"
        assert "steps.build-frontend.outputs.digest" in content, \
            "Frontend digest step should read steps.build-frontend.outputs.digest"

    def test_image_builder_has_no_invalid_lowercase_digest_template(self) -> None:
        """Image builder should not contain invalid {{.digest}} template."""
        content = IMAGE_BUILDER_FILE.read_text()
        assert "{{.digest}}" not in content, \
            "Should not contain invalid {{.digest}} template"
        assert "--format '{{.digest}}'" not in content, \
            "Should not use invalid imagetools format '{{.digest}}'"
        assert '--format "{{.digest}}"' not in content, \
            "Should not use invalid imagetools format with double quotes"

    def test_image_builder_has_no_imagetools_digest_inspect(self) -> None:
        """Image builder should not use imagetools inspect for digest extraction."""
        content = IMAGE_BUILDER_FILE.read_text()
        # Verify no imagetools inspect combined with {{.digest}}
        assert not ("imagetools inspect" in content and "--format '{{.digest}}'" in content), \
            "Should not use imagetools inspect with invalid {{.digest}} template"

    def test_image_builder_digest_steps_fail_closed(self) -> None:
        """Image builder digest steps should fail closed if digest is empty."""
        content = IMAGE_BUILDER_FILE.read_text()
        assert "did not return backend digest" in content, \
            "Backend digest step should fail if empty"
        assert "did not return frontend digest" in content, \
            "Frontend digest step should fail if empty"
        assert "sha256:*" in content, \
            "Digest steps should validate sha256: prefix"

    def test_image_builder_exposes_digest_outputs(self) -> None:
        """Image builder workflow-call outputs should expose digest values."""
        content = IMAGE_BUILDER_FILE.read_text()
        assert "backend_image_digest:" in content, \
            "Workflow-call outputs should expose backend_image_digest"
        assert "frontend_image_digest:" in content, \
            "Workflow-call outputs should expose frontend_image_digest"
        # Verify job outputs map to digest steps
        assert "steps.backend-digest.outputs.digest" in content, \
            "Job outputs should map backend_image_digest from backend-digest step"
        assert "steps.frontend-digest.outputs.digest" in content, \
            "Job outputs should map frontend_image_digest from frontend-digest step"
