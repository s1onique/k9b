import json
import shutil
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from k8s_diag_agent.health.ui import _serialize_llm_activity
from scripts.update_ui_index import update_index


class UpdateUIIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_ui_index(self, run_id: str, run_label: str | None = None) -> Path:
        health_dir = self.tmpdir / "runs" / "health"
        health_dir.mkdir(parents=True, exist_ok=True)
        index_path = health_dir / "ui-index.json"
        data = {"run": {"run_id": run_id, "run_label": run_label or ""}}
        index_path.write_text(json.dumps(data), encoding="utf-8")
        return index_path

    def _write_pack(self, run_id: str, timestamp: str) -> Path:
        packs_dir = self.tmpdir / "runs" / "health" / "diagnostic-packs"
        packs_dir.mkdir(parents=True, exist_ok=True)
        pack_path = packs_dir / f"diagnostic-pack-{run_id}-{timestamp}.zip"
        pack_path.write_bytes(b"zip")
        return pack_path

    def test_update_index_populates_diagnostic_pack(self) -> None:
        run_id = "run-123"
        index_path = self._write_ui_index(run_id, run_label="test-run")
        pack_path = self._write_pack(run_id, "20260505T010000Z")
        result = update_index(self.tmpdir / "runs", run_id)
        self.assertTrue(result)
        data = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertIn("run", data)
        diagnostic = data["run"].get("diagnostic_pack")
        self.assertIsNotNone(diagnostic)
        self.assertEqual(diagnostic["path"], str(pack_path.relative_to(self.tmpdir / "runs" / "health")).replace('\\', '/'))
        self.assertEqual(diagnostic["label"], "test-run")
        self.assertIsNotNone(diagnostic["timestamp"])

    def test_update_index_returns_false_when_missing_pack(self) -> None:
        run_id = "run-999"
        self._write_ui_index(run_id)
        result = update_index(self.tmpdir / "runs", run_id)
        self.assertFalse(result)

    def test_update_index_returns_false_when_index_missing(self) -> None:
        result = update_index(self.tmpdir / "runs", "run-missing")
        self.assertFalse(result)

    def test_serialize_llm_activity_handles_none_timestamp(self) -> None:
        """Regression: datetime.min sentinel must be UTC-aware to avoid TypeError.

        When entries contain None timestamps mixed with valid UTC-aware timestamps,
        the sort key must not use naive datetime.min as a fallback.
        """
        entries: Sequence[Mapping[str, Any]] = [
            {"timestamp": "2026-04-20T10:00:00Z", "run_id": "run-1", "status": "success"},
            {"timestamp": None, "run_id": "run-2", "status": "failed"},  # None timestamp
            {"timestamp": "2026-04-19T09:00:00Z", "run_id": "run-3", "status": "success"},
        ]
        # Should not raise TypeError: can't compare offset-naive and offset-aware datetimes
        result = _serialize_llm_activity(entries, root_dir=self.tmpdir)
        self.assertIsInstance(result, dict)
        self.assertIn("entries", result)
        self.assertIn("summary", result)
        # Verify entries are sorted correctly (most recent first)
        result_entries = result["entries"]
        assert isinstance(result_entries, list)
        timestamps = [e.get("timestamp") for e in result_entries]
        self.assertEqual(timestamps[0], "2026-04-20T10:00:00Z")
        self.assertEqual(timestamps[1], "2026-04-19T09:00:00Z")
        # None timestamp entries are sorted last (EPOCH_SENTINEL is smallest) and have None in output
        self.assertIsNone(timestamps[2])
        self.assertEqual(len(result_entries), 3)

    def test_serialize_llm_activity_handles_all_none_timestamps(self) -> None:
        """Verify _serialize_llm_activity works when all entries have None timestamps."""
        entries: Sequence[Mapping[str, Any]] = [
            {"timestamp": None, "run_id": "run-1", "status": "success"},
            {"timestamp": None, "run_id": "run-2", "status": "failed"},
        ]
        # Should not raise TypeError
        result = _serialize_llm_activity(entries, root_dir=self.tmpdir)
        self.assertIsInstance(result, dict)
        self.assertIn("entries", result)
        result_entries = result["entries"]
        assert isinstance(result_entries, list)
        self.assertEqual(len(result_entries), 2)

    def test_serialize_llm_activity_handles_various_timestamp_formats(self) -> None:
        """Verify _serialize_llm_activity handles various valid ISO timestamp formats."""
        entries: Sequence[Mapping[str, Any]] = [
            {"timestamp": "2026-04-20T10:00:00+00:00", "run_id": "run-1", "status": "success"},
            {"timestamp": "2026-04-20T10:00:00Z", "run_id": "run-2", "status": "success"},
            {"timestamp": "2026-04-20T10:00:00", "run_id": "run-3", "status": "success"},
        ]
        result = _serialize_llm_activity(entries, root_dir=self.tmpdir)
        self.assertIsInstance(result, dict)
        result_entries = result["entries"]
        assert isinstance(result_entries, list)
        self.assertEqual(len(result_entries), 3)
