import unittest
from pathlib import Path

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.collect.fixture_loader import load_fixture
from k8s_diag_agent.normalize.evidence import normalize_signals


class NormalizeTest(unittest.TestCase):
    def test_crashloop_signal_severity(self) -> None:
        fixture = load_fixture(Path("fixtures/crashloop_incomplete.json"))
        evidence, signals = normalize_signals(fixture)
        self.assertTrue(any(sig.severity == "high" for sig in signals))
        self.assertTrue(any(sig.layer.value == "workload" for sig in signals))
        self.assertGreaterEqual(len(evidence), len(signals))


if __name__ == "__main__":
    unittest.main()
