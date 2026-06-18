"""Negative/filter tests for incident detail suggested_checks.

Tests:
- Missing artifact produces empty suggested_checks
- Partial candidates are ignored
- Wrong incident candidates are ignored
- Legacy artifact without linkage fields is ignored
- Malformed JSON artifact is skipped
- Empty candidates list produces empty suggested_checks
- No candidates key produces empty suggested_checks
- Wrong run_id artifact is not loaded

These tests validate that the suggested_checks feature gracefully
handles edge cases and invalid artifacts without crashing.
"""

from __future__ import annotations

import json
import unittest

from k8s_diag_agent.collect.api_incident_reads import handle_get_incident

from .incident_detail_suggested_checks_fixtures import (
    IncidentSuggestedChecksHarness,
    make_empty_candidates_next_check_plan_artifact,
    make_legacy_next_check_plan_artifact,
    make_malformed_next_check_plan_artifact,
    make_no_candidates_key_next_check_plan_artifact,
    make_partial_next_check_plan_artifact,
    make_valid_next_check_plan_artifact,
    make_wrong_incident_next_check_plan_artifact,
)


class TestIncidentDetailSuggestedChecksFilters(
    IncidentSuggestedChecksHarness,
    unittest.TestCase,
):
    """Negative case tests for incident detail suggested_checks.

    Tests that invalid, missing, or malformed artifacts are gracefully
    filtered out and produce empty suggested_checks (not errors).
    """

    def test_missing_artifact_produces_empty_suggested_checks(self) -> None:
        """Missing next-check-plan artifact produces empty suggested_checks."""
        incident_id = self.create_incident_with_signal("run-missing")

        # Don't write any artifact
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertEqual(result["suggested_checks"], [])

    def test_partial_candidates_are_ignored(self) -> None:
        """Partial/unlinked candidates do NOT produce suggested_checks."""
        incident_id = self.create_incident_with_signal("run-partial")

        # Write artifact with partial candidates (no incident_id linkage)
        self.write_plan_artifact("run-partial", make_partial_next_check_plan_artifact("run-partial"))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Partial candidates should be filtered out
        self.assertEqual(result["suggested_checks"], [])

    def test_wrong_incident_candidates_are_ignored(self) -> None:
        """Candidates linked to a different incident do NOT appear in this incident."""
        incident_id = self.create_incident_with_signal("run-wrong")

        # Write artifact where candidate is linked to a DIFFERENT incident
        self.write_plan_artifact("run-wrong", make_wrong_incident_next_check_plan_artifact(
            run_id="run-wrong",
            wrong_incident_id="different-incident-id-12345",
        ))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Should be empty because incident_id doesn't match
        self.assertEqual(result["suggested_checks"], [])

    def test_legacy_artifact_without_linkage_fields_is_ignored(self) -> None:
        """Legacy artifacts without linkage_status and incident_id are ignored."""
        incident_id = self.create_incident_with_signal("run-legacy")

        # Write legacy artifact (no linkage fields)
        self.write_plan_artifact("run-legacy", make_legacy_next_check_plan_artifact("run-legacy"))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Legacy artifacts without linkage fields should produce empty
        self.assertEqual(result["suggested_checks"], [])

    def test_malformed_json_artifact_is_skipped(self) -> None:
        """Malformed JSON in plan artifact is gracefully skipped."""
        incident_id = self.create_incident_with_signal("run-malformed")

        # Write malformed artifact
        self.write_malformed_artifact("run-malformed", make_malformed_next_check_plan_artifact())

        # Should not raise - should gracefully handle
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertEqual(result["suggested_checks"], [])

    def test_empty_candidates_list_produces_empty_suggested_checks(self) -> None:
        """Artifact with empty candidates list produces empty suggested_checks (not an error)."""
        incident_id = self.create_incident_with_signal("run-empty")

        self.write_plan_artifact("run-empty", make_empty_candidates_next_check_plan_artifact("run-empty"))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertEqual(result["suggested_checks"], [])

    def test_no_candidates_key_produces_empty_suggested_checks(self) -> None:
        """Artifact without candidates key produces empty suggested_checks (not an error)."""
        incident_id = self.create_incident_with_signal("run-no-candidates")

        self.write_plan_artifact("run-no-candidates",
                                  make_no_candidates_key_next_check_plan_artifact("run-no-candidates"))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertEqual(result["suggested_checks"], [])

    def test_wrong_run_id_artifact_is_not_loaded(self) -> None:
        """Artifact with wrong run_id in filename is not associated with incident."""
        incident_id = self.create_incident_with_signal("run-correct")

        # Write artifact with WRONG run_id in filename (but correct content)
        correct_artifact = make_valid_next_check_plan_artifact(
            run_id="run-wrong-filename",
            incident_id=incident_id,
        )
        # Write to file with wrong run_id
        wrong_path = self._external_dir / "run-wrong-filename-next-check-plan.json"
        wrong_path.write_text(json.dumps(correct_artifact), encoding="utf-8")

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Should be empty because filename doesn't match signal's run_id
        self.assertEqual(result["suggested_checks"], [])


if __name__ == "__main__":
    unittest.main()
