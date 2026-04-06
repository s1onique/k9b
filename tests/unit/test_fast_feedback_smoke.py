import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from k8s_diag_agent.cli_handlers import handle_run_feedback


class FastFeedbackSmokeTest(unittest.TestCase):
    @patch("k8s_diag_agent.structured_logging.sanitize_log_entry", autospec=True)
    @patch("k8s_diag_agent.cli_handlers.run_feedback_loop", autospec=True)
    def test_run_feedback_cli_loads_config_and_logs(
        self, run_loop_mock: MagicMock, sanitize_mock: MagicMock
    ) -> None:
        run_loop_mock.return_value = (0, [])
        sanitize_mock.side_effect = lambda entry: entry
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = base / "fast-feedback.json"
            config_data = {
                "run_id": "fast-feedback",
                "provider": "default",
                "collector_version": "0.1",
                "output_dir": str(base / "runs"),
                "targets": [{"context": "alpha", "label": "alpha"}],
                "pairs": [
                    {
                        "primary": "alpha",
                        "secondary": "alpha",
                        "label": "alpha-self",
                    }
                ],
            }
            config_path.write_text(json.dumps(config_data), encoding="utf-8")
            args = argparse.Namespace(config=config_path, provider="default", quiet=True)
            exit_code = handle_run_feedback(args)
        self.assertEqual(exit_code, 0)
        run_loop_mock.assert_called_once_with(config_path, provider_override="default", quiet=True)
        self.assertTrue(sanitize_mock.called)
