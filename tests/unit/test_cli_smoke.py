import unittest
from pathlib import Path

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.cli import build_parser, _SUBCOMMANDS


class CLISmokeTest(unittest.TestCase):
    def test_subcommands_parse(self) -> None:
        parser = build_parser()
        fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
        fixture_path = fixture_dir / "crashloop_incomplete.json"
        sanitized_snapshot = fixture_dir / "snapshots" / "sanitized-alpha.json"
        commands = {
            "fixture": ["fixture", str(fixture_path)],
            "snapshot": ["snapshot", "--context", "cluster-alpha", "--output", "snapshots/test.json"],
        "compare": ["compare", str(sanitized_snapshot), str(sanitized_snapshot)],
        "batch-snapshot": ["batch-snapshot", "--config", "snapshots/targets.local.example.json"],
        "assess-snapshots": ["assess-snapshots", str(sanitized_snapshot), "snapshots/test.json"],
        "assess-drilldown": ["assess-drilldown", "runs/health/drilldowns/sample.json"],
        "run-feedback": ["run-feedback", "--config", "runs/run-config.local.example.json"],
        "run-health-loop": [
            "run-health-loop",
            "--config",
            "runs/health-config.local.example.json",
        ],
        "check-proposal": ["check-proposal", "runs/health/proposals/sample.json"],
        "promote-proposal": ["promote-proposal", "runs/health/proposals/sample.json"],
        "health-summary": ["health-summary"],
    }
        for command, args in commands.items():
            with self.subTest(command=command):
                parsed = parser.parse_args(args)
                self.assertEqual(parsed.command, command)
        self.assertEqual(set(commands), _SUBCOMMANDS)
