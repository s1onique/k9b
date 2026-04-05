import importlib
import sys
import unittest
from pathlib import Path


class SnapshotImportabilityTest(unittest.TestCase):
    def test_cli_imports_without_src_path(self) -> None:
        repo_root = Path(__file__).resolve().parents[1].resolve()
        src_path = repo_root / "src"
        original_path = list(sys.path)
        saved_modules = {
            name: sys.modules[name]
            for name in list(sys.modules)
            if name.startswith("k8s_diag_agent")
        }
        for name in saved_modules:
            sys.modules.pop(name, None)
        try:
            while str(src_path) in sys.path:
                sys.path.remove(str(src_path))
            importlib.invalidate_caches()
            module = importlib.import_module("k8s_diag_agent.cli")
            self.assertTrue(module)
        finally:
            sys.path[:] = original_path
            sys.modules.update(saved_modules)
