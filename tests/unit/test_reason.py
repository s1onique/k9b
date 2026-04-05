import unittest
from pathlib import Path

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.collect.fixture_loader import load_fixture
from k8s_diag_agent.correlate.linkers import correlate_signals
from k8s_diag_agent.normalize.evidence import normalize_signals
from k8s_diag_agent.reason.diagnoser import build_findings_and_hypotheses
from k8s_diag_agent.models import ConfidenceLevel


class ReasonTest(unittest.TestCase):
    def test_hypothesis_has_low_confidence_and_falsifiable(self) -> None:
        fixture = load_fixture(Path("fixtures/crashloop_incomplete.json"))
        _, signals = normalize_signals(fixture)
        correlated = correlate_signals(signals)
        findings, hypotheses = build_findings_and_hypotheses(signals, correlated)
        self.assertTrue(findings)
        self.assertTrue(hypotheses)
        self.assertEqual(hypotheses[0].confidence, ConfidenceLevel.LOW)
        self.assertIn("logs", hypotheses[0].what_would_falsify.lower())


if __name__ == "__main__":
    unittest.main()
