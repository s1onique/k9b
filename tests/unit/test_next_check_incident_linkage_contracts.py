"""Tests for next_check_incident_linkage_contracts module.

These tests verify the contract/type definitions and dataclass behavior.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    ObjectKind,
)
from k8s_diag_agent.external_analysis.next_check_incident_linkage_contracts import (
    LINKAGE_SCHEMA_VERSION,
    IncidentLinkageContext,
    NextCheckCandidateLinkage,
    NextCheckPlanLinkage,
)

from .next_check_incident_linkage_fixtures import make_incident_candidate, make_linkage_context

# =============================================================================
# Test Cases: IncidentLinkageContext
# =============================================================================


class TestIncidentLinkageContextFromCandidate(unittest.TestCase):
    """Test creating linkage context from IncidentCandidate."""

    def test_from_incident_candidate_derives_incident_id(self) -> None:
        """incident_id is derived deterministically from candidate components."""
        candidate = make_incident_candidate(
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="my-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
        )

        context = IncidentLinkageContext.from_incident_candidate(candidate, run_id="run-456")

        self.assertEqual(context.namespace, "default")
        self.assertEqual(context.object_kind, "Pod")
        self.assertEqual(context.object_name, "my-pod")
        self.assertEqual(context.candidate_class, "crash_loop")
        self.assertEqual(context.source_candidate_id, candidate.candidate_id)
        self.assertEqual(context.run_id, "run-456")
        # incident_id should be derived deterministically
        self.assertIsNotNone(context.incident_id)
        self.assertIn("default", context.incident_id)
        self.assertIn("pod", context.incident_id)
        self.assertIn("my-pod", context.incident_id)
        self.assertIn("crash_loop", context.incident_id)

    def test_from_incident_candidate_run_id_optional(self) -> None:
        """run_id is optional when creating from candidate."""
        candidate = make_incident_candidate()

        context = IncidentLinkageContext.from_incident_candidate(candidate)

        self.assertIsNone(context.run_id)


# =============================================================================
# Test Cases: NextCheckCandidateLinkage
# =============================================================================


class TestNextCheckCandidateLinkageToDict(unittest.TestCase):
    """Test candidate linkage dict serialization."""

    def test_to_dict_includes_all_linkage_fields(self) -> None:
        """to_dict() includes incident_id, source_candidate_id, entity fields, status, reason."""
        context = make_linkage_context(
            incident_id="default-pod-test-crash-loop",
            source_candidate_id="cand-001",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        linkage = NextCheckCandidateLinkage.from_context(context)

        result = linkage.to_dict()

        self.assertIn("incident_id", result)
        self.assertIn("source_candidate_id", result)
        self.assertIn("namespace", result)
        self.assertIn("objectKind", result)  # camelCase per spec
        self.assertIn("objectName", result)
        self.assertIn("candidateClass", result)
        self.assertIn("linkage_status", result)
        self.assertIn("linkage_reason", result)
        self.assertEqual(result["incident_id"], "default-pod-test-crash-loop")
        self.assertEqual(result["linkage_status"], "linked")

    def test_to_dict_null_when_fields_missing(self) -> None:
        """to_dict() returns null for missing fields."""
        context = make_linkage_context(
            incident_id=None,
            source_candidate_id=None,
            namespace=None,
            object_kind=None,
            object_name=None,
            candidate_class=None,
        )
        linkage = NextCheckCandidateLinkage.from_context(context)

        result = linkage.to_dict()

        self.assertIsNone(result["incident_id"])
        self.assertIsNone(result["source_candidate_id"])
        self.assertIsNone(result["namespace"])
        self.assertIsNone(result["objectKind"])
        self.assertIsNone(result["objectName"])
        self.assertIsNone(result["candidateClass"])


# =============================================================================
# Test Cases: NextCheckPlanLinkage
# =============================================================================


class TestNextCheckPlanLinkageToDict(unittest.TestCase):
    """Test plan linkage dict serialization."""

    def test_to_dict_includes_schema_version(self) -> None:
        """to_dict() includes linkage_schema_version."""
        context = make_linkage_context(run_id="run-123")
        plan_linkage = NextCheckPlanLinkage.from_context(context)

        result = plan_linkage.to_dict()

        self.assertIn("linkage_schema_version", result)
        self.assertEqual(result["linkage_schema_version"], LINKAGE_SCHEMA_VERSION)

    def test_to_dict_includes_run_id_and_status(self) -> None:
        """to_dict() includes run_id and linkage_status."""
        context = make_linkage_context(run_id="run-123", incident_id="inc-001")
        plan_linkage = NextCheckPlanLinkage.from_context(context)

        result = plan_linkage.to_dict()

        self.assertEqual(result["run_id"], "run-123")
        self.assertEqual(result["linkage_status"], "linked")


# =============================================================================
# Test Cases: Schema Version
# =============================================================================


class TestLinkageSchemaVersion(unittest.TestCase):
    """Test schema version constant."""

    def test_schema_version_is_one(self) -> None:
        """LINKAGE_SCHEMA_VERSION should be 1."""
        self.assertEqual(LINKAGE_SCHEMA_VERSION, 1)


# =============================================================================
# Test Cases: Public Import Compatibility
# =============================================================================


class TestPublicImportCompatibility(unittest.TestCase):
    """Test that all expected symbols are importable from the facade."""

    def test_can_import_from_original_module(self) -> None:
        """All public symbols should be importable from next_check_incident_linkage."""
        from k8s_diag_agent.external_analysis.next_check_incident_linkage import (
            LINKAGE_SCHEMA_VERSION,
            IncidentLinkageContext,
            NextCheckCandidateLinkage,
            NextCheckPlanLinkage,
            build_next_check_incident_linkage,
            enrich_next_check_candidate_dict,
            enrich_next_check_plan_dict,
        )

        # Verify imports are not None
        self.assertIsNotNone(LINKAGE_SCHEMA_VERSION)
        self.assertIsNotNone(IncidentLinkageContext)
        self.assertIsNotNone(NextCheckCandidateLinkage)
        self.assertIsNotNone(NextCheckPlanLinkage)
        self.assertIsNotNone(build_next_check_incident_linkage)
        self.assertIsNotNone(enrich_next_check_candidate_dict)
        self.assertIsNotNone(enrich_next_check_plan_dict)


if __name__ == "__main__":
    unittest.main()
