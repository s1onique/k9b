"""Tests for the incident lifecycle boundary verifier CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Import the verifier package
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from incident_lifecycle_boundary import cli


class TestCLIMain:
    """Tests for the main CLI orchestration."""

    def test_verifier_passes_when_all_checks_pass(self) -> None:
        """Verifier should pass when all checks pass."""
        with patch.object(cli, "check_forbidden_imports", return_value=[]):
            with patch.object(cli, "check_reason_allowlist", return_value=[]):
                with patch.object(cli, "check_rejection_reason_type_alias", return_value=[]):
                    with patch.object(cli, "check_status_assignments", return_value=[]):
                        with patch.object(cli, "check_transition_adapter_uses_lifecycle_core", return_value=[]):
                            with patch.object(cli, "check_lifecycle_event_mappings", return_value=[]):
                                with patch.object(cli, "check_evidence_type_contract", return_value=[]):
                                    with patch.object(cli, "check_artifact_id_contract", return_value=[]):
                                        with patch.object(cli, "check_artifact_path_contract", return_value=[]):
                                            with patch.object(cli, "check_llm_safe_evidence_contract", return_value=[]):
                                                with patch.object(cli, "check_llm_safe_helper_signatures", return_value=[]):
                                                    exit_code = cli.main(["verify_incident_lifecycle_boundaries.py"])
                                                    assert exit_code == 0

    def test_verifier_fails_when_forbidden_imports_fail(self) -> None:
        """Verifier should detect forbidden imports."""
        errors = [
            "src/k8s_diag_agent/domain/incident_lifecycle.py:5: "
            "Forbidden import 'subprocess'"
        ]
        with patch.object(cli, "check_forbidden_imports", return_value=errors):
            with patch.object(cli, "check_reason_allowlist", return_value=[]):
                with patch.object(cli, "check_rejection_reason_type_alias", return_value=[]):
                    with patch.object(cli, "check_status_assignments", return_value=[]):
                        with patch.object(cli, "check_transition_adapter_uses_lifecycle_core", return_value=[]):
                            exit_code = cli.main(["verify_incident_lifecycle_boundaries.py"])
                            assert exit_code == 1

    def test_verifier_fails_when_rejection_reasons_fail(self) -> None:
        """Verifier should detect unknown rejection reasons."""
        errors = [
            "src/k8s_diag_agent/domain/incident_lifecycle.py:10: "
            "Unknown rejection reason 'unknown_code'"
        ]
        with patch.object(cli, "check_forbidden_imports", return_value=[]):
            with patch.object(cli, "check_reason_allowlist", return_value=errors):
                with patch.object(cli, "check_rejection_reason_type_alias", return_value=[]):
                    with patch.object(cli, "check_status_assignments", return_value=[]):
                        with patch.object(cli, "check_transition_adapter_uses_lifecycle_core", return_value=[]):
                            exit_code = cli.main(["verify_incident_lifecycle_boundaries.py"])
                            assert exit_code == 1

    def test_verifier_fails_when_type_alias_check_fails(self) -> None:
        """Verifier should detect type alias issues."""
        errors = [
            "src/k8s_diag_agent/domain/incident_lifecycle.py: TransitionRejectionReason alias missing or empty."
        ]
        with patch.object(cli, "check_forbidden_imports", return_value=[]):
            with patch.object(cli, "check_reason_allowlist", return_value=[]):
                with patch.object(cli, "check_rejection_reason_type_alias", return_value=errors):
                    with patch.object(cli, "check_status_assignments", return_value=[]):
                        with patch.object(cli, "check_transition_adapter_uses_lifecycle_core", return_value=[]):
                            exit_code = cli.main(["verify_incident_lifecycle_boundaries.py"])
                            assert exit_code == 1

    def test_verifier_fails_when_status_projection_fails(self) -> None:
        """Verifier should detect status projection violations."""
        errors = [
            "src/k8s_diag_agent/collect/incident_store.py:10: "
            "lifecycle status projection is only allowed in incident_lifecycle_domain_adapter.py::_apply_lifecycle_transition"
        ]
        with patch.object(cli, "check_forbidden_imports", return_value=[]):
            with patch.object(cli, "check_reason_allowlist", return_value=[]):
                with patch.object(cli, "check_rejection_reason_type_alias", return_value=[]):
                    with patch.object(cli, "check_status_assignments", return_value=errors):
                        with patch.object(cli, "check_transition_adapter_uses_lifecycle_core", return_value=[]):
                            exit_code = cli.main(["verify_incident_lifecycle_boundaries.py"])
                            assert exit_code == 1

    def test_verifier_fails_when_transition_adapter_calls_fail(self) -> None:
        """Verifier should detect missing transition adapter calls."""
        errors = [
            "src/k8s_diag_agent/collect/incident_lifecycle_transitions.py: "
            "Missing required lifecycle core CALL 'domain_mark_collecting_evidence'."
        ]
        with patch.object(cli, "check_forbidden_imports", return_value=[]):
            with patch.object(cli, "check_reason_allowlist", return_value=[]):
                with patch.object(cli, "check_rejection_reason_type_alias", return_value=[]):
                    with patch.object(cli, "check_status_assignments", return_value=[]):
                        with patch.object(cli, "check_transition_adapter_uses_lifecycle_core", return_value=errors):
                            exit_code = cli.main(["verify_incident_lifecycle_boundaries.py"])
                            assert exit_code == 1

    def test_verifier_fails_for_missing_domain_module(self) -> None:
        """Verifier should fail gracefully when domain module is missing."""
        with patch.object(Path, "exists", return_value=False):
            exit_code = cli.main(["verify_incident_lifecycle_boundaries.py"])
            assert exit_code == 2


if __name__ == "__main__":
    import unittest
    unittest.main()
