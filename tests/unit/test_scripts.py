import os
import subprocess
import unittest
from pathlib import Path


class ScriptsTest(unittest.TestCase):
    def test_run_health_once_handles_missing_pythonpath(self) -> None:
        script = Path(__file__).resolve().parents[2] / "scripts/run_health_once.sh"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [str(script), "--help"],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Usage: run_health_once.sh", result.stdout)
