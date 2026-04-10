import json
import shutil
import tempfile
import unittest
from pathlib import Path

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