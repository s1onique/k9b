"""Contract tests for harbor-build-image workflow PR write rejection.

Tests Track B: PR boundary enforcement.
"""

from harbor_build_image_authority_support import HARBOR_BUILD_IMAGE_WORKFLOW


class TestPRWriteRejection:
    """Tests for PR write operation rejection."""

    def test_preflight_rejects_pr_image_push(self) -> None:
        """Preflight must reject image push on pull_request event."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        assert "ERROR: PR_WRITE_AUTHORITY_FORBIDDEN" in content, "Must emit PR_WRITE_AUTHORITY_FORBIDDEN error"
        assert "Image push requested on pull_request event" in content, "Must reject image push on PR"

    def test_preflight_rejects_pr_cache_write(self) -> None:
        """Preflight must reject cache write on pull_request event."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        assert "ERROR: PR_WRITE_AUTHORITY_FORBIDDEN" in content, "Must emit PR_WRITE_AUTHORITY_FORBIDDEN error"
        assert "Cache write requested on pull_request event" in content, "Must reject cache write on PR"

    def test_preflight_documents_all_pr_types_rejected(self) -> None:
        """Preflight must document that ALL PR types are rejected."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        assert "Same-repository PR write: REJECTED" in content, "Must reject same-repository PR writes"
        assert "Dependabot PR write: REJECTED" in content, "Must reject Dependabot PR writes"
        assert "Fork PR write: REJECTED" in content, "Must reject fork PR writes"

    def test_no_dependabot_exception(self) -> None:
        """Dependabot must NOT be exempted from PR restrictions."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        assert "/dependabot" not in content or "REJECTED" in content, "Dependabot must be rejected, not exempted"

    def test_actor_classification_not_used_for_trust(self) -> None:
        """Actor classification may be logged but must NOT grant write authority."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        assert 'if [[ "${EVENT_NAME}" == "pull_request" ]]' in content, "PR rejection must be based on event_name"
