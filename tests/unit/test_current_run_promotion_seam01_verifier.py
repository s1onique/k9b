"""Self-tests for the ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 verifier.

The verifier must:

* ACCEPT the corrected implementation.
* REJECT representative negative fixtures that re-introduce the
  production regression patterns.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "verifiers"))

from current_run_promotion_seam01 import (  # noqa: E402
    SEAM_MODULE_SUBSTRINGS,
    _verify_file,
)


def _scan(sources: dict[str, str]) -> list[str]:
    """Run the verifier on a synthetic package and return rendered findings."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        for path, source in sources.items():
            full_path = root / "src" / "k8s_diag_agent" / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(source, encoding="utf-8")
        # Pick a substring that matches every synthetic file's name.
        # The synthetic file names below are chosen to include a
        # substring from ``SEAM_MODULE_SUBSTRINGS``.
        for substring in SEAM_MODULE_SUBSTRINGS:
            for path in sources:
                if substring in path:
                    break
            else:
                continue
            break
        violations = _verify_file(
            root / "src" / "k8s_diag_agent" / "incident_alert_signal_snapshot_adapter.py",
        )
        violations += _verify_file(
            root / "src" / "k8s_diag_agent" / "loop_runner_execute.py",
        )
        violations += _verify_file(
            root / "src" / "k8s_diag_agent" / "loop_automatic_diagnosis.py",
        )
        return [v.render() for v in violations]


class TestVerifierPositive(unittest.TestCase):
    """The corrected implementation must pass the verifier."""

    def test_corrected_implementation_passes(self) -> None:
        sources = {
            "loop_runner_execute.py": '''
"""Health loop runner -- corrected."""
from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelectionFromPromotion,
    DiagnosisSelectionSource,
    selection_source as _selection_source,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionOutcome,
    consistency_error_recorded as _consistency_error_recorded,
)
'''
,
            "loop_automatic_diagnosis.py": '''
"""Diagnosis collector -- corrected."""
from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelection,
    DiagnosisSelectionFromPromotion,
    DiagnosisSelectionSource,
    store_scan_performed as _store_scan_performed,
)

def dispatch(selection: DiagnosisSelection) -> None:
    if _store_scan_performed(selection):
        pass
''',
            "incident_alert_signal_snapshot_adapter.py": '''
"""Persistence adapter -- corrected."""
from k8s_diag_agent.collect.signal_persistence_outcomes import (
    SignalInserted,
    SignalIdentityMatched,
    is_promotable,
)
''',
        }
        rendered = _scan(sources)
        rendered_str = "\n".join(rendered)
        # No violations expected.
        self.assertNotIn("TRUTHINESS_FALLBACK", rendered_str)
        self.assertNotIn("RAW_STORE_SCAN_STRING", rendered_str)
        self.assertNotIn("UNGUARDED_SCAN_INVOCATION", rendered_str)


class TestVerifierNegative(unittest.TestCase):
    """The verifier must flag known regression patterns."""

    def test_truthiness_fallback_with_else_store_scan(self) -> None:
        sources = {
            "loop_runner_execute.py": '''
"""Health loop runner -- bad truthiness fallback."""
def pick_mode(explicit_ids: list) -> str:
    if explicit_ids:
        return "explicit_incident_ids"
    else:
        return "store_scan"
''',
            "loop_automatic_diagnosis.py": '''
"""Empty content for breadth."""
PASS = True
''',
            "incident_alert_signal_snapshot_adapter.py": '''
"""Empty content for breadth."""
PASS = True
''',
        }
        rendered = _scan(sources)
        rendered_str = "\n".join(rendered)
        self.assertIn("TRUTHINESS_FALLBACK", rendered_str)

    def test_raw_store_scan_string_outside_legacy(self) -> None:
        sources = {
            "loop_runner_execute.py": '''
"""Raw store_scan string outside legacy mode mapping."""
def make_mode() -> str:
    return "store_scan"
''',
            "loop_automatic_diagnosis.py": "PASS = True\n",
            "incident_alert_signal_snapshot_adapter.py": "PASS = True\n",
        }
        rendered = _scan(sources)
        rendered_str = "\n".join(rendered)
        self.assertIn("RAW_STORE_SCAN_STRING", rendered_str)

    def test_independent_boolean_assignment(self) -> None:
        sources = {
            "loop_runner_execute.py": "PASS = True\n",
            "loop_automatic_diagnosis.py": "PASS = True\n",
            "incident_alert_signal_snapshot_adapter.py": '''
"""Independent assignment in a non-canonical surface."""
def fake_assign() -> None:
    promotion_may_have_committed = True  # type: ignore
    promotion_propagated_to_diagnosis = False  # type: ignore
''',
        }
        rendered = _scan(sources)
        rendered_str = "\n".join(rendered)
        self.assertIn("INDEPENDENT_BOOLEAN_ASSIGNMENT", rendered_str)


class TestVerifierAcceptsLegitimate(unittest.TestCase):
    """The verifier must accept legitimate seam-correctness code."""

    def test_legacy_mode_mapping_helper(self) -> None:
        sources = {
            "loop_runner_execute.py": "PASS = True\n",
            "loop_automatic_diagnosis.py": '''
def _legacy_selection_mode(selection: object) -> str:
    return "store_scan"
''',
            "incident_alert_signal_snapshot_adapter.py": "PASS = True\n",
        }
        rendered = _scan(sources)
        rendered_str = "\n".join(rendered)
        # The literal sits inside a legacy helper, so it is accepted.
        self.assertNotIn("RAW_STORE_SCAN_STRING", rendered_str)

    def test_if_without_else_branch_is_accepted(self) -> None:
        sources = {
            "loop_runner_execute.py": '''
def pick_mode(canonical_ids: list) -> str:
    if canonical_ids:
        return "explicit_incident_ids"
    return "current_run_empty"
''',
            "loop_automatic_diagnosis.py": "PASS = True\n",
            "incident_alert_signal_snapshot_adapter.py": "PASS = True\n",
        }
        rendered = _scan(sources)
        rendered_str = "\n".join(rendered)
        # No else-branch selecting a scan mode; benign.
        self.assertNotIn("TRUTHINESS_FALLBACK", rendered_str)


if __name__ == "__main__":
    unittest.main()
