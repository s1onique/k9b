"""Tests that review-enrichment prompts pass through sanitize_prompt().

These tests verify the GAP-P1 mitigation: _build_prompt() in llamacpp_adapter.py
MUST call sanitize_prompt() before returning to prevent credential leakage to
external LLM providers.

REM-P1: Add sanitize_prompt() to _build_prompt() in llamacpp_adapter.
REM-P3: Add integration test verifying all prompts pass through sanitizer.

Related: docs/security/llm-prompt-security-audit.md GAP-P1
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.llamacpp_adapter import LlamaCppAdapter
from k8s_diag_agent.external_analysis.review_input import (
    AlertmanagerContext,
    ReviewEnrichmentInput,
    ReviewSelectionContext,
)


@dataclass(frozen=True)
class _MockRequest:
    """Minimal mock ExternalAnalysisRequest for testing _build_prompt()."""
    run_id: str
    cluster_label: str
    source_artifact: str | None = None


class ReviewEnrichmentPromptSanitizationTest(unittest.TestCase):
    """Tests that review-enrichment prompts are sanitized before being sent to LLM.

    GAP-P1 (CRITICAL) required that _build_prompt() calls sanitize_prompt().
    These tests verify that sensitive data in review JSON, alertmanager context,
    and selection artifacts (entry/drilldown/assessment/snapshot) is redacted.
    """

    def setUp(self) -> None:
        self._adapter = LlamaCppAdapter()

    def _build_context(
        self,
        review: dict[str, Any],
        alertmanager: AlertmanagerContext | None = None,
        selections: tuple[ReviewSelectionContext, ...] = (),
        missing_drilldowns: tuple[str, ...] = (),
        missing_assessments: tuple[str, ...] = (),
        missing_snapshots: tuple[str, ...] = (),
    ) -> ReviewEnrichmentInput:
        if alertmanager is None:
            alertmanager = AlertmanagerContext(
                available=False,
                source="unavailable",
                compact=None,
                status=None,
            )
        return ReviewEnrichmentInput(
            run_id="test-run-id",
            review_path=Path("/fake/test-review.json"),
            review=review,
            selections=selections,
            missing_drilldowns=missing_drilldowns,
            missing_assessments=missing_assessments,
            missing_snapshots=missing_snapshots,
            alertmanager_context=alertmanager,
        )

    def _call_build_prompt(
        self,
        review: dict[str, Any],
        alertmanager: AlertmanagerContext | None = None,
        selections: tuple[ReviewSelectionContext, ...] = (),
        missing_drilldowns: tuple[str, ...] = (),
        missing_assessments: tuple[str, ...] = (),
        missing_snapshots: tuple[str, ...] = (),
    ) -> str:
        context = self._build_context(
            review, alertmanager, selections, missing_drilldowns, missing_assessments, missing_snapshots
        )
        request = _MockRequest(run_id="test-run", cluster_label="test-cluster")
        return self._adapter._build_prompt(request, context)

    def test_review_json_with_bearer_token_is_redacted(self) -> None:
        """Verify bearer token in review JSON is redacted with <scrubbed>."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [],
            "metadata": {
                "labels": {
                    "api_token": "Bearer my-secret-jwt-xyz789",
                },
            },
        }
        prompt = self._call_build_prompt(review)

        # Token should be redacted with <scrubbed>
        self.assertNotIn("my-secret-jwt-xyz789", prompt)
        self.assertIn("<scrubbed>", prompt)

    def test_review_json_with_standalone_bearer_token_is_redacted(self) -> None:
        """Verify standalone Bearer token pattern is redacted in prompt."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [],
            "token": "Bearer my-secret-jwt-token-abc123",
        }
        prompt = self._call_build_prompt(review)

        # Bearer token should be redacted
        self.assertNotIn("my-secret-jwt-token-abc123", prompt)
        self.assertIn("<scrubbed>", prompt)

    def test_review_json_with_access_token_is_redacted(self) -> None:
        """Verify access_token field values in review JSON are redacted with <scrubbed>."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [],
            "access_token": "Bearer secret-access-token-xyz789",
        }
        prompt = self._call_build_prompt(review)

        # Bearer token should be redacted with <scrubbed>
        self.assertNotIn("secret-access-token-xyz789", prompt)
        self.assertIn("<scrubbed>", prompt)

    def test_alertmanager_context_with_bearer_token_is_redacted(self) -> None:
        """Verify bearer token in alertmanager context is redacted in prompt."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [],
        }
        alertmanager = AlertmanagerContext(
            available=True,
            source="run_artifact",
            compact={
                "token": "Bearer secret-token-from-alertmanager",
                "endpoint": "https://alertmanager.example.com",
            },
            status="active",
        )
        prompt = self._call_build_prompt(review, alertmanager=alertmanager)

        # Bearer token should be redacted
        self.assertNotIn("secret-token-from-alertmanager", prompt)
        self.assertIn("<scrubbed>", prompt)

    def test_selection_entry_with_bearer_auth_is_redacted(self) -> None:
        """Verify bearer auth in selection entry is redacted in prompt."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [
                {"label": "pod-abc", "context": "default"},
            ],
        }
        selection = ReviewSelectionContext(
            label="pod-abc",
            context="default",
            entry={
                "label": "pod-abc",
                "context": "default",
                "auth": "Bearer my-auth-token-12345",
            },
            drilldown_path=None,
            drilldown=None,
            assessment_path=None,
            assessment=None,
            snapshot_path=None,
            snapshot=None,
        )
        prompt = self._call_build_prompt(review, selections=(selection,))

        # Auth token should be redacted
        self.assertNotIn("my-auth-token-12345", prompt)
        self.assertIn("<scrubbed>", prompt)

    def test_selection_entry_with_token_key_is_redacted(self) -> None:
        """Verify token=VALUE pattern in selection entry is redacted in prompt."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [
                {"label": "svc-api", "context": "production"},
            ],
        }
        selection = ReviewSelectionContext(
            label="svc-api",
            context="production",
            entry={
                "label": "svc-api",
                "context": "production",
                "token": "Bearer api-secret-key-abc",
            },
            drilldown_path=None,
            drilldown=None,
            assessment_path=None,
            assessment=None,
            snapshot_path=None,
            snapshot=None,
        )
        prompt = self._call_build_prompt(review, selections=(selection,))

        # Token should be redacted
        self.assertNotIn("api-secret-key-abc", prompt)
        self.assertIn("<scrubbed>", prompt)

    def test_selection_drilldown_with_bearer_token_is_redacted(self) -> None:
        """Verify bearer token in drilldown artifact is redacted in prompt."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [
                {"label": "pod-xyz", "context": "production"},
            ],
        }
        # Drilldown with embedded bearer token (common in cluster data)
        drilldown_data = {
            "kind": "Pod",
            "metadata": {"name": "nginx-pod"},
            "auth": {
                "token": "Bearer my-drilldown-secret-token",
            },
        }
        selection = ReviewSelectionContext(
            label="pod-xyz",
            context="production",
            entry={"label": "pod-xyz", "context": "production"},
            drilldown_path="/fake/drilldown.json",
            drilldown=drilldown_data,
            assessment_path=None,
            assessment=None,
            snapshot_path=None,
            snapshot=None,
        )
        prompt = self._call_build_prompt(review, selections=(selection,))

        # Bearer token should be redacted
        self.assertNotIn("my-drilldown-secret-token", prompt)
        self.assertIn("<scrubbed>", prompt)

    def test_selection_assessment_with_bearer_token_is_redacted(self) -> None:
        """Verify bearer token in assessment artifact are redacted in prompt."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [
                {"label": "deployment-api", "context": "staging"},
            ],
        }
        assessment_data = {
            "snapshot_path": "/fake/snapshot.json",
            "kind": "Deployment",
            "metadata": {"name": "api-deployment"},
            "credentials": {
                "client_id": "my-client-id",
                "bearer_token": "Bearer access-token-xyz",
            },
        }
        selection = ReviewSelectionContext(
            label="deployment-api",
            context="staging",
            entry={"label": "deployment-api", "context": "staging"},
            drilldown_path=None,
            drilldown=None,
            assessment_path="/fake/assessment.json",
            assessment=assessment_data,
            snapshot_path=None,
            snapshot=None,
        )
        prompt = self._call_build_prompt(review, selections=(selection,))

        # Bearer token should be redacted
        self.assertNotIn("access-token-xyz", prompt)
        self.assertIn("<scrubbed>", prompt)

    def test_selection_snapshot_with_token_is_redacted(self) -> None:
        """Verify token in snapshot data is redacted in prompt."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [
                {"label": "statefulset-db", "context": "production"},
            ],
        }
        assessment_data = {
            "snapshot_path": "/fake/snapshot.json",
        }
        snapshot_data = {
            "kind": "StatefulSet",
            "metadata": {"name": "postgres-db"},
            "spec": {
                "service_name": "postgres-headless",
                "selector": {"matchLabels": {"app": "postgres"}},
            },
            "token_secret": "Bearer token-from-snapshot-data",
        }
        selection = ReviewSelectionContext(
            label="statefulset-db",
            context="production",
            entry={"label": "statefulset-db", "context": "production"},
            drilldown_path=None,
            drilldown=None,
            assessment_path="/fake/assessment.json",
            assessment=assessment_data,
            snapshot_path="/fake/snapshot.json",
            snapshot=snapshot_data,
        )
        prompt = self._call_build_prompt(review, selections=(selection,))

        # Token should be redacted
        self.assertNotIn("token-from-snapshot-data", prompt)
        self.assertIn("<scrubbed>", prompt)

    def test_multiple_selections_with_mixed_bearer_tokens_all_redacted(self) -> None:
        """Verify all bearer tokens across multiple selections are redacted."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [
                {"label": "svc-a", "context": "default"},
                {"label": "svc-b", "context": "production"},
            ],
        }
        selection_a = ReviewSelectionContext(
            label="svc-a",
            context="default",
            entry={"label": "svc-a", "auth": "Bearer token-aaa-123"},
            drilldown_path=None,
            drilldown=None,
            assessment_path=None,
            assessment=None,
            snapshot_path=None,
            snapshot=None,
        )
        selection_b = ReviewSelectionContext(
            label="svc-b",
            context="production",
            entry={"label": "svc-b", "auth": "Bearer token-bbb-456"},
            drilldown_path=None,
            drilldown=None,
            assessment_path=None,
            assessment=None,
            snapshot_path=None,
            snapshot=None,
        )
        prompt = self._call_build_prompt(review, selections=(selection_a, selection_b))

        # Both bearer tokens should be redacted
        self.assertNotIn("token-aaa-123", prompt)
        self.assertNotIn("token-bbb-456", prompt)
        self.assertIn("<scrubbed>", prompt)

    def test_prompt_contains_expected_structure(self) -> None:
        """Verify sanitized prompt still contains expected structure."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [],
            "summary": "All systems operational",
        }
        prompt = self._call_build_prompt(review)

        # Core structure should be preserved
        self.assertIn("LLM external analysis request", prompt)
        self.assertIn("test-run", prompt)  # run_id appears in header
        self.assertIn("cluster_label=cluster-", prompt)  # cluster_label is anonymized
        self.assertIn("Review artifact:", prompt)
        self.assertIn("All systems operational", prompt)
        self.assertIn("nextChecks", prompt)  # Output format instruction

    def test_missing_context_with_token_pattern_is_redacted(self) -> None:
        """Verify token=VALUE pattern in missing context notes is redacted in prompt."""
        review = {
            "run_id": "test-run",
            "selected_drilldowns": [],
        }
        prompt = self._call_build_prompt(
            review,
            missing_drilldowns=("api_token=BearerSecretToken123",),
        )

        # Token in missing context should be redacted
        self.assertNotIn("BearerSecretToken123", prompt)
        self.assertIn("<scrubbed>", prompt)
        # But the missing context section should still exist
        self.assertIn("Missing drilldown artifacts:", prompt)


if __name__ == "__main__":
    unittest.main()
