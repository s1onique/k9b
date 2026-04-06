import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.cli_handlers import (
    handle_batch_snapshot,
    handle_compare,
    handle_run_feedback,
    handle_snapshot,
)


class DummySnapshot:
    def __init__(self) -> None:
        self.collection_status = argparse.Namespace(helm_error=None, missing_evidence=())

    def to_dict(self) -> dict:
        return {"metadata": {}, "status": {}}


class CLIStructuredLoggingTest(unittest.TestCase):
    def test_snapshot_logs_start_and_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            args = argparse.Namespace(context="alpha", output=Path(tmpdir) / "snapshot.json")
            with patch("k8s_diag_agent.cli_handlers.list_kube_contexts", return_value=["alpha"]), \
                patch("k8s_diag_agent.cli_handlers.collect_cluster_snapshot", return_value=DummySnapshot()), \
                patch("k8s_diag_agent.cli_handlers.emit_structured_log") as log_mock:
                result = handle_snapshot(args)
        self.assertEqual(result, 0)
        self.assertEqual(log_mock.call_count, 2)
        self.assertEqual(log_mock.call_args_list[0][1]["component"], "cli-snapshot")
        self.assertEqual(log_mock.call_args_list[0][1]["message"], "snapshot command started")
        self.assertEqual(log_mock.call_args_list[-1][1]["message"], "snapshot command completed")

    def test_batch_snapshot_logs_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "targets": [{"context": "alpha", "label": "alpha"}],
                        "output_dir": str(Path(tmpdir) / "out"),
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(config=config_path)
            with patch("k8s_diag_agent.cli_handlers.list_kube_contexts", return_value=["alpha"]), \
                patch("k8s_diag_agent.cli_handlers.collect_cluster_snapshot", return_value=DummySnapshot()), \
                patch("k8s_diag_agent.cli_handlers.emit_structured_log") as log_mock:
                result = handle_batch_snapshot(args, default_config=config_path)
            self.assertEqual(result, 0)
            messages = [call[1]["message"] for call in log_mock.call_args_list]
            self.assertIn("batch snapshot command started", messages)
            self.assertIn("batch snapshot completed", messages)

    def test_compare_logs_completion(self) -> None:
        args = argparse.Namespace(snapshot_a=Path("a.json"), snapshot_b=Path("b.json"))
        dummy_comparison = argparse.Namespace(differences={}, metadata=None)
        with patch("k8s_diag_agent.cli_handlers._load_snapshot", return_value=DummySnapshot()), \
            patch("k8s_diag_agent.cli_handlers.compare_snapshots", return_value=dummy_comparison), \
            patch("k8s_diag_agent.cli_handlers.emit_structured_log") as log_mock:
            result = handle_compare(args)
        self.assertEqual(result, 0)
        self.assertEqual(log_mock.call_args_list[-1][1]["message"], "compare command completed with no differences")

    def test_run_feedback_logs_every_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "run.json"
            config_path.write_text(
                json.dumps(
                    {
                        "run_id": "test-run",
                        "collector_version": "0.1",
                        "output_dir": str(Path(tmpdir) / "runs"),
                        "targets": [{"context": "alpha", "label": "alpha"}],
                        "pairs": [
                            {"primary": "alpha", "secondary": "alpha", "label": "alpha-vs-alpha"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(config=config_path, provider=None, quiet=True)
            with patch("k8s_diag_agent.cli_handlers.run_feedback_loop", return_value=(0, [])), \
                patch("k8s_diag_agent.cli_handlers.emit_structured_log") as log_mock:
                result = handle_run_feedback(args, default_config=config_path)
            self.assertEqual(result, 0)
            self.assertEqual(log_mock.call_args_list[0][1]["message"], "run-feedback command started")
            self.assertEqual(log_mock.call_args_list[-1][1]["message"], "run-feedback command completed")
