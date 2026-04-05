import json
import tempfile
import unittest
from pathlib import Path

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.cli import main
from k8s_diag_agent.schemas import AssessmentValidator


class CliIntegrationTest(unittest.TestCase):
    def test_cli_outputs_valid_assessment(self) -> None:
        fixture_path = Path("fixtures/crashloop_incomplete.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "assessment.json"
            result = main([str(fixture_path), "--output", str(output_file), "--quiet"])
            self.assertEqual(result, 0)
            self.assertTrue(output_file.exists())
            assessment = json.loads(output_file.read_text(encoding="utf-8"))
            AssessmentValidator.validate(assessment)
            self.assertIn("observed_signals", assessment)
            self.assertIn("hypotheses", assessment)


if __name__ == "__main__":
    unittest.main()
