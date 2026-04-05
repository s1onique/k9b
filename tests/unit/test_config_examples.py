import json
import unittest
from pathlib import Path


class ConfigExamplesTest(unittest.TestCase):
    def test_run_config_example_uses_placeholder_contexts(self) -> None:
        example_path = Path("runs/run-config.local.example.json")
        data = json.loads(example_path.read_text(encoding="utf-8"))
        contexts: list[str] = [target.get("context", "") for target in data.get("targets", []) if isinstance(target, dict)]
        for pair in data.get("pairs", []):
            if not isinstance(pair, dict):
                continue
            primary = pair.get("primary")
            secondary = pair.get("secondary")
            if primary:
                contexts.append(primary)
            if secondary:
                contexts.append(secondary)
        self.assertTrue(contexts, "Example config should declare at least one context")
        for context in contexts:
            with self.subTest(context=context):
                self.assertTrue(
                    isinstance(context, str) and context.startswith("cluster-"),
                    "Example contexts must start with 'cluster-'",
                )
