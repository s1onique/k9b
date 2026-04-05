import io
import json
import tempfile
import unittest
from typing import Any
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.cli import main
from k8s_diag_agent.llm.assessor_schema import AssessorAssessment
from k8s_diag_agent.llm.provider import LLMProvider


class AssessorSchemaTest(unittest.TestCase):
    def test_from_dict_requires_fields(self) -> None:
        with self.assertRaises(ValueError):
            AssessorAssessment.from_dict({})

    def test_roundtrip_preserves_data(self) -> None:
        payload = {
            "observed_signals": [
                {
                    "id": "sig-1",
                    "description": "Primary metric spike",
                    "layer": "workload",
                    "evidence_id": "evt-1",
                    "severity": "warning",
                }
            ],
            "findings": [
                {
                    "description": "Replica set is starved for CPU.",
                    "supporting_signals": ["sig-1"],
                    "layer": "workload",
                }
            ],
            "hypotheses": [
                {
                    "description": "CPU limit likely too low.",
                    "confidence": "medium",
                    "probable_layer": "workload",
                    "what_would_falsify": "Telemetry shows CPU well below the limit.",
                }
            ],
            "next_evidence_to_collect": [
                {
                    "description": "Gather `kubectl top pod` for the affected pods.",
                    "owner": "platform-engineer",
                    "method": "kubectl",
                    "evidence_needed": ["kubectl top pod"],
                }
            ],
            "recommended_action": {
                "type": "observation",
                "description": "Monitor the pods while gathering CPU metrics.",
                "references": ["sig-1"],
                "safety_level": "low-risk",
            },
            "safety_level": "low-risk",
            "probable_layer_of_origin": "workload",
            "overall_confidence": "medium",
        }
        assessment = AssessorAssessment.from_dict(payload)
        self.assertEqual(assessment.to_dict(), payload)


class RecordingProvider(LLMProvider):
    def __init__(self):
        self.last_payload = None

    def assess(self, prompt: str, payload: Any) -> dict:
        self.last_payload = payload
        return {
            "observed_signals": [
                {
                    "id": "mocked",
                    "description": "mocked signal",
                    "layer": "observability",
                    "evidence_id": "mocked.comparison",
                    "severity": "info",
                }
            ],
            "findings": [
                {
                    "description": "mocked finding",
                    "supporting_signals": ["mocked"],
                    "layer": "workload",
                }
            ],
            "hypotheses": [
                {
                    "description": "mocked hypothesis",
                    "confidence": "low",
                    "probable_layer": "workload",
                    "what_would_falsify": "mocked falsifier",
                }
            ],
            "next_evidence_to_collect": [
                {
                    "description": "mocked check",
                    "owner": "platform-engineer",
                    "method": "kubectl",
                    "evidence_needed": ["mocked evidence"],
                }
            ],
            "recommended_action": {
                "type": "observation",
                "description": "mocked action",
                "references": ["mocked"],
                "safety_level": "low-risk",
            },
            "safety_level": "low-risk",
            "probable_layer_of_origin": "workload",
            "overall_confidence": "low",
        }


class LLMCLIWiringTest(unittest.TestCase):
    def test_assess_snapshots_uses_provider_output(self) -> None:
        fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
        primary_path = fixture_dir / "snapshots" / "sanitized-alpha.json"
        secondary_data = json.loads(primary_path.read_text(encoding="utf-8"))
        secondary_data["metadata"]["node_count"] = 4
        secondary_data["metadata"]["pod_count"] = 61
        secondary_data["helm_releases"][0]["chart_version"] = "2.2.0"
        secondary_data["helm_releases"][0]["chart"] = "payments-2.2.0"
        secondary_data["helm_releases"][0]["app_version"] = "2.2.0"
        secondary_data["crds"] = [
            {
                "name": "widgets.example.com",
                "served_versions": ["v1"],
                "storage_version": "v1",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            secondary_path = Path(tmpdir) / "secondary.json"
            secondary_path.write_text(json.dumps(secondary_data), encoding="utf-8")
            provider = RecordingProvider()
            with patch("k8s_diag_agent.cli.get_provider", return_value=provider):
                with patch("sys.stdout", new_callable=io.StringIO) as fake_out:
                    exit_code = main([
                        "assess-snapshots",
                        str(primary_path),
                        str(secondary_path),
                    ])
            self.assertEqual(exit_code, 0)
            assessment = json.loads(fake_out.getvalue())
            self.assertEqual(
                assessment["observed_signals"][0]["id"],
                "mocked",
            )
            self.assertIsNotNone(provider.last_payload)
